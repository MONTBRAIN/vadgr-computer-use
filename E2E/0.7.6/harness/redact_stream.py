# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Capture an agent JSONL stream while removing typed values at ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "expression",
        "password",
        "prompt",
        "secret",
        "text",
        "token",
        "value",
    }
)

# Keep only these public setup codes. Error messages can contain page data,
# local paths or secrets, so the surrounding text must still be removed.
SETUP_ERROR_CODES = frozenset(
    {"not_set_up", "extension_disabled", "extension_missing", "recovery_timed_out"}
)


def marker(value: str) -> dict[str, object]:
    return {
        "redacted": True,
        "length": len(value),
    }


def redact(value: Any, literals: tuple[str, ...], key: str | None = None) -> Any:
    if isinstance(value, dict):
        if value.get("type") in {"image", "audio"} and isinstance(value.get("data"), str):
            return {
                item_key: marker(item) if item_key == "data" else redact(
                    item, literals, str(item_key).lower()
                )
                for item_key, item in value.items()
            }
        return {
            item_key: redact(item, literals, str(item_key).lower())
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, literals) for item in value]
    if isinstance(value, str):
        if key == "text":
            try:
                nested = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
            else:
                return json.dumps(redact(nested, literals), separators=(",", ":"))
        if key in SENSITIVE_KEYS:
            result = marker(value)
            if key == "text":
                message = value.removeprefix("Error executing tool browser: ")
                for code in SETUP_ERROR_CODES:
                    if message.startswith(f"[{code}] "):
                        result["error_code"] = code
                        break
            return result
        replaced = value
        for literal in literals:
            replaced = replaced.replace(literal, "[redacted typed fixture]")
        try:
            nested = json.loads(replaced)
        except (json.JSONDecodeError, TypeError):
            return replaced
        return json.dumps(redact(nested, literals), separators=(",", ":"))
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sensitive-file", type=Path)
    args = parser.parse_args()
    literals: tuple[str, ...] = ()
    if args.sensitive_file:
        literals = tuple(
            line for line in args.sensitive_file.read_text(encoding="utf-8").splitlines() if line
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        for line in sys.stdin:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            output.write(json.dumps(redact(event, literals), separators=(",", ":")) + "\n")
            output.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
