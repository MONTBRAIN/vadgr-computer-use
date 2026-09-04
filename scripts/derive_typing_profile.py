#!/usr/bin/env python3
# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Derive and confirm the checked-in observable-context typing profile."""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import inspect
import io
import json
import math
import platform
import re
import statistics
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from computer_use.core.typing_boundaries import classify_boundary_gaps, classify_gap
from computer_use.core.typing_profile import CLASSES, ArtifactInterpreter
from scripts import released_typing_comparator as released_comparator

KEYRECS_SHA256 = "e38362914461c73a7ae6f25ac59304801f1324363d00ca00e059ac36e922c196"
KEYRECS_MD5 = "a5ca6fcb0970cfdcd8eb958b3fe9f22a"
SKAID_SHA256 = "5e84c19209df891b88e8de600f171511e9af370be2de903d85353bd0b2c19eda"
SKAID_MD5 = "b14e1817c552e8bffe1b18afaa9d3b90"
SKAID_README_SHA256 = "c51f24e74879a79f36d37e3da56ce7e79a23a5b83b227a5b2948c66f960b93e3"
SKAID_DOI = "10.5281/zenodo.17282184"
SKAID_VERSION = "1.0"
SKAID_DEMOGRAPHICS_SHA256 = "5dcc02ad315d01f91563a9434a856d198b9f52a1d26036b940cd332e0f047569"
SKAID_DEMOGRAPHICS_MD5 = "8a3fdb18d7ca72defa0ce6e39d85e4a1"
RELEASED_BASELINE_COMMIT = "a4a5b298b90c005063a41db6210fa07fb3c62dfa"
RELEASED_PROFILE_SHA256 = "78f278bb4a1233b37a0c3fcd20aaab68da01675e541fdfc7ce60dc19e0d239c5"
PROFILE_PATH = ROOT / "computer_use/core/typing_profiles/us_adult_transcription_2026.json"

QUANTILE_PROBABILITIES = tuple(index / 100 for index in range(101))
SHRINKAGE_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
RANK_TRANSITION_ALPHA_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
PILOT_COUNTS = (256, 512, 1024, 2048)
PILOT_BLOCKS = 4
OUTER_FOLDS = 5
INNER_FOLDS = 4
BOOTSTRAP_SAMPLES = 2_000
SEED = 760_2026
CALIBRATION_RATE_TOLERANCE_WPM = 1e-9
MIN_INTERVAL_MS = 20.0
RELEASED_MAX_INTERVAL_MS = 1500.0
MAX_TOTAL_GAP_MS = 5000.0
SPACE_MAX_MS = 1500.0
MIN_VALIDATION_GRAPHEMES = 200
SKAID_SOURCE_PARTICIPANTS = 27
SKAID_CONFIRMATION_PARTICIPANTS = 25
SKAID_CONFIRMATION_PHASES = 50
SECONDARY_MARGINS = {
    "three_quantile_error": 0.01,
    "lag_one_correlation_error": 0.01,
    "rank_run_error": 0.005,
    "population_wpm_crps": 0.0,
    "expected_wpm_relative_error": 0.02,
}
BOUNDARY_MARGINS = {"crps": 0.01, "three_quantile_error": 0.01}
SEQUENCE_ENERGY_NONINFERIORITY_MARGIN = 0.10
EPSILON = 1e-12
RELEASED_PARENTS = {
    "same_key": "within",
    "same_finger": "within",
    "same_hand": "within",
    "alternate_hand": "within",
    "other": "within",
    "ordinary_space": "word",
    "clause": "within",
    "sentence": "sentence",
}
RELEASED_CLASS_ALIASES = {
    **RELEASED_PARENTS,
    "newline": "word",
    "paragraph": "word",
}
MODEL_LADDER = (
    "context_parent",
    "observable_context",
    "observable_context_rank4",
)


@dataclass(frozen=True)
class Gap:
    participant: str
    session: str
    order: int
    segment: int
    first: str
    second: str
    interval_ms: float
    gap_class: str


@dataclass(frozen=True)
class PreparedKeyRecs:
    gaps: tuple[Gap, ...]
    comparator_rows: tuple[object, ...]
    participants: tuple[str, ...]
    session_centers: Mapping[tuple[str, str], float]
    rejected_rows: int


@dataclass(frozen=True)
class SkaidDataset:
    gaps: tuple[Gap, ...]
    source_participant_count: int
    participant_count: int
    phase_counts: Mapping[str, int]
    file_manifest: tuple[Mapping[str, object], ...]
    exact_segment_reconstruction: bool
    session_ids: tuple[str, ...]
    demographics_manifest: Mapping[str, object] | None
    identity_manifest: tuple[Mapping[str, str], ...]
    alignment_manifest: tuple[Mapping[str, object], ...]
    exclusion_reasons: Mapping[str, int]


@dataclass(frozen=True)
class _Press:
    key: str
    character: str
    timestamp_ms: float
    row: int
    segment: int
    released: bool = False


@dataclass(frozen=True)
class _PhaseImport:
    gaps: tuple[Gap, ...]
    next_segment: int
    diagnostics: Mapping[str, object]


def _hash(path: Path, name: str) -> str:
    digest = hashlib.new(name)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _byte_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _keyrecs_character(key: str) -> str | None:
    if key == "Space":
        return " "
    if key in {"Enter", "Return"}:
        return "\n"
    return key if len(key) == 1 and key.isprintable() else None


def _classify_segment(rows: Sequence[Gap], segment: int) -> list[Gap]:
    units = (rows[0].first, *(row.second for row in rows))
    boundaries = classify_boundary_gaps(units)
    result = []
    for row, boundary in zip(rows, boundaries):
        gap_class = classify_gap(row.first, row.second, boundary)
        result.append(replace(row, segment=segment, gap_class=gap_class))
    return result


def _read_keyrecs(path: Path) -> tuple[list[Gap], int]:
    """Read only valid contiguous KeyRecs total gaps."""
    raw: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    row_order: dict[tuple[str, str], int] = defaultdict(int)
    rejected = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"participant", "session", "key1", "key2", "DD.key1.key2"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("KeyRecs columns are invalid")
        for record in reader:
            participant = str(record.get("participant", ""))
            session = str(record.get("session", ""))
            key = participant, session
            order = row_order[key]
            row_order[key] += 1
            first = _keyrecs_character(str(record.get("key1", "")))
            second = _keyrecs_character(str(record.get("key2", "")))
            try:
                interval_ms = float(record.get("DD.key1.key2", "")) * 1000.0
            except (TypeError, ValueError):
                interval_ms = math.nan
            if (
                not re.fullmatch(r"p\d+", participant)
                or session not in {"1", "2"}
                or first is None
                or second is None
                or not math.isfinite(interval_ms)
                or not MIN_INTERVAL_MS <= interval_ms <= RELEASED_MAX_INTERVAL_MS
            ):
                rejected += 1
                continue
            raw[key].append(
                Gap(participant, session, order, -1, first, second, interval_ms, "other")
            )

    result: list[Gap] = []
    segment = 0
    for key in sorted(raw):
        rows = sorted(raw[key], key=lambda row: row.order)
        current: list[Gap] = []
        for row in rows:
            if current and (row.order != current[-1].order + 1 or row.first != current[-1].second):
                result.extend(_classify_segment(current, segment))
                segment += 1
                current = []
            current.append(row)
        if current:
            result.extend(_classify_segment(current, segment))
            segment += 1
    return result, rejected


def _prepare_keyrecs(
    gaps: Sequence[Gap],
    rejected_rows: int,
    comparator_rows: Sequence[object] | None = None,
) -> PreparedKeyRecs:
    source_rows = tuple(gaps if comparator_rows is None else comparator_rows)
    sessions: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in source_rows:
        sessions[(str(row.participant), str(row.session))].append(float(row.interval_ms))
    centers = {key: statistics.fmean(values) for key, values in sessions.items()}
    retained = tuple(gap for gap in gaps if (gap.participant, gap.session) in centers)
    participants = tuple(sorted({gap.participant for gap in retained}))
    if len(participants) < OUTER_FOLDS:
        raise ValueError("KeyRecs has too few retained participants")
    return PreparedKeyRecs(
        retained,
        source_rows,
        participants,
        centers,
        rejected_rows,
    )


def _group_folds(participants: Sequence[str], count: int, seed: int) -> list[tuple[str, ...]]:
    values = sorted(participants)
    np.random.default_rng(seed).shuffle(values)
    return [tuple(values[index::count]) for index in range(count)]


def _weighted_quantiles(
    values: Sequence[tuple[float, float]],
    probabilities: Sequence[float] = QUANTILE_PROBABILITIES,
) -> tuple[float, ...]:
    if not values:
        raise ValueError("an empirical law has no observations")
    if any(not math.isfinite(weight) or weight < 0 for _, weight in values):
        raise ValueError("empirical weights are invalid")
    ordered = sorted((value, weight) for value, weight in values if weight > 0)
    if not ordered:
        raise ValueError("an empirical law has no positive-weight observations")
    total = sum(weight for _, weight in ordered)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("empirical weights are invalid")
    targets = [probability * total for probability in probabilities]
    result: list[float] = []
    cumulative = 0.0
    target = 0
    for value, weight in ordered:
        cumulative += weight
        while target < len(targets) and cumulative >= targets[target]:
            result.append(float(value))
            target += 1
    result.extend([float(ordered[-1][0])] * (len(targets) - len(result)))
    return tuple(result)


def _weighted_values(
    prepared: PreparedKeyRecs,
    participants: set[str],
    predicate: Callable[[Gap], bool],
) -> list[tuple[float, float]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for gap in prepared.gaps:
        if gap.participant in participants and predicate(gap):
            center = prepared.session_centers[(gap.participant, gap.session)]
            grouped[gap.participant][gap.session].append(gap.interval_ms / center)
    weighted: list[tuple[float, float]] = []
    for participant in sorted(grouped):
        sessions = grouped[participant]
        session_weight = 1.0 / len(sessions)
        for values in sessions.values():
            weight = session_weight / len(values)
            weighted.extend((value, weight) for value in values)
    return weighted


def _fit_parent_buckets(
    prepared: PreparedKeyRecs, participants: set[str]
) -> dict[str, tuple[float, ...]]:
    model = released_comparator.fit(prepared.comparator_rows, participants)
    return {
        name: tuple(float(value) for value in model["residual_quantiles"][name])
        for name in ("within", "word", "sentence")
    }


def _shrunken_quantiles(
    child_values: Sequence[tuple[float, float]],
    parent_quantiles: Sequence[float],
    shrinkage: float,
) -> tuple[float, ...]:
    if shrinkage == 0 or not child_values:
        return tuple(float(value) for value in parent_quantiles)
    parent_weight = (1.0 - shrinkage) / len(parent_quantiles)
    child_total = sum(weight for _, weight in child_values)
    mixture = [(float(value), parent_weight) for value in parent_quantiles] + [
        (float(value), shrinkage * weight / child_total) for value, weight in child_values
    ]
    return _weighted_quantiles(mixture)


def _empirical_crps(values: Sequence[float], quantiles: Sequence[float]) -> float:
    samples = np.asarray(quantiles, dtype=float)
    observed = np.asarray(values, dtype=float)
    first = np.mean(np.abs(samples[:, None] - observed[None, :]), axis=0)
    ordered = np.sort(samples)
    count = len(ordered)
    coefficients = 2 * np.arange(1, count + 1) - count - 1
    second = float(np.sum(coefficients * ordered)) / (count * count)
    return float(np.mean(first - second))


def _normalized_observations(
    prepared: PreparedKeyRecs,
    participants: set[str],
    gap_class: str,
) -> list[float]:
    return [
        gap.interval_ms / prepared.session_centers[(gap.participant, gap.session)]
        for gap in prepared.gaps
        if gap.participant in participants and gap.gap_class == gap_class
    ]


def _select_one_shrinkage(
    prepared: PreparedKeyRecs,
    participants: set[str],
    gap_class: str,
    parent_name: str,
    seed: int,
    *,
    hard_shrinkage: float | None = None,
) -> tuple[float, list[dict[str, object]]]:
    folds = _group_folds(sorted(participants), min(INNER_FOLDS, len(participants)), seed)
    scores: dict[float, list[float]] = {value: [] for value in SHRINKAGE_GRID}
    fold_records = []
    for fold_index, held_values in enumerate(folds):
        held = set(held_values)
        train = participants - held
        released = _fit_parent_buckets(prepared, train)
        if parent_name == "hard_break":
            hard_values = _weighted_values(
                prepared, train, lambda gap: gap.gap_class in {"newline", "paragraph"}
            )
            hard_parent = _shrunken_quantiles(
                hard_values,
                released["sentence"],
                0.0 if hard_shrinkage is None else hard_shrinkage,
            )
            parent = hard_parent
        else:
            parent = released[parent_name]
        child = _weighted_values(prepared, train, lambda gap, name=gap_class: gap.gap_class == name)
        observed = _normalized_observations(prepared, held, gap_class)
        fold_scores = {}
        for shrinkage in SHRINKAGE_GRID:
            quantiles = _shrunken_quantiles(child, parent, shrinkage)
            score = _empirical_crps(observed, quantiles) if observed else None
            if score is not None:
                scores[shrinkage].append(score)
            fold_scores[str(shrinkage)] = round(score, 10) if score is not None else None
        fold_records.append(
            {
                "fold": fold_index,
                "split_seed": seed,
                "held_out_participants": len(held),
                "held_out_participant_ids": sorted(held),
                "scores": fold_scores,
            }
        )
    scored = [value for value in SHRINKAGE_GRID if scores[value]]
    selected = (
        min(scored, key=lambda value: (statistics.fmean(scores[value]), value)) if scored else 0.0
    )
    return selected, fold_records


def _select_shrinkage(
    prepared: PreparedKeyRecs, participants: set[str], seed: int
) -> tuple[dict[str, float], dict[str, object]]:
    selected: dict[str, float] = {}
    records: dict[str, object] = {}
    candidates = (*RELEASED_PARENTS.items(), ("hard_break", "sentence"))
    for offset, (name, parent) in enumerate(candidates):
        target = name if name != "hard_break" else "newline"
        if name == "hard_break":
            # Score the pooled hard-break law against both observable children.
            folds = _group_folds(
                sorted(participants), min(INNER_FOLDS, len(participants)), seed + offset
            )
            by_value = {value: [] for value in SHRINKAGE_GRID}
            detail = []
            for fold_index, held_values in enumerate(folds):
                held = set(held_values)
                train = participants - held
                released = _fit_parent_buckets(prepared, train)
                child = _weighted_values(
                    prepared,
                    train,
                    lambda gap: gap.gap_class in {"newline", "paragraph"},
                )
                observed = _normalized_observations(prepared, held, "newline")
                observed += _normalized_observations(prepared, held, "paragraph")
                fold_scores = {}
                for value in SHRINKAGE_GRID:
                    quantiles = _shrunken_quantiles(child, released["sentence"], value)
                    score = _empirical_crps(observed, quantiles) if observed else None
                    if score is not None:
                        by_value[value].append(score)
                    fold_scores[str(value)] = round(score, 10) if score is not None else None
                detail.append(
                    {
                        "fold": fold_index,
                        "split_seed": seed + offset,
                        "held_out_participants": len(held),
                        "held_out_participant_ids": sorted(held),
                        "scores": fold_scores,
                    }
                )
            scored = [value for value in SHRINKAGE_GRID if by_value[value]]
            value = (
                min(scored, key=lambda item: (statistics.fmean(by_value[item]), item))
                if scored
                else 0.0
            )
            selected[name] = value
            records[name] = detail
            continue
        value, detail = _select_one_shrinkage(prepared, participants, target, parent, seed + offset)
        selected[name] = value
        records[name] = detail

    for offset, name in enumerate(("newline", "paragraph"), start=10):
        value, detail = _select_one_shrinkage(
            prepared,
            participants,
            name,
            "hard_break",
            seed + offset,
            hard_shrinkage=selected["hard_break"],
        )
        selected[name] = value
        records[name] = detail
    return selected, records


def _rank_bin(value: float, quantiles: Sequence[float]) -> int:
    """Map one normalized observed gap to its fitted marginal quartile bin."""
    return int(np.searchsorted(np.asarray(quantiles)[[25, 50, 75]], value, side="right"))


def _rank_transition_joint(
    prepared: PreparedKeyRecs,
    participants: set[str],
    class_quantiles: Mapping[str, Sequence[float]],
) -> tuple[np.ndarray, dict[str, int]]:
    """Build participant/session/transition-equal contiguous rank-pair mass."""
    sessions: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    for gap in prepared.gaps:
        if gap.participant in participants:
            sessions[(gap.participant, gap.session)].append(gap)
    grouped: dict[str, list[list[tuple[int, int]]]] = defaultdict(list)
    raw_pairs = 0
    for (participant, _), rows in sorted(sessions.items()):
        ordered = sorted(rows, key=lambda gap: gap.order)
        pairs = []
        for left, right in pairwise(ordered):
            if left.segment != right.segment or right.order != left.order + 1:
                continue
            left_value = (
                left.interval_ms / prepared.session_centers[(left.participant, left.session)]
            )
            right_value = (
                right.interval_ms / prepared.session_centers[(right.participant, right.session)]
            )
            pairs.append(
                (
                    _rank_bin(left_value, class_quantiles[left.gap_class]),
                    _rank_bin(right_value, class_quantiles[right.gap_class]),
                )
            )
        if pairs:
            grouped[participant].append(pairs)
            raw_pairs += len(pairs)
    if not grouped:
        raise ValueError("rank transition has no contiguous training pairs")
    joint = np.zeros((4, 4), dtype=float)
    for participant in sorted(grouped):
        participant_weight = 1.0 / len(grouped)
        session_weight = participant_weight / len(grouped[participant])
        for pairs in grouped[participant]:
            pair_weight = session_weight / len(pairs)
            for left, right in pairs:
                joint[left, right] += pair_weight
    return joint, {
        "participants": len(grouped),
        "sessions": sum(len(values) for values in grouped.values()),
        "transitions": raw_pairs,
    }


def _doubly_stochastic_transition(joint: np.ndarray) -> np.ndarray:
    """KL-project positive empirical joint mass to uniform row/column marginals."""
    if joint.shape != (4, 4) or not np.all(np.isfinite(joint)) or np.any(joint <= 0):
        raise ValueError("rank transition requires positive support in all 16 cells")
    projected = np.asarray(joint, dtype=float).copy()
    projected /= float(np.sum(projected))
    for _ in range(10_000):
        projected *= (0.25 / np.sum(projected, axis=1))[:, None]
        projected *= (0.25 / np.sum(projected, axis=0))[None, :]
        error = max(
            float(np.max(np.abs(np.sum(projected, axis=1) - 0.25))),
            float(np.max(np.abs(np.sum(projected, axis=0) - 0.25))),
        )
        if error <= 1e-14:
            return projected * 4.0
    raise RuntimeError("rank transition projection did not converge")


def _blend_rank_transition(empirical: np.ndarray, alpha: float) -> np.ndarray:
    if alpha not in RANK_TRANSITION_ALPHA_GRID:
        raise ValueError("rank transition alpha is outside the frozen grid")
    return (1.0 - alpha) * np.full((4, 4), 0.25) + alpha * empirical


def _fit_rank_transition(
    prepared: PreparedKeyRecs,
    participants: set[str],
    class_quantiles: Mapping[str, Sequence[float]],
    alpha: float,
) -> tuple[dict[str, object], dict[str, object]]:
    joint, counts = _rank_transition_joint(prepared, participants, class_quantiles)
    empirical = _doubly_stochastic_transition(joint)
    selected = _blend_rank_transition(empirical, alpha)
    return (
        {
            "bins": 4,
            "initial": [0.25] * 4,
            "matrix": [[round(float(value), 12) for value in row] for row in selected],
        },
        {
            "alpha": alpha,
            "counts": counts,
            "empirical_doubly_stochastic_matrix": [
                [round(float(value), 12) for value in row] for row in empirical
            ],
        },
    )


def _select_rank_transition_alpha(
    prepared: PreparedKeyRecs,
    participants: set[str],
    seed: int,
    class_quantiles: Mapping[str, Sequence[float]] | None = None,
) -> tuple[float, list[dict[str, object]]]:
    """Select dependence strength by grouped held-transition logarithmic score."""
    folds = _group_folds(sorted(participants), min(INNER_FOLDS, len(participants)), seed)
    scores = {alpha: [] for alpha in RANK_TRANSITION_ALPHA_GRID}
    records = []
    for fold_index, held_values in enumerate(folds):
        held = set(held_values)
        train = participants - held
        quantiles = (
            class_quantiles
            if class_quantiles is not None
            else _fit_profile(
                prepared,
                train,
                _select_shrinkage(prepared, train, seed + 100 + fold_index * 100)[0],
                candidate_rung="observable_context",
            )["model"]["class_quantiles"]
        )
        training_joint, counts = _rank_transition_joint(prepared, train, quantiles)
        empirical = _doubly_stochastic_transition(training_joint)
        held_joint, held_counts = _rank_transition_joint(prepared, held, quantiles)
        fold_scores = {}
        for alpha in RANK_TRANSITION_ALPHA_GRID:
            transition = _blend_rank_transition(empirical, alpha)
            score = -float(np.sum(held_joint * np.log(transition)))
            scores[alpha].append(score)
            fold_scores[str(alpha)] = round(score, 10)
        records.append(
            {
                "fold": fold_index,
                "split_seed": seed,
                "fixed_released_marginals": class_quantiles is not None,
                "held_out_participants": len(held),
                "held_out_participant_ids": sorted(held),
                "training_counts": counts,
                "held_out_counts": held_counts,
                "scores": fold_scores,
            }
        )
    baseline = scores[0.0]
    eligible = [
        alpha
        for alpha in RANK_TRANSITION_ALPHA_GRID
        if alpha > 0 and all(value < baseline[index] for index, value in enumerate(scores[alpha]))
    ]
    if not eligible:
        raise RuntimeError("no rank dependence strength improves every held fold")
    means = {alpha: statistics.fmean(values) for alpha, values in scores.items()}
    selected = min(eligible, key=lambda alpha: (means[alpha], alpha))
    return selected, records


def _fit_styles(prepared: PreparedKeyRecs, participants: set[str]) -> tuple[dict[str, float], ...]:
    participant_centers = []
    for participant in sorted(participants):
        values = [
            center
            for (owner, _), center in prepared.session_centers.items()
            if owner == participant
        ]
        if values:
            participant_centers.append(statistics.fmean(values))
    population_center = math.exp(statistics.fmean(math.log(value) for value in participant_centers))
    speed_logs = sorted(math.log(value / population_center) for value in participant_centers)
    groups = np.array_split(np.asarray(speed_logs), min(8, len(speed_logs)))
    return tuple(
        {
            "weight": round(len(group) / len(speed_logs), 10),
            "speed_log": round(float(np.mean(group)), 10),
        }
        for group in groups
    )


def _class_counts(
    prepared: PreparedKeyRecs, participants: set[str], gap_class: str
) -> dict[str, int]:
    rows = [
        gap
        for gap in prepared.gaps
        if gap.participant in participants and gap.gap_class == gap_class
    ]
    return {
        "participants": len({gap.participant for gap in rows}),
        "sessions": len({(gap.participant, gap.session) for gap in rows}),
        "gaps": len(rows),
    }


def _fit_profile(
    prepared: PreparedKeyRecs,
    participants: set[str],
    shrinkage: Mapping[str, float],
    *,
    name: str = "fold_candidate",
    candidate_rung: str = "observable_context",
    rank_transition_alpha: float | None = None,
) -> dict[str, object]:
    if candidate_rung not in MODEL_LADDER:
        raise ValueError("unknown candidate rung")
    rank_rungs = {"observable_context_rank4"}
    if (candidate_rung in rank_rungs) != (rank_transition_alpha is not None):
        raise ValueError("rank transition alpha does not match candidate rung")
    released = _fit_parent_buckets(prepared, participants)
    child_values = {
        gap_class: _weighted_values(
            prepared,
            participants,
            lambda gap, selected=gap_class: gap.gap_class == selected,
        )
        for gap_class in CLASSES
    }
    hard_values = _weighted_values(
        prepared,
        participants,
        lambda gap: gap.gap_class in {"newline", "paragraph"},
    )
    hard_parent = _shrunken_quantiles(hard_values, released["sentence"], shrinkage["hard_break"])
    quantiles = {
        **{
            name: _shrunken_quantiles(child_values[name], released[parent], shrinkage[name])
            for name, parent in RELEASED_PARENTS.items()
        },
        "newline": _shrunken_quantiles(child_values["newline"], hard_parent, shrinkage["newline"]),
        "paragraph": _shrunken_quantiles(
            child_values["paragraph"], hard_parent, shrinkage["paragraph"]
        ),
    }
    counts = Counter(gap.gap_class for gap in prepared.gaps if gap.participant in participants)
    total = sum(counts.values())
    class_maximum = {
        "same_key": 1500.0,
        "same_finger": 1500.0,
        "same_hand": 1500.0,
        "alternate_hand": 1500.0,
        "other": 1500.0,
        "ordinary_space": SPACE_MAX_MS,
        "clause": 2500.0,
        "sentence": 3500.0,
        "newline": MAX_TOTAL_GAP_MS,
        "paragraph": MAX_TOTAL_GAP_MS,
    }
    rank_transition = None
    rank_transition_fit = None
    if candidate_rung in rank_rungs:
        assert rank_transition_alpha is not None
        rank_transition, rank_transition_fit = _fit_rank_transition(
            prepared, participants, quantiles, rank_transition_alpha
        )
    profile: dict[str, object] = {
        "schema": 6,
        "profile": name,
        "nominal_wpm": 65,
        "limits": {
            "minimum_interval_ms": MIN_INTERVAL_MS,
            "maximum_total_gap_ms": MAX_TOTAL_GAP_MS,
            "maximum_transport_unit_ms": MAX_TOTAL_GAP_MS,
            "minimum_validation_graphemes": MIN_VALIDATION_GRAPHEMES,
            "class_maximum_ms": class_maximum,
        },
        "model": {
            "kind": "observable_context_empirical_total_gap",
            "version": 1,
            "rank_dependence": (
                "markov_4_bin" if candidate_rung == "observable_context_rank4" else "independent"
            ),
            "rank_transition": rank_transition,
            "ordinary_space_added_pause_ms": 0.0,
            "styles": list(_fit_styles(prepared, participants)),
            "class_quantiles": {
                key: [round(value, 10) for value in values] for key, values in quantiles.items()
            },
            "reference_class_weights": {
                gap_class: round(counts[gap_class] / total, 10) for gap_class in CLASSES
            },
            "calibration_scale": 1.0,
        },
        "fit": {
            "candidate_rung": candidate_rung,
            "parents": {
                **{name: f"released_{parent}" for name, parent in RELEASED_PARENTS.items()},
                "newline": "hard_break",
                "paragraph": "hard_break",
                "hard_break": "released_sentence",
            },
            "shrinkage": {key: float(value) for key, value in sorted(shrinkage.items())},
            "intermediate_parent_quantiles": {
                "hard_break": [round(value, 10) for value in hard_parent],
            },
            "rank_transition": rank_transition_fit,
            "classes": {
                gap_class: {
                    **_class_counts(prepared, participants, gap_class),
                    "support_ms": [MIN_INTERVAL_MS, class_maximum[gap_class]],
                }
                for gap_class in CLASSES
            },
        },
        "validation": {"cleared": False},
    }
    interpreter = ArtifactInterpreter(profile, require_cleared=False)
    scale = interpreter._scale_for_quantiles(
        65,
        interpreter.class_quantiles,
        custom=False,
    )
    stored_scale = round(scale, 12)
    achieved_wpm = interpreter._expected_rate(
        stored_scale, interpreter.class_quantiles, custom=False
    )
    if abs(achieved_wpm - 65.0) > CALIBRATION_RATE_TOLERANCE_WPM:
        raise RuntimeError("candidate calibration did not meet its frozen tolerance")
    profile["model"]["calibration_scale"] = stored_scale
    profile["fit"]["calibration_rate_error_wpm"] = round(abs(achieved_wpm - 65.0), 14)
    return profile


def _parent_only_shrinkage() -> dict[str, float]:
    return {
        **{name: 0.0 for name in RELEASED_PARENTS},
        "hard_break": 0.0,
        "newline": 0.0,
        "paragraph": 0.0,
    }


def _crps_ensemble(observed: np.ndarray, simulations: np.ndarray) -> float:
    first = np.mean(np.abs(simulations - observed[None, :]), axis=0)
    simulations.sort(axis=0)
    ordered = simulations
    count = simulations.shape[0]
    coefficients = 2 * np.arange(1, count + 1) - count - 1
    second = np.sum(coefficients[:, None] * ordered, axis=0) / (count * count)
    return float(np.mean(first - second))


def _scalar_crps(observed: float, simulations: np.ndarray) -> float:
    values = np.sort(simulations)
    count = len(values)
    first = float(np.mean(np.abs(values - observed)))
    coefficients = 2 * np.arange(1, count + 1) - count - 1
    second = float(np.sum(coefficients * values)) / (count * count)
    return first - second


def _segment_pairs(rows: Sequence[Gap]) -> np.ndarray:
    return np.asarray(
        [
            index
            for index in range(1, len(rows))
            if rows[index].segment == rows[index - 1].segment
            and rows[index].order == rows[index - 1].order + 1
        ],
        dtype=int,
    )


def _summary(values: np.ndarray, rows: Sequence[Gap]) -> np.ndarray:
    q10, q50, q90 = np.quantile(values, (0.1, 0.5, 0.9))
    pairs = _segment_pairs(rows)
    if not len(pairs):
        return np.asarray([q10, q50, q90, 0.0, 0.0, 0.0])
    left = values[pairs - 1]
    right = values[pairs]
    correlation = float(np.corrcoef(left, right)[0, 1]) if len(pairs) > 1 else 0.0
    if not math.isfinite(correlation):
        correlation = 0.0
    q75 = float(np.quantile(values, 0.75))
    slow_run = float(np.mean((left > q75) & (right > q75)))
    edges = np.quantile(values, (0.25, 0.5, 0.75))
    rank_run = float(np.mean(np.searchsorted(edges, left) == np.searchsorted(edges, right)))
    return np.asarray([q10, q50, q90, correlation, slow_run, rank_run])


def _summary_scales(rows: Sequence[Gap], participants: set[str]) -> np.ndarray:
    sessions: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    for gap in rows:
        if gap.participant in participants:
            sessions[(gap.participant, gap.session)].append(gap)
    summaries = []
    for values in sessions.values():
        values = sorted(values, key=lambda gap: gap.order)
        if len(values) < MIN_VALIDATION_GRAPHEMES:
            continue
        observed = np.asarray([gap.interval_ms for gap in values])
        summaries.append(_summary(observed / float(np.mean(observed)), values))
    if len(summaries) < 2:
        return np.asarray([0.02, 0.02, 0.02, 0.02, 0.005, 0.02])
    return np.maximum(
        np.std(np.asarray(summaries), axis=0, ddof=1),
        np.asarray([0.02, 0.02, 0.02, 0.02, 0.005, 0.02]),
    )


def _energy_score(
    observed: np.ndarray,
    simulations: np.ndarray,
    rows: Sequence[Gap],
    scales: np.ndarray,
) -> float:
    observed_summary = _summary(observed, rows)[:5] / scales[:5]
    summaries = np.asarray([_summary(values, rows)[:5] / scales[:5] for values in simulations])
    first = float(np.mean(np.linalg.norm(summaries - observed_summary, axis=1)))
    count = len(summaries)
    if count < 2:
        return first
    # A deterministic half split avoids the quadratic simulation-pair matrix.
    left = summaries[: count // 2]
    right = summaries[-len(left) :]
    second = float(np.mean(np.linalg.norm(left - right, axis=1)))
    return first - second / 2


def _simulate_candidate(
    interpreter: ArtifactInterpreter,
    rows: Sequence[Gap],
    count: int,
    namespace: Sequence[int],
) -> np.ndarray:
    classes = [gap.gap_class for gap in rows]
    rank_resets = [
        index == 0
        or rows[index].segment != rows[index - 1].segment
        or rows[index].order != rows[index - 1].order + 1
        for index in range(len(rows))
    ]
    result = np.empty((count, len(rows)))
    for simulation in range(count):
        random = _stream_random(1, namespace, simulation)
        result[simulation] = [
            sample.total_ms
            for sample in interpreter.simulate(
                classes,
                65,
                random,
                rank_resets=rank_resets,
            )
        ]
    return result


def _simulate_comparator(
    rows: Sequence[Gap],
    model: Mapping[str, object],
    count: int,
    namespace: Sequence[int],
) -> np.ndarray:
    return np.asarray(
        [
            released_comparator.simulate_once(
                rows,
                model,
                _stream_random(2, namespace, simulation),
                65.0,
            )
            for simulation in range(count)
        ]
    )


def _stream_identity(
    model_namespace: int, namespace: Sequence[int], simulation: int
) -> tuple[int, ...]:
    return (SEED, model_namespace, *namespace, simulation)


def _stream_random(
    model_namespace: int, namespace: Sequence[int], simulation: int
) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence(_stream_identity(model_namespace, namespace, simulation))
    )


def _session_score(
    rows: Sequence[Gap],
    interpreter: ArtifactInterpreter,
    comparator_model: Mapping[str, object],
    count: int,
    stream_namespace: Sequence[int],
    scales: np.ndarray,
    rate_factor: float,
) -> dict[str, object]:
    rows = sorted(rows, key=lambda gap: gap.order)
    observed_raw = np.asarray([gap.interval_ms for gap in rows])
    observed = observed_raw / float(np.mean(observed_raw))
    observed_summary = _summary(observed, rows)
    observed_rate = 12_000.0 / float(np.mean(observed_raw)) * rate_factor
    candidate = _score_simulation_matrix(
        _simulate_candidate(interpreter, rows, count, stream_namespace),
        observed,
        observed_summary,
        observed_rate,
        rows,
        scales,
    )
    comparator = _score_simulation_matrix(
        _simulate_comparator(rows, comparator_model, count, stream_namespace),
        observed,
        observed_summary,
        observed_rate,
        rows,
        scales,
    )
    result: dict[str, object] = {
        "gap_crps_difference": candidate["gap_crps"] - comparator["gap_crps"],
        "sequence_energy_difference": candidate["sequence_energy"] - comparator["sequence_energy"],
        **{
            f"{metric}_{model_name}": model[metric]
            for metric in (
                "three_quantile_error",
                "lag_one_correlation_error",
                "rank_run_error",
                "population_wpm_crps",
                "expected_wpm_relative_error",
            )
            for model_name, model in (
                ("candidate", candidate),
                ("comparator", comparator),
            )
        },
        "observed_wpm": observed_rate,
        "candidate_wpm_quantiles": candidate["wpm_quantiles"],
        "comparator_wpm_quantiles": comparator["wpm_quantiles"],
        "candidate_wpm_rate_draws": candidate["wpm_rate_draws"],
        "comparator_wpm_rate_draws": comparator["wpm_rate_draws"],
        "candidate_wpm_median": candidate["wpm_quantiles"][1],
        "comparator_wpm_median": comparator["wpm_quantiles"][1],
        "maximum_candidate_gap_ms": candidate["maximum_gap_ms"],
        "maximum_candidate_space_ms": candidate["maximum_space_ms"],
        "boundaries": {
            gap_class: {
                f"{metric}_{model_name}": model["boundaries"][gap_class][metric]
                for metric in ("crps", "three_quantile_error")
                for model_name, model in (
                    ("candidate", candidate),
                    ("comparator", comparator),
                )
            }
            for gap_class in set(candidate["boundaries"]) & set(comparator["boundaries"])
        },
    }
    return result


def _score_simulation_matrix(
    simulations: np.ndarray,
    observed: np.ndarray,
    observed_summary: np.ndarray,
    observed_rate: float,
    rows: Sequence[Gap],
    scales: np.ndarray,
) -> dict[str, object]:
    rates = 12_000.0 / np.mean(simulations, axis=1)
    maximum = float(np.max(simulations))
    maximum_space = max(
        (
            float(np.max(simulations[:, index]))
            for index, gap in enumerate(rows)
            if gap.gap_class == "ordinary_space"
        ),
        default=0.0,
    )
    simulations /= np.mean(simulations, axis=1)[:, None]
    summaries = np.asarray([_summary(values, rows) for values in simulations])
    boundaries = {}
    for gap_class in ("clause", "sentence", "newline", "paragraph"):
        indexes = [index for index, gap in enumerate(rows) if gap.gap_class == gap_class]
        if not indexes:
            continue
        observed_boundary = observed[indexes]
        simulated_boundary = simulations[:, indexes]
        boundaries[gap_class] = {
            "crps": _crps_ensemble(observed_boundary, simulated_boundary),
            "three_quantile_error": _predictive_three_quantile_error(
                observed_boundary, simulated_boundary
            ),
        }
    sequence_energy = _energy_score(observed, simulations, rows, scales)
    gap_crps = _crps_ensemble(observed, simulations)
    result = {
        "gap_crps": gap_crps,
        "sequence_energy": sequence_energy,
        "three_quantile_error": float(
            np.mean(np.abs(np.mean(summaries[:, :3], axis=0) - observed_summary[:3]))
        ),
        "lag_one_correlation_error": abs(float(np.mean(summaries[:, 3]) - observed_summary[3])),
        "rank_run_error": abs(float(np.mean(summaries[:, 5]) - observed_summary[5])),
        "population_wpm_crps": _scalar_crps(observed_rate, rates),
        "expected_wpm_relative_error": abs(float(np.mean(rates)) - 65) / 65,
        "wpm_quantiles": tuple(float(value) for value in np.quantile(rates, (0.05, 0.5, 0.95))),
        "wpm_rate_draws": rates,
        "maximum_gap_ms": maximum,
        "maximum_space_ms": maximum_space,
        "boundaries": boundaries,
    }
    return result


def _predictive_three_quantile_error(observed: np.ndarray, simulations: np.ndarray) -> float:
    predictive = np.quantile(simulations, (0.1, 0.5, 0.9), axis=0)
    return float(np.mean(np.abs(predictive - observed[None, :])))


def _participant_metric(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]], key: str
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for (participant, _), score in session_scores.items():
        grouped[participant].append(float(score[key]))
    return {participant: statistics.fmean(values) for participant, values in grouped.items()}


def _bootstrap_interval(values: Sequence[float], seed: int) -> tuple[float, float]:
    array = np.asarray(values)
    random = np.random.default_rng(seed)
    indexes = random.integers(0, len(array), size=(BOOTSTRAP_SAMPLES, len(array)))
    means = np.mean(array[indexes], axis=1)
    return tuple(float(value) for value in np.quantile(means, (0.025, 0.975)))


def _bootstrap_standard_error(values: Sequence[float], seed: int) -> float:
    array = np.asarray(values)
    random = np.random.default_rng(seed)
    indexes = random.integers(0, len(array), size=(BOOTSTRAP_SAMPLES, len(array)))
    return float(np.std(np.mean(array[indexes], axis=1), ddof=1))


def _monte_carlo_standard_error(block_differences: Sequence[float]) -> float:
    if len(block_differences) < 2:
        raise ValueError("at least two Monte Carlo blocks are required")
    return statistics.stdev(block_differences) / math.sqrt(len(block_differences))


def _primary_precision_maximum(participant_bootstrap_se: float) -> float:
    return participant_bootstrap_se / 5.0


def _block_sign_agreement(values: Sequence[float]) -> dict[str, object]:
    if values and all(value < 0 for value in values):
        sign = "negative"
    elif values and all(value > 0 for value in values):
        sign = "positive"
    elif values and all(value == 0 for value in values):
        sign = "zero"
    else:
        sign = "mixed"
    return {"sign": sign, "cleared": sign != "mixed"}


def _aggregate_block_participants(
    blocks: Sequence[Mapping[str, Mapping[str, float]]], metric: str
) -> list[float]:
    participant_blocks: dict[str, list[float]] = defaultdict(list)
    for block in blocks:
        for participant, value in block[metric].items():
            participant_blocks[participant].append(float(value))
    return [statistics.fmean(values) for _, values in sorted(participant_blocks.items())]


def _training_rate_factor(prepared: PreparedKeyRecs, participants: set[str]) -> tuple[float, float]:
    rates: dict[str, list[float]] = defaultdict(list)
    sessions: dict[tuple[str, str], list[float]] = defaultdict(list)
    for gap in prepared.gaps:
        if gap.participant in participants:
            sessions[(gap.participant, gap.session)].append(gap.interval_ms)
    for (participant, _), values in sessions.items():
        rates[participant].append(12_000.0 / statistics.fmean(values))
    center = statistics.fmean(statistics.fmean(values) for values in rates.values())
    return 65.0 / center, center


def _eligible_sessions(
    gaps: Sequence[Gap], participants: set[str]
) -> dict[tuple[str, str], list[Gap]]:
    grouped: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    for gap in gaps:
        if gap.participant in participants:
            grouped[(gap.participant, gap.session)].append(gap)
    return {
        key: sorted(rows, key=lambda gap: gap.order)
        for key, rows in grouped.items()
        if len(rows) >= MIN_VALIDATION_GRAPHEMES
    }


def _pilot_block(
    sessions: Mapping[tuple[str, str], Sequence[Gap]],
    interpreter: ArtifactInterpreter,
    comparator_model: Mapping[str, object],
    count: int,
    block: int,
    scales: np.ndarray,
    rate_factor: float,
) -> tuple[dict[str, float], dict[str, object]]:
    scores = {
        key: _session_score(
            rows,
            interpreter,
            comparator_model,
            count,
            (0, block, index),
            scales,
            rate_factor,
        )
        for index, (key, rows) in enumerate(sorted(sessions.items()))
    }
    participant_gap = _participant_metric(scores, "gap_crps_difference")
    participant_sequence = _participant_metric(scores, "sequence_energy_difference")
    return (
        {
            "gap_crps_difference": statistics.fmean(participant_gap.values()),
            "sequence_energy_difference": statistics.fmean(participant_sequence.values()),
        },
        {
            "gap_crps_difference": participant_gap,
            "sequence_energy_difference": participant_sequence,
        },
    )


def _panel_candidates(
    prepared: PreparedKeyRecs,
) -> dict[str, list[tuple[tuple[str, str], list[Gap]]]]:
    grouped: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    for gap in prepared.gaps:
        grouped[(gap.participant, gap.session)].append(gap)
    by_participant: dict[str, list[tuple[tuple[str, str], list[Gap]]]] = defaultdict(list)
    for key, rows in grouped.items():
        ordered = sorted(rows, key=lambda gap: gap.order)
        if len(ordered) >= MIN_VALIDATION_GRAPHEMES:
            by_participant[key[0]].append((key, ordered))
    return by_participant


def _fixed_panels(
    prepared: PreparedKeyRecs,
    participants: Sequence[str],
) -> tuple[dict[tuple[str, str], list[Gap]], list[dict[str, object]]]:
    """Select 200 retained gaps from the earliest eligible session without score feedback."""
    by_participant = _panel_candidates(prepared)
    missing = sorted(set(participants) - set(by_participant))
    if missing:
        raise ValueError("KeyRecs participant has no eligible 200-gap session")
    panels = {}
    manifest = []
    for participant in sorted(participants):
        key, rows = min(
            by_participant[participant],
            key=lambda value: (value[0][1], value[1][0].order),
        )
        panel = rows[:MIN_VALIDATION_GRAPHEMES]
        panels[(participant, key[1])] = panel
        segment_ranges = []
        for segment in dict.fromkeys(gap.segment for gap in panel):
            segment_rows = [gap for gap in panel if gap.segment == segment]
            segment_ranges.append(
                {
                    "segment": segment,
                    "first_order": segment_rows[0].order,
                    "last_order": segment_rows[-1].order,
                    "gaps": len(segment_rows),
                }
            )
        manifest.append(
            {
                "participant": participant,
                "session": key[1],
                "first_order": panel[0].order,
                "last_order": panel[-1].order,
                "gaps": len(panel),
                "segment_count": len(segment_ranges),
                "segment_ranges": segment_ranges,
            }
        )
    return panels, manifest


def _pilot_panels(
    prepared: PreparedKeyRecs,
) -> tuple[tuple[str, ...], dict[tuple[str, str], list[Gap]], list[dict[str, object]]]:
    eligible = sorted(_panel_candidates(prepared))
    np.random.default_rng(np.random.SeedSequence((SEED, 0, 0))).shuffle(eligible)
    held = tuple(eligible[:8])
    if len(held) != 8:
        raise ValueError("KeyRecs has fewer than eight eligible pilot participants")
    panels, manifest = _fixed_panels(prepared, held)
    return held, panels, manifest


def _run_pilot(prepared: PreparedKeyRecs) -> dict[str, object]:
    held_values, sessions, panel_manifest = _pilot_panels(prepared)
    held = set(held_values)
    train = set(prepared.participants) - held
    shrinkage, _ = _select_shrinkage(prepared, train, SEED + 701)
    rank_alpha, rank_selection = _select_rank_transition_alpha(
        prepared,
        train,
        SEED + 702,
    )
    rung_shrinkage = {
        "context_parent": _parent_only_shrinkage(),
        "observable_context": shrinkage,
        "observable_context_rank4": shrinkage,
    }
    rung_alpha = {
        "context_parent": None,
        "observable_context": None,
        "observable_context_rank4": rank_alpha,
    }
    interpreters = {
        rung: ArtifactInterpreter(
            _fit_profile(
                prepared,
                train,
                values,
                candidate_rung=rung,
                rank_transition_alpha=rung_alpha[rung],
            ),
            require_cleared=False,
        )
        for rung, values in rung_shrinkage.items()
    }
    comparator_model = released_comparator.fit(prepared.comparator_rows, train)
    scales = _summary_scales(prepared.gaps, train)
    rate_factor, _ = _training_rate_factor(prepared, train)
    precision_panels = []
    eligible_counts: dict[str, int] = {}
    for count in PILOT_COUNTS:
        block_scores: dict[str, list[dict[str, float]]] = {rung: [] for rung in MODEL_LADDER}
        participant_scores: dict[str, list[dict[str, object]]] = {rung: [] for rung in MODEL_LADDER}
        for block in range(PILOT_BLOCKS):
            for rung in MODEL_LADDER:
                score, participants = _pilot_block(
                    sessions,
                    interpreters[rung],
                    comparator_model,
                    count,
                    block,
                    scales,
                    rate_factor,
                )
                block_scores[rung].append(score)
                participant_scores[rung].append(participants)
        rung_reports = {}
        for rung_index, rung in enumerate(MODEL_LADDER):
            metrics = {}
            rung_cleared = True
            for offset, metric in enumerate(("gap_crps_difference", "sequence_energy_difference")):
                differences = [score[metric] for score in block_scores[rung]]
                aggregate_participants = _aggregate_block_participants(
                    participant_scores[rung], metric
                )
                bootstrap_seed = SEED + count + rung_index * 10 + offset
                bootstrap_se = _bootstrap_standard_error(aggregate_participants, bootstrap_seed)
                mc_se = _monte_carlo_standard_error(differences)
                maximum = _primary_precision_maximum(bootstrap_se)
                precision_cleared = mc_se <= maximum
                sign_agreement = _block_sign_agreement(differences)
                metric_cleared = precision_cleared and bool(sign_agreement["cleared"])
                rung_cleared = rung_cleared and metric_cleared
                metrics[metric] = {
                    "block_differences": [round(value, 10) for value in differences],
                    "mean_difference": round(statistics.fmean(differences), 10),
                    "monte_carlo_standard_error": round(mc_se, 10),
                    "participant_bootstrap_standard_error": round(bootstrap_se, 10),
                    "participant_bootstrap_seed": bootstrap_seed,
                    "participant_count": len(aggregate_participants),
                    "maximum_allowed": round(maximum, 10),
                    "block_sign_agreement": sign_agreement,
                    "cleared": metric_cleared,
                }
            rung_reports[rung] = {
                "shrinkage": dict(sorted(rung_shrinkage[rung].items())),
                "rank_transition_alpha": rung_alpha[rung],
                "primary": metrics,
                "cleared": rung_cleared,
            }
            if rung_cleared and rung not in eligible_counts:
                eligible_counts[rung] = count
        panel = {
            "simulations_per_session": count,
            "block_count": PILOT_BLOCKS,
            "block_stream_namespaces": [[0, block] for block in range(PILOT_BLOCKS)],
            "rungs": rung_reports,
            "newly_eligible_rungs": [
                rung for rung in MODEL_LADDER if eligible_counts.get(rung) == count
            ],
        }
        precision_panels.append(panel)
        if len(eligible_counts) == len(MODEL_LADDER):
            break
    return {
        "method": "KeyRecs-only adaptive paired seed-block pilot",
        "candidate_ladder": list(MODEL_LADDER),
        "pilot_participants": list(held_values),
        "training_participants": sorted(train),
        "selection_seed": SEED + 701,
        "rank_transition_selection_seed": SEED + 702,
        "rank_transition_selection": rank_selection,
        "panel_split_seed_namespace": [0, 0],
        "panel_selection": (
            "first 200 retained gaps in source order from the lexicographically earliest "
            "eligible session; original segment identifiers preserved"
        ),
        "participant_panels": panel_manifest,
        "memory_strategy": (
            "one 2048-by-200 matrix at a time; candidate and comparator scored "
            "sequentially; nested prefixes recomputed from fixed streams"
        ),
        "candidate_counts": list(PILOT_COUNTS),
        "rung_simulation_counts": {
            rung: eligible_counts[rung] for rung in MODEL_LADDER if rung in eligible_counts
        },
        "eligible_rungs": [rung for rung in MODEL_LADDER if rung in eligible_counts],
        "ineligible_rungs": [rung for rung in MODEL_LADDER if rung not in eligible_counts],
        "panels": precision_panels,
        "cleared": bool(eligible_counts),
    }


def _pilot_failure_diagnostic(pilot: Mapping[str, object]) -> str:
    final_panel = pilot["panels"][-1]
    metrics = []
    for rung in MODEL_LADDER:
        primary = final_panel["rungs"][rung]["primary"]
        for name in ("gap_crps_difference", "sequence_energy_difference"):
            result = primary[name]
            metrics.append(
                f"{rung}.{name}(mean={result['mean_difference']}, "
                f"mc_se={result['monte_carlo_standard_error']}, "
                f"maximum_allowed={result['maximum_allowed']}, "
                f"sign={result['block_sign_agreement']['sign']}, "
                f"cleared={str(bool(result['cleared'])).lower()})"
            )
    return "; ".join(metrics)


def _pilot_measured_rung(pilot: Mapping[str, object], rung: str) -> bool:
    """Return whether the chosen pilot panel measured and cleared one rung."""
    counts = pilot.get("rung_simulation_counts", {})
    if rung not in counts:
        return False
    chosen = int(counts[rung])
    for panel in pilot["panels"]:
        if int(panel["simulations_per_session"]) != chosen:
            continue
        rungs = panel.get("rungs", {})
        return rung in rungs and bool(rungs[rung]["cleared"])
    return False


def _development_failure_diagnostic(development: Mapping[str, object]) -> str:
    diagnostics = []
    for rung in MODEL_LADDER:
        if rung not in development["rungs"]:
            continue
        primary = development["rungs"][rung]["primary"]
        diagnostics.append(
            f"{rung}(gap_upper="
            f"{primary['gap_crps_difference']['participant_clustered_95_percent_interval'][1]}, "
            f"sequence_upper="
            f"{primary['sequence_energy_difference']['participant_clustered_95_percent_interval'][1]})"
        )
    return "; ".join(diagnostics)


def _phase(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"1", "phase 1", "phase1", "email 1", "email"} or "email" in text:
        return "1"
    if text in {"2", "phase 2", "phase2", "free form", "free-form"} or "free" in text:
        return "2"
    raise ValueError(f"unknown SKAID phase: {value!r}")


_SKAID_TEXT_KEYS = {
    "space": " ",
    "spacebar": " ",
    "enter": "\n",
    "return": "\n",
    "tab": "\t",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "semicolon": ";",
    "colon": ":",
    "question": "?",
    "questionmark": "?",
    "exclamation": "!",
    "exclamationmark": "!",
}
_SKAID_MODIFIERS = frozenset(
    (
        "shift",
        "shiftleft",
        "shiftright",
        "control",
        "controlleft",
        "controlright",
        "ctrl",
        "alt",
        "altleft",
        "altright",
        "meta",
        "metaleft",
        "metaright",
        "capslock",
    )
)
_SKAID_CORRECTIONS = frozenset(("backspace", "delete", "del"))
_SKAID_MODIFIER_ALIASES = {
    "shiftl": "shiftleft",
    "shiftr": "shiftright",
    "ctrll": "controlleft",
    "ctrlleft": "controlleft",
    "ctrlr": "controlright",
    "ctrlright": "controlright",
    "altl": "altleft",
    "altr": "altright",
    "cmd": "meta",
    "cmdl": "metaleft",
    "cmdleft": "metaleft",
    "cmdr": "metaright",
    "cmdright": "metaright",
    "windows": "meta",
}
_SKAID_SHIFTED_CHARACTERS = dict(zip("`1234567890-=[]\\;',./", '~!@#$%^&*()_+{}|:"<>?'))


def _skaid_key(value: object) -> tuple[str, str | None, str]:
    original = str(value)
    raw = original.strip()
    named = False
    if raw[:4].lower() == "key.":
        raw = raw[4:]
        named = True
    normalized = re.sub(r"[\s_\-]+", "", raw).lower()
    if not named and len(original) == 1 and original.isprintable():
        return "text", original, f"literal:{normalized}"
    if named and len(raw) == 1 and raw.isprintable():
        return "text", raw.lower(), f"named:{normalized}"
    if normalized.startswith("key") and len(normalized) == 4 and normalized[-1].isalpha():
        return "text", normalized[-1], f"named:{normalized[-1]}"
    if normalized in _SKAID_TEXT_KEYS:
        return "text", _SKAID_TEXT_KEYS[normalized], f"named:{normalized}"
    normalized = _SKAID_MODIFIER_ALIASES.get(normalized, normalized)
    if normalized in _SKAID_MODIFIERS:
        return "modifier", None, normalized
    if normalized in _SKAID_CORRECTIONS:
        return "correction", None, normalized
    return "control", None, normalized


def _event(value: object) -> str:
    normalized = re.sub(r"[\s_\-]+", "", str(value)).lower()
    if normalized in {"press", "keypress", "keydown", "down"}:
        return "press"
    if normalized in {"release", "keyrelease", "keyup", "up"}:
        return "release"
    raise ValueError(f"unknown SKAID event: {value!r}")


def _csv_records(value: bytes, required: set[str]) -> list[dict[str, str]]:
    text = value.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None or set(reader.fieldnames) != required:
        raise ValueError("SKAID columns are invalid")
    return [dict(row) for row in reader]


def _phase_gaps(
    participant: str,
    phase: str,
    records: Sequence[Mapping[str, str]],
    expected: str,
    segment_start: int,
) -> _PhaseImport:
    presses: list[_Press] = []
    open_keys: dict[str, list[tuple[int | None, int]]] = defaultdict(list)
    break_rows: set[int] = set()
    invalid_timestamp_rows = 0
    timestamp_reversals = 0
    unmatched_releases = 0
    caps_lock = False
    previous_timestamp = -math.inf
    valid_timestamps: set[float] = set()
    for row_index, record in enumerate(records):
        try:
            timestamp = float(record["Timestamp (ms)"])
        except (TypeError, ValueError):
            invalid_timestamp_rows += 1
            break_rows.add(row_index)
            continue
        if not math.isfinite(timestamp):
            invalid_timestamp_rows += 1
            break_rows.add(row_index)
            continue
        if timestamp < previous_timestamp:
            timestamp_reversals += 1
            break_rows.add(row_index)
        previous_timestamp = timestamp
        valid_timestamps.add(timestamp)
        try:
            event = _event(record["Event"])
        except ValueError:
            break_rows.add(row_index)
            continue
        kind, character, key = _skaid_key(record["Key"])
        if event == "release":
            if open_keys[key]:
                for press_index, press_row in open_keys.pop(key):
                    if row_index in break_rows:
                        break_rows.add(press_row)
                    if press_index is not None:
                        presses[press_index] = replace(presses[press_index], released=True)
            else:
                unmatched_releases += 1
                break_rows.add(row_index)
            continue
        if kind == "modifier":
            if key == "capslock" and not open_keys[key]:
                caps_lock = not caps_lock
            open_keys[key].append((None, row_index))
            continue
        if kind == "correction":
            open_keys[key].append((None, row_index))
            break_rows.add(row_index)
            continue
        if kind != "text" or character is None:
            open_keys[key].append((None, row_index))
            break_rows.add(row_index)
            continue
        shift = any(open_keys[name] for name in ("shift", "shiftleft", "shiftright"))
        if character.isalpha():
            character = character.upper() if caps_lock != shift else character.lower()
        elif shift:
            character = _SKAID_SHIFTED_CHARACTERS.get(character, character)
        press_index = len(presses)
        presses.append(_Press(key, character, timestamp, row_index, 0))
        open_keys[key].append((press_index, row_index))

    unmatched_presses = sum(len(indexes) for indexes in open_keys.values())
    for indexes in open_keys.values():
        for _press_index, press_row in indexes:
            break_rows.add(press_row)

    observed = "".join(press.character for press in presses)
    matcher = difflib.SequenceMatcher(None, expected, observed, autojunk=False)
    blocks = tuple(block for block in matcher.get_matching_blocks() if block.size)
    matched_characters = sum(block.size for block in blocks)

    result: list[Gap] = []
    output_segment = segment_start
    for block in blocks:
        raw_segment: list[Gap] = []
        for offset in range(block.size - 1):
            first = presses[block.b + offset]
            second = presses[block.b + offset + 1]
            interval = second.timestamp_ms - first.timestamp_ms
            interrupted = any(first.row < row < second.row for row in break_rows)
            contiguous = (
                first.released
                and second.released
                and first.row < second.row
                and first.row not in break_rows
                and second.row not in break_rows
                and not interrupted
                and MIN_INTERVAL_MS <= interval <= MAX_TOTAL_GAP_MS
            )
            if not contiguous:
                if raw_segment:
                    result.extend(_classify_segment(raw_segment, output_segment))
                    output_segment += 1
                    raw_segment = []
                continue
            gap = Gap(
                participant,
                phase,
                block.a + offset,
                output_segment,
                first.character,
                second.character,
                interval,
                "other",
            )
            raw_segment.append(gap)
        if raw_segment:
            result.extend(_classify_segment(raw_segment, output_segment))
            output_segment += 1
        # Matching blocks are separated by at least one skipped source or target
        # character; never permit a segment to bridge that discontinuity.
        if block.size:
            output_segment = max(output_segment, segment_start + 1)

    diagnostics: dict[str, object] = {
        "participant": participant,
        "phase": phase,
        "expected_characters": len(expected),
        "observable_text_presses": len(presses),
        "matched_characters": matched_characters,
        "skipped_expected_characters": len(expected) - matched_characters,
        "skipped_observable_presses": len(presses) - matched_characters,
        "matched_coverage": round(matched_characters / len(expected), 12) if expected else 1.0,
        "matching_blocks": len(blocks),
        "retained_valid_gaps": len(result),
        "retained_segments": len({gap.segment for gap in result}),
        "unmatched_presses": unmatched_presses,
        "unmatched_releases": unmatched_releases,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "timestamp_reversals": timestamp_reversals,
        "distinct_valid_timestamps": len(valid_timestamps),
    }
    return _PhaseImport(tuple(result), max(output_segment, segment_start + 1), diagnostics)


def _read_demographics(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    if (
        _hash(path, "sha256") != SKAID_DEMOGRAPHICS_SHA256
        or _hash(path, "md5") != SKAID_DEMOGRAPHICS_MD5
    ):
        raise ValueError("SKAID demographics identity does not match the frozen source")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        expected = {"Session ID", "Age Range", "Typing Method", "Device Used", "Email"}
        if reader.fieldnames is None or set(reader.fieldnames) != expected:
            raise ValueError("SKAID demographics columns are invalid")
        records = [dict(record) for record in reader]
    by_session = {record["Session ID"]: record for record in records}
    if len(records) != 27 or len(by_session) != len(records):
        raise ValueError("SKAID demographics does not contain 27 unique participants")
    return by_session, {
        "path": path.name,
        "sha256": SKAID_DEMOGRAPHICS_SHA256,
        "md5": SKAID_DEMOGRAPHICS_MD5,
        "rows": len(records),
    }


def _skaid_confirmation_eligibility(
    participants: set[str],
    gaps_by_phase: Mapping[tuple[str, str], Sequence[Gap]],
    alignment_manifest: Sequence[Mapping[str, object]],
) -> tuple[set[str], dict[str, int]]:
    diagnostics_by_participant: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for diagnostic in alignment_manifest:
        diagnostics_by_participant[str(diagnostic["participant"])].append(diagnostic)
    eligible = {
        participant
        for participant in participants
        if all(
            len(gaps_by_phase.get((participant, phase), ())) >= MIN_VALIDATION_GRAPHEMES
            for phase in ("1", "2")
        )
    }
    exclusion_reasons: Counter[str] = Counter()
    for participant in sorted(participants - eligible):
        diagnostics = diagnostics_by_participant[participant]
        if diagnostics and all(
            int(value["distinct_valid_timestamps"]) <= 1 for value in diagnostics
        ):
            exclusion_reasons["zero_timestamp_variation"] += 1
        else:
            exclusion_reasons["phase_below_minimum_retained_valid_gaps"] += 1
    return eligible, dict(sorted(exclusion_reasons.items()))


def _read_skaid(
    path: Path,
    *,
    expected_pairs: int = 27,
    demographics: Mapping[str, Mapping[str, str]] | None = None,
    demographics_manifest: Mapping[str, object] | None = None,
) -> SkaidDataset:
    production_source = expected_pairs == SKAID_SOURCE_PARTICIPANTS
    if production_source and demographics is None:
        raise ValueError("SKAID production import requires official demographics")
    manifest = []
    gaps_by_phase: dict[tuple[str, str], tuple[Gap, ...]] = {}
    session_owners: dict[str, str] = {}
    matched_demographics: set[str] = set()
    identity_manifest = []
    alignment_manifest = []
    segment = 0
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("Keystroke Logs/") and name.endswith(".csv")
        )
        logs = {name[:-4] for name in names if not name.endswith("_full_text.csv")}
        texts = {
            name[: -len("_full_text.csv")] for name in names if name.endswith("_full_text.csv")
        }
        if logs != texts or len(logs) != expected_pairs:
            raise ValueError("SKAID log and text files are not a complete bijection")
        for stem in sorted(logs):
            log_name = f"{stem}.csv"
            text_name = f"{stem}_full_text.csv"
            log_bytes = archive.read(log_name)
            text_bytes = archive.read(text_name)
            for name, value in ((log_name, log_bytes), (text_name, text_bytes)):
                manifest.append({"path": name, "bytes": len(value), "sha256": _byte_hash(value)})
            log_records = _csv_records(
                log_bytes, {"Session ID", "Timestamp (ms)", "Event", "Key", "Phase"}
            )
            text_records = _csv_records(
                text_bytes, {"Session ID", "Phase", "Text", "Selected Email"}
            )
            log_sessions = {str(record["Session ID"]) for record in log_records}
            text_sessions = {str(record["Session ID"]) for record in text_records}
            if len(log_sessions) != 1 or log_sessions != text_sessions:
                raise ValueError("SKAID participant file has inconsistent session identity")
            session_id = next(iter(log_sessions))
            if session_id in session_owners:
                raise ValueError("SKAID session identity occurs in more than one file pair")
            participant = Path(stem).name
            demographic_id = "qt_session_" + participant.removeprefix("qt_")
            if demographics is not None:
                if not re.fullmatch(r"qt_\d+", participant) or demographic_id not in demographics:
                    raise ValueError("SKAID filename has no official demographic identity")
                if session_id != demographic_id:
                    raise ValueError("SKAID log session does not match its filename identity")
                matched_demographics.add(demographic_id)
            identity_manifest.append(
                {
                    "file_participant": participant,
                    "session_id": session_id,
                    **({"demographic_id": demographic_id} if demographics is not None else {}),
                }
            )
            session_owners[session_id] = participant
            expected_by_phase: dict[str, str] = {}
            selected_email_by_phase: dict[str, str] = {}
            for record in text_records:
                phase = _phase(record["Phase"])
                if phase in expected_by_phase:
                    raise ValueError("SKAID full text repeats a participant phase")
                expected_by_phase[phase] = str(record["Text"])
                selected_email_by_phase[phase] = str(record["Selected Email"])
            logs_by_phase: dict[str, list[Mapping[str, str]]] = defaultdict(list)
            for record in log_records:
                logs_by_phase[_phase(record["Phase"])].append(record)
            if set(expected_by_phase) != set(logs_by_phase):
                raise ValueError("SKAID log and text phases differ")
            if production_source and set(expected_by_phase) != {"1", "2"}:
                raise ValueError("SKAID production pair does not contain both phases")
            if (
                demographics is not None
                and selected_email_by_phase.get("1") != demographics[demographic_id]["Email"]
            ):
                raise ValueError("SKAID Phase 1 selected email does not match demographics")
            for phase in sorted(expected_by_phase):
                imported = _phase_gaps(
                    participant,
                    phase,
                    logs_by_phase[phase],
                    expected_by_phase[phase],
                    segment,
                )
                gaps_by_phase[(participant, phase)] = imported.gaps
                alignment_manifest.append(imported.diagnostics)
                segment = imported.next_segment
    if demographics is not None and matched_demographics != set(demographics):
        raise ValueError("SKAID files and demographics are not a participant bijection")

    participants = set(session_owners.values())
    if production_source:
        eligible, exclusion_reasons = _skaid_confirmation_eligibility(
            participants, gaps_by_phase, alignment_manifest
        )
    else:
        eligible = participants
        exclusion_reasons = {}

    all_gaps = tuple(
        gap for key in sorted(gaps_by_phase) if key[0] in eligible for gap in gaps_by_phase[key]
    )
    phase_counts = Counter(phase for participant, phase in gaps_by_phase if participant in eligible)
    return SkaidDataset(
        gaps=all_gaps,
        source_participant_count=len(session_owners),
        participant_count=len(eligible),
        phase_counts=dict(sorted(phase_counts.items())),
        file_manifest=tuple(manifest),
        exact_segment_reconstruction=True,
        session_ids=tuple(sorted(eligible)),
        demographics_manifest=demographics_manifest,
        identity_manifest=tuple(identity_manifest),
        alignment_manifest=tuple(alignment_manifest),
        exclusion_reasons=exclusion_reasons,
    )


def _run_development(
    prepared: PreparedKeyRecs,
    simulation_counts: Mapping[str, int],
) -> dict[str, object]:
    """Select the smallest participant-disjoint KeyRecs candidate rung."""
    eligible_rungs = tuple(rung for rung in MODEL_LADDER if rung in simulation_counts)
    if not eligible_rungs:
        raise ValueError("development requires at least one pilot-eligible rung")
    folds = _group_folds(prepared.participants, OUTER_FOLDS, SEED + 800)
    all_scores: dict[str, dict[tuple[str, str], Mapping[str, object]]] = {
        rung: {} for rung in eligible_rungs
    }
    fold_reports = []
    for fold_index, held_values in enumerate(folds):
        held = set(held_values)
        train = set(prepared.participants) - held
        selection_seed = SEED + 1_000 + fold_index * 100
        rank_selection_seed = selection_seed + 50
        if any(rung != "context_parent" for rung in eligible_rungs):
            shrinkage, selection = _select_shrinkage(
                prepared,
                train,
                selection_seed,
            )
        else:
            shrinkage = _parent_only_shrinkage()
            selection = {"method": "no child rung was pilot-eligible"}
        rank_alpha = None
        rank_selection = None
        if "observable_context_rank4" in eligible_rungs:
            rank_alpha, rank_selection = _select_rank_transition_alpha(
                prepared,
                train,
                rank_selection_seed,
            )
        rung_shrinkage = {
            "context_parent": _parent_only_shrinkage(),
            "observable_context": shrinkage,
            "observable_context_rank4": shrinkage,
        }
        rung_alpha = {
            "context_parent": None,
            "observable_context": None,
            "observable_context_rank4": rank_alpha,
        }
        interpreters = {
            rung: ArtifactInterpreter(
                _fit_profile(
                    prepared,
                    train,
                    values,
                    candidate_rung=rung,
                    rank_transition_alpha=rung_alpha[rung],
                ),
                require_cleared=False,
            )
            for rung, values in rung_shrinkage.items()
            if rung in eligible_rungs
        }
        comparator_model = released_comparator.fit(prepared.comparator_rows, train)
        scales = _summary_scales(prepared.gaps, train)
        rate_factor, training_wpm = _training_rate_factor(prepared, train)
        sessions, panel_manifest = _fixed_panels(prepared, held_values)
        scores = {
            rung: {
                key: _session_score(
                    rows,
                    interpreter,
                    comparator_model,
                    int(simulation_counts[rung]),
                    (1, fold_index, index),
                    scales,
                    rate_factor,
                )
                for index, (key, rows) in enumerate(sorted(sessions.items()))
            }
            for rung, interpreter in interpreters.items()
        }
        for rung in eligible_rungs:
            all_scores[rung].update(scores[rung])
        fold_reports.append(
            {
                "fold": fold_index,
                "training_participants": len(train),
                "training_participant_ids": sorted(train),
                "held_out_participants": len(held),
                "held_out_participant_ids": sorted(held),
                "inner_selection_seed": selection_seed,
                "rank_transition_selection_seed": rank_selection_seed,
                "eligible_sessions": len(sessions),
                "panel_manifest": panel_manifest,
                "rungs": {
                    rung: {
                        "shrinkage": dict(sorted(rung_shrinkage[rung].items())),
                        "rank_transition_alpha": rung_alpha[rung],
                        "simulations_per_session": int(simulation_counts[rung]),
                        "primary_mean_differences": {
                            metric: round(
                                statistics.fmean(
                                    _participant_metric(scores[rung], metric).values()
                                ),
                                10,
                            )
                            for metric in (
                                "gap_crps_difference",
                                "sequence_energy_difference",
                            )
                        },
                    }
                    for rung in eligible_rungs
                },
                "inner_selection": selection,
                "rank_transition_selection": rank_selection,
                "training_population_wpm": round(training_wpm, 10),
            }
        )
    rung_reports = {
        rung: {
            "primary": _primary_report(all_scores[rung], SEED + 1_800 + index * 10),
            "eligible_sessions": len(all_scores[rung]),
            "participants_scored": len({key[0] for key in all_scores[rung]}),
        }
        for index, rung in enumerate(eligible_rungs)
    }
    for report in rung_reports.values():
        report["cleared"] = all(value["cleared"] for value in report["primary"].values())
    selected_candidate = _select_candidate_rung(rung_reports)
    return {
        "role": "candidate_selection",
        "outer_split_seed": SEED + 800,
        "outer_folds": OUTER_FOLDS,
        "candidate_ladder": list(MODEL_LADDER),
        "pilot_eligible_rungs": list(eligible_rungs),
        "rung_simulation_counts": {rung: int(simulation_counts[rung]) for rung in eligible_rungs},
        "selected_candidate": selected_candidate,
        "cleared": selected_candidate is not None,
        "panel_selection": (
            "first 200 retained gaps in source order from the lexicographically earliest "
            "eligible session; original segment identifiers preserved"
        ),
        "rungs": rung_reports,
        "folds": fold_reports,
    }


def _select_candidate_rung(rung_reports: Mapping[str, Mapping[str, object]]) -> str | None:
    """Select the first preregistered rung that clears both primary gates."""
    return next(
        (
            rung
            for rung in MODEL_LADDER
            if rung in rung_reports and bool(rung_reports[rung]["cleared"])
        ),
        None,
    )


def _participant_nested_metric(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]],
    boundary: str,
    key: str,
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for (participant, _), score in session_scores.items():
        boundaries = score["boundaries"]
        if boundary in boundaries:
            grouped[participant].append(float(boundaries[boundary][key]))
    return {
        participant: statistics.fmean(values) for participant, values in sorted(grouped.items())
    }


def _primary_report(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]], seed: int
) -> dict[str, object]:
    report = {}
    for offset, metric in enumerate(("gap_crps_difference", "sequence_energy_difference")):
        participants = _participant_metric(session_scores, metric)
        values = list(participants.values())
        interval = _bootstrap_interval(values, seed + offset)
        mean = statistics.fmean(values)
        is_gap = metric == "gap_crps_difference"
        cleared = (
            interval[1] < 0
            if is_gap
            else (mean < 0 and interval[1] < SEQUENCE_ENERGY_NONINFERIORITY_MARGIN)
        )
        report[metric] = {
            "mean_difference": round(mean, 10),
            "participant_clustered_95_percent_interval": [
                round(interval[0], 10),
                round(interval[1], 10),
            ],
            "participant_count": len(values),
            "bootstrap_seed": seed + offset,
            "claim": ("superiority" if is_gap else "noninferiority_with_favorable_point_estimate"),
            "maximum_difference": (0.0 if is_gap else SEQUENCE_ENERGY_NONINFERIORITY_MARGIN),
            "favorable_point_estimate_required": not is_gap,
            "cleared": cleared,
        }
    return report


def _paired_noninferiority(
    candidate: Mapping[str, float],
    comparator: Mapping[str, float],
    margin: float,
    seed: int,
) -> dict[str, object]:
    participants = sorted(set(candidate) & set(comparator))
    if not participants:
        return {
            "candidate": 0.0,
            "comparator": 0.0,
            "difference": 0.0,
            "participant_clustered_95_percent_interval": [0.0, 0.0],
            "maximum_difference": margin,
            "participant_count": 0,
            "bootstrap_seed": seed,
            "cleared": False,
        }
    candidate_mean = statistics.fmean(candidate[value] for value in participants)
    comparator_mean = statistics.fmean(comparator[value] for value in participants)
    paired = [candidate[value] - comparator[value] for value in participants]
    interval = _bootstrap_interval(paired, seed)
    return {
        "candidate": round(candidate_mean, 10),
        "comparator": round(comparator_mean, 10),
        "difference": round(statistics.fmean(paired), 10),
        "participant_clustered_95_percent_interval": [
            round(interval[0], 10),
            round(interval[1], 10),
        ],
        "maximum_difference": margin,
        "participant_count": len(participants),
        "bootstrap_seed": seed,
        "cleared": interval[1] <= margin,
    }


def _secondary_report(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]], seed: int
) -> dict[str, object]:
    result = {}
    for offset, (name, margin) in enumerate(SECONDARY_MARGINS.items()):
        result[name] = _paired_noninferiority(
            _participant_metric(session_scores, f"{name}_candidate"),
            _participant_metric(session_scores, f"{name}_comparator"),
            margin,
            seed + offset,
        )
    return result


def _boundary_report(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]], seed: int
) -> dict[str, object]:
    result = {}
    for boundary_offset, boundary in enumerate(("clause", "sentence", "newline", "paragraph")):
        metrics = {
            name: _paired_noninferiority(
                _participant_nested_metric(session_scores, boundary, f"{name}_candidate"),
                _participant_nested_metric(session_scores, boundary, f"{name}_comparator"),
                margin,
                seed + boundary_offset * 10 + offset,
            )
            for offset, (name, margin) in enumerate(BOUNDARY_MARGINS.items())
        }
        result[boundary] = {
            "metrics": metrics,
            "cleared": all(value["cleared"] for value in metrics.values()),
        }
    return result


def _wpm_report(
    session_scores: Mapping[tuple[str, str], Mapping[str, object]],
) -> dict[str, object]:
    observed = _participant_metric(session_scores, "observed_wpm")
    candidate = _participant_metric(session_scores, "candidate_wpm_median")
    comparator = _participant_metric(session_scores, "comparator_wpm_median")
    coverage: dict[str, list[float]] = defaultdict(list)
    predictive: dict[str, dict[str, list[np.ndarray]]] = {
        "candidate": defaultdict(list),
        "comparator": defaultdict(list),
    }
    for (participant, _), score in session_scores.items():
        low, _, high = score["candidate_wpm_quantiles"]
        coverage[participant].append(float(low <= score["observed_wpm"] <= high))
        for model in ("candidate", "comparator"):
            predictive[model][participant].append(
                np.asarray(score[f"{model}_wpm_rate_draws"], dtype=float)
            )

    def population_quantiles(model: str) -> dict[str, float]:
        values = []
        weights = []
        participant_weight = 1.0 / len(predictive[model])
        for participant in sorted(predictive[model]):
            sessions = predictive[model][participant]
            session_weight = participant_weight / len(sessions)
            for draws in sessions:
                if not len(draws) or not np.all(np.isfinite(draws)):
                    raise ValueError("predictive WPM draws are invalid")
                values.append(draws)
                weights.append(np.full(len(draws), session_weight / len(draws)))
        mixed_values = np.concatenate(values)
        mixed_weights = np.concatenate(weights)
        order = np.argsort(mixed_values, kind="stable")
        ordered_values = mixed_values[order]
        cumulative = np.cumsum(mixed_weights[order])
        targets = np.asarray((0.05, 0.5, 0.95)) * float(cumulative[-1])
        quantiles = ordered_values[np.searchsorted(cumulative, targets, side="left")]
        return {
            probability: round(float(quantiles[index]), 10)
            for index, probability in enumerate(("5", "50", "95"))
        }

    return {
        "participant_count": len(observed),
        "observed_mean": round(statistics.fmean(observed.values()), 10),
        "candidate_predictive_median_mean": round(statistics.fmean(candidate.values()), 10),
        "comparator_predictive_median_mean": round(statistics.fmean(comparator.values()), 10),
        "candidate_population_predictive_wpm_quantiles": population_quantiles("candidate"),
        "comparator_population_predictive_wpm_quantiles": population_quantiles("comparator"),
        "candidate_90_percent_interval_coverage": round(
            statistics.fmean(statistics.fmean(values) for values in coverage.values()),
            10,
        ),
    }


def _confirmation_report(
    dataset: SkaidDataset,
    session_scores: Mapping[tuple[str, str], Mapping[str, object]],
    pilot: Mapping[str, object],
    profile: Mapping[str, object],
) -> dict[str, object]:
    primary = _primary_report(session_scores, SEED + 2_000)
    by_phase = {}
    for phase in ("1", "2"):
        scores = {key: value for key, value in session_scores.items() if key[1] == phase}
        phase_seed = SEED + 2_100 + int(phase) * 100
        by_phase[phase] = {
            "primary": _primary_report(scores, phase_seed),
            "secondary": _secondary_report(scores, phase_seed + 20),
            "boundaries": _boundary_report(scores, phase_seed + 40),
            "wpm": _wpm_report(scores),
        }

    secondary = _secondary_report(session_scores, SEED + 2_400)
    boundaries = _boundary_report(session_scores, SEED + 2_500)
    wpm = _wpm_report(session_scores)
    candidate_maximum = max(
        float(score["maximum_candidate_gap_ms"]) for score in session_scores.values()
    )
    candidate_space_maximum = max(
        float(score["maximum_candidate_space_ms"]) for score in session_scores.values()
    )
    class_quantiles = profile["model"]["class_quantiles"]
    eligible_by_phase = Counter(key[1] for key in session_scores)
    hard_gates = {
        "pilot_precision": bool(pilot["cleared"]),
        "archive_pair_count": dataset.source_participant_count == SKAID_SOURCE_PARTICIPANTS,
        "fixed_confirmation_cohort": dataset.participant_count == SKAID_CONFIRMATION_PARTICIPANTS,
        "both_phases_per_participant": dataset.phase_counts
        == {"1": SKAID_CONFIRMATION_PARTICIPANTS, "2": SKAID_CONFIRMATION_PARTICIPANTS},
        "exact_segment_reconstruction": dataset.exact_segment_reconstruction,
        "minimum_session_graphemes": len(session_scores) == SKAID_CONFIRMATION_PHASES
        and eligible_by_phase
        == {"1": SKAID_CONFIRMATION_PARTICIPANTS, "2": SKAID_CONFIRMATION_PARTICIPANTS},
        "finite_bounded_total_gaps": math.isfinite(candidate_maximum)
        and candidate_maximum <= MAX_TOTAL_GAP_MS,
        "ordinary_space_maximum": candidate_space_maximum <= SPACE_MAX_MS,
        "clause_median_below_sentence_median": float(np.quantile(class_quantiles["clause"], 0.5))
        < float(np.quantile(class_quantiles["sentence"], 0.5)),
        "all_observable_classes_present": set(class_quantiles) == set(CLASSES),
    }
    cleared = (
        all(value["cleared"] for value in primary.values())
        and all(value["cleared"] for value in secondary.values())
        and all(value["cleared"] for value in boundaries.values())
        and all(hard_gates.values())
    )
    return {
        "role": "final_acceptance",
        "cluster_unit": "participant",
        "acceptance_claim": (
            "superior normalized gap-distribution fidelity and sequence fidelity "
            "noninferior within 0.10 standardized energy-loss units with a "
            "directionally favorable point estimate"
        ),
        "primary": primary,
        "phases": by_phase,
        "secondary": secondary,
        "boundaries": boundaries,
        "wpm": wpm,
        "hard_gates": hard_gates,
        "observed_maximum_candidate_gap_ms": round(candidate_maximum, 10),
        "observed_maximum_candidate_ordinary_space_ms": round(candidate_space_maximum, 10),
        "cleared": cleared,
    }


def _validate_confirmation_cohort(dataset: SkaidDataset) -> None:
    expected_phases = {
        "1": SKAID_CONFIRMATION_PARTICIPANTS,
        "2": SKAID_CONFIRMATION_PARTICIPANTS,
    }
    if (
        dataset.source_participant_count != SKAID_SOURCE_PARTICIPANTS
        or dataset.participant_count != SKAID_CONFIRMATION_PARTICIPANTS
        or dataset.phase_counts != expected_phases
        or len(dataset.session_ids) != SKAID_CONFIRMATION_PARTICIPANTS
        or not dataset.exact_segment_reconstruction
    ):
        raise ValueError(
            "SKAID structural import does not match the frozen 25-participant/50-phase "
            "confirmation cohort; confirmation scoring was not run"
        )


def _run_confirmation(
    dataset: SkaidDataset,
    interpreter: ArtifactInterpreter,
    comparator_model: Mapping[str, object],
    simulation_count: int,
    scales: np.ndarray,
    rate_factor: float,
    pilot: Mapping[str, object],
    profile: Mapping[str, object],
) -> dict[str, object]:
    _validate_confirmation_cohort(dataset)
    sessions = _eligible_sessions(dataset.gaps, set(dataset.session_ids))
    if len(sessions) != SKAID_CONFIRMATION_PHASES:
        raise ValueError(
            "SKAID structural import does not provide 50 eligible confirmation phases; "
            "confirmation scoring was not run"
        )
    scores = {
        key: _session_score(
            rows,
            interpreter,
            comparator_model,
            simulation_count,
            (2, 0, index),
            scales,
            rate_factor,
        )
        for index, (key, rows) in enumerate(sorted(sessions.items()))
    }
    return _confirmation_report(dataset, scores, pilot, profile)


def _serialized(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _source_aliases(values: Sequence[str], source: str) -> dict[str, str]:
    return {value: f"{source}-{index:03d}" for index, value in enumerate(sorted(values), start=1)}


def _replace_identifiers(value: object, aliases: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, Mapping):
        return {
            aliases.get(str(key), str(key)): _replace_identifiers(item, aliases)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_replace_identifiers(item, aliases) for item in value]
    return value


def _public_skaid_identity(dataset: SkaidDataset) -> dict[str, object]:
    identities = sorted(dataset.identity_manifest, key=lambda value: value["file_participant"])
    aliases = _source_aliases([value["file_participant"] for value in identities], "skaid")
    eligible = set(dataset.session_ids)
    public_files = []
    for value in dataset.file_manifest:
        path = str(value["path"])
        filename = Path(path).name
        role = "full_text" if filename.endswith("_full_text.csv") else "log"
        raw_participant = filename.removesuffix("_full_text.csv").removesuffix(".csv")
        public_files.append(
            {
                "participant": aliases[raw_participant],
                "role": role,
                "bytes": value["bytes"],
                "sha256": value["sha256"],
            }
        )
    return {
        "source_participant_ids": [aliases[value["file_participant"]] for value in identities],
        "participant_ids": [aliases[value] for value in sorted(eligible)],
        "identity_manifest": [
            {
                "participant": aliases[value["file_participant"]],
                "file_session_demographic_bijection": "demographic_id" in value,
            }
            for value in identities
        ],
        "file_manifest": sorted(
            public_files, key=lambda value: (value["participant"], value["role"])
        ),
        "alignment_manifest": sorted(
            (_replace_identifiers(value, aliases) for value in dataset.alignment_manifest),
            key=lambda value: (str(value["participant"]), str(value["phase"])),
        ),
    }


def _callable_hash(*functions: Callable[..., object]) -> str:
    source = "\n".join(inspect.getsource(function) for function in functions)
    return _byte_hash(source.encode("utf-8"))


def _frozen_protocol(
    profile: Mapping[str, object],
    comparator_model: Mapping[str, object],
    scales: np.ndarray,
    rate_factor: float,
    simulation_count: int,
    confirmation_source: Mapping[str, object],
    pilot: Mapping[str, object] | None = None,
    development: Mapping[str, object] | None = None,
) -> dict[str, object]:
    class_map_path = ROOT / "computer_use/core/typing_boundaries.py"
    comparator_path = Path(released_comparator.__file__)
    return {
        "model": profile["model"],
        "comparator": comparator_model,
        "limits": profile["limits"],
        "filters": {
            "minimum_interval_ms": MIN_INTERVAL_MS,
            "maximum_total_gap_ms": MAX_TOTAL_GAP_MS,
            "minimum_validation_graphemes": MIN_VALIDATION_GRAPHEMES,
        },
        "candidate_ladder": list(MODEL_LADDER),
        "ordinary_space_semantics": {
            "added_pause_ms": 0.0,
            "complete_total_gap_support_ms": [MIN_INTERVAL_MS, SPACE_MAX_MS],
        },
        "margins": {
            "primary_sequence_energy": SEQUENCE_ENERGY_NONINFERIORITY_MARGIN,
            "secondary": SECONDARY_MARGINS,
            "boundary": BOUNDARY_MARGINS,
        },
        "primary_gate": {
            "gap_crps": "participant-bootstrap 95% interval upper bound below zero",
            "sequence_energy": (
                "paired mean below zero and participant-bootstrap 95% interval upper "
                "bound below 0.10 standardized energy-loss units"
            ),
            "sequence_margin_basis": (
                "operational loss margin anchored to the energy score's triangle-inequality "
                "response to a one-tenth-SD Euclidean perturbation; it is not a "
                "componentwise error guarantee"
            ),
        },
        "claim_revision": {
            "stage": "after KeyRecs development and before untouched SKAID confirmation",
            "original_dual_superiority_result": (
                "failed because the global rank4 sequence-energy 95% upper bound was "
                "+0.0153869572; its point estimate was favorable and gap CRPS cleared"
            ),
            "confirmation_role": "SKAID is the sole confirmatory acceptance source",
        },
        "seed": SEED,
        "simulation_streams": {
            "seed_sequence_entropy": [
                "root_seed",
                "model_namespace",
                "stage_namespace",
                "fold_or_block",
                "session",
                "simulation",
            ],
            "model_namespaces": {"candidate": 1, "comparator": 2},
            "stage_namespaces": {"pilot": 0, "development": 1, "confirmation": 2},
            "pilot_prefixes_nested": True,
        },
        "simulation_count": simulation_count,
        "calibration_rate_tolerance_wpm": CALIBRATION_RATE_TOLERANCE_WPM,
        "summary_scales": [round(float(value), 12) for value in scales],
        "rate_factor": round(rate_factor, 12),
        "confirmation_source": confirmation_source,
        "fit": profile["fit"],
        "pilot": pilot,
        "development": development,
        "source_code": {
            "class_map_sha256": _hash(class_map_path, "sha256"),
            "importer_sha256": _callable_hash(
                _read_skaid,
                _skaid_confirmation_eligibility,
                _phase_gaps,
                _csv_records,
                _event,
                _skaid_key,
            ),
            "deriver_sha256": _hash(Path(__file__), "sha256"),
            "comparator_sha256": _hash(comparator_path, "sha256"),
        },
    }


def _verify_readme(path: Path) -> dict[str, object]:
    digest = _hash(path, "sha256")
    if digest != SKAID_README_SHA256:
        raise ValueError("SKAID README identity does not match the frozen source")
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    required = ("skaid:", "each participant", "email 1", "free form", "zenodo")
    if any(term not in lowered for term in required):
        raise ValueError("SKAID README identity or phase description is invalid")
    return {
        "path": path.name,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "doi": SKAID_DOI,
        "version": SKAID_VERSION,
        "license": "CC BY 4.0",
    }


def _keyrecs_source(path: Path) -> dict[str, object]:
    return {
        "title": "KeyRecs: Keystroke Dynamics Dataset",
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": _hash(path, "sha256"),
        "md5": _hash(path, "md5"),
        "doi": "10.5281/zenodo.7886743",
        "article_doi": "10.1016/j.dib.2023.109509",
        "license": "CC BY 4.0",
    }


def _released_rank_profile(
    prepared: PreparedKeyRecs,
    keyrecs_path: Path,
) -> dict[str, object]:
    """Add one fitted rank chain without changing the released gap tables."""
    participants = set(prepared.participants)
    released_model = released_comparator.fit(prepared.comparator_rows, participants)
    released_quantiles = {
        name: list(released_model["residual_quantiles"][name])
        for name in ("within", "word", "sentence")
    }
    class_quantiles = {
        name: list(released_quantiles[parent]) for name, parent in RELEASED_CLASS_ALIASES.items()
    }
    alpha, raw_selection = _select_rank_transition_alpha(
        prepared,
        participants,
        SEED + 4_050,
        class_quantiles,
    )
    transition, transition_fit = _fit_rank_transition(
        prepared,
        participants,
        class_quantiles,
        alpha,
    )
    selection = _replace_identifiers(
        raw_selection,
        _source_aliases(prepared.participants, "keyrecs"),
    )
    counts = Counter(gap.gap_class for gap in prepared.gaps if gap.participant in participants)
    total = sum(counts.values())
    class_maximum = {
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
    }
    profile: dict[str, object] = {
        "schema": 6,
        "profile": "us_adult_transcription_2026",
        "nominal_wpm": 65,
        "limits": {
            "minimum_interval_ms": MIN_INTERVAL_MS,
            "maximum_total_gap_ms": MAX_TOTAL_GAP_MS,
            "maximum_transport_unit_ms": MAX_TOTAL_GAP_MS,
            "minimum_validation_graphemes": MIN_VALIDATION_GRAPHEMES,
            "class_maximum_ms": class_maximum,
        },
        "model": {
            "kind": "observable_context_empirical_total_gap",
            "version": 1,
            "rank_dependence": "markov_4_bin",
            "rank_transition": transition,
            "ordinary_space_added_pause_ms": 0.0,
            "styles": [{"weight": 1.0, "speed_log": 0.0}],
            "class_quantiles": class_quantiles,
            "reference_class_weights": {
                gap_class: round(counts[gap_class] / total, 10) for gap_class in CLASSES
            },
            "calibration_scale": 1.0,
        },
        "fit": {
            "candidate_rung": "released_marginals_rank4",
            "class_aliases": RELEASED_CLASS_ALIASES,
            "released_quantiles": released_quantiles,
            "released_profile": {
                "commit": RELEASED_BASELINE_COMMIT,
                "sha256": RELEASED_PROFILE_SHA256,
            },
            "rank_transition": transition_fit,
            "rank_transition_selection": selection,
            "rank_transition_selection_seed": SEED + 4_050,
            "classes": {
                gap_class: _class_counts(prepared, participants, gap_class) for gap_class in CLASSES
            },
            "source": _keyrecs_source(keyrecs_path),
        },
        "validation": {
            "cleared": True,
            "acceptance_source": (
                "algebraic marginal invariant and participant-disjoint KeyRecs transition scoring"
            ),
            "marginal_invariant": {
                "initial_rank_mass": [0.25] * 4,
                "required_matrix_property": "doubly_stochastic",
                "proof": "uniform row mass times a unit-sum column remains uniform",
            },
            "failed_experiment": {
                "source": "SKAID 1.0",
                "candidate": "observable_context_rank4",
                "gap_crps_difference": 0.0025101441,
                "gap_crps_95_percent_interval": [0.0009466781, 0.0042491979],
                "sequence_energy_difference": -0.2225342663,
                "sequence_energy_95_percent_interval": [
                    -0.3105449439,
                    -0.1343539406,
                ],
                "verdict": "failed and not rescored for this replacement",
            },
        },
        "provenance": {
            "script": Path(__file__).name,
            "script_sha256": _hash(Path(__file__), "sha256"),
            "seed": SEED,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
    }
    interpreter = ArtifactInterpreter(profile, require_cleared=False)
    scale = interpreter._scale_for_quantiles(
        65,
        interpreter.class_quantiles,
        custom=False,
    )
    profile["model"]["calibration_scale"] = round(scale, 12)
    validate_release_artifact(profile, verify_script=False)
    return profile


def validate_release_artifact(
    profile: Mapping[str, object],
    *,
    verify_script: bool = True,
) -> None:
    """Validate the cheap release invariants without source data or fitting."""
    interpreter = ArtifactInterpreter(profile)
    model = profile["model"]
    fit = profile["fit"]
    if model["styles"] != [{"weight": 1.0, "speed_log": 0.0}]:
        raise ValueError("the released profile must use one neutral speed entry")
    if fit["released_profile"] != {
        "commit": RELEASED_BASELINE_COMMIT,
        "sha256": RELEASED_PROFILE_SHA256,
    }:
        raise ValueError("the released typing source identity changed")
    if fit["class_aliases"] != RELEASED_CLASS_ALIASES:
        raise ValueError("the released typing class aliases changed")
    for gap_class, parent in RELEASED_CLASS_ALIASES.items():
        if model["class_quantiles"][gap_class] != fit["released_quantiles"][parent]:
            raise ValueError("a released conditional quantile table changed")
    selected = str(fit["rank_transition"]["alpha"])
    for fold in fit["rank_transition_selection"]:
        if not fold["scores"][selected] < fold["scores"]["0.0"]:
            raise ValueError("rank dependence does not improve every held fold")
    matrix = interpreter.rank_transition
    uniform = [math.fsum(matrix[row][column] * 0.25 for row in range(4)) for column in range(4)]
    if any(not math.isclose(value, 0.25, abs_tol=2e-7) for value in uniform):
        raise ValueError("rank dependence does not preserve uniform marginal mass")
    if verify_script:
        provenance = profile.get("provenance")
        if not isinstance(provenance, Mapping) or provenance.get("script_sha256") != _hash(
            Path(__file__), "sha256"
        ):
            raise ValueError("the checked profile does not match this derivation script")


def derive_release(keyrecs_path: Path, *, verify_hashes: bool = True) -> dict[str, object]:
    """Derive the release artifact from KeyRecs without simulation or SKAID."""
    if verify_hashes and (
        _hash(keyrecs_path, "sha256") != KEYRECS_SHA256 or _hash(keyrecs_path, "md5") != KEYRECS_MD5
    ):
        raise ValueError("KeyRecs source identity does not match the frozen source")
    gaps, rejected_rows = _read_keyrecs(keyrecs_path)
    comparator_rows, _ = released_comparator.read(keyrecs_path)
    prepared = _prepare_keyrecs(gaps, rejected_rows, comparator_rows)
    return _released_rank_profile(prepared, keyrecs_path)


def derive(
    keyrecs_path: Path,
    skaid_archive: Path,
    skaid_readme: Path,
    skaid_demographics: Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, object]:
    if verify_hashes and (
        _hash(keyrecs_path, "sha256") != KEYRECS_SHA256 or _hash(keyrecs_path, "md5") != KEYRECS_MD5
    ):
        raise ValueError("KeyRecs source identity does not match the frozen source")

    gaps, rejected_rows = _read_keyrecs(keyrecs_path)
    comparator_rows, _ = released_comparator.read(keyrecs_path)
    prepared = _prepare_keyrecs(gaps, rejected_rows, comparator_rows)
    keyrecs_aliases = _source_aliases(prepared.participants, "keyrecs")
    pilot = _replace_identifiers(_run_pilot(prepared), keyrecs_aliases)
    assert isinstance(pilot, dict)
    if not pilot["cleared"]:
        raise RuntimeError(
            "Monte Carlo pilot precision did not clear at the simulation cap; "
            f"{_pilot_failure_diagnostic(pilot)}; outer and confirmation scoring were not run"
        )

    simulation_counts = {
        str(rung): int(count) for rung, count in pilot["rung_simulation_counts"].items()
    }
    development = _replace_identifiers(
        _run_development(prepared, simulation_counts), keyrecs_aliases
    )
    assert isinstance(development, dict)
    if not development["cleared"]:
        raise RuntimeError(
            "No KeyRecs candidate rung cleared both primary development gates; "
            f"{_development_failure_diagnostic(development)}; confirmation inputs were not read"
        )
    participants = set(prepared.participants)
    candidate_rung = str(development["selected_candidate"])
    if not _pilot_measured_rung(pilot, candidate_rung):
        raise RuntimeError("the outer-selected candidate rung did not clear pilot precision")
    simulation_count = simulation_counts[candidate_rung]
    rank_transition_alpha = None
    raw_rank_selection = None
    rank_selection_seed = None
    if candidate_rung == "context_parent":
        shrinkage = _parent_only_shrinkage()
        raw_selection: object = {
            "method": "parent-only rung selected by participant-disjoint outer development"
        }
    else:
        shrinkage, raw_selection = _select_shrinkage(prepared, participants, SEED + 4_000)
        if candidate_rung == "observable_context_rank4":
            rank_selection_seed = SEED + 4_050
            rank_transition_alpha, raw_rank_selection = _select_rank_transition_alpha(
                prepared,
                participants,
                rank_selection_seed,
            )
    selection = _replace_identifiers(raw_selection, keyrecs_aliases)
    rank_selection = _replace_identifiers(raw_rank_selection, keyrecs_aliases)
    profile = _fit_profile(
        prepared,
        participants,
        shrinkage,
        name="us_adult_transcription_2026",
        candidate_rung=candidate_rung,
        rank_transition_alpha=rank_transition_alpha,
    )
    interpreter = ArtifactInterpreter(profile, require_cleared=False)
    comparator_model = released_comparator.fit(prepared.comparator_rows, participants)
    scales = _summary_scales(prepared.gaps, participants)
    rate_factor, training_wpm = _training_rate_factor(prepared, participants)
    profile["comparator"] = {
        "release_commit": RELEASED_BASELINE_COMMIT,
        "model": comparator_model,
    }
    profile["fit"].update(
        {
            "estimation_source": "KeyRecs free-text task",
            "participants": len(participants),
            "sessions": len(prepared.session_centers),
            "retained_gaps": len(prepared.gaps),
            "rejected_rows": prepared.rejected_rows,
            "selection": selection,
            "selection_seed": SEED + 4_000,
            "rank_transition_selection": rank_selection,
            "rank_transition_selection_seed": rank_selection_seed,
            "training_population_wpm": round(training_wpm, 10),
            "calibration": {
                "target_wpm": 65,
                "rate_tolerance_wpm": CALIBRATION_RATE_TOLERANCE_WPM,
                "equation": "population mean of reciprocal expected style gaps",
            },
            "source": _keyrecs_source(keyrecs_path),
        }
    )
    archive_sha256 = _hash(skaid_archive, "sha256")
    archive_md5 = _hash(skaid_archive, "md5")
    if verify_hashes and (archive_sha256 != SKAID_SHA256 or archive_md5 != SKAID_MD5):
        raise ValueError("SKAID archive identity does not match the frozen source")
    readme_manifest = _verify_readme(skaid_readme)
    demographics, demographics_manifest = _read_demographics(skaid_demographics)
    dataset = _read_skaid(
        skaid_archive,
        demographics=demographics,
        demographics_manifest=demographics_manifest,
    )
    _validate_confirmation_cohort(dataset)
    public_identity = _public_skaid_identity(dataset)
    confirmation_source = {
        "archive": skaid_archive.name,
        "sha256": archive_sha256,
        "md5": archive_md5,
        "doi": SKAID_DOI,
        "version": SKAID_VERSION,
        "license": "CC BY 4.0",
        "participant_file_pairs": dataset.source_participant_count,
        "eligible_paired_participants": dataset.participant_count,
        "eligible_phases": sum(dataset.phase_counts.values()),
        "source_participant_ids": public_identity["source_participant_ids"],
        "participant_ids": public_identity["participant_ids"],
        "identity_manifest": public_identity["identity_manifest"],
        "phase_counts": dict(dataset.phase_counts),
        "exact_segment_reconstruction": dataset.exact_segment_reconstruction,
        "alignment": {
            "algorithm": "difflib.SequenceMatcher(autojunk=False) exact matching blocks",
            "python_version": platform.python_version(),
            "manifest": public_identity["alignment_manifest"],
        },
        "aggregate_exclusion_reasons": dict(dataset.exclusion_reasons),
        "source_format_audit": {
            "original_27_participant_54_phase_whole_text_assumption": "failed",
            "repair_frozen_before_confirmation_scoring": True,
            "model_scores_available_when_repair_was_frozen": False,
        },
        "file_manifest": public_identity["file_manifest"],
        "readme": readme_manifest,
        "demographics": dataset.demographics_manifest,
    }
    frozen_protocol = _frozen_protocol(
        profile,
        comparator_model,
        scales,
        rate_factor,
        simulation_count,
        confirmation_source,
        pilot,
        development,
    )
    frozen_hash = _byte_hash(_serialized(frozen_protocol).encode("utf-8"))
    confirmation = _run_confirmation(
        dataset,
        interpreter,
        comparator_model,
        simulation_count,
        scales,
        rate_factor,
        pilot,
        profile,
    )
    if (
        _byte_hash(
            _serialized(
                _frozen_protocol(
                    profile,
                    comparator_model,
                    scales,
                    rate_factor,
                    simulation_count,
                    confirmation_source,
                    pilot,
                    development,
                )
            ).encode("utf-8")
        )
        != frozen_hash
    ):
        raise RuntimeError("the frozen confirmation protocol changed while scoring SKAID")

    profile["validation"] = {
        "cleared": bool(confirmation["cleared"]),
        "acceptance_source": "SKAID participant-clustered untouched confirmation",
        "released_comparator_commit": RELEASED_BASELINE_COMMIT,
        "pilot": pilot,
        "development": development,
        "confirmation": confirmation,
        "frozen_protocol": frozen_protocol,
        "frozen_protocol_sha256": frozen_hash,
        "confirmation_source": confirmation_source,
    }
    profile["provenance"] = {
        "script": Path(__file__).name,
        "script_sha256": _hash(Path(__file__), "sha256"),
        "seed": SEED,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    return profile


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyrecs_csv", nargs="?", type=Path)
    parser.add_argument("--reproduce-failed-experiment", action="store_true")
    parser.add_argument("--skaid-archive", type=Path)
    parser.add_argument("--skaid-readme", type=Path)
    parser.add_argument("--skaid-demographics", type=Path)
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path)
    destination.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    if arguments.check:
        if not PROFILE_PATH.exists():
            print(f"{PROFILE_PATH} does not exist", file=sys.stderr)
            return 1
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        try:
            validate_release_artifact(profile)
        except (KeyError, TypeError, ValueError) as error:
            print(f"{PROFILE_PATH} is invalid: {error}", file=sys.stderr)
            return 1
        print(f"{PROFILE_PATH} passed local invariant checks")
        return 0
    if arguments.keyrecs_csv is None:
        raise SystemExit("keyrecs_csv is required unless --check is used")
    if arguments.reproduce_failed_experiment:
        if not all((arguments.skaid_archive, arguments.skaid_readme, arguments.skaid_demographics)):
            raise SystemExit("all SKAID inputs are required for the failed experiment")
        profile = derive(
            arguments.keyrecs_csv,
            arguments.skaid_archive,
            arguments.skaid_readme,
            arguments.skaid_demographics,
            verify_hashes=True,
        )
    else:
        if any((arguments.skaid_archive, arguments.skaid_readme, arguments.skaid_demographics)):
            raise SystemExit("SKAID inputs require --reproduce-failed-experiment")
        profile = derive_release(arguments.keyrecs_csv, verify_hashes=True)
    content = _serialized(profile)
    if arguments.output:
        arguments.output.write_text(content, encoding="utf-8")
        print(arguments.output)
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
