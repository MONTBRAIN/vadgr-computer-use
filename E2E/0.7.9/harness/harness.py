"""Prepare and account for isolated 0.7.9 observations; never drive the product."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = ".cua-079-root.json"
REPO = Path(__file__).resolve().parents[3]
RUNBOOK = REPO / "E2E" / "0.7.9" / "e2e.md"
CELL = re.compile(r"^### (P\d{2}-[a-z0-9_-]+): (.+)$", re.MULTILINE)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def checked_root(path: Path) -> Path:
    original = path.absolute()
    root = path.resolve(strict=True)
    if original != root or root.is_symlink() or not root.name.startswith("vadgr-cua-079-"):
        raise ValueError("root must be an unre-directed isolated 0.7.9 directory")
    marker = json.loads((root / MARKER).read_text(encoding="utf-8"))
    if marker != {"root": str(root), "schema": 1}:
        raise ValueError("root marker does not match")
    for parent in [root, *root.parents]:
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("root crosses a symlink or junction")
    return root


def initialize(parent: Path) -> Path:
    parent = parent.resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="vadgr-cua-079-", dir=parent))
    write_new(root / MARKER, {"root": str(root), "schema": 1})
    for name in ("home", "appdata", "localappdata", "state", "work", "build"):
        (root / name).mkdir()
    return root


def mcp_config(root: Path, entry: Path) -> dict:
    root = checked_root(root)
    entry = entry.resolve(strict=True)
    if entry.name not in ("vadgr-cua", "vadgr-cua.exe") or REPO in entry.parents:
        raise ValueError("use the installed public entry point outside the checkout")
    env = {"HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
           "APPDATA": str(root / "appdata"), "LOCALAPPDATA": str(root / "localappdata"),
           "XDG_CONFIG_HOME": str(root / "home" / ".config"),
           "XDG_STATE_HOME": str(root / "state")}
    config = {"mcpServers": {"cua": {"command": str(entry),
                                     "args": ["--transport", "stdio"], "env": env}}}
    write_new(root / "work" / ".mcp.json", config)
    # CLI overrides carry only paths. Driver authentication remains in its own environment.
    quote = lambda value: json.dumps(value, ensure_ascii=True)
    overrides = ["-c", "mcp_servers.cua.command=" + quote(str(entry)),
                 "-c", 'mcp_servers.cua.args=["--transport","stdio"]',
                 "-c", "mcp_servers.cua.env={" + ",".join(
                     key + "=" + quote(value) for key, value in env.items()) + "}"]
    return {"claude_mcp_config": str(root / "work" / ".mcp.json"),
            "codex_override_argv": overrides, "product_child_env": env}


def cells(runbook: Path = RUNBOOK) -> list[dict]:
    source = runbook.read_text(encoding="utf-8")
    matches = list(CELL.finditer(source))
    result = []
    for number, match in enumerate(matches):
        end = matches[number + 1].start() if number + 1 < len(matches) else len(source)
        block = source[match.end():end]
        fields = {}
        for field in ("Precondition", "Setup", "Task given to the agent", "Expected result",
                      "Verdict from the JSON", "Evidence boundary", "Cleanup", "Result"):
            found = re.search(rf"^\*\*{re.escape(field)}:\*\* (.+)$", block, re.MULTILINE)
            if not found:
                raise ValueError(f"{match[1]} lacks {field}")
            fields[field] = found[1]
        result.append({"id": match[1], "title": match[2], **fields})
    if not result or len({item["id"] for item in result}) != len(result):
        raise ValueError("missing or duplicate cell IDs")
    if {item["id"].split("-")[0] for item in result} != {f"P{i:02}" for i in range(1, 15)}:
        raise ValueError("P01-P14 must all be expanded")
    return result


def preflight(root: Path, entry: Path, evidence: Path, head: str, evidence_pr: str) -> dict:
    root = checked_root(root)
    entry = entry.resolve(strict=True)
    evidence = evidence.resolve(strict=True)
    if root == evidence or root in evidence.parents:
        raise ValueError("evidence must be outside the disposable root")
    if REPO == entry or REPO in entry.parents:
        raise ValueError("entry point must be installed outside the checkout")
    if entry.name not in ("vadgr-cua", "vadgr-cua.exe"):
        raise ValueError("use the installed public vadgr-cua entry point")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("exact source head required")
    if not re.fullmatch(r"https://github.com/[^/]+/[^/]+/pull/[1-9][0-9]*", evidence_pr):
        raise ValueError("resolved evidence pull request required")
    actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                           text=True, check=True).stdout
    if actual != head or dirty:
        raise ValueError("source must be clean and match the tested head")
    return {"schema": 1, "head": head, "entry_sha256": digest(entry),
            "evidence_pr": evidence_pr, "free_bytes": shutil.disk_usage(root).free,
            "cells": len(cells()), "codex_available": shutil.which("codex") is not None,
            "claude_available": shutil.which("claude") is not None}


def record(evidence: Path, cell: str, artifacts: list[Path]) -> dict:
    if cell not in {item["id"] for item in cells()}:
        raise ValueError("unknown written cell")
    evidence = evidence.resolve(strict=True)
    rows = []
    for artifact in artifacts:
        path = artifact.resolve(strict=True)
        if evidence not in path.parents or not path.is_file():
            raise ValueError("artifact must be a file already inside the evidence boundary")
        if path.name in (".env", "auth.json", "credentials.json"):
            raise ValueError("credential files are not evidence")
        rows.append({"path": path.relative_to(evidence).as_posix(),
                     "size": path.stat().st_size, "sha256": digest(path)})
    if not rows:
        raise ValueError("an evidence record must contain real artifacts")
    result = {"schema": 1, "cell": cell, "artifacts": rows,
              "verdict": "unreviewed: hashes do not prove a live result"}
    write_new(evidence / f"{cell}.artifacts.json", result)
    return result


def cleanup(root: Path, evidence: Path, execute: bool = False) -> dict:
    root = checked_root(root)
    evidence = evidence.resolve(strict=True)
    if root == evidence or root in evidence.parents:
        raise ValueError("evidence cannot be inside the cleanup root")
    target = root.with_name(root.name + ".cleanup-pending")
    result = {"action": "move to recoverable sibling", "root": str(root),
              "destination": str(target), "executed": False}
    if not execute:
        return result
    # A clean pushed evidence checkout is required before test state is retired.
    for argv in (["git", "diff", "--exit-code"], ["git", "diff", "--cached", "--exit-code"]):
        subprocess.run(argv, cwd=evidence, capture_output=True, check=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=evidence,
                            capture_output=True, text=True, check=True)
    if status.stdout.strip():
        raise ValueError("evidence checkout has uncommitted files")
    for rev in ("HEAD", "@{upstream}"):
        completed = subprocess.run(["git", "rev-parse", rev], cwd=evidence,
                                   capture_output=True, text=True, check=True)
        result[rev] = completed.stdout.strip()
    if result["HEAD"] != result["@{upstream}"]:
        raise ValueError("evidence HEAD is not the pushed upstream HEAD")
    release = json.loads((root / "cleanup-clearance.json").read_text(encoding="utf-8"))
    if release != {"owned_processes_stopped": True, "owner_references_checked": True,
                   "root": str(root)}:
        raise ValueError("manual process and owner-launcher checks are required")
    if target.exists():
        raise ValueError("cleanup destination already exists")
    root.rename(target)
    result["executed"] = True
    result["reclaimed_bytes"] = 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--parent", type=Path, default=Path(tempfile.gettempdir()))
    sub.add_parser("status")
    config = sub.add_parser("mcp-config")
    config.add_argument("--root", type=Path, required=True)
    config.add_argument("--entry", type=Path, required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--root", type=Path, required=True)
    pre.add_argument("--entry", type=Path, required=True)
    pre.add_argument("--evidence", type=Path, required=True)
    pre.add_argument("--head", required=True)
    pre.add_argument("--evidence-pr", required=True)
    rec = sub.add_parser("evidence")
    rec.add_argument("--evidence", type=Path, required=True)
    rec.add_argument("--cell", required=True)
    rec.add_argument("artifacts", type=Path, nargs="+")
    clean = sub.add_parser("cleanup")
    clean.add_argument("--root", type=Path, required=True)
    clean.add_argument("--evidence", type=Path, required=True)
    clean.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = {"root": str(initialize(args.parent))}
        elif args.command == "status":
            result = {"cells": [{"id": c["id"], "result": c["Result"]} for c in cells()]}
        elif args.command == "mcp-config":
            result = mcp_config(args.root, args.entry)
        elif args.command == "preflight":
            result = preflight(args.root, args.entry, args.evidence, args.head, args.evidence_pr)
        elif args.command == "evidence":
            result = record(args.evidence, args.cell, args.artifacts)
        else:
            result = cleanup(args.root, args.evidence, args.execute)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"harness refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
