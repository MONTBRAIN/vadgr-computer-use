import hashlib
import json
import math
import random
import statistics
from pathlib import Path

import pytest

import computer_use.core.typing as typing_model
from computer_use.core.typing import (
    DEFAULT_PROFILE,
    TypingCancelled,
    TypingDeadlineExceeded,
    TypingOptions,
    TypingPlan,
    TypingUnit,
    build_typing_plan,
    chunk_typing_plan,
    require_typing_deadline,
    validate_typing_options,
)
from computer_use.core.typing_boundaries import classify_boundary_gaps
from computer_use.core.typing_profile import ArtifactInterpreter, GapSample
from scripts import derive_typing_profile as profile_deriver

pytestmark = pytest.mark.usefixtures("schema_six_typing_runtime")


def test_cancellation_error_reports_only_completed_unit_count():
    error = TypingCancelled(3)
    assert str(error) == "typing_cancelled: 3 complete units"
    assert error.completed_units == 3


def test_deadline_error_reports_only_completed_unit_count():
    error = TypingDeadlineExceeded(4)
    assert str(error) == "typing_deadline_exceeded: 4 complete units"
    assert error.completed_units == 4


def test_fast_plan_preserves_one_bulk_unit():
    plan = build_typing_plan("secret text", TypingOptions())
    assert [unit.text for unit in plan.units] == ["secret text"]
    assert plan.predicted_ms == 0
    assert plan.human is False


def test_named_profile_is_deterministic_with_injected_random_source():
    one = build_typing_plan(
        "one two. Three", TypingOptions(human=True), _typing_random=random.Random(7)
    )
    two = build_typing_plan(
        "one two. Three", TypingOptions(human=True), _typing_random=random.Random(7)
    )
    assert one == two
    assert one.timing_profile == DEFAULT_PROFILE
    assert one.nominal_wpm == 68
    assert len({round(unit.delay_before_ms, 3) for unit in one.units[1:]}) > 1


def test_runtime_plan_matches_the_artifact_interpreter_for_one_fixed_stream(
    schema_six_profile,
):
    text = "aazf j.\n\nQ"
    units = tuple(typing_model.grapheme_clusters(text))
    boundaries = classify_boundary_gaps(units)
    classes = tuple(
        typing_model._context(units[index], units[index + 1], boundaries[index])
        for index in range(len(units) - 1)
    )
    interpreter = ArtifactInterpreter(schema_six_profile)
    expected = interpreter.simulate(classes, 68, random.Random(19))

    plan = build_typing_plan(
        text,
        TypingOptions(human=True),
        _typing_random=random.Random(19),
    )

    assert classes == (
        "same_key",
        "same_finger",
        "same_hand",
        "other",
        "ordinary_space",
        "same_hand",
        "other",
        "paragraph",
        "other",
    )
    assert [unit.delay_before_ms for unit in plan.units[1:]] == [
        sample.total_ms for sample in expected
    ]


def test_human_plan_marks_non_ascii_units_as_insertion_fallback():
    plan = build_typing_plan("Aé🙂\n", TypingOptions(human=True), _typing_random=random.Random(7))
    assert [unit.fallback for unit in plan.units] == [False, True, True, False]
    assert plan.fallback_units == 2


def test_human_plan_uses_unicode_grapheme_clusters_as_units():
    plan = build_typing_plan(
        "e\N{COMBINING ACUTE ACCENT}\N{WOMAN}\N{ZERO WIDTH JOINER}\N{PERSONAL COMPUTER}",
        TypingOptions(human=True),
        _typing_random=random.Random(7),
    )
    assert [unit.text for unit in plan.units] == ["é", "👩‍💻"]
    assert plan.fallback_units == 2


@pytest.mark.parametrize(
    "options",
    [
        TypingOptions(human=True),
        TypingOptions(human=True, wpm=10, iki_cv=1.0),
        TypingOptions(human=True, wpm=200, iki_cv=0.0),
    ],
)
def test_ordinary_space_complete_gaps_stay_inside_empirical_support(options):
    text = "alpha beta gamma delta"
    plan = build_typing_plan(text, options, _typing_random=random.Random(11))
    for index, unit in enumerate(plan.units[1:], start=1):
        if plan.units[index - 1].text == " ":
            assert unit.delay_before_ms <= 1500


def test_boundary_precedence_selects_one_complete_total_gap_law():
    plan = build_typing_plan(
        "Done. Next",
        TypingOptions(human=True, wpm=200, iki_cv=0),
        _typing_random=random.Random(5),
    )

    sentence_gap = plan.units[5].delay_before_ms
    assert 20 <= sentence_gap <= 3500
    assert typing_model._context(".", " ", "sentence") == "sentence"


def test_default_profile_does_not_rescale_each_message_to_exact_wpm():
    text = "A professional writes one sentence, then checks another sentence. " * 4
    rates = {
        round(
            build_typing_plan(
                text,
                TypingOptions(human=True),
                _typing_random=random.Random(seed),
            ).realized_wpm,
            3,
        )
        for seed in range(8)
    }
    assert len(rates) > 1
    assert rates != {68.0}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A.  B", [None, "sentence", None, None]),
        ("A,\nB", [None, None, "newline"]),
        ("A.\n\nB", [None, None, "paragraph", None]),
        ("A, . B", [None, None, None, "sentence", None]),
        ("A! \n B", [None, None, None, "newline", None]),
        ("A, \n \n B", [None, None, None, "paragraph", None, None, None]),
        ("A   B", [None, None, None, None]),
        ("A , B", [None, None, "clause", None]),
    ],
)
def test_boundary_clusters_contribute_at_most_one_pause(text, expected):
    units = tuple(typing_model.grapheme_clusters(text))
    boundaries = classify_boundary_gaps(units)
    assert list(boundaries) == expected
    assert sum(boundary is not None for boundary in boundaries) <= 1


def test_crlf_counts_as_one_line_break_inside_a_boundary_cluster():
    assert classify_boundary_gaps(("A", ".", "\r\n", " ", "B")) == (
        None,
        None,
        "newline",
        None,
    )
    assert classify_boundary_gaps(("A", ".", "\r\n", " ", "\r\n", "B")) == (
        None,
        None,
        "paragraph",
        None,
        None,
    )


def test_each_separate_boundary_cluster_gets_its_own_event():
    assert classify_boundary_gaps(tuple("A. B, C")) == (
        None,
        "sentence",
        None,
        None,
        "clause",
        None,
    )


def test_profile_deriver_uses_the_shared_maximal_cluster_classifier(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text(
        "participant,session,key1,key2,DD.key1.key2\n"
        "p1,1,A,;,0.1\n"
        "p1,1,;,Space,0.1\n"
        "p1,1,Space,.,0.1\n"
        "p1,1,.,Space,0.1\n"
        "p1,1,Space,B,0.1\n",
        encoding="utf-8",
    )

    gaps, rejected = profile_deriver._read_keyrecs(source)

    assert rejected == 0
    assert [gap.gap_class for gap in gaps] == [
        "alternate_hand",
        "other",
        "ordinary_space",
        "sentence",
        "ordinary_space",
    ]


def test_timing_metadata_reports_realized_rate_only_when_defined():
    empty = build_typing_plan("", TypingOptions(human=True))
    one = build_typing_plan("a", TypingOptions(human=True))
    many = build_typing_plan("abc", TypingOptions(human=True), _typing_random=random.Random(2))
    assert empty.metadata()["realized_wpm"] is None
    assert one.metadata()["realized_wpm"] is None
    assert many.metadata()["realized_wpm"] == many.realized_wpm


def test_custom_zero_cv_removes_residual_but_keeps_context_timing():
    plan = build_typing_plan(
        "aaaaaa",
        TypingOptions(human=True, wpm=60, iki_cv=0),
        _typing_random=random.Random(1),
    )
    assert len({round(unit.delay_before_ms, 6) for unit in plan.units[1:]}) == 1


def test_custom_plan_has_calibrated_population_rate_and_finite_bounds():
    text = "The quick brown fox types code, checks tests, and ships it. " * 20
    plans = [
        build_typing_plan(
            text,
            TypingOptions(human=True, wpm=52, iki_cv=0.3),
            _typing_random=random.Random(seed),
        )
        for seed in range(100)
    ]
    delays = [unit.delay_before_ms for plan in plans for unit in plan.units[1:]]
    assert all(math.isfinite(value) and 20 <= value <= 5000 for value in delays)
    rates = [plan.realized_wpm for plan in plans]
    assert statistics.fmean(rate for rate in rates if rate is not None) == pytest.approx(
        52, rel=0.08
    )


def test_long_plan_has_no_implicit_total_deadline():
    plan = build_typing_plan(
        "a" * 400,
        TypingOptions(human=True, wpm=10, iki_cv=0),
        _typing_random=random.Random(1),
    )
    assert plan.predicted_ms > 60_000
    require_typing_deadline(plan, plan.predicted_ms + 1)


def test_explicit_deadline_refuses_the_complete_plan():
    plan = build_typing_plan(
        "a" * 400,
        TypingOptions(human=True, wpm=65, iki_cv=0),
        _typing_random=random.Random(1),
    )
    with pytest.raises(TypingDeadlineExceeded) as captured:
        require_typing_deadline(plan, plan.predicted_ms - 1)
    assert captured.value.completed_units == 0


def test_deadline_and_realized_rate_use_exact_fractional_schedule():
    plan = TypingPlan(
        True,
        "test",
        60,
        (TypingUnit("a", 0), TypingUnit("b", 100.25)),
        101,
        100.25,
    )

    require_typing_deadline(plan, 100.25)
    with pytest.raises(TypingDeadlineExceeded):
        require_typing_deadline(plan, 100.24)
    assert plan.realized_wpm == pytest.approx(12_000 / 100.25)


def test_generated_plan_ceil_rounds_its_exact_schedule():
    plan = build_typing_plan(
        "ab",
        TypingOptions(human=True, wpm=200, iki_cv=0),
        _typing_random=random.Random(1),
    )

    assert plan._scheduled_ms_exact is not None
    assert plan.predicted_ms == math.ceil(plan._scheduled_ms_exact)


def test_runtime_adds_nothing_to_interpreter_total_gaps(monkeypatch):
    class RecordingInterpreter:
        profile = {"nominal_wpm": 65}

        def simulate(self, classes, _wpm, _random, iki_cv=None):
            assert iki_cv is None
            assert classes == ("ordinary_space",)
            return (GapSample("ordinary_space", 0.5, 321.5),)

    monkeypatch.setattr(typing_model, "_profile_interpreter", RecordingInterpreter)
    plan = build_typing_plan(" a", TypingOptions(human=True), _typing_random=random.Random(1))

    assert plan.units[1].delay_before_ms == 321.5


def test_browser_chunks_obey_every_transport_bound_and_reconstruct_the_plan():
    plan = build_typing_plan(
        "a" * 800,
        TypingOptions(human=True, wpm=65, iki_cv=0),
        _typing_random=random.Random(1),
    )
    chunks = chunk_typing_plan(plan)
    assert tuple(unit for chunk in chunks for unit in chunk) == plan.units
    assert all(len(chunk) <= 256 for chunk in chunks)
    assert all(sum(unit.delay_before_ms for unit in chunk) <= 5_000 for chunk in chunks)
    assert all(
        len(
            json.dumps(
                [
                    {
                        "text": unit.text,
                        "delay_before_ms": unit.delay_before_ms,
                        "fallback": unit.fallback,
                    }
                    for unit in chunk
                ],
                separators=(",", ":"),
            ).encode("utf-8")
        )
        <= 256 * 1024
        for chunk in chunks
    )


def test_browser_chunks_reject_one_unit_above_planned_duration_bound():
    plan = TypingPlan(
        True,
        "test",
        60,
        (TypingUnit("a", typing_model.MAX_TYPING_CHUNK_PLANNED_MS + 0.001),),
        5_001,
    )

    with pytest.raises(ValueError, match="chunk duration limit"):
        chunk_typing_plan(plan)


def test_checked_in_schema_six_profile_names_source_and_exact_deriver():
    root = Path(__file__).parents[2]
    profile = json.loads(
        (root / "computer_use/core/typing_profiles/us_adult_transcription_2026.json").read_text()
    )
    if profile.get("schema") != 6:
        with pytest.raises(ValueError):
            ArtifactInterpreter(profile)
        pytest.skip("gated schema-6 artifact has not been generated")
    script = root / "scripts" / profile["provenance"]["script"]
    source = profile["fit"]["source"]
    assert source["doi"] == "10.5281/zenodo.7886743"
    assert source["article_doi"] == "10.1016/j.dib.2023.109509"
    assert source["license"] == "CC BY 4.0"
    assert source["bytes"] > 0
    assert len(source["sha256"]) == 64
    assert hashlib.sha256(script.read_bytes()).hexdigest() == profile["provenance"]["script_sha256"]
    assert profile["fit"]["candidate_rung"] == "released_marginals_rank4"
    assert profile["nominal_wpm"] == 68
    assert profile["model"]["styles"] == [{"speed_log": 0.0, "weight": 1.0}]
    for gap_class, parent in profile["fit"]["class_aliases"].items():
        assert (
            profile["model"]["class_quantiles"][gap_class]
            == profile["fit"]["released_quantiles"][parent]
        )
    assert profile["model"]["ordinary_space_added_pause_ms"] == 0.0
    assert profile["limits"]["class_maximum_ms"]["ordinary_space"] == 1500.0
    ArtifactInterpreter(profile)
    assert profile["validation"]["cleared"] is True
    selected = str(profile["fit"]["rank_transition"]["alpha"])
    assert all(
        fold["scores"][selected] < fold["scores"]["0.0"]
        for fold in profile["fit"]["rank_transition_selection"]
    )
    assert profile["validation"]["failed_experiment"]["verdict"].startswith("failed")


@pytest.mark.parametrize(
    "options",
    [
        TypingOptions(wpm=50),
        TypingOptions(human=True, wpm=50),
        TypingOptions(human=True, iki_cv=0.2),
        TypingOptions(human=True, wpm=9, iki_cv=0.2),
        TypingOptions(human=True, wpm=201, iki_cv=0.2),
        TypingOptions(human=True, wpm=50, iki_cv=-0.1),
        TypingOptions(human=True, wpm=50, iki_cv=1.0001),
        TypingOptions(human=True, timing_profile="unknown"),
        TypingOptions(human=True, timing_profile=DEFAULT_PROFILE, wpm=50, iki_cv=0.2),
    ],
)
def test_invalid_options_fail_before_dispatch(options):
    with pytest.raises(ValueError):
        validate_typing_options(options)
