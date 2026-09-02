#!/usr/bin/env python3
# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Derive the checked-in human typing profile from KeyRecs free-text data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SOURCE_SHA256 = "e38362914461c73a7ae6f25ac59304801f1324363d00ca00e059ac36e922c196"
SOURCE_MD5 = "a5ca6fcb0970cfdcd8eb958b3fe9f22a"
QUANTILE_PROBABILITIES = tuple(index / 100 for index in range(101))


def _hash(path: Path, name: str) -> str:
    digest = hashlib.new(name)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _weighted_quantiles(
    values: list[tuple[float, float]], probabilities: tuple[float, ...]
) -> list[float]:
    ordered = sorted(values)
    total = sum(weight for _, weight in ordered)
    targets = [probability * total for probability in probabilities]
    result: list[float] = []
    cumulative = 0.0
    target_index = 0
    for value, weight in ordered:
        cumulative += weight
        while target_index < len(targets) and cumulative >= targets[target_index]:
            result.append(value)
            target_index += 1
    result.extend([ordered[-1][0]] * (len(targets) - len(result)))
    return result


def derive(path: Path) -> dict[str, object]:
    sha256 = _hash(path, "sha256")
    md5 = _hash(path, "md5")
    if sha256 != SOURCE_SHA256 or md5 != SOURCE_MD5:
        raise SystemExit(f"source hash mismatch: sha256={sha256}, md5={md5}")

    raw_sessions: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    rejected_rows = 0
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
            if (
                not participant.startswith("p")
                or session not in {"1", "2"}
                or first is None
                or second is None
                or not 0 < interval_ms <= 1500
            ):
                rejected_rows += 1
                continue
            raw_sessions[(participant, session)].append((_bucket(first), interval_ms))

    participants: dict[str, list[dict[str, list[float]]]] = defaultdict(list)
    for (participant, _session), intervals in raw_sessions.items():
        mean = sum(value for _, value in intervals) / len(intervals)
        normalized: dict[str, list[float]] = defaultdict(list)
        for bucket, value in intervals:
            normalized[bucket].append(value / mean)
        participants[participant].append(dict(normalized))

    output: dict[str, list[float]] = {}
    counts: dict[str, dict[str, int]] = {}
    for bucket in ("within", "word", "sentence"):
        weighted: list[tuple[float, float]] = []
        participant_count = session_count = interval_count = 0
        for sessions in participants.values():
            eligible = [session[bucket] for session in sessions if session.get(bucket)]
            if not eligible:
                continue
            participant_count += 1
            session_count += len(eligible)
            interval_count += sum(len(values) for values in eligible)
            for values in eligible:
                weight = 1.0 / len(eligible) / len(values)
                weighted.extend((value, weight) for value in values)
        output[bucket] = [
            round(value, 6) for value in _weighted_quantiles(weighted, QUANTILE_PROBABILITIES)
        ]
        counts[bucket] = {
            "participants": participant_count,
            "sessions": session_count,
            "intervals": interval_count,
        }

    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "schema": 1,
        "profile": "us_adult_transcription_2026",
        "nominal_wpm": 38,
        "speed_source": {
            "doi": "10.1038/s41598-026-36500-7",
            "statistic": "rounded United States adult computer transcription median",
        },
        "residual_source": {
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
            "bytes": path.stat().st_size,
            "md5": md5,
            "sha256": sha256,
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
        },
        "filters": {
            "task": "free-text.csv transcription sessions only",
            "rows": "adjacent printable key pairs only; controls, malformed rows, and modifier transitions excluded",
            "interval_ms": "DD.key1.key2 greater than 0 and at most 1500",
            "normalization": "divide each participant session by its retained mean key-down interval",
            "weighting": "participants equal; sessions equal within participant; intervals equal within session and context bucket",
            "rejected_rows": rejected_rows,
        },
        "context_buckets": {
            "within": "first printable character is not whitespace or .?!",
            "word": "first printable character is whitespace",
            "sentence": "first printable character is .?!",
        },
        "counts": counts,
        "quantile_probabilities": list(QUANTILE_PROBABILITIES),
        "residual_quantiles": output,
        "derivation": {
            "path": "scripts/derive_typing_profile.py",
            "sha256": script_hash,
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
