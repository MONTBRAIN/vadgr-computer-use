# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""One validated timing plan for browser and pixel text input."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

DEFAULT_PROFILE = "us_adult_transcription_2026"
MIN_WPM = 10
MAX_WPM = 200
MAX_INTERVAL_MS = 1500.0
MIN_INTERVAL_MS = 20.0
MAX_TYPING_DURATION_MS = 45_000


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class TypingOptions:
    human: bool = False
    timing_profile: str | None = None
    wpm: int | None = None
    iki_cv: float | None = None


@dataclass(frozen=True)
class TypingUnit:
    text: str
    delay_before_ms: float
    fallback: bool = False


@dataclass(frozen=True)
class TypingPlan:
    human: bool
    timing_profile: str | None
    nominal_wpm: int | None
    units: tuple[TypingUnit, ...]
    predicted_ms: int

    @property
    def fallback_units(self) -> int:
        return sum(unit.fallback for unit in self.units)

    def metadata(self, *, elapsed_ms: int | None = None) -> dict[str, object]:
        result: dict[str, object] = {
            "human": self.human,
            "timing_profile": self.timing_profile,
            "nominal_wpm": self.nominal_wpm,
            "units": len(self.units),
            "fallback_units": self.fallback_units,
            "predicted_ms": self.predicted_ms,
        }
        if elapsed_ms is not None:
            result["elapsed_ms"] = elapsed_ms
        return result


class TypingCancelled(RuntimeError):
    """Human-paced input stopped between complete input units."""

    def __init__(self, completed_units: int):
        super().__init__(f"typing_cancelled: {completed_units} complete units")
        self.completed_units = completed_units


def _load_profile() -> dict[str, object]:
    resource = files("computer_use.core").joinpath("typing_profiles", f"{DEFAULT_PROFILE}.json")
    return json.loads(resource.read_text(encoding="utf-8"))


_PROFILE = _load_profile()
_EMPIRICAL_QUANTILES = {
    name: tuple(float(value) for value in values)
    for name, values in dict(_PROFILE["residual_quantiles"]).items()
}


def require_typing_deadline(plan: TypingPlan, remaining_ms: float) -> None:
    """Refuse a plan before mutation when the available time is insufficient."""
    if not math.isfinite(remaining_ms) or remaining_ms < 0:
        raise ValueError("typing_deadline_exceeded")
    if plan.predicted_ms > min(float(remaining_ms), MAX_TYPING_DURATION_MS):
        raise ValueError("typing_deadline_exceeded")


def validate_typing_options(options: TypingOptions) -> None:
    """Reject invalid combinations before a caller changes focus or input."""
    if not options.human:
        if (
            options.timing_profile is not None
            or options.wpm is not None
            or options.iki_cv is not None
        ):
            raise ValueError("typing_options_require_human")
        return
    if options.timing_profile is not None and (
        options.wpm is not None or options.iki_cv is not None
    ):
        raise ValueError("timing_profile and custom timing are mutually exclusive")
    if (options.wpm is None) != (options.iki_cv is None):
        raise ValueError("custom timing requires both wpm and iki_cv")
    if options.timing_profile not in (None, DEFAULT_PROFILE):
        raise ValueError(f"unsupported timing profile {options.timing_profile!r}")
    if options.wpm is not None:
        if isinstance(options.wpm, bool) or not isinstance(options.wpm, int):
            raise ValueError("wpm must be an integer")
        if not MIN_WPM <= options.wpm <= MAX_WPM:
            raise ValueError(f"wpm must be from {MIN_WPM} through {MAX_WPM}")
        assert options.iki_cv is not None
        if not math.isfinite(options.iki_cv) or options.iki_cv < 0:
            raise ValueError("iki_cv must be finite and greater than or equal to zero")


def _sample_quantiles(values: tuple[float, ...], rng: RandomSource) -> float:
    position = min(max(rng.random(), 0.0), math.nextafter(1.0, 0.0)) * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _log_logistic_beta(cv: float) -> float:
    """Solve the supported log-logistic CV equation for beta greater than two."""
    if cv == 0:
        return math.inf

    def candidate(beta: float) -> float:
        t = math.pi / beta
        first = 2 * t / math.sin(2 * t)
        second = (t / math.sin(t)) ** 2
        return math.sqrt(max(first / second - 1, 0.0))

    low, high = 2.000001, 1_000_000.0
    for _ in range(100):
        mid = (low + high) / 2
        if candidate(mid) > cv:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _custom_residual(cv: float, rng: RandomSource) -> float:
    if cv == 0:
        return 1.0
    beta = _log_logistic_beta(cv)
    u = min(max(rng.random(), 1e-12), 1 - 1e-12)
    raw = (u / (1 - u)) ** (1 / beta)
    mean = (math.pi / beta) / math.sin(math.pi / beta)
    return raw / mean


def _bucket(previous: str) -> str:
    if previous in ".?!":
        return "sentence"
    if previous.isspace():
        return "word"
    return "within"


def build_typing_plan(
    text: str,
    options: TypingOptions,
    *,
    rng: RandomSource | None = None,
) -> TypingPlan:
    """Build the complete schedule without sleeping or changing input state."""
    validate_typing_options(options)
    if not options.human:
        return TypingPlan(False, None, None, (TypingUnit(text, 0.0),), 0)
    source = rng or random.SystemRandom()
    profile = options.timing_profile or (DEFAULT_PROFILE if options.wpm is None else None)
    wpm = options.wpm or 38
    mean_ms = 12_000.0 / wpm
    raw: list[float] = []
    for index in range(1, len(text)):
        if profile is not None:
            residual = _sample_quantiles(_EMPIRICAL_QUANTILES[_bucket(text[index - 1])], source)
        else:
            assert options.iki_cv is not None
            residual = _custom_residual(options.iki_cv, source)
        raw.append(min(MAX_INTERVAL_MS, max(MIN_INTERVAL_MS, mean_ms * residual)))
    target = mean_ms * max(len(text) - 1, 0)
    if raw:
        scale = target / sum(raw)
        intervals = [min(MAX_INTERVAL_MS, max(MIN_INTERVAL_MS, value * scale)) for value in raw]
        # Safety bounds can disturb the first normalization. Normalize the free
        # residual once more without exceeding the documented bounds.
        remaining = target - sum(intervals)
        free = [i for i, value in enumerate(intervals) if MIN_INTERVAL_MS < value < MAX_INTERVAL_MS]
        if free and abs(remaining) > 0.01:
            step = remaining / len(free)
            for i in free:
                intervals[i] = min(MAX_INTERVAL_MS, max(MIN_INTERVAL_MS, intervals[i] + step))
    else:
        intervals = []
    units = tuple(
        TypingUnit(char, 0.0 if index == 0 else intervals[index - 1])
        for index, char in enumerate(text)
    )
    return TypingPlan(True, profile, wpm, units, round(sum(intervals)))
