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
from functools import lru_cache
from importlib.resources import files
from statistics import NormalDist
from typing import Protocol

from uniseg.graphemecluster import grapheme_clusters

DEFAULT_PROFILE = "us_adult_transcription_2026"
MIN_WPM = 10
MAX_WPM = 200
MAX_IKI_CV = 1.0
MAX_INTERVAL_MS = 1500.0
MAX_CUSTOM_INTERVAL_MS = 4000.0
MIN_INTERVAL_MS = 20.0
ORDINARY_SPACE_MAX_MS = 300.0
MAX_TYPING_CHUNK_UNITS = 256
MAX_TYPING_CHUNK_PLANNED_MS = 5_000.0
MAX_TYPING_CHUNK_BYTES = 256 * 1024


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

    @property
    def realized_wpm(self) -> float | None:
        if not self.human or len(self.units) < 2 or self.predicted_ms <= 0:
            return None
        return 12_000.0 * (len(self.units) - 1) / self.predicted_ms

    def metadata(self, *, elapsed_ms: int | None = None) -> dict[str, object]:
        result: dict[str, object] = {
            "human": self.human,
            "timing_profile": self.timing_profile,
            "nominal_wpm": self.nominal_wpm,
            "units": len(self.units),
            "fallback_units": self.fallback_units,
            "predicted_ms": self.predicted_ms,
            "realized_wpm": self.realized_wpm,
        }
        if elapsed_ms is not None:
            result["elapsed_ms"] = elapsed_ms
        return result


class TypingCancelled(RuntimeError):
    """Human-paced input stopped between complete input units."""

    def __init__(self, completed_units: int):
        super().__init__(f"typing_cancelled: {completed_units} complete units")
        self.completed_units = completed_units


class TypingDeadlineExceeded(RuntimeError):
    """Human-paced input exhausted an explicit caller deadline."""

    def __init__(self, completed_units: int):
        super().__init__(f"typing_deadline_exceeded: {completed_units} complete units")
        self.completed_units = completed_units


def _load_profile() -> dict[str, object]:
    resource = files("computer_use.core").joinpath("typing_profiles", f"{DEFAULT_PROFILE}.json")
    return json.loads(resource.read_text(encoding="utf-8"))


_PROFILE = _load_profile()
_LIMITS = dict(_PROFILE["limits"])
_MOTOR = dict(_PROFILE["motor"])
_STYLES = tuple(dict(style) for style in _PROFILE["styles"])
_BOUNDARIES = {
    name: dict(model) for name, model in dict(_PROFILE["boundaries"]).items()
}
_BOUNDARY_WEIGHTS = {
    name: float(weight)
    for name, weight in dict(_PROFILE["reference_boundary_weights"]).items()
}
_CONTEXT_EFFECTS = {
    name: float(value) for name, value in dict(_MOTOR["context_log_effects"]).items()
}
_CONTEXT_WEIGHTS = {
    name: float(value) for name, value in dict(_MOTOR["reference_context_weights"]).items()
}
_INNOVATION_QUANTILES = tuple(float(value) for value in _MOTOR["innovation_quantiles"])
_INNOVATION_LOG_SCALE = float(_MOTOR["innovation_log_scale"])

_KEYS = {
    **{key: value for key, value in zip("12345", ((0, "L", i) for i in range(5)))},
    **{key: value for key, value in zip("67890", ((0, "R", i) for i in range(5)))},
    **{key: value for key, value in zip("qwert", ((1, "L", i) for i in range(5)))},
    **{key: value for key, value in zip("yuiop", ((1, "R", i) for i in range(5)))},
    **{key: value for key, value in zip("asdfg", ((2, "L", i) for i in range(5)))},
    **{key: value for key, value in zip("hjkl;", ((2, "R", i) for i in range(5)))},
    **{key: value for key, value in zip("zxcvb", ((3, "L", i) for i in range(5)))},
    **{key: value for key, value in zip("nm,./", ((3, "R", i) for i in range(5)))},
}


def require_typing_deadline(plan: TypingPlan, remaining_ms: float) -> None:
    """Refuse a plan before mutation when the available time is insufficient."""
    if not math.isfinite(remaining_ms) or remaining_ms < 0:
        raise TypingDeadlineExceeded(0)
    if plan.predicted_ms > float(remaining_ms):
        raise TypingDeadlineExceeded(0)


def _typing_unit_wire_size(unit: TypingUnit) -> int:
    return len(
        json.dumps(
            {
                "text": unit.text,
                "delay_before_ms": unit.delay_before_ms,
                "fallback": unit.fallback,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def chunk_typing_plan(plan: TypingPlan) -> tuple[tuple[TypingUnit, ...], ...]:
    """Split a human plan into bounded native-message progress units."""
    chunks: list[tuple[TypingUnit, ...]] = []
    current: list[TypingUnit] = []
    planned_ms = 0.0
    wire_bytes = 2
    for unit in plan.units:
        unit_bytes = _typing_unit_wire_size(unit)
        added_bytes = unit_bytes + int(bool(current))
        if unit_bytes + 2 > MAX_TYPING_CHUNK_BYTES:
            raise ValueError("one typing unit exceeds the browser chunk byte limit")
        if current and (
            len(current) >= MAX_TYPING_CHUNK_UNITS
            or planned_ms + unit.delay_before_ms > MAX_TYPING_CHUNK_PLANNED_MS
            or wire_bytes + added_bytes > MAX_TYPING_CHUNK_BYTES
        ):
            chunks.append(tuple(current))
            current = []
            planned_ms = 0.0
            wire_bytes = 2
            added_bytes = unit_bytes
        current.append(unit)
        planned_ms += unit.delay_before_ms
        wire_bytes += added_bytes
    if current:
        chunks.append(tuple(current))
    return tuple(chunks)


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
        if not math.isfinite(options.iki_cv) or not 0 <= options.iki_cv <= MAX_IKI_CV:
            raise ValueError(f"iki_cv must be finite and from 0 through {MAX_IKI_CV:g}")


def _sample_quantiles(values: tuple[float, ...], rng: RandomSource) -> float:
    position = min(max(rng.random(), 0.0), math.nextafter(1.0, 0.0)) * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _normal_quantile(rng: RandomSource) -> float:
    probability = min(max(rng.random(), 1e-9), 1 - 1e-9)
    return NormalDist().inv_cdf(probability)


def _context(first: str, second: str, boundary: str | None) -> str:
    if first == " " or second == " ":
        return "ordinary_space"
    left = _KEYS.get(first.lower())
    right = _KEYS.get(second.lower())
    if left is None or right is None:
        return "other"
    if first.lower() == second.lower():
        return "same_key"
    if left[1:] == right[1:]:
        return "same_finger"
    if left[1] == right[1]:
        return "same_hand"
    return "alternate_hand"


_BOUNDARY_MARKS = frozenset(".,;:?!\n\r\t ")


def _boundary_for_gap(units: tuple[str, ...], index: int) -> str | None:
    first = units[index]
    if first not in ".,;:?!\n\r":
        return None
    cursor = index - 1
    while cursor >= 0 and all(char in _BOUNDARY_MARKS for char in units[cursor]):
        if any(char in ".,;:?!\n\r" for char in units[cursor]):
            return None
        cursor -= 1
    cluster: list[str] = []
    cursor = index
    while cursor < len(units) and all(char in _BOUNDARY_MARKS for char in units[cursor]):
        cluster.append(units[cursor])
        cursor += 1
    joined = "".join(cluster)
    if "\n\n" in joined or "\r\n\r\n" in joined:
        return "paragraph"
    if "\n" in joined or "\r" in joined:
        return "newline"
    if any(char in joined for char in ".?!"):
        return "sentence"
    return "clause"


_CALIBRATION_PROBABILITIES = tuple(index / 100 for index in range(2, 100, 4))


@lru_cache(maxsize=512)
def _style_stationary_quantiles(style_index: int, iki_cv: float | None) -> tuple[float, ...]:
    style = _STYLES[style_index]
    if iki_cv is not None:
        if iki_cv == 0:
            return (1.0,) * len(_CALIBRATION_PROBABILITIES)
        sigma = math.sqrt(math.log1p(iki_cv * iki_cv))
        return tuple(
            math.exp(sigma * NormalDist().inv_cdf(probability) - sigma * sigma / 2)
            for probability in _CALIBRATION_PROBABILITIES
        )
    phi = float(style["persistence"])
    scale = _INNOVATION_LOG_SCALE * float(style["innovation_scale"])
    stationary_scale = scale / math.sqrt(max(1 - phi * phi, 0.01))
    return tuple(
        math.exp(stationary_scale * _sample_quantiles(_INNOVATION_QUANTILES, _FixedRandom(probability)))
        for probability in _CALIBRATION_PROBABILITIES
    )


class _FixedRandom:
    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


@lru_cache(maxsize=None)
def _mean_pause_ms(style_index: int) -> float:
    style = _STYLES[style_index]
    total = 0.0
    boundary_scale = float(style["boundary_scale"])
    for name, weight in _BOUNDARY_WEIGHTS.items():
        model = _BOUNDARIES[name]
        probability = min(float(model["probability"]) * boundary_scale, 1.0)
        pauses = [math.exp(float(value)) for value in model["log_pause_quantiles"]]
        total += weight * probability * (sum(pauses) / len(pauses))
    return total


def _expected_gap_ms(
    style_index: int, scale_ms: float, iki_cv: float | None
) -> float:
    style = _STYLES[style_index]
    speed = 0.0 if iki_cv is not None else float(style["speed_log"])
    residuals = _style_stationary_quantiles(style_index, iki_cv)

    def context_mean(name: str) -> float:
        upper = (
            ORDINARY_SPACE_MAX_MS
            if name == "ordinary_space"
            else MAX_CUSTOM_INTERVAL_MS if iki_cv is not None else MAX_INTERVAL_MS
        )
        effect = math.exp(speed + _CONTEXT_EFFECTS[name])
        values = [min(upper, max(MIN_INTERVAL_MS, scale_ms * effect * value)) for value in residuals]
        return sum(values) / len(values)

    motor = sum(weight * context_mean(name) for name, weight in _CONTEXT_WEIGHTS.items())
    motor += sum(
        float(weight) * context_mean(name)
        for name, weight in dict(_MOTOR["reference_boundary_context_weights"]).items()
    )
    return motor + _mean_pause_ms(style_index)


@lru_cache(maxsize=256)
def _calibrated_scale_ms(wpm: int, iki_cv: float | None) -> float:
    def population_rate(scale_ms: float) -> float:
        rates = [
            12_000.0 / _expected_gap_ms(index, scale_ms, iki_cv)
            for index in range(len(_STYLES))
        ]
        return sum(rates) / len(rates)

    low, high = 0.01, 10_000.0
    if not population_rate(low) >= wpm >= population_rate(high):
        raise ValueError("requested typing rate is outside the validated timing support")
    for _ in range(48):
        middle = (low + high) / 2
        if population_rate(middle) > wpm:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _sample_style(rng: RandomSource) -> dict[str, object]:
    position = min(int(rng.random() * len(_STYLES)), len(_STYLES) - 1)
    return _STYLES[position]


def _sample_pause(boundary: str | None, style: dict[str, object], rng: RandomSource) -> float:
    if boundary is None:
        return 0.0
    model = _BOUNDARIES[boundary]
    probability = min(float(model["probability"]) * float(style["boundary_scale"]), 1.0)
    if rng.random() >= probability:
        return 0.0
    values = tuple(float(value) for value in model["log_pause_quantiles"])
    return math.exp(_sample_quantiles(values, rng))


def build_typing_plan(
    text: str,
    options: TypingOptions,
    *,
    _typing_random: RandomSource | None = None,
) -> TypingPlan:
    """Build the complete schedule without sleeping or changing input state."""
    validate_typing_options(options)
    if not options.human:
        return TypingPlan(False, None, None, (TypingUnit(text, 0.0),), 0)
    source = _typing_random or random.SystemRandom()
    profile = options.timing_profile or (DEFAULT_PROFILE if options.wpm is None else None)
    wpm = options.wpm or int(_PROFILE["nominal_wpm"])
    iki_cv = options.iki_cv if profile is None else None
    units_text = tuple(grapheme_clusters(text))
    if len(units_text) < 2:
        units = tuple(
            TypingUnit(
                unit,
                0.0,
                fallback=not (
                    unit in {"\n", "\t"}
                    or (len(unit) == 1 and 0x20 <= ord(unit) <= 0x7E)
                ),
            )
            for unit in units_text
        )
        return TypingPlan(True, profile, wpm, units, 0)
    style = _sample_style(source)
    scale_ms = _calibrated_scale_ms(wpm, iki_cv)
    phi = float(style["persistence"])
    if iki_cv is None:
        innovation_scale = _INNOVATION_LOG_SCALE * float(style["innovation_scale"])
        latent = (
            innovation_scale
            * _sample_quantiles(_INNOVATION_QUANTILES, source)
            / math.sqrt(max(1 - phi * phi, 0.01))
        )
        speed = float(style["speed_log"])
    else:
        sigma = math.sqrt(math.log1p(iki_cv * iki_cv))
        innovation_scale = sigma * math.sqrt(max(1 - phi * phi, 0.0))
        latent = sigma * _normal_quantile(source) if sigma else 0.0
        speed = 0.0
    intervals: list[float] = []
    for index in range(len(units_text) - 1):
        if index:
            if iki_cv is None:
                innovation = innovation_scale * _sample_quantiles(
                    _INNOVATION_QUANTILES, source
                )
            else:
                innovation = innovation_scale * _normal_quantile(source) if innovation_scale else 0.0
            latent = phi * latent + innovation
        boundary = _boundary_for_gap(units_text, index)
        context = _context(units_text[index], units_text[index + 1], boundary)
        motor_upper = (
            ORDINARY_SPACE_MAX_MS
            if context == "ordinary_space"
            else MAX_CUSTOM_INTERVAL_MS if iki_cv is not None else MAX_INTERVAL_MS
        )
        motor = scale_ms * math.exp(speed + _CONTEXT_EFFECTS[context] + latent)
        motor = min(motor_upper, max(MIN_INTERVAL_MS, motor))
        pause = _sample_pause(boundary, style, source)
        intervals.append(motor + pause)

    units = tuple(
        TypingUnit(
            unit,
            0.0 if index == 0 else intervals[index - 1],
            fallback=not (
                unit in {"\n", "\t"}
                or (len(unit) == 1 and 0x20 <= ord(unit) <= 0x7E)
            ),
        )
        for index, unit in enumerate(units_text)
    )
    return TypingPlan(True, profile, wpm, units, round(sum(intervals)))
