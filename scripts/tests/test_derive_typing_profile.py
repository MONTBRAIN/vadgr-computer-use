import csv
import importlib.util
import io
import json
import math
import statistics
import sys
import weakref
import zipfile
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from computer_use.core import typing_profile
from computer_use.core.typing_boundaries import classify_gap

SCRIPT = Path(__file__).parents[1] / "derive_typing_profile.py"
SPEC = importlib.util.spec_from_file_location("derive_typing_profile", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
derive = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = derive
SPEC.loader.exec_module(derive)
ArtifactInterpreter = derive.ArtifactInterpreter


def _minimal_profile(*, cleared=True):
    quantiles = {
        "same_key": [0.5, 1.5],
        "same_finger": [0.5, 1.5],
        "same_hand": [0.5, 1.5],
        "alternate_hand": [0.5, 1.5],
        "other": [0.5, 1.5],
        "ordinary_space": [1.0, 2.0],
        "clause": [1.0, 2.0],
        "sentence": [1.5, 2.5],
        "newline": [2.0, 3.0],
        "paragraph": [2.5, 3.5],
    }
    return {
        "schema": 6,
        "profile": "test",
        "nominal_wpm": 65,
        "limits": {
            "minimum_interval_ms": 20.0,
            "maximum_total_gap_ms": 5000.0,
            "maximum_transport_unit_ms": 5000.0,
            "minimum_validation_graphemes": 200,
            "class_maximum_ms": {
                "same_key": 1500.0,
                "same_finger": 1500.0,
                "same_hand": 1500.0,
                "alternate_hand": 1500.0,
                "other": 1500.0,
                "ordinary_space": 1500.0,
                "clause": 2500.0,
                "sentence": 3500.0,
                "newline": 5000.0,
                "paragraph": 5000.0,
            },
        },
        "model": {
            "kind": "observable_context_empirical_total_gap",
            "version": 1,
            "rank_dependence": "independent",
            "rank_transition": None,
            "ordinary_space_added_pause_ms": 0.0,
            "styles": [
                {"weight": 0.5, "speed_log": -0.2},
                {"weight": 0.5, "speed_log": 0.2},
            ],
            "class_quantiles": quantiles,
            "reference_class_weights": {
                "same_key": 0.05,
                "same_finger": 0.1,
                "same_hand": 0.2,
                "alternate_hand": 0.35,
                "other": 0.1,
                "ordinary_space": 0.15,
                "clause": 0.02,
                "sentence": 0.02,
                "newline": 0.005,
                "paragraph": 0.005,
            },
            "calibration_scale": 100.0,
        },
        "fit": {},
        "validation": {"cleared": cleared},
    }


def _gap(
    participant,
    order,
    interval,
    *,
    first="a",
    second="s",
    gap_class="same_hand",
    session="1",
    segment=0,
):
    return derive.Gap(
        participant=participant,
        session=session,
        order=order,
        segment=segment,
        first=first,
        second=second,
        interval_ms=interval,
        gap_class=gap_class,
    )


def test_interpreter_rejects_uncleared_and_non_schema_six_artifacts():
    with pytest.raises(ValueError, match="did not clear"):
        ArtifactInterpreter(_minimal_profile(cleared=False))
    old = _minimal_profile()
    old["schema"] = 5
    with pytest.raises(ValueError, match="unsupported"):
        ArtifactInterpreter(old)


def test_interpreter_is_strict_about_model_shape_and_latent_fields():
    profile = _minimal_profile()
    profile["model"]["transition"] = [[1.0]]
    with pytest.raises(ValueError, match="model fields"):
        ArtifactInterpreter(profile)

    profile = _minimal_profile()
    profile["model"]["rank_dependence"] = "markov"
    with pytest.raises(ValueError, match="rank dependence"):
        ArtifactInterpreter(profile)

    profile = _minimal_profile()
    profile["model"]["ordinary_space_added_pause_ms"] = 0.001
    with pytest.raises(ValueError, match="must be zero"):
        ArtifactInterpreter(profile)


def _markov_profile(matrix=None):
    profile = _minimal_profile()
    profile["model"]["rank_dependence"] = "markov_4_bin"
    profile["model"]["rank_transition"] = {
        "bins": 4,
        "initial": [0.25] * 4,
        "matrix": matrix
        or [
            [0.4, 0.3, 0.2, 0.1],
            [0.3, 0.3, 0.2, 0.2],
            [0.2, 0.2, 0.3, 0.3],
            [0.1, 0.2, 0.3, 0.4],
        ],
    }
    return profile


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bins", 5, "initialization"),
        ("initial", [1.0, 0.0, 0.0, 0.0], "initialization"),
        ("matrix", [[0.25] * 4] * 3, "matrix"),
        (
            "matrix",
            [[0.4, 0.3, 0.2, 0.2], [0.3, 0.3, 0.2, 0.2], [0.2] * 4, [0.1] * 4],
            "matrix",
        ),
        (
            "matrix",
            [[0.4, 0.2, 0.2, 0.2]] * 4,
            "doubly stochastic",
        ),
    ],
)
def test_interpreter_strictly_validates_rank_transition(field, value, message):
    profile = _markov_profile()
    profile["model"]["rank_transition"][field] = value
    with pytest.raises(ValueError, match=message):
        ArtifactInterpreter(profile)


def test_independent_profile_rejects_a_rank_transition():
    profile = _minimal_profile()
    profile["model"]["rank_transition"] = _markov_profile()["model"]["rank_transition"]
    with pytest.raises(ValueError, match="has a rank transition"):
        ArtifactInterpreter(profile)


def test_interpreter_rejects_removed_cadence3_schema():
    profile = _markov_profile()
    profile["model"]["rank_dependence"] = "markov_4_bin_cadence3"
    profile["model"]["rank_transition"] = {
        "bins": 4,
        "initial": [0.25] * 4,
        "cadence_styles": [profile["model"]["rank_transition"]["matrix"]] * 3,
    }
    with pytest.raises(ValueError, match="rank dependence"):
        ArtifactInterpreter(profile)


@pytest.mark.parametrize(
    ("first", "second", "boundary", "expected"),
    [
        ("a", "a", None, "same_key"),
        ("c", "d", None, "same_finger"),
        ("a", "f", None, "same_hand"),
        ("a", "j", None, "alternate_hand"),
        ("é", "a", None, "other"),
        (" ", "a", None, "ordinary_space"),
        ("a", " ", None, "other"),
        (" ", "a", "sentence", "sentence"),
    ],
)
def test_observable_context_classifier_has_left_ownership_and_boundary_precedence(
    first, second, boundary, expected
):
    assert classify_gap(first, second, boundary) == expected


def test_interpreter_validates_every_class_weight_quantile_and_support():
    profile = _minimal_profile()
    profile["model"]["reference_class_weights"]["same_key"] = 0.8
    with pytest.raises(ValueError, match="reference class weights"):
        ArtifactInterpreter(profile)

    profile = _minimal_profile()
    profile["model"]["class_quantiles"]["clause"] = [2.0, 1.0]
    with pytest.raises(ValueError, match="quantiles"):
        ArtifactInterpreter(profile)

    profile = _minimal_profile()
    profile["limits"]["class_maximum_ms"]["ordinary_space"] = 1501.0
    with pytest.raises(ValueError, match="class support"):
        ArtifactInterpreter(profile)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("minimum_interval_ms",), 19.999, "limits"),
        (("maximum_total_gap_ms",), 4999.0, "limits"),
        (("maximum_transport_unit_ms",), 5001.0, "limits"),
        (("class_maximum_ms", "same_key"), 1499.0, "class support"),
        (("class_maximum_ms", "same_finger"), 1501.0, "class support"),
        (("class_maximum_ms", "same_hand"), 1499.0, "class support"),
        (("class_maximum_ms", "alternate_hand"), 1501.0, "class support"),
        (("class_maximum_ms", "other"), 1499.0, "class support"),
        (("class_maximum_ms", "ordinary_space"), 1501.0, "class support"),
        (("class_maximum_ms", "clause"), 2499.0, "class support"),
        (("class_maximum_ms", "sentence"), 3501.0, "class support"),
        (("class_maximum_ms", "newline"), 4999.0, "class support"),
        (("class_maximum_ms", "paragraph"), 5001.0, "class support"),
    ],
)
def test_interpreter_rejects_any_change_to_frozen_global_and_class_limits(path, value, message):
    profile = _minimal_profile()
    target = profile["limits"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=message):
        ArtifactInterpreter(profile)


def test_default_operation_draws_one_style_then_independent_gap_ranks():
    class CountingRandom:
        def __init__(self):
            self.values = iter((0.8, 0.1, 0.9))
            self.calls = 0

        def random(self):
            self.calls += 1
            return next(self.values)

    random = CountingRandom()
    values = ArtifactInterpreter(_minimal_profile()).simulate(["same_hand", "sentence"], 65, random)

    assert random.calls == 3
    assert [value.quantile_draw for value in values] == [0.1, 0.9]
    assert values[0].total_ms != values[1].total_ms


def test_markov_rank_runtime_uses_one_draw_per_gap_and_resets_at_segment_breaks():
    class CountingRandom:
        def __init__(self):
            self.values = iter((0.1, 0.1, 0.9, 0.9))
            self.calls = 0

        def random(self):
            self.calls += 1
            return next(self.values)

    profile = _markov_profile(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    random = CountingRandom()
    values = ArtifactInterpreter(profile).simulate(
        ["same_hand"] * 3,
        65,
        random,
        rank_resets=[True, False, True],
    )

    assert random.calls == 4
    assert [sample.rank_bin for sample in values] == [0, 0, 3]
    assert [sample.quantile_draw for sample in values] == pytest.approx([0.1, 0.225, 0.9])


def test_doubly_stochastic_rank_transition_preserves_uniform_stationary_marginal():
    joint = np.asarray(
        [
            [9.0, 3.0, 2.0, 1.0],
            [3.0, 8.0, 2.0, 2.0],
            [2.0, 2.0, 8.0, 3.0],
            [1.0, 2.0, 3.0, 9.0],
        ]
    )
    transition = derive._doubly_stochastic_transition(joint)

    assert transition.sum(axis=1) == pytest.approx(np.ones(4))
    assert transition.sum(axis=0) == pytest.approx(np.ones(4))
    assert np.full(4, 0.25) @ transition == pytest.approx(np.full(4, 0.25))
    assert derive._blend_rank_transition(transition, 0.0) == pytest.approx(np.full((4, 4), 0.25))


def test_custom_wpm_and_zero_cv_fix_style_and_flatten_non_boundary_residuals():
    class CountingRandom:
        def __init__(self):
            self.calls = 0

        def random(self):
            self.calls += 1
            return 0.9

    random = CountingRandom()
    interpreter = ArtifactInterpreter(_minimal_profile())
    values = interpreter.simulate(
        ["same_hand", "same_hand", "ordinary_space", "sentence"],
        80,
        random,
        iki_cv=0.0,
    )

    assert random.calls == 4
    assert values[0].total_ms == pytest.approx(values[1].total_ms)
    assert values[0].total_ms != values[2].total_ms
    assert values[3].total_ms != values[0].total_ms
    assert interpreter.expected_wpm(80, 0.0) == pytest.approx(80, rel=1e-6)


@pytest.mark.parametrize("wpm,cv", [(0, 0.2), (201, 0.2), (65, -0.1), (65, 1.1)])
def test_custom_timing_rejects_values_outside_the_public_contract(wpm, cv):
    with pytest.raises(ValueError, match="custom timing"):
        ArtifactInterpreter(_minimal_profile()).calibration(wpm, cv)


def test_keyrecs_reader_reconstructs_only_contiguous_adjacent_pairs(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text(
        "participant,session,key1,key2,DD.key1.key2\n"
        "p001,1,A,;,0.100\n"
        "p001,1,;,Space,0.110\n"
        "p001,1,Space,.,0.120\n"
        "p001,1,.,Space,0.130\n"
        "p001,1,Space,B,0.140\n"
        "p001,1,B,Shift,0.150\n"
        "p001,1,Shift,C,0.160\n"
        "p001,1,C,D,0.170\n",
        encoding="utf-8",
    )

    gaps, rejected = derive._read_keyrecs(path)

    assert rejected == 2
    assert [(gap.first, gap.second) for gap in gaps] == [
        ("A", ";"),
        (";", " "),
        (" ", "."),
        (".", " "),
        (" ", "B"),
        ("C", "D"),
    ]
    assert [gap.gap_class for gap in gaps] == [
        "alternate_hand",
        "other",
        "ordinary_space",
        "sentence",
        "ordinary_space",
        "same_finger",
    ]
    assert gaps[-1].segment != gaps[0].segment


def test_shrinkage_endpoints_reproduce_parent_and_child_laws_exactly():
    parent = tuple(float(index) for index in range(101))
    child = [(1000.0 + index, 1.0) for index in range(101)]
    assert derive._shrunken_quantiles(child, parent, 0.0) == parent
    assert derive._shrunken_quantiles(child, parent, 1.0) == derive._weighted_quantiles(child)


def test_rank_transition_pairs_are_participant_and_session_equal_and_never_cross_breaks():
    rows = [
        _gap("p1", 0, 10, session="a", segment=0),
        _gap("p1", 1, 10, session="a", segment=0),
        _gap("p1", 0, 30, session="b", segment=0),
        _gap("p1", 1, 30, session="b", segment=0),
        _gap("p2", 0, 60, session="a", segment=0),
        _gap("p2", 1, 60, session="a", segment=0),
        _gap("p2", 2, 10, session="a", segment=1),
    ]
    prepared = derive.PreparedKeyRecs(
        tuple(rows),
        tuple(rows),
        ("p1", "p2"),
        {("p1", "a"): 1.0, ("p1", "b"): 1.0, ("p2", "a"): 1.0},
        0,
    )
    quantiles = {
        gap_class: tuple(float(index) for index in range(101)) for gap_class in derive.CLASSES
    }

    joint, counts = derive._rank_transition_joint(prepared, {"p1", "p2"}, quantiles)

    assert joint[0, 0] == pytest.approx(0.25)
    assert joint[1, 1] == pytest.approx(0.25)
    assert joint[2, 2] == pytest.approx(0.5)
    assert joint.sum() == pytest.approx(1.0)
    assert counts == {"participants": 2, "sessions": 3, "transitions": 3}


def test_rank_transition_alpha_is_restricted_to_the_frozen_grid():
    empirical = np.full((4, 4), 0.25)
    with pytest.raises(ValueError, match="frozen grid"):
        derive._blend_rank_transition(empirical, 0.3)


def test_rank_alpha_selection_is_participant_disjoint_and_train_only(monkeypatch):
    participants = {"p1", "p2", "p3", "p4"}
    prepared = derive.PreparedKeyRecs((), (), tuple(sorted(participants)), {}, 0)
    joints = []
    folds = (("p1", "p2"), ("p3", "p4"))

    monkeypatch.setattr(derive, "_group_folds", lambda *_args: folds)

    def fake_joint(_prepared, selected, _quantiles):
        joints.append(set(selected))
        joint = np.full((4, 4), 0.01)
        np.fill_diagonal(joint, 0.21)
        return joint, {
            "participants": len(selected),
            "sessions": len(selected),
            "transitions": len(selected),
        }

    monkeypatch.setattr(derive, "_rank_transition_joint", fake_joint)

    selected, records = derive._select_rank_transition_alpha(
        prepared, participants, 123, {name: [0.5, 1.5] for name in derive.CLASSES}
    )

    assert selected > 0.0
    assert joints == [
        {"p3", "p4"},
        {"p1", "p2"},
        {"p1", "p2"},
        {"p3", "p4"},
    ]
    assert all(record["fixed_released_marginals"] for record in records)
    training_sets = joints[::2]
    assert all(
        not (set(record["held_out_participant_ids"]) & training_sets[index])
        for index, record in enumerate(records)
    )


def test_parent_candidate_rung_sets_every_empirical_shrinkage_to_zero():
    shrinkage = derive._parent_only_shrinkage()
    assert set(shrinkage) == {
        *derive.RELEASED_PARENTS,
        "hard_break",
        "newline",
        "paragraph",
    }
    assert set(shrinkage.values()) == {0.0}


def test_candidate_ladder_selects_the_first_asymmetric_primary_clearing_rung():
    assert (
        derive._select_candidate_rung(
            {
                "context_parent": {"cleared": True},
                "observable_context": {"cleared": True},
            }
        )
        == "context_parent"
    )
    assert (
        derive._select_candidate_rung(
            {
                "context_parent": {"cleared": False},
                "observable_context": {"cleared": True},
            }
        )
        == "observable_context"
    )
    assert (
        derive._select_candidate_rung(
            {
                "context_parent": {"cleared": False},
                "observable_context": {"cleared": False},
                "observable_context_rank4": {"cleared": True},
            }
        )
        == "observable_context_rank4"
    )
    assert derive._select_candidate_rung({"observable_context_rank4": {"cleared": False}}) is None


def test_empirical_quantiles_reject_negative_weights_and_skip_zero_weights():
    with pytest.raises(ValueError, match="weights"):
        derive._weighted_quantiles([(1.0, -1.0), (2.0, 1.0)])
    assert derive._weighted_quantiles([(1.0, 0.0), (2.0, 1.0)]) == (2.0,) * 101


def test_released_comparator_matches_schema_one_runtime_seed_and_normalization():
    text = "a b.c"
    rows = [
        _gap("p001", index, 100, first=first, second=second, gap_class="within")
        for index, (first, second) in enumerate(pairwise(text))
    ]
    artifact = {
        "residual_quantiles": {
            "within": [0.5 + index / 100 for index in range(101)],
            "word": [1.0 + index / 100 for index in range(101)],
            "sentence": [2.0 + index / 100 for index in range(101)],
        }
    }
    result = derive.released_comparator.simulate_once(rows, artifact, np.random.default_rng(123))

    assert result == pytest.approx(
        [
            169.83808293054648,
            151.37536223235273,
            103.4755757695422,
            313.772517529097,
        ]
    )
    assert np.sum(result) == pytest.approx(len(rows) * 12_000 / 65)


def test_released_comparator_uses_its_own_schema_one_reader_and_fitter(tmp_path):
    path = tmp_path / "released.csv"
    path.write_text(
        "participant,session,key1,key2,DD.key1.key2\n"
        "p001,1,A,B,0.001\n"
        "p001,1,B,Space,0.200\n"
        "p001,1,Space,C,0.300\n"
        "p001,1,.,D,0.400\n"
        "p001,1,Enter,A,0.100\n",
        encoding="utf-8",
    )

    rows, rejected = derive.released_comparator.read(path)
    model = derive.released_comparator.fit(rows, {"p001"})

    assert [row.interval_ms for row in rows] == [1.0, 200.0, 300.0, 400.0]
    assert rejected == 1
    assert model["counts"] == {
        "within": {"participants": 1, "sessions": 1, "intervals": 2},
        "word": {"participants": 1, "sessions": 1, "intervals": 1},
        "sentence": {"participants": 1, "sessions": 1, "intervals": 1},
    }


def test_candidate_zero_shrinkage_equals_exact_released_parents_including_sub_20(tmp_path):
    path = tmp_path / "keyrecs.csv"
    records = ["participant,session,key1,key2,DD.key1.key2"]
    for index in range(5):
        participant = f"p{index + 1:03d}"
        records.extend(
            [
                f"{participant},1,A,B,0.010",
                f"{participant},1,A,B,0.100",
                f"{participant},1,B,Space,0.200",
                f"{participant},1,Space,.,0.300",
                f"{participant},1,.,C,0.400",
            ]
        )
    path.write_text("\n".join(records) + "\n", encoding="utf-8")

    candidate_rows, rejected = derive._read_keyrecs(path)
    comparator_rows, _ = derive.released_comparator.read(path)
    prepared = derive._prepare_keyrecs(candidate_rows, rejected, comparator_rows)
    parents = derive._fit_parent_buckets(prepared, set(prepared.participants))
    released = derive.released_comparator.fit(comparator_rows, set(prepared.participants))[
        "residual_quantiles"
    ]

    assert all(
        prepared.session_centers[(participant, "1")] == pytest.approx(202.0)
        for participant in prepared.participants
    )
    assert parents == {name: tuple(values) for name, values in released.items()}
    assert derive._shrunken_quantiles([(99.0, 1.0)], parents["within"], 0.0) == tuple(
        released["within"]
    )
    profile = derive._fit_profile(
        prepared,
        set(prepared.participants),
        {
            "same_key": 0.0,
            "same_finger": 0.0,
            "same_hand": 0.0,
            "alternate_hand": 0.0,
            "other": 0.0,
            "ordinary_space": 0.0,
            "clause": 0.0,
            "sentence": 0.0,
            "hard_break": 0.0,
            "newline": 0.0,
            "paragraph": 0.0,
        },
    )
    assert profile["model"]["class_quantiles"]["same_hand"] == released["within"]
    assert profile["model"]["class_quantiles"]["ordinary_space"] == released["word"]
    assert profile["fit"]["intermediate_parent_quantiles"]["hard_break"] == released["sentence"]
    assert profile["fit"]["calibration_rate_error_wpm"] <= (derive.CALIBRATION_RATE_TOLERANCE_WPM)


def test_monte_carlo_standard_error_uses_all_paired_block_differences():
    differences = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0]
    expected = np.std(differences, ddof=1) / math.sqrt(len(differences))
    assert derive._monte_carlo_standard_error(differences) == pytest.approx(expected)


def test_primary_precision_uses_only_same_metric_bootstrap_error():
    assert derive._primary_precision_maximum(0.123) == pytest.approx(0.0246)


def test_medium_validation_budget_is_frozen():
    assert derive.PILOT_COUNTS == (256, 512, 1024, 2048)
    assert derive.PILOT_BLOCKS == 4
    assert derive.BOOTSTRAP_SAMPLES == 2_000


def test_sparse_inner_fold_records_null_and_uses_parent(monkeypatch):
    prepared = derive.PreparedKeyRecs((), (), ("a", "b"), {}, 0)
    parent = tuple(float(index) for index in range(101))
    monkeypatch.setattr(derive, "_group_folds", lambda *_args: [("a",), ("b",)])
    monkeypatch.setattr(
        derive,
        "_fit_parent_buckets",
        lambda *_args: {"within": parent, "word": parent, "sentence": parent},
    )
    monkeypatch.setattr(derive, "_weighted_values", lambda *_args: [])
    monkeypatch.setattr(derive, "_normalized_observations", lambda *_args: [])

    selected, records = derive._select_one_shrinkage(prepared, {"a", "b"}, "same_key", "within", 1)

    assert selected == 0.0
    assert all(score is None for record in records for score in record["scores"].values())
    derive._serialized(records)


def test_sparse_hard_break_folds_record_null_and_use_parent(monkeypatch):
    prepared = derive.PreparedKeyRecs((), (), ("a", "b"), {}, 0)
    parent = tuple(float(index) for index in range(101))
    monkeypatch.setattr(derive, "_group_folds", lambda *_args: [("a",), ("b",)])
    monkeypatch.setattr(
        derive,
        "_fit_parent_buckets",
        lambda *_args: {"within": parent, "word": parent, "sentence": parent},
    )
    monkeypatch.setattr(derive, "_weighted_values", lambda *_args: [])
    monkeypatch.setattr(derive, "_normalized_observations", lambda *_args: [])

    selected, records = derive._select_shrinkage(prepared, {"a", "b"}, 1)

    assert set(selected.values()) == {0.0}
    assert all(
        score is None
        for class_records in records.values()
        for record in class_records
        for score in record["scores"].values()
    )
    derive._serialized(records)


def test_pilot_requires_all_seed_blocks_to_agree_on_primary_sign():
    assert derive._block_sign_agreement([-0.1] * 8) == {
        "sign": "negative",
        "cleared": True,
    }
    assert derive._block_sign_agreement([-0.1] * 7 + [0.1]) == {
        "sign": "mixed",
        "cleared": False,
    }


@pytest.mark.parametrize("observable_mixed", [False, True])
def test_pilot_measures_every_rung_identically_and_eligibility_is_independent(
    monkeypatch, observable_mixed
):
    held = tuple(f"p{index:03d}" for index in range(8))
    sessions = {(participant, "1"): [object()] for participant in held}
    prepared = derive.PreparedKeyRecs((), (), (*held, "p999"), {}, 0)
    calls = []

    class FakeInterpreter:
        def __init__(self, profile, *, require_cleared):
            assert not require_cleared
            self.profile = profile

    def fake_block(
        received_sessions,
        interpreter,
        comparator,
        count,
        block,
        scales,
        rate_factor,
    ):
        rung = interpreter.profile["candidate_rung"]
        calls.append(
            (
                rung,
                id(received_sessions),
                id(comparator),
                count,
                block,
                id(scales),
                rate_factor,
            )
        )
        sign = 1.0 if observable_mixed and rung == "observable_context" and block % 2 else -1.0
        gap = {participant: sign * (0.1 + index / 1000) for index, participant in enumerate(held)}
        sequence = {
            participant: sign * (0.2 + index / 1000) for index, participant in enumerate(held)
        }
        return (
            {
                "gap_crps_difference": statistics.fmean(gap.values()),
                "sequence_energy_difference": statistics.fmean(sequence.values()),
            },
            {
                "gap_crps_difference": gap,
                "sequence_energy_difference": sequence,
            },
        )

    monkeypatch.setattr(derive, "PILOT_COUNTS", (256,))
    monkeypatch.setattr(
        derive,
        "_pilot_panels",
        lambda _prepared: (held, sessions, [{"participant": value} for value in held]),
    )
    monkeypatch.setattr(
        derive,
        "_select_shrinkage",
        lambda *_args: ({name: 0.5 for name in derive._parent_only_shrinkage()}, {}),
    )
    monkeypatch.setattr(
        derive,
        "_select_rank_transition_alpha",
        lambda *_args: (0.5, [{"fold": 0}]),
    )
    monkeypatch.setattr(
        derive,
        "_fit_profile",
        lambda *_args, candidate_rung, **_kwargs: {"candidate_rung": candidate_rung},
    )
    monkeypatch.setattr(derive, "ArtifactInterpreter", FakeInterpreter)
    monkeypatch.setattr(derive.released_comparator, "fit", lambda *_args: {"released": True})
    monkeypatch.setattr(derive, "_summary_scales", lambda *_args: np.ones(6))
    monkeypatch.setattr(derive, "_training_rate_factor", lambda *_args: (1.0, 65.0))
    monkeypatch.setattr(derive, "_pilot_block", fake_block)

    result = derive._run_pilot(prepared)

    assert result["candidate_ladder"] == list(derive.MODEL_LADDER)
    assert result["cleared"]
    assert set(result["panels"][0]["rungs"]) == set(derive.MODEL_LADDER)
    assert result["panels"][0]["rungs"]["context_parent"]["cleared"]
    assert result["panels"][0]["rungs"]["observable_context"]["cleared"] is (not observable_mixed)
    assert result["panels"][0]["rungs"]["observable_context_rank4"]["cleared"]
    assert ("observable_context" in result["eligible_rungs"]) is (not observable_mixed)
    assert ("observable_context" in result["ineligible_rungs"]) is observable_mixed
    assert len(calls) == len(derive.MODEL_LADDER) * derive.PILOT_BLOCKS
    for block in range(derive.PILOT_BLOCKS):
        matched = [call[1:] for call in calls if call[4] == block]
        assert len(matched) == len(derive.MODEL_LADDER)
        assert len(set(matched)) == 1


def test_outer_selected_rung_must_have_cleared_the_chosen_pilot_panel():
    pilot = {
        "rung_simulation_counts": {
            "context_parent": 256,
            "observable_context_rank4": 512,
        },
        "panels": [
            {
                "simulations_per_session": 256,
                "rungs": {rung: {"cleared": True} for rung in derive.MODEL_LADDER},
            },
            {
                "simulations_per_session": 512,
                "rungs": {
                    "context_parent": {"cleared": True},
                    "observable_context": {"cleared": False},
                    "observable_context_rank4": {"cleared": True},
                },
            },
        ],
    }

    assert derive._pilot_measured_rung(pilot, "context_parent")
    assert not derive._pilot_measured_rung(pilot, "observable_context")
    assert derive._pilot_measured_rung(pilot, "observable_context_rank4")
    assert not derive._pilot_measured_rung(pilot, "unregistered")


def test_pilot_bootstrap_participants_are_aggregated_across_all_blocks():
    blocks = [
        {"score": {"p1": 1.0, "p2": 4.0}},
        {"score": {"p1": 3.0, "p2": 8.0}},
    ]
    assert derive._aggregate_block_participants(blocks, "score") == [2.0, 6.0]


def test_simulation_seed_namespaces_are_pairwise_disjoint():
    identities = {
        derive._stream_identity(model, (stage, block, session), simulation)
        for model in (1, 2)
        for stage in range(3)
        for block in range(8)
        for session in range(2)
        for simulation in range(4)
    }
    states = {
        np.random.SeedSequence(identity).generate_state(4).tobytes() for identity in identities
    }
    assert len(identities) == 2 * 3 * 8 * 2 * 4
    assert len(states) == len(identities)


def test_candidate_matrix_is_released_before_comparator_allocation(monkeypatch):
    candidate_reference = None

    def candidate(*_args):
        nonlocal candidate_reference
        matrix = np.asarray([[100.0, 120.0, 140.0], [110.0, 130.0, 150.0]])
        candidate_reference = weakref.ref(matrix)
        return matrix

    def comparator(*_args):
        assert candidate_reference is not None
        assert candidate_reference() is None
        return np.asarray([[90.0, 120.0, 150.0], [100.0, 130.0, 160.0]])

    monkeypatch.setattr(derive, "_simulate_candidate", candidate)
    monkeypatch.setattr(derive, "_simulate_comparator", comparator)
    rows = [_gap("p001", index, 100 + index * 10) for index in range(3)]

    result = derive._session_score(
        rows,
        object(),
        {},
        2,
        (0, 0, 0),
        np.ones(6),
        1.0,
    )

    assert math.isfinite(result["gap_crps_difference"])


def test_rank4_deriver_simulation_matches_interpreter_and_resets_between_segments():
    interpreter = ArtifactInterpreter(_markov_profile())
    rows = [
        _gap("p001", 0, 100, segment=0),
        _gap("p001", 1, 100, segment=0),
        _gap("p001", 2, 100, segment=1),
    ]
    namespace = (7, 8, 9)

    actual = derive._simulate_candidate(interpreter, rows, 1, namespace)[0]
    expected = interpreter.simulate(
        [row.gap_class for row in rows],
        65,
        derive._stream_random(1, namespace, 0),
        rank_resets=[True, False, True],
    )

    assert actual == pytest.approx([sample.total_ms for sample in expected])


def test_pilot_uses_eight_200_gap_panels_without_crossing_retained_segment_breaks():
    rows = []
    centers = {}
    for participant_index in range(8):
        participant = f"p{participant_index + 1:03d}"
        centers[(participant, "1")] = 100.0
        rows.extend(_gap(participant, order, 100, segment=2) for order in range(100))
        rows.extend(_gap(participant, order, 100, segment=3) for order in range(100, 210))
    prepared = derive.PreparedKeyRecs(
        tuple(rows), tuple(rows), tuple(sorted({row.participant for row in rows})), centers, 0
    )

    held, panels, manifest = derive._pilot_panels(prepared)

    assert len(held) == len(panels) == len(manifest) == 8
    assert {len(panel) for panel in panels.values()} == {200}
    assert {entry["segment_count"] for entry in manifest} == {2}
    assert all(len(entry["segment_ranges"]) == 2 for entry in manifest)
    assert all(len(derive._segment_pairs(panel)) == 198 for panel in panels.values())


def test_development_caps_each_held_participant_at_one_200_gap_multisegment_panel():
    rows = []
    centers = {}
    participants = ["p003", "p001", "p002"]
    for participant in participants:
        centers[(participant, "1")] = 100.0
        centers[(participant, "2")] = 100.0
        rows.extend(_gap(participant, order, 100, session="2", segment=5) for order in range(230))
        rows.extend(_gap(participant, order, 100, session="1", segment=3) for order in range(99))
        rows.extend(
            _gap(participant, order, 100, session="1", segment=4) for order in range(99, 205)
        )
    prepared = derive.PreparedKeyRecs(
        tuple(rows), tuple(rows), tuple(sorted(participants)), centers, 0
    )

    panels, manifest = derive._fixed_panels(prepared, participants)

    assert len(panels) == len(manifest) == 3
    assert {len(panel) for panel in panels.values()} == {200}
    assert {entry["session"] for entry in manifest} == {"1"}
    assert {entry["segment_count"] for entry in manifest} == {2}
    assert all(len(entry["segment_ranges"]) == 2 for entry in manifest)
    assert all(len(derive._segment_pairs(panel)) == 198 for panel in panels.values())


def test_development_scores_only_pilot_eligible_rungs_at_their_measured_count(
    monkeypatch,
):
    prepared = derive.PreparedKeyRecs((), (), ("p1", "p2"), {}, 0)
    fitted = []
    counts = []

    class FakeInterpreter:
        def __init__(self, profile, *, require_cleared):
            assert not require_cleared
            self.rung = profile["rung"]

    monkeypatch.setattr(derive, "_group_folds", lambda *_args: (("p1",),))
    monkeypatch.setattr(
        derive,
        "_select_shrinkage",
        lambda *_args: ({name: 0.5 for name in derive._parent_only_shrinkage()}, []),
    )

    def fake_fit(*_args, candidate_rung, **_kwargs):
        fitted.append(candidate_rung)
        return {"rung": candidate_rung}

    monkeypatch.setattr(derive, "_fit_profile", fake_fit)
    monkeypatch.setattr(derive, "ArtifactInterpreter", FakeInterpreter)
    monkeypatch.setattr(derive.released_comparator, "fit", lambda *_args: {})
    monkeypatch.setattr(derive, "_summary_scales", lambda *_args: np.ones(6))
    monkeypatch.setattr(derive, "_training_rate_factor", lambda *_args: (1.0, 65.0))
    monkeypatch.setattr(
        derive,
        "_fixed_panels",
        lambda *_args: ({("p1", "1"): [object()]}, [{"participant": "p1"}]),
    )

    def fake_score(_rows, interpreter, _comparator, count, *_args):
        counts.append((interpreter.rung, count))
        return {
            "gap_crps_difference": -0.1,
            "sequence_energy_difference": -0.2,
        }

    monkeypatch.setattr(derive, "_session_score", fake_score)

    result = derive._run_development(prepared, {"observable_context": 512})

    assert fitted == ["observable_context"]
    assert counts == [("observable_context", 512)]
    assert result["pilot_eligible_rungs"] == ["observable_context"]
    assert result["selected_candidate"] == "observable_context"
    assert result["cleared"]


def test_piecewise_linear_moments_are_integrated_not_point_averaged():
    mean, second = typing_profile._piecewise_moments((0.0, 2.0))
    assert mean == pytest.approx(1.0)
    assert second == pytest.approx(4 / 3)
    assert typing_profile._piecewise_clipped_mean((-1.0, 3.0), 0.0, 2.0) == pytest.approx(1.0)


def test_sparse_boundary_quantile_error_uses_each_predictive_distribution():
    observed = np.asarray([1.0])
    simulations = np.asarray([[0.0], [1.0], [2.0]])
    assert derive._predictive_three_quantile_error(observed, simulations) == pytest.approx(
        (0.8 + 0.0 + 0.8) / 3
    )


def test_phase_reports_include_primary_secondary_boundary_and_wpm_diagnostics():
    scores = {}
    for participant_index in range(25):
        participant = f"qt_{participant_index}"
        for phase in ("1", "2"):
            score = {
                "gap_crps_difference": -0.1,
                "sequence_energy_difference": -0.1,
                "observed_wpm": 65.0,
                "candidate_wpm_median": 65.0,
                "comparator_wpm_median": 65.0,
                "candidate_wpm_quantiles": (50.0, 65.0, 80.0),
                "comparator_wpm_quantiles": (45.0, 64.0, 85.0),
                "candidate_wpm_rate_draws": np.asarray(
                    [10.0, 10.0, 90.0] if phase == "1" else [90.0, 90.0, 90.0]
                ),
                "comparator_wpm_rate_draws": np.asarray(
                    [20.0, 20.0, 80.0] if phase == "1" else [80.0, 80.0, 80.0]
                ),
                "maximum_candidate_gap_ms": 200.0,
                "maximum_candidate_space_ms": 200.0,
                "boundaries": {},
            }
            for name in derive.SECONDARY_MARGINS:
                score[f"{name}_candidate"] = 0.1
                score[f"{name}_comparator"] = 0.1
            for boundary in ("clause", "sentence", "newline", "paragraph"):
                score["boundaries"][boundary] = {
                    "crps_candidate": 0.1,
                    "crps_comparator": 0.1,
                    "three_quantile_error_candidate": 0.1,
                    "three_quantile_error_comparator": 0.1,
                }
            scores[(participant, phase)] = score
    dataset = derive.SkaidDataset(
        gaps=(),
        source_participant_count=27,
        participant_count=25,
        phase_counts={"1": 25, "2": 25},
        file_manifest=(),
        exact_segment_reconstruction=True,
        session_ids=tuple(f"qt_{index}" for index in range(25)),
        demographics_manifest=None,
        identity_manifest=(),
        alignment_manifest=(),
        exclusion_reasons={
            "phase_below_minimum_retained_valid_gaps": 1,
            "zero_timestamp_variation": 1,
        },
    )

    report = derive._confirmation_report(
        dataset, scores, {"cleared": True}, _minimal_profile(cleared=False)
    )

    assert set(report["phases"]) == {"1", "2"}
    assert all(
        set(phase_report) == {"primary", "secondary", "boundaries", "wpm"}
        for phase_report in report["phases"].values()
    )
    assert report["wpm"]["candidate_population_predictive_wpm_quantiles"] == {
        "5": 10.0,
        "50": 90.0,
        "95": 90.0,
    }
    assert report["wpm"]["comparator_population_predictive_wpm_quantiles"] == {
        "5": 20.0,
        "50": 80.0,
        "95": 80.0,
    }
    assert "superior normalized gap-distribution fidelity" in report["acceptance_claim"]
    assert "sequence fidelity noninferior" in report["acceptance_claim"]
    assert "sequence superiority" not in report["acceptance_claim"]


def test_asymmetric_primary_gate_accepts_strict_boundary_clearance(monkeypatch):
    intervals = iter(
        (
            (-0.1, -1e-12),
            (-0.2, derive.SEQUENCE_ENERGY_NONINFERIORITY_MARGIN - 1e-12),
        )
    )
    monkeypatch.setattr(derive, "_bootstrap_interval", lambda *_args: next(intervals))
    scores = {
        (f"p{index}", "s"): {
            "gap_crps_difference": -0.01,
            "sequence_energy_difference": -0.01,
        }
        for index in range(4)
    }

    report = derive._primary_report(scores, 10)

    assert report["gap_crps_difference"]["cleared"]
    assert report["gap_crps_difference"]["claim"] == "superiority"
    assert report["sequence_energy_difference"]["cleared"]
    assert report["sequence_energy_difference"]["maximum_difference"] == 0.10
    assert report["sequence_energy_difference"]["favorable_point_estimate_required"]


@pytest.mark.parametrize(
    ("gap_upper", "sequence_mean", "sequence_upper", "failed_metric"),
    [
        (0.0, -0.01, 0.09, "gap_crps_difference"),
        (-0.01, 0.0, 0.09, "sequence_energy_difference"),
        (-0.01, 0.01, 0.09, "sequence_energy_difference"),
        (-0.01, -0.01, 0.10, "sequence_energy_difference"),
    ],
)
def test_asymmetric_primary_gate_rejects_boundary_and_unfavorable_mean(
    monkeypatch, gap_upper, sequence_mean, sequence_upper, failed_metric
):
    intervals = iter(((-0.1, gap_upper), (-0.2, sequence_upper)))
    monkeypatch.setattr(derive, "_bootstrap_interval", lambda *_args: next(intervals))
    scores = {
        (f"p{index}", "s"): {
            "gap_crps_difference": -0.01,
            "sequence_energy_difference": sequence_mean,
        }
        for index in range(4)
    }

    report = derive._primary_report(scores, 10)

    assert not report[failed_metric]["cleared"]


def test_paired_noninferiority_gates_bootstrap_interval_upper_bound():
    comparator = {f"p{index}": 1.0 for index in range(8)}
    passing = {participant: 1.05 for participant in comparator}
    failing = {participant: 1.2 for participant in comparator}

    passed = derive._paired_noninferiority(passing, comparator, 0.1, 17)
    failed = derive._paired_noninferiority(failing, comparator, 0.1, 17)

    assert passed["difference"] == pytest.approx(0.05)
    assert passed["participant_clustered_95_percent_interval"] == pytest.approx([0.05, 0.05])
    assert passed["cleared"]
    assert not failed["cleared"]


def test_skaid_readme_identity_is_pinned_before_confirmation(tmp_path):
    assert derive.SKAID_README_SHA256 == (
        "c51f24e74879a79f36d37e3da56ce7e79a23a5b83b227a5b2948c66f960b93e3"
    )
    assert derive.SKAID_DOI == "10.5281/zenodo.17282184"
    assert derive.SKAID_VERSION == "1.0"
    path = tmp_path / "README.txt"
    path.write_text("not the frozen confirmation README", encoding="utf-8")
    with pytest.raises(ValueError, match="README identity"):
        derive._verify_readme(path)


def test_failed_pilot_prevents_outer_and_confirmation_reads(monkeypatch, tmp_path):
    calls = []
    failed_pilot = {
        "cleared": False,
        "panels": [
            {
                "rungs": {
                    rung: {
                        "primary": {
                            "gap_crps_difference": {
                                "mean_difference": 0.0345,
                                "monte_carlo_standard_error": 0.0123,
                                "maximum_allowed": 0.0005,
                                "block_sign_agreement": {"sign": "mixed"},
                                "cleared": False,
                            },
                            "sequence_energy_difference": {
                                "mean_difference": 0.0678,
                                "monte_carlo_standard_error": 0.0045,
                                "maximum_allowed": 0.0004,
                                "block_sign_agreement": {"sign": "positive"},
                                "cleared": False,
                            },
                        }
                    }
                    for rung in derive.MODEL_LADDER
                },
            }
        ],
    }
    monkeypatch.setattr(derive, "_read_keyrecs", lambda _path: ([], 0))
    monkeypatch.setattr(derive.released_comparator, "read", lambda _path: ([], 0))
    empty = derive.PreparedKeyRecs((), (), (), {}, 0)
    monkeypatch.setattr(derive, "_prepare_keyrecs", lambda *_args: empty)
    monkeypatch.setattr(derive, "_run_pilot", lambda *_args: failed_pilot)
    monkeypatch.setattr(derive, "_run_development", lambda *_args: calls.append("outer"))
    monkeypatch.setattr(
        derive, "_read_skaid", lambda *_args, **_kwargs: calls.append("confirmation")
    )

    with pytest.raises(RuntimeError, match="pilot precision") as raised:
        derive.derive(
            tmp_path / "keyrecs.csv",
            tmp_path / "skaid.zip",
            tmp_path / "README.txt",
            tmp_path / "demographics.csv",
            verify_hashes=False,
        )
    assert str(raised.value) == (
        "Monte Carlo pilot precision did not clear at the simulation cap; "
        "context_parent.gap_crps_difference(mean=0.0345, mc_se=0.0123, "
        "maximum_allowed=0.0005, sign=mixed, cleared=false); "
        "context_parent.sequence_energy_difference(mean=0.0678, mc_se=0.0045, "
        "maximum_allowed=0.0004, sign=positive, cleared=false); "
        "observable_context.gap_crps_difference(mean=0.0345, mc_se=0.0123, "
        "maximum_allowed=0.0005, sign=mixed, cleared=false); "
        "observable_context.sequence_energy_difference(mean=0.0678, mc_se=0.0045, "
        "maximum_allowed=0.0004, sign=positive, cleared=false); "
        "observable_context_rank4.gap_crps_difference(mean=0.0345, mc_se=0.0123, "
        "maximum_allowed=0.0005, sign=mixed, cleared=false); "
        "observable_context_rank4.sequence_energy_difference(mean=0.0678, mc_se=0.0045, "
        "maximum_allowed=0.0004, sign=positive, cleared=false); outer and confirmation "
        "scoring were not run"
    )
    assert calls == []


def test_failed_keyrecs_candidate_ladder_prevents_confirmation_input_reads(monkeypatch, tmp_path):
    calls = []
    primary = {
        metric: {"participant_clustered_95_percent_interval": [-0.1, 0.01]}
        for metric in ("gap_crps_difference", "sequence_energy_difference")
    }
    development = {
        "cleared": False,
        "rungs": {rung: {"primary": primary} for rung in derive.MODEL_LADDER},
    }
    empty = derive.PreparedKeyRecs((), (), (), {}, 0)
    monkeypatch.setattr(derive, "_read_keyrecs", lambda _path: ([], 0))
    monkeypatch.setattr(derive.released_comparator, "read", lambda _path: ([], 0))
    monkeypatch.setattr(derive, "_prepare_keyrecs", lambda *_args: empty)
    monkeypatch.setattr(
        derive,
        "_run_pilot",
        lambda *_args: {
            "cleared": True,
            "rung_simulation_counts": {"context_parent": 256},
        },
    )
    monkeypatch.setattr(derive, "_run_development", lambda *_args: development)
    monkeypatch.setattr(derive, "_hash", lambda *_args: calls.append("source"))
    monkeypatch.setattr(derive, "_read_skaid", lambda *_args, **_kwargs: calls.append("skaid"))

    with pytest.raises(RuntimeError, match="No KeyRecs candidate rung"):
        derive.derive(
            tmp_path / "keyrecs.csv",
            tmp_path / "skaid.zip",
            tmp_path / "README.txt",
            tmp_path / "demographics.csv",
            verify_hashes=False,
        )

    assert calls == []


def _csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode()


def _phase_record(timestamp, event, key):
    return {
        "Session ID": "fixture",
        "Timestamp (ms)": str(timestamp),
        "Event": event,
        "Key": key,
        "Phase": "1",
    }


def test_skaid_key_removes_exactly_one_dotted_prefix_and_maps_modifier_aliases():
    assert derive._skaid_key("Key.a") == ("text", "a", "named:a")
    assert derive._skaid_key("KEY.space") == ("text", " ", "named:space")
    assert derive._skaid_key("A") == ("text", "A", "literal:a")
    assert derive._skaid_key("Key.shift_l") == ("modifier", None, "shiftleft")
    assert derive._skaid_key("Key.ctrl_r") == ("modifier", None, "controlright")
    assert derive._skaid_key("Key.Key.a")[0] == "control"


def test_skaid_phase_uses_observed_caps_lock_and_shift_case_semantics():
    records = [
        _phase_record(10, "press", "Key.caps_lock"),
        _phase_record(20, "release", "Key.caps_lock"),
        _phase_record(100, "press", "Key.a"),
        _phase_record(120, "release", "Key.a"),
        _phase_record(130, "press", "Key.caps_lock"),
        _phase_record(140, "release", "Key.caps_lock"),
        _phase_record(180, "press", "Key.shift_l"),
        _phase_record(200, "press", "Key.b"),
        _phase_record(220, "release", "Key.b"),
        _phase_record(230, "release", "Key.shift_l"),
        _phase_record(300, "press", "Key.c"),
        _phase_record(320, "release", "Key.c"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "ABc", 0)

    assert [(gap.first, gap.second) for gap in imported.gaps] == [("A", "B"), ("B", "c")]
    assert imported.diagnostics["matched_coverage"] == 1.0


def test_skaid_auto_repeat_release_closes_the_whole_press_run():
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(150, "press", "Key.a"),
        _phase_record(170, "release", "Key.a"),
        _phase_record(250, "press", "Key.b"),
        _phase_record(270, "release", "Key.b"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "aab", 0)

    assert [gap.interval_ms for gap in imported.gaps] == [50.0, 100.0]
    assert imported.diagnostics["unmatched_presses"] == 0


@pytest.mark.parametrize("interrupting_key", ["Key.backspace", "Key.left"])
def test_skaid_edit_or_control_event_breaks_an_exact_aligned_run(interrupting_key):
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(120, "release", "Key.a"),
        _phase_record(150, "press", interrupting_key),
        _phase_record(160, "release", interrupting_key),
        _phase_record(250, "press", "Key.b"),
        _phase_record(270, "release", "Key.b"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "ab", 0)

    assert imported.gaps == ()


def test_skaid_repeated_character_alignment_is_deterministic_and_breaks_skips():
    records = []
    for index in range(4):
        records.extend(
            (
                _phase_record(100 + index * 100, "press", "Key.a"),
                _phase_record(120 + index * 100, "release", "Key.a"),
            )
        )

    first = derive._phase_gaps("fixture", "1", records, "aaa", 0)
    second = derive._phase_gaps("fixture", "1", records, "aaa", 0)

    assert first == second
    assert first.diagnostics["skipped_observable_presses"] == 1
    assert len(first.gaps) == 2


def test_skaid_invalid_timestamp_breaks_without_inferred_timing():
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(120, "release", "Key.a"),
        _phase_record("invalid", "press", "Key.b"),
        _phase_record(220, "release", "Key.b"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "ab", 0)

    assert imported.gaps == ()
    assert imported.diagnostics["invalid_timestamp_rows"] == 1
    assert imported.diagnostics["skipped_expected_characters"] == 1


def test_skaid_timestamp_reversal_and_unmatched_release_break_segments():
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(120, "release", "Key.a"),
        _phase_record(90, "press", "Key.b"),
        _phase_record(130, "release", "Key.b"),
        _phase_record(140, "release", "Key.left"),
        _phase_record(250, "press", "Key.c"),
        _phase_record(270, "release", "Key.c"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "abc", 0)

    assert imported.gaps == ()
    assert imported.diagnostics["timestamp_reversals"] == 1
    assert imported.diagnostics["unmatched_releases"] == 1


def test_skaid_timestamp_reversal_on_release_breaks_its_press_gap():
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(200, "press", "Key.b"),
        _phase_record(50, "release", "Key.a"),
        _phase_record(250, "release", "Key.b"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "ab", 0)

    assert imported.gaps == ()
    assert imported.diagnostics["timestamp_reversals"] == 1


def test_skaid_skipped_expected_character_breaks_the_aligned_runs():
    records = [
        _phase_record(100, "press", "Key.a"),
        _phase_record(120, "release", "Key.a"),
        _phase_record(250, "press", "Key.b"),
        _phase_record(270, "release", "Key.b"),
    ]

    imported = derive._phase_gaps("fixture", "1", records, "axb", 0)

    assert imported.gaps == ()
    assert imported.diagnostics["skipped_expected_characters"] == 1
    assert imported.diagnostics["matching_blocks"] == 2


def test_skaid_confirmation_eligibility_uses_both_phase_200_gap_floor():
    participants = {"short", "eligible", "zero"}
    gaps = {
        ("short", "1"): [object()] * 199,
        ("short", "2"): [object()] * 200,
        ("eligible", "1"): [object()] * 200,
        ("eligible", "2"): [object()] * 200,
        ("zero", "1"): [],
        ("zero", "2"): [],
    }
    diagnostics = [
        {"participant": participant, "distinct_valid_timestamps": distinct}
        for participant, distinct in (
            ("short", 50),
            ("short", 50),
            ("eligible", 50),
            ("eligible", 50),
            ("zero", 1),
            ("zero", 1),
        )
    ]

    eligible, reasons = derive._skaid_confirmation_eligibility(participants, gaps, diagnostics)

    assert eligible == {"eligible"}
    assert reasons == {
        "phase_below_minimum_retained_valid_gaps": 1,
        "zero_timestamp_variation": 1,
    }


def test_confirmation_scoring_cannot_start_if_frozen_cohort_counts_differ(monkeypatch):
    dataset = derive.SkaidDataset(
        gaps=(),
        source_participant_count=27,
        participant_count=24,
        phase_counts={"1": 24, "2": 24},
        file_manifest=(),
        exact_segment_reconstruction=True,
        session_ids=tuple(f"participant-{index}" for index in range(24)),
        demographics_manifest=None,
        identity_manifest=(),
        alignment_manifest=(),
        exclusion_reasons={},
    )
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(derive, "_eligible_sessions", forbidden)

    with pytest.raises(ValueError, match="25-participant/50-phase"):
        derive._run_confirmation(
            dataset,
            object(),
            {},
            1,
            np.ones(6),
            1.0,
            {"cleared": True},
            _minimal_profile(),
        )
    assert not called


def test_skaid_import_checks_phase_pairs_event_alignment_and_exact_text(tmp_path):
    archive = tmp_path / "logs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "Keystroke Logs/person.csv",
            _csv_bytes(
                [
                    ["Session ID", "Timestamp (ms)", "Event", "Key", "Phase"],
                    ["person", "100", "press", "a", "1"],
                    ["person", "120", "release", "a", "1"],
                    ["person", "210", "press", "b", "1"],
                    ["person", "230", "release", "b", "1"],
                    ["person", "300", "press", "c", "2"],
                    ["person", "320", "release", "c", "2"],
                    ["person", "430", "press", "d", "2"],
                    ["person", "450", "release", "d", "2"],
                ]
            ),
        )
        output.writestr(
            "Keystroke Logs/person_full_text.csv",
            _csv_bytes(
                [
                    ["Session ID", "Phase", "Text", "Selected Email"],
                    ["person", "1", "ab", "Email 1"],
                    ["person", "2", "cd", "Free Form"],
                ]
            ),
        )

    imported = derive._read_skaid(archive, expected_pairs=1)

    assert imported.participant_count == 1
    assert imported.phase_counts == {"1": 1, "2": 1}
    assert [gap.interval_ms for gap in imported.gaps] == [110.0, 130.0]
    assert imported.exact_segment_reconstruction
    assert len(imported.file_manifest) == 2


def test_skaid_import_records_unmatched_text_without_inventing_timing(tmp_path):
    archive = tmp_path / "logs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "Keystroke Logs/person.csv",
            _csv_bytes(
                [
                    ["Session ID", "Timestamp (ms)", "Event", "Key", "Phase"],
                    ["person", "100", "press", "a", "1"],
                    ["person", "120", "release", "a", "1"],
                ]
            ),
        )
        output.writestr(
            "Keystroke Logs/person_full_text.csv",
            _csv_bytes(
                [
                    ["Session ID", "Phase", "Text", "Selected Email"],
                    ["person", "1", "x", "Email 1"],
                ]
            ),
        )
    imported = derive._read_skaid(archive, expected_pairs=1)

    assert imported.gaps == ()
    assert imported.alignment_manifest[0]["matched_characters"] == 0
    assert imported.alignment_manifest[0]["skipped_expected_characters"] == 1
    assert imported.alignment_manifest[0]["skipped_observable_presses"] == 1


def test_skaid_import_breaks_unmatched_phase_end_press(tmp_path):
    archive = tmp_path / "logs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "Keystroke Logs/person.csv",
            _csv_bytes(
                [
                    ["Session ID", "Timestamp (ms)", "Event", "Key", "Phase"],
                    ["person", "100", "press", "a", "1"],
                ]
            ),
        )
        output.writestr(
            "Keystroke Logs/person_full_text.csv",
            _csv_bytes(
                [
                    ["Session ID", "Phase", "Text", "Selected Email"],
                    ["person", "1", "a", "Email 1"],
                ]
            ),
        )
    imported = derive._read_skaid(archive, expected_pairs=1)

    assert imported.gaps == ()
    assert imported.alignment_manifest[0]["unmatched_presses"] == 1


def test_skaid_identity_joins_filename_session_demographics_and_email(tmp_path):
    archive = tmp_path / "logs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "Keystroke Logs/qt_1.csv",
            _csv_bytes(
                [
                    ["Session ID", "Timestamp (ms)", "Event", "Key", "Phase"],
                    ["qt_session_1", "100", "press", "a", "1"],
                    ["qt_session_1", "120", "release", "a", "1"],
                ]
            ),
        )
        output.writestr(
            "Keystroke Logs/qt_1_full_text.csv",
            _csv_bytes(
                [
                    ["Session ID", "Phase", "Text", "Selected Email"],
                    ["qt_session_1", "1", "a", "Email 1"],
                ]
            ),
        )
    demographics = {"qt_session_1": {"Email": "Email 1"}}

    imported = derive._read_skaid(
        archive,
        expected_pairs=1,
        demographics=demographics,
        demographics_manifest={"rows": 1},
    )
    assert imported.session_ids == ("qt_1",)
    assert imported.demographics_manifest == {"rows": 1}

    demographics["qt_session_1"]["Email"] = "Email 2"
    with pytest.raises(ValueError, match="selected email"):
        derive._read_skaid(archive, expected_pairs=1, demographics=demographics)


def test_official_demographics_manifest_is_hash_pinned(monkeypatch, tmp_path):
    path = tmp_path / "all_participants_demographics.csv"
    rows = [
        ["Session ID", "Age Range", "Typing Method", "Device Used", "Email"],
        *[[f"qt_session_{index}", "18-22", "Standard", "Laptop", "Email 1"] for index in range(27)],
    ]
    path.write_bytes(_csv_bytes(rows))
    monkeypatch.setattr(
        derive,
        "_hash",
        lambda _path, name: (
            derive.SKAID_DEMOGRAPHICS_SHA256 if name == "sha256" else derive.SKAID_DEMOGRAPHICS_MD5
        ),
    )

    demographics, manifest = derive._read_demographics(path)

    assert len(demographics) == 27
    assert manifest["sha256"] == derive.SKAID_DEMOGRAPHICS_SHA256
    assert manifest["md5"] == derive.SKAID_DEMOGRAPHICS_MD5


def test_feature_scale_estimation_does_not_truncate_long_sessions(monkeypatch):
    lengths = []

    def record_length(_values, rows):
        lengths.append(len(rows))
        return np.zeros(6)

    monkeypatch.setattr(derive, "_summary", record_length)
    rows = [_gap("p001", index, 100) for index in range(300)]

    derive._summary_scales(rows, {"p001"})

    assert lengths == [300]


def test_frozen_protocol_contains_all_confirmation_inputs():
    source = {"sha256": "archive", "file_manifest": [{"sha256": "file"}]}
    protocol = derive._frozen_protocol(
        _minimal_profile(cleared=False),
        {"schema": 1, "residual_quantiles": {}},
        np.asarray([1.0, 2.0]),
        1.25,
        512,
        source,
    )

    assert protocol["comparator"]["schema"] == 1
    assert protocol["summary_scales"] == [1.0, 2.0]
    assert protocol["rate_factor"] == 1.25
    assert protocol["confirmation_source"] == source
    assert protocol["margins"]["primary_sequence_energy"] == 0.10
    assert (
        "one-tenth-SD Euclidean perturbation" in protocol["primary_gate"]["sequence_margin_basis"]
    )
    assert "componentwise error guarantee" in protocol["primary_gate"]["sequence_margin_basis"]
    assert protocol["claim_revision"]["stage"] == (
        "after KeyRecs development and before untouched SKAID confirmation"
    )
    assert "+0.0153869572" in protocol["claim_revision"]["original_dual_superiority_result"]
    assert protocol["claim_revision"]["confirmation_role"] == (
        "SKAID is the sole confirmatory acceptance source"
    )
    assert set(protocol["source_code"]) == {
        "class_map_sha256",
        "importer_sha256",
        "deriver_sha256",
        "comparator_sha256",
    }


def test_confirmation_manifest_mutation_changes_frozen_protocol_hash():
    source = {"sha256": "archive", "file_manifest": [{"sha256": "before"}]}

    def digest():
        protocol = derive._frozen_protocol(
            _minimal_profile(cleared=False),
            {"schema": 1},
            np.asarray([1.0]),
            1.0,
            256,
            source,
        )
        return derive._byte_hash(derive._serialized(protocol).encode())

    before = digest()
    source["file_manifest"][0]["sha256"] = "after"

    assert digest() != before


def test_public_profile_and_protocol_manifests_never_serialize_raw_participant_ids():
    raw_keyrecs = "p-private-fixture"
    raw_skaid = "qt_private_fixture"
    aliases = derive._source_aliases([raw_keyrecs], "keyrecs")
    pilot = derive._replace_identifiers(
        {
            "participant_ids": [raw_keyrecs],
            "panel_manifest": [{"participant": raw_keyrecs, "session": "1"}],
        },
        aliases,
    )
    dataset = derive.SkaidDataset(
        gaps=(),
        source_participant_count=1,
        participant_count=1,
        phase_counts={"1": 1, "2": 1},
        file_manifest=(
            {
                "path": f"Keystroke Logs/{raw_skaid}.csv",
                "bytes": 10,
                "sha256": "log-hash",
            },
            {
                "path": f"Keystroke Logs/{raw_skaid}_full_text.csv",
                "bytes": 20,
                "sha256": "text-hash",
            },
        ),
        exact_segment_reconstruction=True,
        session_ids=(raw_skaid,),
        demographics_manifest={"sha256": "demographics-hash"},
        identity_manifest=(
            {
                "file_participant": raw_skaid,
                "session_id": "qt_session_private_fixture",
                "demographic_id": "qt_session_private_fixture",
            },
        ),
        alignment_manifest=(
            {
                "participant": raw_skaid,
                "phase": "1",
                "matched_characters": 1,
            },
        ),
        exclusion_reasons={},
    )
    public_skaid = derive._public_skaid_identity(dataset)
    confirmation_source = {
        "source_participant_ids": public_skaid["source_participant_ids"],
        "participant_ids": public_skaid["participant_ids"],
        "identity_manifest": public_skaid["identity_manifest"],
        "file_manifest": public_skaid["file_manifest"],
        "alignment_manifest": public_skaid["alignment_manifest"],
        "aggregate_exclusion_reasons": dataset.exclusion_reasons,
    }
    profile = _minimal_profile(cleared=False)
    profile["fit"] = {"pilot": pilot}
    protocol = derive._frozen_protocol(
        profile,
        {"schema": 1},
        np.asarray([1.0]),
        1.0,
        256,
        confirmation_source,
        pilot,
    )
    profile["validation"] = {
        "pilot": pilot,
        "confirmation_source": confirmation_source,
        "frozen_protocol": protocol,
    }

    serialized = derive._serialized(profile)

    assert raw_keyrecs not in serialized
    assert raw_skaid not in serialized
    assert "qt_session_private_fixture" not in serialized
    assert "keyrecs-001" in serialized
    assert "skaid-001" in serialized
    assert "Keystroke Logs" not in serialized


def test_unverified_mode_is_not_exposed_by_the_cli(tmp_path):
    arguments = [
        str(tmp_path / "keyrecs.csv"),
        "--skaid-archive",
        str(tmp_path / "logs.zip"),
        "--skaid-readme",
        str(tmp_path / "README.txt"),
        "--skaid-demographics",
        str(tmp_path / "demographics.csv"),
        "--skip-source-hash-check",
    ]
    with pytest.raises(SystemExit):
        derive._parse_args(arguments)


def test_keyrecs_artifact_metadata_records_identity_license_and_dois(tmp_path):
    path = tmp_path / "free-text.final.csv"
    path.write_text("fixture", encoding="utf-8")

    source = derive._keyrecs_source(path)

    assert source["bytes"] == 7
    assert source["license"] == "CC BY 4.0"
    assert source["doi"] == "10.5281/zenodo.7886743"
    assert source["article_doi"] == "10.1016/j.dib.2023.109509"
    assert len(source["sha256"]) == 64
    assert len(source["md5"]) == 32


def test_serialization_is_canonical_and_byte_stable():
    value = {"z": 1, "a": "João"}
    first = derive._serialized(value)
    assert first == derive._serialized(json.loads(first))
    assert first.endswith("\n")


def test_deriver_contains_no_obsolete_latent_pipeline_terms():
    source = Path(derive.__file__).read_text(encoding="utf-8").lower()
    forbidden = ("pause_threshold", "rank_markov", "motor_quantiles", "hurdle", "hsmm")
    assert not [term for term in forbidden if term in source]
