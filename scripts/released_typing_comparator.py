# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Frozen a4a5b298 schema-1 fitter and runtime comparator."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

QUANTILE_PROBABILITIES = tuple(index / 100 for index in range(101))
MIN_INTERVAL_MS = 20.0
MAX_INTERVAL_MS = 1500.0


@dataclass(frozen=True)
class ReleasedGap:
    participant: str
    session: str
    first: str
    second: str
    interval_ms: float


def _character(key: str) -> str | None:
    if key == "Space":
        return " "
    return key if len(key) == 1 and key.isprintable() else None


def _bucket(previous: str) -> str:
    if previous in ".?!":
        return "sentence"
    if previous.isspace():
        return "word"
    return "within"


def read(path: Path) -> tuple[tuple[ReleasedGap, ...], int]:
    """Apply the released reader without candidate filtering or segmentation."""
    rows = []
    rejected = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        for record in csv.DictReader(source):
            participant = str(record.get("participant", ""))
            session = str(record.get("session", ""))
            first = _character(str(record.get("key1", "")))
            second = _character(str(record.get("key2", "")))
            try:
                interval_ms = float(record.get("DD.key1.key2", "")) * 1000
            except (TypeError, ValueError):
                interval_ms = -1
            if (
                not participant.startswith("p")
                or session not in {"1", "2"}
                or first is None
                or second is None
                or not 0 < interval_ms <= MAX_INTERVAL_MS
            ):
                rejected += 1
                continue
            rows.append(ReleasedGap(participant, session, first, second, interval_ms))
    return tuple(rows), rejected


def _weighted_quantiles(values: Sequence[tuple[float, float]]) -> list[float]:
    ordered = sorted(values)
    total = sum(weight for _, weight in ordered)
    targets = [probability * total for probability in QUANTILE_PROBABILITIES]
    result = []
    cumulative = 0.0
    target_index = 0
    for value, weight in ordered:
        cumulative += weight
        while target_index < len(targets) and cumulative >= targets[target_index]:
            result.append(value)
            target_index += 1
    result.extend([ordered[-1][0]] * (len(targets) - len(result)))
    return result


def fit(rows: Sequence[ReleasedGap], participants: set[str]) -> dict[str, object]:
    """Refit the released equal-participant/session/context empirical laws."""
    raw_sessions: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if row.participant in participants:
            raw_sessions[(row.participant, row.session)].append(
                (_bucket(row.first), row.interval_ms)
            )

    grouped: dict[str, list[dict[str, list[float]]]] = defaultdict(list)
    for (participant, _), intervals in raw_sessions.items():
        mean = sum(value for _, value in intervals) / len(intervals)
        normalized: dict[str, list[float]] = defaultdict(list)
        for bucket, value in intervals:
            normalized[bucket].append(value / mean)
        grouped[participant].append(dict(normalized))

    quantiles = {}
    counts = {}
    for bucket in ("within", "word", "sentence"):
        weighted = []
        participant_count = session_count = interval_count = 0
        for sessions in grouped.values():
            eligible = [session[bucket] for session in sessions if session.get(bucket)]
            if not eligible:
                continue
            participant_count += 1
            session_count += len(eligible)
            interval_count += sum(len(values) for values in eligible)
            for values in eligible:
                weight = 1.0 / len(eligible) / len(values)
                weighted.extend((value, weight) for value in values)
        if not weighted:
            raise ValueError(f"released comparator has no {bucket} observations")
        quantiles[bucket] = [round(value, 6) for value in _weighted_quantiles(weighted)]
        counts[bucket] = {
            "participants": participant_count,
            "sessions": session_count,
            "intervals": interval_count,
        }
    return {
        "schema": 1,
        "nominal_wpm": 65,
        "residual_quantiles": quantiles,
        "counts": counts,
    }


def _sample_quantiles(values: Sequence[float], random: np.random.Generator) -> float:
    position = min(max(float(random.random()), 0.0), math.nextafter(1.0, 0.0)) * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return float(values[lower]) + (float(values[upper]) - float(values[lower])) * fraction


def simulate_once(
    rows: Sequence[object],
    model: Mapping[str, object],
    random: np.random.Generator,
    wpm: float = 65.0,
) -> np.ndarray:
    """Run the released generator, including complete-message normalization."""
    mean_ms = 12_000.0 / wpm
    laws = model["residual_quantiles"]
    raw = [
        min(
            MAX_INTERVAL_MS,
            max(
                MIN_INTERVAL_MS,
                mean_ms * _sample_quantiles(laws[_bucket(str(row.first))], random),
            ),
        )
        for row in rows
    ]
    target = mean_ms * len(rows)
    if not raw:
        return np.asarray([])
    scale = target / sum(raw)
    intervals = [min(MAX_INTERVAL_MS, max(MIN_INTERVAL_MS, value * scale)) for value in raw]
    remaining = target - sum(intervals)
    free = [
        index for index, value in enumerate(intervals) if MIN_INTERVAL_MS < value < MAX_INTERVAL_MS
    ]
    if free and abs(remaining) > 0.01:
        step = remaining / len(free)
        for index in free:
            intervals[index] = min(
                MAX_INTERVAL_MS,
                max(MIN_INTERVAL_MS, intervals[index] + step),
            )
    return np.asarray(intervals)


__all__ = ["ReleasedGap", "fit", "read", "simulate_once"]
