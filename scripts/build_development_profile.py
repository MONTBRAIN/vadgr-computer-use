#!/usr/bin/env python3
"""Build an unsigned, non-publishable one-architecture wheel for development E2E."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import tomllib
from build_profile_wheels import (
    PREFIX,
    ROOT,
    canonical,
    digest,
    freeze,
    helper_files,
    identity,
    interpreter,
    inventory,
    source_files,
    wheel_bytes,
)


def require_exact_clean_source(repository: Path, commit: str) -> None:
    """Require the named committed tree without tracked or untracked source drift."""

    def git(*arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repository), *arguments], text=True
        ).strip()

    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("development wheel requires the exact clean committed source")


def build_development(
    repository: Path, helpers: Path, architecture: str, commit: str, output: Path
) -> dict:
    if architecture not in {"x86_64", "aarch64"}:
        raise ValueError("unknown development architecture")
    project = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    payload, helper = helper_files(helpers, architecture, project["version"], commit)
    files = source_files(repository)
    files[f"vadgr_computer_use-{project['version']}.dist-info/licenses/LICENSE"] = (
        repository / "LICENSE"
    ).read_bytes()
    files.update(payload)
    for name in (
        "install.ps1",
        "install-managed.ps1",
        "adopt-native.ps1",
        "predecessor-catalog.json",
    ):
        files[PREFIX + "winbroker/" + name] = (
            repository / PREFIX / "winbroker" / name
        ).read_bytes()
    hashes = {}
    manifests = {}
    for os_name in ("windows", "wsl"):
        profile = os_name + "-" + architecture
        executables, archives = inventory(files, profile)
        manifest = {
            "schema": 1,
            "cua_version": project["version"],
            "source_commit": commit,
            "release_profile": profile,
            "interpreter": interpreter(profile),
            "files": [identity(p, b, "wheel_path") for p, b in sorted(files.items())],
            "executables": executables,
            "archives": archives,
            "helpers": helper,
        }
        raw = canonical(manifest)
        hashes[profile] = digest(raw)
        manifests[PREFIX + f"profiles/{profile}/cua-profile-manifest.json"] = raw
    files.update(manifests)
    trust = {
        "schema": 1,
        "mode": "standalone-input",
        "development": True,
        "manifest_sha256": hashes,
    }
    files[PREFIX + "_profile_trust.py"] = ("TRUST = " + repr(trust) + "\n").encode()
    # A conspicuous build tag and separate receipt keep this out of the release catalog.
    build_tag = "0development" + architecture.replace("_", "")
    name = f"vadgr_computer_use-{project['version']}-{build_tag}-py3-none-any.whl"
    wheel = freeze(
        output / name,
        wheel_bytes(files, project, "py3-none-any", build_tag=build_tag),
    )
    receipt = {
        "schema": 1,
        "development": True,
        "publishable": False,
        "source_commit": commit,
        "architecture": architecture,
        "wheel": wheel,
        "manifest_sha256": hashes,
        "signing": "unsigned-input",
        "adoption": "disabled",
    }
    freeze(output / "development-receipt.json", canonical(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--helpers", type=Path, required=True)
    parser.add_argument("--architecture", choices=("x86_64", "aarch64"), required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_exact_clean_source(args.repository, args.source_commit)
    result = build_development(
        args.repository, args.helpers, args.architecture, args.source_commit, args.output
    )
    print(
        f"Unsigned development wheel: {result['wheel']['filename']}; publication and adoption disabled"
    )


if __name__ == "__main__":
    main()
