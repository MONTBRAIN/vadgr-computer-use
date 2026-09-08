# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Capture an agent JSONL stream while removing typed values at ingestion."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "command",
        "expression",
        "password",
        "prompt",
        "secret",
        "text",
        "token",
        "value",
    }
)

# Keep only public browser codes. Error messages can contain page data,
# local paths or secrets, so the surrounding text must still be removed.
BROWSER_ERROR_CODES = frozenset(
    {
        "not_set_up",
        "not_connected",
        "op_unsupported",
        "proto_mismatch",
        "waking",
        "op_failed",
        "target_lost",
        "profile_ambiguous",
        "target_owned_by_another_client",
        "recovery_timed_out",
        "extension_disabled",
        "extension_missing",
        "typing_mismatch",
        "typing_deadline_exceeded",
        "typing_cancelled",
        "typing_state_uncertain",
        "inactive_tab_trusted_keyboard_unsupported",
        "target_discarded",
        "target_frozen",
        "target_restricted",
    }
)

# Exact public messages only. These annotations preserve observed text, not an
# isError flag: some drivers omit that wire field even for failed tool calls.
TYPING_ERROR_MESSAGES = frozenset(
    {"Error executing tool type_text"}
    | {
        f"Error executing tool type_text: {message}"
        for message in (
            "typing_options_require_human",
            "timing_profile and custom timing are mutually exclusive",
            "custom timing requires both wpm and iki_cv",
            "wpm must be an integer",
            "wpm must be from 10 through 200",
            "iki_cv must be finite and from 0 through 1",
            "timeout must be a positive finite number of milliseconds",
        )
    }
)
TYPING_INTERRUPTION = re.compile(
    r"Error executing tool type_text: "
    r"(typing_cancelled|typing_deadline_exceeded): ([0-9]{1,12}) complete units"
)


def marker(value: str) -> dict[str, object]:
    return {
        "redacted": True,
        "length": len(value),
    }


def redact(value: Any, literals: tuple[str, ...], key: str | None = None) -> Any:
    if isinstance(value, dict):
        if value.get("type") == "control_response":
            response = value.get("response")
            payload = response.get("response") if isinstance(response, dict) else None
            if isinstance(payload, dict) and "account" in payload:
                value = dict(value)
                response = dict(response)
                response["response"] = {**payload, "account": {"redacted": True}}
                value["response"] = response
        if value.get("type") in {"image", "audio"} and isinstance(value.get("source"), dict):
            value = dict(value)
            source = dict(value["source"])
            if isinstance(source.get("data"), str):
                source["data"] = marker(source["data"])
            value["source"] = source
        if value.get("type") in {"image", "audio"} and isinstance(value.get("data"), str):
            return {
                item_key: marker(item)
                if item_key == "data"
                else redact(item, literals, str(item_key).lower())
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
                if value in TYPING_ERROR_MESSAGES:
                    result["error_message"] = value
                interruption = TYPING_INTERRUPTION.fullmatch(value)
                if interruption:
                    result["error_code"] = interruption[1]
                    result["completed_units"] = int(interruption[2])
                message = value.removeprefix("Error executing tool browser: ")
                for code in BROWSER_ERROR_CODES:
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
