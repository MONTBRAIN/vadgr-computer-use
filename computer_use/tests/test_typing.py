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
    build_typing_plan,
    chunk_typing_plan,
    require_typing_deadline,
    validate_typing_options,
)


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
    assert one.nominal_wpm == 65
    assert len({round(unit.delay_before_ms, 3) for unit in one.units[1:]}) > 1


def test_human_plan_marks_non_ascii_units_as_insertion_fallback():
    plan = build_typing_plan(
        "Aé🙂\n", TypingOptions(human=True), _typing_random=random.Random(7)
    )
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
def test_ordinary_spaces_never_have_a_long_gap(options):
    text = "alpha beta gamma delta"
    plan = build_typing_plan(text, options, _typing_random=random.Random(11))
    for index, unit in enumerate(plan.units[1:], start=1):
        if plan.units[index - 1].text == " " or unit.text == " ":
            assert unit.delay_before_ms <= 300


def test_sentence_pause_is_additive_to_space_motor_cap(monkeypatch):
    monkeypatch.setattr(typing_model, "_sample_pause", lambda *_args: 450.0)
    plan = build_typing_plan(
        "Done. Next",
        TypingOptions(human=True, wpm=200, iki_cv=0),
        _typing_random=random.Random(5),
    )

    sentence_gap = plan.units[5].delay_before_ms
    assert sentence_gap > 450
    assert sentence_gap <= 750


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
    assert rates != {65.0}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A.  B", [None, "sentence", None, None]),
        ("A,\nB", [None, "newline", None]),
        ("A.\n\nB", [None, "paragraph", None, None]),
    ],
)
def test_boundary_clusters_contribute_at_most_one_pause(text, expected):
    units = tuple(typing_model.grapheme_clusters(text))
    assert [typing_model._boundary_for_gap(units, index) for index in range(len(units) - 1)] == expected


def test_timing_metadata_reports_realized_rate_only_when_defined():
    empty = build_typing_plan("", TypingOptions(human=True))
    one = build_typing_plan("a", TypingOptions(human=True))
    many = build_typing_plan(
        "abc", TypingOptions(human=True), _typing_random=random.Random(2)
    )
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
    assert all(math.isfinite(value) and 20 <= value <= 4000 for value in delays)
    rates = [plan.realized_wpm for plan in plans]
    assert statistics.fmean(rate for rate in rates if rate is not None) == pytest.approx(52, rel=0.08)


def test_long_plan_has_no_implicit_total_deadline():
    plan = build_typing_plan(
        "a" * 400,
        TypingOptions(human=True, wpm=65, iki_cv=0),
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


def test_checked_in_profile_names_redistributable_source_and_exact_deriver():
    root = Path(__file__).parents[2]
    profile = json.loads(
        (root / "computer_use/core/typing_profiles/us_adult_transcription_2026.json").read_text()
    )
    script = root / profile["derivation"]["path"]
    assert profile["residual_source"] == {
        "title": "KeyRecs: Keystroke Dynamics Dataset",
        "authors": [
            "Tiago Dias",
            "João Vitorino",
            "Eva Maia",
            "Orlando Sousa",
            "Isabel Praça",
        ],
        "doi": "10.5281/zenodo.7886743",
        "article_doi": "10.1016/j.dib.2023.109509",
        "file": "free-text.csv",
        "bytes": 25402938,
        "md5": "a5ca6fcb0970cfdcd8eb958b3fe9f22a",
        "sha256": "e38362914461c73a7ae6f25ac59304801f1324363d00ca00e059ac36e922c196",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }
    assert hashlib.sha256(script.read_bytes()).hexdigest() == profile["derivation"]["sha256"]
    assert profile["selected_model"] == "context_ar1"
    assert profile["validation"]["cleared"] is True
    assert profile["validation"]["hard_gates"] == {
        "clause_median_below_sentence_median": True,
        "finite_support": True,
        "ordinary_space_max_ms": 300.0,
        "ordinary_space_pause_probability": 0,
    }


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
