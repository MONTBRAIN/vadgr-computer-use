#!/usr/bin/env python3
"""Prepare hash-bound, unapproved rule drafts from two retained review packets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging/profiles"))
from adoption_inputs import ARCHITECTURES, SIGNATURE_FIELDS, reviewed_digest
from build_profile_wheels import canonical, digest, freeze, read_json, safe_path
from producer import source_input

MAX_PACKET_BYTES = 16 * 1024 * 1024


def read_packet(directory: Path, receipt_sha256: str, architecture: str) -> tuple[dict, dict]:
    """A digest selected during review, never an adjacent receipt, establishes identity."""
    if not reviewed_digest(receipt_sha256):
        raise ValueError("an independently reviewed receipt SHA-256 is required")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("review packet must be a regular directory")
    files = {}
    total = 0
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("review packet contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("review packet contains a non-regular file")
        name = path.relative_to(directory).as_posix()
        safe_path(name)
        total += path.stat().st_size
        if total > MAX_PACKET_BYTES:
            raise ValueError("review packet exceeds its size limit")
        files[name] = path.read_bytes()
    raw = files.get("review-inputs.json", b"")
    if digest(raw) != receipt_sha256:
        raise ValueError("review receipt digest differs")
    receipt = read_json(raw)
    source = source_input()
    if (
        receipt.get("schema") != 1
        or receipt.get("mode") != "review-inputs"
        or receipt.get("architecture") != architecture
        or receipt.get("source_commit") != source["source_commit"]
        or receipt.get("version") != source["version"]
        or receipt.get("attempt") != 1
        or receipt.get("publishable") is not False
        or receipt.get("legal_approval") is not False
        or receipt.get("signing_approval") is not False
        or receipt.get("adoption") != "disabled"
    ):
        raise ValueError("review receipt target or unapproved state differs")
    expected = {"review-inputs.json"}
    for row in receipt["files"]:
        name = safe_path(row["path"])
        if name in expected or name not in files:
            raise ValueError("review packet has a duplicate or missing file")
        expected.add(name)
        if len(files[name]) != row["size"] or digest(files[name]) != row["sha256"]:
            raise ValueError("review packet file differs: " + name)
    if set(files) != expected:
        raise ValueError("review packet has an unrecorded file")
    if read_json(files["build-inputs/source-input.json"]) != source:
        raise ValueError("review packet source pin differs")
    inventory = read_json(files["member-inventory.json"])
    if (
        set(inventory) != {"schema", "architecture", "files"}
        or inventory["schema"] != 1
        or inventory["architecture"] != architecture
        or not isinstance(inventory["files"], list)
        or not inventory["files"]
    ):
        raise ValueError("review inventory target differs")
    rows = {}
    for member in inventory["files"]:
        if set(member) != {"path", "size", "sha256", "native_identity", "trust_class"}:
            raise ValueError("review member fields differ")
        name = safe_path(member["path"])
        if name.casefold() in {p.casefold() for p in rows}:
            raise ValueError("review member paths collide")
        if (
            not reviewed_digest(member["sha256"])
            or type(member["size"]) is not int
            or member["size"] < 0
            or member["trust_class"] is not None
            or member["native_identity"] not in (None, ["windows", architecture])
        ):
            raise ValueError("review member identity or approval state differs")
        row = dict.fromkeys(SIGNATURE_FIELDS)
        row["input_sha256"] = member["sha256"]
        # Native signature classes and algorithms require independent review.
        if member["native_identity"] is None:
            row["trust_class"] = "data"
        rows[name] = row
    return receipt, rows


def prepare(packets: dict[str, tuple[Path, str]], output: Path) -> dict:
    if output.exists():
        raise FileExistsError("review draft output must be new")
    rules = {
        "schema": 1,
        "expires_at": None,
        "source_sha_allowlist": [],
        "signer_sha_allowlist": [],
        "files": {},
    }
    binding = {"schema": 1, "mode": "unapproved-adoption-review", "packets": {}}
    common = None
    for architecture in ARCHITECTURES:
        directory, receipt_sha256 = packets[architecture]
        receipt, rows = read_packet(directory, receipt_sha256, architecture)
        identity = {key: receipt[key] for key in (
            "source_commit", "tooling_commit", "version", "run_id", "attempt"
        )}
        if common is not None and identity != common:
            raise ValueError("architecture review packets have different producer identities")
        common = identity
        rules["files"][architecture] = rows
        binding["packets"][architecture] = {
            **identity,
            "review_receipt_sha256": receipt_sha256,
            "input_closure": receipt["input_closure"],
            "member_count": len(rows),
            "native_member_count": sum(row["trust_class"] is None for row in rows.values()),
        }
    raw = canonical(rules)
    binding["draft_sha256"] = digest(raw)
    freeze(output / "adoption-rules.draft.json", raw)
    freeze(output / "review-binding.json", canonical(binding))
    return binding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("x86-64", "aarch64"):
        parser.add_argument(f"--{name}-review", type=Path, required=True)
        parser.add_argument(f"--{name}-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binding = prepare({
        "x86_64": (args.x86_64_review, args.x86_64_receipt_sha256),
        "aarch64": (args.aarch64_review, args.aarch64_receipt_sha256),
    }, args.output)
    for architecture, packet in binding["packets"].items():
        print(f"{architecture}: {packet['member_count']} exact members; "
              f"{packet['native_member_count']} native classifications remain unapproved")
    print("Draft prepared; legal, signing, producer authority and expiry remain unset")


if __name__ == "__main__":
    main()
