#!/usr/bin/env python3
"""Export unapproved native review data without producing wheels or authority."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging/profiles"))
from producer import source_input
from build_profile_wheels import canonical, digest, freeze, helper_files, native_identity, read_json, zip_members


def review_preflight() -> None:
    """Require build pins only; final producer preflight remains independently strict."""
    source_input()
    base = ROOT / "packaging/profiles"
    for name in ("toolchain.json", "notice-inputs.json"):
        read_json((base / name).read_bytes())
    # The released predecessor record preserves its historical field order.
    json.loads((base / "predecessor-input.json").read_bytes())
    lock = ROOT / "requirements/windows-broker-build.txt"
    if not lock.is_file() or not lock.stat().st_size:
        raise ValueError("review build dependency lock is absent")


def hosted_identity() -> dict:
    expected = {
        "GITHUB_REPOSITORY": "MONTBRAIN/vadgr-computer-use",
        "GITHUB_REPOSITORY_ID": "1215350293",
        "GITHUB_REPOSITORY_OWNER_ID": "165305289",
        "GITHUB_REF": "refs/heads/master",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": "MONTBRAIN/vadgr-computer-use/.github/workflows/profile-review-inputs.yml@refs/heads/master",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("review producer must be the first trusted master dispatch")
    tooling = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", tooling) or tooling == "0" * 40 or not run_id.isdigit() or int(run_id) <= 0:
        raise ValueError("review producer exact identity is absent")
    return {"tooling_commit": tooling, "run_id": int(run_id), "attempt": 1}


def export(inputs: Path, output: Path, architecture: str) -> None:
    review_preflight()
    hosted = hosted_identity()
    source = source_input()
    if output.exists():
        raise FileExistsError("review output must be new")
    payload, helper = helper_files(inputs, architecture, source["version"], source["source_commit"])
    members = zip_members(payload[helper["archive"]["path"]])
    if "vadgr-cua-host.exe" in members:
        raise ValueError("relay collides with a broker member")
    members["vadgr-cua-host.exe"] = payload[helper["relay"]["path"]]
    rows = []
    notices = {}
    for name, data in sorted(members.items()):
        native = native_identity(data)
        if native is not None and native != ("windows", architecture):
            raise ValueError("review member architecture differs")
        rows.append({
            "path": name, "size": len(data), "sha256": digest(data),
            "native_identity": list(native) if native else None,
            "trust_class": None,
        })
        basename = Path(name).name.upper()
        if name.startswith("THIRD-PARTY-NOTICES/") or any(word in basename for word in ("LICENSE", "NOTICE", "COPYING", "COPYRIGHT")):
            if native is not None or data.startswith((b"PK", b"\x1f\x8b")):
                raise ValueError("review notice must not contain an executable or archive")
            data.decode("utf-8")
            notices["notices/" + name] = data
    if not notices:
        raise ValueError("native closure has no review notices")
    sboms = list(inputs.glob("*.spdx.json"))
    if len(sboms) != 1:
        raise ValueError("review requires one exact native SBOM")
    sbom_bytes = sboms[0].read_bytes()
    sbom = read_json(sbom_bytes)
    if sbom.get("spdxVersion") != "SPDX-2.3" or sbom.get("name") != f"vadgr-cua-browser-broker-{source['version']}-windows-{architecture}":
        raise ValueError("review SBOM target differs")
    sbom_rows = {row["fileName"]: row["checksums"] for row in sbom.get("files", [])}
    if len(sbom_rows) != len(sbom.get("files", [])) or any(
        sbom_rows.get("./" + name) != [{"algorithm": "SHA256", "checksumValue": digest(data)}]
        for name, data in members.items()
    ):
        raise ValueError("review SBOM member hashes differ")
    files = {
        "member-inventory.json": canonical({"schema": 1, "architecture": architecture, "files": rows}),
        "broker.manifest.json": payload[helper["member_manifest"]["path"]],
        "broker.spdx.json": sbom_bytes,
        **notices,
    }
    for name in ("source-input.json", "toolchain.json", "notice-inputs.json", "predecessor-input.json"):
        files["build-inputs/" + name] = (ROOT / "packaging/profiles" / name).read_bytes()
    files["build-inputs/windows-broker-build.txt"] = (ROOT / "requirements/windows-broker-build.txt").read_bytes()
    receipt = {
        "schema": 1, "mode": "review-inputs", "publishable": False,
        "legal_approval": False, "signing_approval": False, "adoption": "disabled",
        "architecture": architecture, "source_commit": source["source_commit"],
        "version": source["version"], **hosted,
        "input_closure": helper,
        "files": [{"path": name, "size": len(data), "sha256": digest(data)} for name, data in sorted(files.items())],
    }
    # No native payload, policy, wheel, catalog or attestation enters this output.
    for name, data in sorted(files.items()):
        freeze(output / name, data)
    freeze(output / "review-inputs.json", canonical(receipt))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--architecture", choices=("x86_64", "aarch64"))
    args = parser.parse_args()
    if args.preflight:
        review_preflight()
        print("Unsigned review build inputs verified; no legal or signing approval asserted")
    else:
        if not all((args.inputs, args.output, args.architecture)):
            parser.error("export requires inputs, output and architecture")
        export(args.inputs, args.output, args.architecture)
        print("Unapproved review packet retained; no installable or signed output produced")


if __name__ == "__main__":
    main()
