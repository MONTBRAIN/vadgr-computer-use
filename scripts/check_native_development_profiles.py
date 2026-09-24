#!/usr/bin/env python3
"""Validate exact non-publishable Linux and macOS development artifacts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from build_profile_wheels import PREFIX, digest, interpreter, read_json, zip_members
from check_profile_wheels import (
    check_manifest,
    check_record,
    checked_file,
    exact_keys,
    package_trust,
)


def check_native_development_receipt(path: Path) -> dict:
    receipt = read_json(path.read_bytes())
    exact_keys(
        receipt,
        {
            "schema",
            "development",
            "publishable",
            "signing",
            "adoption",
            "source_commit",
            "platform",
            "architecture",
            "artifacts",
        },
        "native development receipt",
    )
    platform, architecture = receipt["platform"], receipt["architecture"]
    profile = f"{platform}-{architecture}"
    if (
        receipt["schema"] != 1
        or receipt["development"] is not True
        or receipt["publishable"] is not False
        or receipt["signing"] != "not-applicable"
        or receipt["adoption"] != "disabled"
        or platform not in {"linux", "macos"}
        or architecture not in {"x86_64", "aarch64"}
        or not re.fullmatch(r"[0-9a-f]{40}", receipt["source_commit"])
    ):
        raise ValueError("native development receipt identity differs")
    if set(receipt["artifacts"]) != {"managed", "standalone"}:
        raise ValueError("native development artifact set differs")
    root = path.parent
    manifest_raw = None
    for kind in ("managed", "standalone"):
        artifact = receipt["artifacts"][kind]
        exact_keys(artifact, {"release_profile", "wheel", "manifest"}, "development artifact")
        if artifact["release_profile"] != profile:
            raise ValueError("development artifact profile differs")
        current_manifest = checked_file(root, artifact["manifest"])
        if manifest_raw is not None and current_manifest != manifest_raw:
            raise ValueError("development artifacts use different manifests")
        manifest_raw = current_manifest
        manifest = read_json(manifest_raw)
        version = manifest.get("cua_version")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError("native development version differs")
        files = zip_members(checked_file(root, artifact["wheel"]))
        tags = interpreter(profile)
        wheel_tag = f"{tags['python']}-{tags['abi']}-{tags['platform']}"
        compact = profile.replace("-", "").replace("_", "")
        build_tag = "0development" + kind + compact
        wanted = f"vadgr_computer_use-{version}-{build_tag}-{wheel_tag}.whl"
        if artifact["wheel"]["filename"] != wanted:
            raise ValueError("native development wheel filename differs")
        metadata = check_record(files, version, wheel_tag, build_tag=build_tag)
        marker_path = PREFIX + "development-artifact.json"
        marker = read_json(files[marker_path])
        expected_marker = {
            "schema": 1,
            "development": True,
            "publishable": False,
            "signing": "not-applicable",
            "adoption": "disabled",
            "source_commit": receipt["source_commit"],
            "platform": platform,
            "architecture": architecture,
            "artifact_kind": kind,
        }
        if marker != expected_marker:
            raise ValueError("native development artifact marker differs")
        trust = package_trust(files)
        manifest_sha = digest(manifest_raw)
        if kind == "managed":
            expected_trust = {
                "schema": 1,
                "mode": "managed",
                "release_profile": profile,
                "manifest_sha256": {profile: manifest_sha},
            }
        else:
            expected_trust = {
                "schema": 1,
                "mode": "standalone-input",
                "development": True,
                "manifest_sha256": {profile: manifest_sha},
            }
        if trust != expected_trust:
            raise ValueError("native development package trust differs")
        manifest_path = PREFIX + f"profiles/{profile}/cua-profile-manifest.json"
        if files.get(manifest_path) != manifest_raw:
            raise ValueError("packaged development manifest differs")
        forbidden = [
            name
            for name in files
            if name.startswith((PREFIX + "adoption/", PREFIX + "winhost/"))
            or name.endswith(".ps1")
            or name.startswith(PREFIX + "winbroker/")
            and not name.endswith(".py")
        ]
        if forbidden:
            raise ValueError("native development artifact contains Windows-only payload")
        for name in metadata | {
            manifest_path,
            marker_path,
            PREFIX + "_profile_trust.py",
        }:
            files.pop(name)
        check_manifest(manifest, files, profile, version, receipt["source_commit"])
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = check_native_development_receipt(args.receipt)
    print(
        f"Native development receipt passed: {receipt['platform']}-{receipt['architecture']}; "
        "publication, signing and adoption disabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
