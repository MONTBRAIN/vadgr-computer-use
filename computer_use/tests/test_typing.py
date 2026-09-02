import hashlib
import json
import math
import random
from pathlib import Path

import pytest

from computer_use.core.typing import (
    DEFAULT_PROFILE,
    TypingCancelled,
    TypingOptions,
    build_typing_plan,
    validate_typing_options,
)


def test_cancellation_error_reports_only_completed_unit_count():
    error = TypingCancelled(3)
    assert str(error) == "typing_cancelled: 3 complete units"
    assert error.completed_units == 3


def test_fast_plan_preserves_one_bulk_unit():
    plan = build_typing_plan("secret text", TypingOptions())
    assert [unit.text for unit in plan.units] == ["secret text"]
    assert plan.predicted_ms == 0
    assert plan.human is False


def test_named_profile_is_deterministic_with_injected_random_source():
    one = build_typing_plan("one two. Three", TypingOptions(human=True), rng=random.Random(7))
    two = build_typing_plan("one two. Three", TypingOptions(human=True), rng=random.Random(7))
    assert one == two
    assert one.timing_profile == DEFAULT_PROFILE
    assert one.nominal_wpm == 38
    assert len({round(unit.delay_before_ms, 3) for unit in one.units[1:]}) > 1


def test_human_plan_marks_non_ascii_units_as_insertion_fallback():
    plan = build_typing_plan("Aé🙂\n", TypingOptions(human=True), rng=random.Random(7))
    assert [unit.fallback for unit in plan.units] == [False, True, True, False]
    assert plan.fallback_units == 2


def test_custom_zero_cv_is_constant_control():
    plan = build_typing_plan(
        "abcdef", TypingOptions(human=True, wpm=60, iki_cv=0), rng=random.Random(1)
    )
    assert {round(unit.delay_before_ms, 6) for unit in plan.units[1:]} == {200.0}


def test_custom_plan_has_requested_duration_and_finite_bounds():
    plan = build_typing_plan(
        "a" * 1000, TypingOptions(human=True, wpm=52, iki_cv=0.3), rng=random.Random(9)
    )
    delays = [unit.delay_before_ms for unit in plan.units[1:]]
    assert all(math.isfinite(value) and 20 <= value <= 1500 for value in delays)
    expected = 12_000 / 52 * 999
    assert sum(delays) == pytest.approx(expected, rel=0.01)


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


@pytest.mark.parametrize(
    "options",
    [
        TypingOptions(wpm=50),
        TypingOptions(human=True, wpm=50),
        TypingOptions(human=True, iki_cv=0.2),
        TypingOptions(human=True, wpm=9, iki_cv=0.2),
        TypingOptions(human=True, wpm=201, iki_cv=0.2),
        TypingOptions(human=True, wpm=50, iki_cv=-0.1),
        TypingOptions(human=True, timing_profile="unknown"),
        TypingOptions(human=True, timing_profile=DEFAULT_PROFILE, wpm=50, iki_cv=0.2),
    ],
)
def test_invalid_options_fail_before_dispatch(options):
    with pytest.raises(ValueError):
        validate_typing_options(options)
