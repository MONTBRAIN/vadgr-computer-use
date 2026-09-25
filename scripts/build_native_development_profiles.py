#!/usr/bin/env python3
"""Build exact non-publishable native development profile wheels."""

from __future__ import annotations

import argparse
from pathlib import Path

import tomllib
from build_development_profile import require_exact_clean_source
from build_profile_wheels import (
    PREFIX,
    ROOT,
    canonical,
    digest,
    freeze,
    identity,
    interpreter,
    inventory,
    source_files,
    wheel_bytes,
)

NATIVE_PLATFORMS = {"linux", "macos"}
ARCHITECTURES = {"x86_64", "aarch64"}


def _marker(commit: str, platform: str, architecture: str, kind: str) -> dict:
    return {
        "schema": 1,
        "development": True,
        "publishable": False,
        "signing": "not-applicable",
        "adoption": "disabled",
        "source_commit": commit,
        "platform": platform,
        "architecture": architecture,
        "artifact_kind": kind,
    }


def build_native_development(
    repository: Path, platform: str, architecture: str, commit: str, output: Path
) -> dict:
    if platform not in NATIVE_PLATFORMS:
        raise ValueError("native development platform must be linux or macos")
    if architecture not in ARCHITECTURES:
        raise ValueError("unknown native development architecture")
    profile = f"{platform}-{architecture}"
    project = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    common = source_files(repository)
    common[f"vadgr_computer_use-{project['version']}.dist-info/licenses/LICENSE"] = (
        repository / "LICENSE"
    ).read_bytes()
    if (repository / "NOTICE").is_file():
        common[f"vadgr_computer_use-{project['version']}.dist-info/licenses/NOTICE"] = (
            repository / "NOTICE"
        ).read_bytes()
    executables, archives = inventory(common, profile)
    manifest = {
        "schema": 1,
        "cua_version": project["version"],
        "source_commit": commit,
        "release_profile": profile,
        "interpreter": interpreter(profile),
        "files": [identity(path, data, "wheel_path") for path, data in sorted(common.items())],
        "executables": executables,
        "archives": archives,
        "helpers": None,
    }
    manifest_bytes = canonical(manifest)
    manifest_record = freeze(
        output / f"{profile}-development-cua-profile-manifest.json", manifest_bytes
    )
    manifest_path = PREFIX + f"profiles/{profile}/cua-profile-manifest.json"
    marker_path = PREFIX + "development-artifact.json"
    tags = interpreter(profile)
    wheel_tag = f"{tags['python']}-{tags['abi']}-{tags['platform']}"
    compact = profile.replace("-", "").replace("_", "")

    managed_files = dict(common)
    managed_files[manifest_path] = manifest_bytes
    managed_files[marker_path] = canonical(_marker(commit, platform, architecture, "managed"))
    managed_files[PREFIX + "_profile_trust.py"] = (
        "TRUST = "
        + repr(
            {
                "schema": 1,
                "mode": "managed",
                "release_profile": profile,
                "manifest_sha256": {profile: digest(manifest_bytes)},
            }
        )
        + "\n"
    ).encode()
    managed_tag = "0developmentmanaged" + compact
    managed_name = f"vadgr_computer_use-{project['version']}-{managed_tag}-{wheel_tag}.whl"
    managed_wheel = freeze(
        output / managed_name,
        wheel_bytes(managed_files, project, wheel_tag, build_tag=managed_tag),
    )

    standalone_files = dict(common)
    standalone_files[manifest_path] = manifest_bytes
    standalone_files[marker_path] = canonical(_marker(commit, platform, architecture, "standalone"))
    standalone_files[PREFIX + "_profile_trust.py"] = (
        "TRUST = "
        + repr(
            {
                "schema": 1,
                "mode": "standalone-input",
                "development": True,
                "manifest_sha256": {profile: digest(manifest_bytes)},
            }
        )
        + "\n"
    ).encode()
    standalone_tag = "0developmentstandalone" + compact
    standalone_name = f"vadgr_computer_use-{project['version']}-{standalone_tag}-{wheel_tag}.whl"
    standalone_wheel = freeze(
        output / standalone_name,
        wheel_bytes(standalone_files, project, wheel_tag, build_tag=standalone_tag),
    )

    receipt = {
        "schema": 1,
        "development": True,
        "publishable": False,
        "signing": "not-applicable",
        "adoption": "disabled",
        "source_commit": commit,
        "platform": platform,
        "architecture": architecture,
        "artifacts": {
            "managed": {
                "release_profile": profile,
                "wheel": managed_wheel,
                "manifest": manifest_record,
            },
            "standalone": {
                "release_profile": profile,
                "wheel": standalone_wheel,
                "manifest": manifest_record,
            },
        },
    }
    freeze(output / f"native-development-{profile}-receipt.json", canonical(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--platform", choices=sorted(NATIVE_PLATFORMS), required=True)
    parser.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require_exact_clean_source(args.repository, args.source_commit)
    receipt = build_native_development(
        args.repository, args.platform, args.architecture, args.source_commit, args.output
    )
    print(
        "Native development artifacts: "
        + ", ".join(
            receipt["artifacts"][kind]["wheel"]["filename"] for kind in ("managed", "standalone")
        )
    )


if __name__ == "__main__":
    main()
