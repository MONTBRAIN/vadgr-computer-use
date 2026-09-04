# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Pure boundary-cluster classification shared by runtime and profile fitting."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

Boundary = Literal["clause", "sentence", "newline", "paragraph"]
KeyboardContext = Literal[
    "same_key",
    "same_finger",
    "same_hand",
    "alternate_hand",
    "other",
]
GapClass = Literal[
    "same_key",
    "same_finger",
    "same_hand",
    "alternate_hand",
    "other",
    "ordinary_space",
    "clause",
    "sentence",
    "newline",
    "paragraph",
]

_CLAUSE_MARKS = frozenset(",;:")
_SENTENCE_MARKS = frozenset(".?!")
_LINE_MARKS = frozenset("\r\n")
_CLUSTER_MARKS = _CLAUSE_MARKS | _SENTENCE_MARKS | _LINE_MARKS | frozenset(" \t")
_KEYS = {
    **{key: value for key, value in zip("12345", ((0, "L", index) for index in range(5)))},
    **{key: value for key, value in zip("67890", ((0, "R", index) for index in range(5)))},
    **{key: value for key, value in zip("qwert", ((1, "L", index) for index in range(5)))},
    **{key: value for key, value in zip("yuiop", ((1, "R", index) for index in range(5)))},
    **{key: value for key, value in zip("asdfg", ((2, "L", index) for index in range(5)))},
    **{key: value for key, value in zip("hjkl;", ((2, "R", index) for index in range(5)))},
    **{key: value for key, value in zip("zxcvb", ((3, "L", index) for index in range(5)))},
    **{key: value for key, value in zip("nm,./", ((3, "R", index) for index in range(5)))},
}


def _is_cluster_unit(unit: str) -> bool:
    return bool(unit) and all(character in _CLUSTER_MARKS for character in unit)


def _line_break_count(value: str) -> int:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.count("\n")


def _classify_cluster(value: str) -> Boundary | None:
    line_breaks = _line_break_count(value)
    if line_breaks >= 2:
        return "paragraph"
    if line_breaks == 1:
        return "newline"
    if any(character in _SENTENCE_MARKS for character in value):
        return "sentence"
    if any(character in _CLAUSE_MARKS for character in value):
        return "clause"
    return None


def classify_boundary_gaps(units: Sequence[str]) -> tuple[Boundary | None, ...]:
    """Classify at most one gap in each maximal punctuation/whitespace cluster.

    The event is attached to the first mark for the selected class. This keeps
    newline ownership on the newline even when punctuation precedes it. Leading
    and ordinary spaces remain unclassified. Classification uses the fixed
    precedence paragraph, newline, sentence, then clause.
    """
    boundaries: list[Boundary | None] = [None] * max(len(units) - 1, 0)
    cursor = 0
    while cursor < len(units):
        if not _is_cluster_unit(units[cursor]):
            cursor += 1
            continue
        end = cursor + 1
        while end < len(units) and _is_cluster_unit(units[end]):
            end += 1
        cluster = "".join(units[cursor:end])
        boundary = _classify_cluster(cluster)
        if boundary is not None:
            owner_marks = {
                "paragraph": _LINE_MARKS,
                "newline": _LINE_MARKS,
                "sentence": _SENTENCE_MARKS,
                "clause": _CLAUSE_MARKS,
            }[boundary]
            event = next(
                index
                for index in range(cursor, end)
                if any(character in owner_marks for character in units[index])
            )
            if event < len(boundaries):
                boundaries[event] = boundary
        cursor = end
    return tuple(boundaries)


def classify_keyboard_context(first: str, second: str) -> KeyboardContext:
    """Classify one non-boundary gap from observable US-keyboard positions."""
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


def classify_gap(first: str, second: str, boundary: Boundary | None) -> GapClass:
    """Assign the one observable class owned by the left unit of a gap."""
    if boundary is not None:
        return boundary
    if first == " ":
        return "ordinary_space"
    return classify_keyboard_context(first, second)


__all__ = [
    "Boundary",
    "GapClass",
    "KeyboardContext",
    "classify_boundary_gaps",
    "classify_gap",
    "classify_keyboard_context",
]
