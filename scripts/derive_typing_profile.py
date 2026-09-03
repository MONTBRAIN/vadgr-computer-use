#!/usr/bin/env python3
# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Fit and validate the checked-in human typing cadence profile."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SOURCE_SHA256 = "e38362914461c73a7ae6f25ac59304801f1324363d00ca00e059ac36e922c196"
SOURCE_MD5 = "a5ca6fcb0970cfdcd8eb958b3fe9f22a"
QUANTILES = tuple(index / 100 for index in range(1, 100))
MIN_INTERVAL_MS = 20.0
MAX_INTERVAL_MS = 1500.0
SPACE_MAX_MS = 300.0
PAUSE_THRESHOLD_MS = 40.0

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


@dataclass(frozen=True)
class Gap:
    participant: str
    session: str
    order: int
    first: str
    second: str
    interval_ms: float
    boundary: str | None
    context: str


def _hash(path: Path, name: str) -> str:
    digest = hashlib.new(name)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _character(key: str) -> str | None:
    if key == "Space":
        return " "
    if key in {"Enter", "Return"}:
        return "\n"
    return key if len(key) == 1 and key.isprintable() else None


def _boundary(first: str, second: str) -> str | None:
    if first == "\n":
        return "paragraph" if second == "\n" else "newline"
    if first in ".?!":
        return "sentence"
    if first in ",;:":
        return "clause"
    return None


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


def _read(path: Path) -> tuple[list[Gap], int]:
    gaps: list[Gap] = []
    rejected = 0
    order: dict[tuple[str, str], int] = defaultdict(int)
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            participant = str(row.get("participant", ""))
            session = str(row.get("session", ""))
            first = _character(str(row.get("key1", "")))
            second = _character(str(row.get("key2", "")))
            try:
                interval_ms = float(row.get("DD.key1.key2", "")) * 1000
            except (TypeError, ValueError):
                interval_ms = -1
            key = (participant, session)
            position = order[key]
            order[key] += 1
            if (
                not participant.startswith("p")
                or session not in {"1", "2"}
                or first is None
                or second is None
                or not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS
            ):
                rejected += 1
                continue
            boundary = _boundary(first, second)
            gaps.append(
                Gap(
                    participant,
                    session,
                    position,
                    first,
                    second,
                    interval_ms,
                    boundary,
                    _context(first, second, boundary),
                )
            )
    return gaps, rejected


def _quantiles(values: list[float] | np.ndarray) -> list[float]:
    return [round(float(value), 8) for value in np.quantile(values, QUANTILES)]


def _piecewise_log_density(values: np.ndarray, quantiles: np.ndarray) -> np.ndarray:
    indexes = np.searchsorted(quantiles, values, side="right")
    indexes = np.clip(indexes, 1, len(quantiles) - 1)
    widths = np.maximum(quantiles[indexes] - quantiles[indexes - 1], 1e-6)
    return np.log(0.01 / widths)


def _pinball(values: np.ndarray, predictions: np.ndarray | float, probability: float) -> float:
    errors = values - predictions
    return float(np.mean(np.maximum(probability * errors, (probability - 1) * errors)))


def _fit_components(gaps: list[Gap]) -> dict[str, object]:
    by_session: dict[tuple[str, str], list[Gap]] = defaultdict(list)
    for gap in gaps:
        by_session[(gap.participant, gap.session)].append(gap)

    baselines: dict[tuple[str, str], float] = {}
    for key, session in by_session.items():
        values = [
            gap.interval_ms
            for gap in session
            if gap.boundary is None and gap.context not in {"ordinary_space", "other"}
        ]
        if len(values) >= 20:
            baselines[key] = statistics.median(values)

    retained = [gap for gap in gaps if (gap.participant, gap.session) in baselines]
    context_logs: dict[str, list[float]] = defaultdict(list)
    for gap in retained:
        if gap.boundary is not None:
            continue
        observed = min(gap.interval_ms, SPACE_MAX_MS) if gap.context == "ordinary_space" else gap.interval_ms
        context_logs[gap.context].append(
            math.log(observed / baselines[(gap.participant, gap.session)])
        )
    context_effects = {name: statistics.median(values) for name, values in context_logs.items()}

    session_residuals: dict[tuple[str, str], list[tuple[int, str, str, float]]] = defaultdict(list)
    context_counts: dict[str, int] = defaultdict(int)
    for gap in retained:
        if gap.boundary is not None:
            continue
        observed = min(gap.interval_ms, SPACE_MAX_MS) if gap.context == "ordinary_space" else gap.interval_ms
        residual = math.log(observed / baselines[(gap.participant, gap.session)]) - context_effects[gap.context]
        session_residuals[(gap.participant, gap.session)].append(
            (gap.order, gap.first, gap.second, residual)
        )
        context_counts[gap.context] += 1

    pairs: list[tuple[str, tuple[str, str], float, float]] = []
    for key, rows in session_residuals.items():
        rows.sort()
        for previous, current in zip(rows, rows[1:]):
            if current[0] == previous[0] + 1 and previous[2] == current[1]:
                pairs.append((key[0], key, previous[3], current[3]))

    x = np.asarray([pair[2] for pair in pairs])
    y = np.asarray([pair[3] for pair in pairs])
    phi = min(max(float(np.dot(x, y) / max(float(np.dot(x, x)), 1e-12)), 0.0), 0.95)
    innovations = y - phi * x
    innovation_scale = float(np.std(innovations)) or 1.0
    normalized_innovations = innovations / innovation_scale

    central_baseline = statistics.median(baselines.values())
    speed_logs = [math.log(value / central_baseline) for value in baselines.values()]
    speed_low, speed_high = np.quantile(speed_logs, (0.05, 0.95))

    boundary_positive: dict[str, int] = defaultdict(int)
    boundary_total: dict[str, int] = defaultdict(int)
    pause_logs: dict[str, list[float]] = defaultdict(list)
    session_positive: dict[tuple[str, str], int] = defaultdict(int)
    session_total: dict[tuple[str, str], int] = defaultdict(int)
    for gap in retained:
        if gap.boundary is None:
            continue
        key = (gap.participant, gap.session)
        motor = baselines[key] * math.exp(context_effects.get(gap.context, 0.0))
        pause = max(gap.interval_ms - motor, 0.0)
        boundary_total[gap.boundary] += 1
        session_total[key] += 1
        if pause >= PAUSE_THRESHOLD_MS:
            boundary_positive[gap.boundary] += 1
            session_positive[key] += 1
            pause_logs[gap.boundary].append(math.log(pause))

    global_pause_rate = sum(boundary_positive.values()) / max(sum(boundary_total.values()), 1)
    styles: list[dict[str, float]] = []
    pairs_by_session: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for _, key, previous, current in pairs:
        pairs_by_session[key].append((previous, current))
    for key, baseline in sorted(baselines.items()):
        local = pairs_by_session[key]
        if local:
            local_x = np.asarray([pair[0] for pair in local])
            local_y = np.asarray([pair[1] for pair in local])
            local_phi = min(
                max(float(np.dot(local_x, local_y) / max(float(np.dot(local_x, local_x)), 1e-12)), 0.0),
                0.9,
            )
            scale = float(np.std(local_y - local_phi * local_x)) / innovation_scale
        else:
            local_phi = phi
            scale = 1.0
        smoothed_rate = (session_positive[key] + 4 * global_pause_rate) / (session_total[key] + 4)
        styles.append(
            {
                "speed_log": round(min(max(math.log(baseline / central_baseline), speed_low), speed_high), 8),
                "persistence": round(local_phi, 8),
                "innovation_scale": round(min(max(scale, 0.5), 1.5), 8),
                "boundary_scale": round(min(max(smoothed_rate / max(global_pause_rate, 1e-9), 0.5), 1.5), 8),
            }
        )

    boundaries: dict[str, object] = {}
    for name in ("clause", "sentence", "newline", "paragraph"):
        values = pause_logs[name]
        boundaries[name] = {
            "probability": round(boundary_positive[name] / max(boundary_total[name], 1), 8),
            "count": boundary_total[name],
            "positive_count": boundary_positive[name],
            "log_pause_quantiles": _quantiles(values),
        }
    return {
        "retained": retained,
        "context_effects": context_effects,
        "context_counts": context_counts,
        "pairs": pairs,
        "phi": phi,
        "innovation_scale": innovation_scale,
        "normalized_innovations": normalized_innovations,
        "styles": styles,
        "boundaries": boundaries,
    }


def _validate(components: dict[str, object]) -> dict[str, object]:
    pairs = components["pairs"]
    assert isinstance(pairs, list)
    participants = sorted({pair[0] for pair in pairs})
    totals = defaultdict(float)
    observations = 0
    folds = 0
    for participant in participants:
        train = [pair for pair in pairs if pair[0] != participant]
        test = [pair for pair in pairs if pair[0] == participant]
        if len(test) < 20:
            continue
        train_x = np.asarray([pair[2] for pair in train])
        train_y = np.asarray([pair[3] for pair in train])
        test_x = np.asarray([pair[2] for pair in test])
        test_y = np.asarray([pair[3] for pair in test])
        phi = min(max(float(np.dot(train_x, train_y) / max(float(np.dot(train_x, train_x)), 1e-12)), 0.0), 0.95)
        train_innovations = train_y - phi * train_x
        test_innovations = test_y - phi * test_x
        baseline_quantiles = np.quantile(train_y, QUANTILES)
        candidate_quantiles = np.quantile(train_innovations, QUANTILES)
        totals["baseline_nll"] -= float(np.sum(_piecewise_log_density(test_y, baseline_quantiles)))
        totals["candidate_nll"] -= float(np.sum(_piecewise_log_density(test_innovations, candidate_quantiles)))
        for probability in (0.1, 0.25, 0.5, 0.75, 0.9):
            totals["baseline_pinball"] += _pinball(
                test_y, float(np.quantile(train_y, probability)), probability
            ) * len(test_y)
            totals["candidate_pinball"] += _pinball(
                test_y,
                phi * test_x + float(np.quantile(train_innovations, probability)),
                probability,
            ) * len(test_y)
        observed_correlation = float(np.corrcoef(test_x, test_y)[0, 1])
        if math.isfinite(observed_correlation):
            totals["baseline_correlation"] += abs(observed_correlation)
            totals["candidate_correlation"] += abs(observed_correlation - phi)
        threshold = float(np.quantile(train_y, 0.75))
        observed_transition = float(np.mean((test_x > threshold) & (test_y > threshold)))
        train_transition = float(np.mean((train_x > threshold) & (train_y > threshold)))
        baseline_transition = float(np.mean(train_x > threshold) * np.mean(train_y > threshold))
        totals["candidate_burst"] += abs(observed_transition - train_transition)
        totals["baseline_burst"] += abs(observed_transition - baseline_transition)
        observations += len(test_y)
        folds += 1

    metrics = {
        "folds": folds,
        "observations": observations,
        "negative_log_likelihood_per_gap": {
            "released_independent": round(totals["baseline_nll"] / observations, 8),
            "context_ar1": round(totals["candidate_nll"] / observations, 8),
        },
        "weighted_decile_loss_per_gap": {
            "released_independent": round(totals["baseline_pinball"] / observations, 8),
            "context_ar1": round(totals["candidate_pinball"] / observations, 8),
        },
        "absolute_lag_one_correlation_error": {
            "released_independent": round(totals["baseline_correlation"] / folds, 8),
            "context_ar1": round(totals["candidate_correlation"] / folds, 8),
        },
        "slow_burst_transition_error": {
            "released_independent": round(totals["baseline_burst"] / folds, 8),
            "context_ar1": round(totals["candidate_burst"] / folds, 8),
        },
    }
    boundaries = components["boundaries"]
    clause_median = boundaries["clause"]["log_pause_quantiles"][49]
    sentence_median = boundaries["sentence"]["log_pause_quantiles"][49]
    boundary_ordering = clause_median < sentence_median
    finite_support = all(
        math.isfinite(value)
        for boundary in boundaries.values()
        for value in boundary["log_pause_quantiles"]
    )
    cleared = (
        metrics["negative_log_likelihood_per_gap"]["context_ar1"]
        < metrics["negative_log_likelihood_per_gap"]["released_independent"]
        and metrics["weighted_decile_loss_per_gap"]["context_ar1"]
        < metrics["weighted_decile_loss_per_gap"]["released_independent"]
        and metrics["absolute_lag_one_correlation_error"]["context_ar1"]
        <= metrics["absolute_lag_one_correlation_error"]["released_independent"]
        and metrics["slow_burst_transition_error"]["context_ar1"]
        <= metrics["slow_burst_transition_error"]["released_independent"]
        and boundary_ordering
        and finite_support
    )
    return {
        "method": "grouped leave-one-participant-out",
        "baseline": "released independent empirical sampler",
        "candidate": "context-conditioned AR(1) Markov renewal model",
        "metrics": metrics,
        "hard_gates": {
            "finite_support": finite_support,
            "ordinary_space_pause_probability": 0,
            "ordinary_space_max_ms": SPACE_MAX_MS,
            "clause_median_below_sentence_median": boundary_ordering,
        },
        "cleared": cleared,
    }


def derive(path: Path) -> dict[str, object]:
    sha256 = _hash(path, "sha256")
    md5 = _hash(path, "md5")
    if sha256 != SOURCE_SHA256 or md5 != SOURCE_MD5:
        raise SystemExit(f"source hash mismatch: sha256={sha256}, md5={md5}")
    gaps, rejected = _read(path)
    components = _fit_components(gaps)
    validation = _validate(components)
    if not validation["cleared"]:
        raise SystemExit(f"candidate did not clear the fit gate: {validation['metrics']}")
    retained = components["retained"]
    context_counts = components["context_counts"]
    boundary_counts = {
        name: model["count"] for name, model in components["boundaries"].items()
    }
    total_contexts = len(retained)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "schema": 2,
        "profile": "us_adult_transcription_2026",
        "nominal_wpm": 65,
        "limits": {
            "minimum_interval_ms": MIN_INTERVAL_MS,
            "maximum_interval_ms": MAX_INTERVAL_MS,
            "maximum_custom_interval_ms": 4000.0,
            "ordinary_space_max_ms": SPACE_MAX_MS,
            "maximum_iki_cv": 1.0,
            "minimum_validation_graphemes": 200,
        },
        "selected_model": "context_ar1",
        "speed_source": {
            "doi": "10.1136/bmj-2022-072784",
            "statistic": "rounded corrected mean among trained professional computer users",
        },
        "residual_source": {
            "title": "KeyRecs: Keystroke Dynamics Dataset",
            "authors": ["Tiago Dias", "João Vitorino", "Eva Maia", "Orlando Sousa", "Isabel Praça"],
            "doi": "10.5281/zenodo.7886743",
            "article_doi": "10.1016/j.dib.2023.109509",
            "file": "free-text.csv",
            "bytes": path.stat().st_size,
            "md5": md5,
            "sha256": sha256,
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
        },
        "filters": {
            "task": "free-text.csv transcription sessions only",
            "rows": "adjacent printable, space, and enter pairs with 20 through 1500 ms key-down intervals",
            "session_baseline": "median non-boundary, non-space mapped-key interval with at least 20 observations",
            "ordinary_space": "motor observation capped at the 300 ms product bound; semantic pause fixed to zero",
            "rejected_rows": rejected,
            "retained_rows": len(retained),
        },
        "motor": {
            "context_log_effects": {
                key: round(float(value), 8)
                for key, value in sorted(components["context_effects"].items())
            },
            "reference_context_weights": {
                key: round(value / total_contexts, 10)
                for key, value in sorted(context_counts.items())
            },
            "reference_boundary_context_weights": {
                key: round(value / total_contexts, 10)
                for key, value in sorted(
                    {
                        context: sum(
                            1
                            for gap in retained
                            if gap.boundary is not None and gap.context == context
                        )
                        for context in context_counts
                    }.items()
                )
                if value
            },
            "pooled_persistence": round(float(components["phi"]), 8),
            "innovation_log_scale": round(float(components["innovation_scale"]), 8),
            "innovation_quantiles": _quantiles(components["normalized_innovations"]),
        },
        "styles": components["styles"],
        "boundaries": components["boundaries"],
        "reference_boundary_weights": {
            key: round(value / total_contexts, 10)
            for key, value in sorted(boundary_counts.items())
        },
        "calibration": {
            "equation": "mean_style(12000 / expected_gap_ms_given_style) = nominal_wpm",
            "custom": "solve again for each accepted wpm and iki_cv pair",
        },
        "validation": validation,
        "derivation": {
            "path": "scripts/derive_typing_profile.py",
            "sha256": script_hash,
            "python": "3.12",
            "numpy": np.__version__,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("free_text_csv", type=Path)
    args = parser.parse_args()
    print(json.dumps(derive(args.free_text_csv), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
