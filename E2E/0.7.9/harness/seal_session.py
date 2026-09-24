"""Retain observed CUA calls and results, omitting driver account metadata."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path

REDACTOR_SOURCE = Path(__file__).resolve().parents[2] / "0.7.6/harness/redact_stream.py"
PRIVATE_ARTIFACT_NAMES = {"registry-backup.json"}
spec = importlib.util.spec_from_file_location("cua_e2e_redact_stream", REDACTOR_SOURCE)
redactor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redactor)


def scrub_private_identity(value, roots):
    if isinstance(value, dict):
        return {key: scrub_private_identity(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_private_identity(item, roots) for item in value]
    if isinstance(value, str):
        for root in roots:
            value = value.replace(root, "<private-root>").replace(
                root.replace("\\", "/"), "<private-root>"
            )
        return re.sub(r"S-1-5-21-(?:\d+-){2,}\d+", "<owner-sid>", value)
    return value


def clean(value, roots):
    """Use the audited stream redactor, then remove owner-private identities."""
    return scrub_private_identity(redactor.redact(value, ()), roots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--private-root", action="append", default=[])
    parser.add_argument(
        "--artifacts-only",
        action="store_true",
        help="seal JSON receipts without inventing an agent stream",
    )
    args = parser.parse_args()
    roots = sorted([*args.private_root, os.environ.get("USERPROFILE", "")], key=len, reverse=True)
    roots = [root for root in roots if root]
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=True)
    seen = set()
    calls = results = errors = 0
    if not args.artifacts_only:
        with (destination / "agent.jsonl").open("x", encoding="utf-8") as output:
            for line in (args.source / "agent.jsonl").read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                for block in event.get("message", {}).get("content", []):
                    if not isinstance(block, dict):
                        continue
                    keep = False
                    if block.get("type") == "tool_use" and block.get("name", "").startswith(
                        "mcp__cua__"
                    ):
                        seen.add(block["id"])
                        calls += 1
                        keep = True
                    elif block.get("type") == "tool_result" and block.get("tool_use_id") in seen:
                        results += 1
                        errors += bool(block.get("is_error"))
                        keep = True
                    if keep:
                        output.write(
                            json.dumps(
                                clean(
                                    {
                                        "timestamp": event.get("timestamp"),
                                        "type": event["type"],
                                        "message": {"content": [block]},
                                    },
                                    roots,
                                ),
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
    for path in args.source.glob("*.json"):
        if path.name.endswith(".private.json") or path.name in PRIVATE_ARTIFACT_NAMES:
            continue
        raw = path.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        value = json.loads(raw.decode(encoding))
        with (destination / path.name).open("x", encoding="utf-8") as output:
            json.dump(clean(value, roots), output, indent=2)
            output.write("\n")
    print(
        json.dumps(
            {
                "mode": "artifacts-only" if args.artifacts_only else "agent-stream",
                "calls": calls,
                "results": results,
                "error_results": errors,
                "verdict": "unreviewed: counts alone do not prove a cell",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
