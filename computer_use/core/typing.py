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
from functools import cache
from importlib.resources import files
from typing import Protocol

from uniseg.graphemecluster import grapheme_clusters

from computer_use.core.typing_boundaries import classify_boundary_gaps, classify_gap
from computer_use.core.typing_profile import ArtifactInterpreter

DEFAULT_PROFILE = "us_adult_transcription_2026"
MIN_WPM = 10
MAX_WPM = 200
MAX_IKI_CV = 1.0
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
    _scheduled_ms_exact: float | None = None

    @property
    def _scheduled_duration_ms(self) -> float:
        if self._scheduled_ms_exact is None:
            return float(self.predicted_ms)
        return self._scheduled_ms_exact

    @property
    def fallback_units(self) -> int:
        return sum(unit.fallback for unit in self.units)

    @property
    def realized_wpm(self) -> float | None:
        scheduled_ms = self._scheduled_duration_ms
        if not self.human or len(self.units) < 2 or scheduled_ms <= 0:
            return None
        return 12_000.0 * (len(self.units) - 1) / scheduled_ms

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


@cache
def _profile_interpreter() -> ArtifactInterpreter:
    return ArtifactInterpreter(_load_profile())


def require_typing_deadline(plan: TypingPlan, remaining_ms: float) -> None:
    """Refuse a plan before mutation when the available time is insufficient."""
    if not math.isfinite(remaining_ms) or remaining_ms < 0:
        raise TypingDeadlineExceeded(0)
    if plan._scheduled_duration_ms > float(remaining_ms):
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
        if unit.delay_before_ms > MAX_TYPING_CHUNK_PLANNED_MS:
            raise ValueError("one typing unit exceeds the browser chunk duration limit")
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


def _context(first: str, second: str, boundary: str | None) -> str:
    return classify_gap(first, second, boundary)


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
    interpreter = _profile_interpreter()
    wpm = options.wpm or int(interpreter.profile["nominal_wpm"])
    iki_cv = options.iki_cv if profile is None else None
    units_text = tuple(grapheme_clusters(text))
    if len(units_text) < 2:
        units = tuple(
            TypingUnit(
                unit,
                0.0,
                fallback=not (
                    unit in {"\n", "\t"} or (len(unit) == 1 and 0x20 <= ord(unit) <= 0x7E)
                ),
            )
            for unit in units_text
        )
        return TypingPlan(True, profile, wpm, units, 0)
    boundaries = classify_boundary_gaps(units_text)
    classes = tuple(
        classify_gap(units_text[index], units_text[index + 1], boundaries[index])
        for index in range(len(units_text) - 1)
    )
    intervals = [
        sample.total_ms for sample in interpreter.simulate(classes, wpm, source, iki_cv=iki_cv)
    ]

    units = tuple(
        TypingUnit(
            unit,
            0.0 if index == 0 else intervals[index - 1],
            fallback=not (unit in {"\n", "\t"} or (len(unit) == 1 and 0x20 <= ord(unit) <= 0x7E)),
        )
        for index, unit in enumerate(units_text)
    )
    scheduled_ms_exact = math.fsum(intervals)
    return TypingPlan(
        True,
        profile,
        wpm,
        units,
        math.ceil(scheduled_ms_exact),
        scheduled_ms_exact,
    )
