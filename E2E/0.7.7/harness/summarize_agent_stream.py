#!/usr/bin/env python3
"""Summarize a Codex JSONL stream without retaining text, paths or account data."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def strings(value, key: str):
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key and isinstance(child, str):
                yield child
            yield from strings(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child, key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stream", type=Path)
    args = parser.parse_args()
    events = []
    for line in args.stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append(value)
    types = collections.Counter(str(event.get("type", "unknown")) for event in events)
    names = sorted(
        {
            name
            for event in events
            for name in strings(event, "name")
            if name.startswith("mcp__cua__")
        }
    )
    codes = sorted(
        {
            code
            for event in events
            for code in strings(event, "code")
            if code.startswith(("browser_", "target_", "window_"))
        }
    )
    print(
        json.dumps(
            {
                "event_count": len(events),
                "event_types": dict(sorted(types.items())),
                "mcp_tools": names,
                "public_error_codes": codes,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
