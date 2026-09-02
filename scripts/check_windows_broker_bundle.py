#!/usr/bin/env python3
"""Verify the committed Windows browser broker without executing it."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import tomllib


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"windows broker bundle check failed: {message}")


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    root = repository / "computer_use" / "browser" / "winbroker"
    archive = root / "vadgr-cua-browser-broker-win-x64.zip"
    manifest_path = root / "vadgr-cua-browser-broker-win-x64.manifest.json"
    sbom_path = root / "vadgr-cua-browser-broker-win-x64.spdx.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    if manifest.get("version") != version:
        fail("manifest version differs from pyproject.toml")
    raw_archive = archive.read_bytes()
    if manifest.get("archive_sha256") != sha256_bytes(raw_archive):
        fail("archive SHA-256 differs from its manifest")
    if manifest.get("archive_size") != len(raw_archive):
        fail("archive size differs from its manifest")
    if manifest.get("python") != {
        "version": "3.12.14",
        "distribution": "python-build-standalone",
        "build": "20260825",
    }:
        fail("CPython build identity is not the approved pin")
    if manifest.get("builder") != {"pyinstaller": "6.22.2", "uv": "0.12.6"}:
        fail("builder identity is not the approved pin")

    source_files = manifest.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        fail("source inventory is absent")
    source_commit = manifest.get("source_commit")
    if not isinstance(source_commit, str) or len(source_commit) != 40:
        fail("source commit is absent or malformed")
    commit_check = subprocess.run(
        ["git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=repository,
        capture_output=True,
    )
    if commit_check.returncode != 0:
        fail("source commit is not present in repository history")
    for item in source_files:
        relative = str(item["path"])
        path = repository / relative
        if not path.is_file():
            fail(f"bundle source is absent: {relative}")
        committed = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"],
            cwd=repository,
            capture_output=True,
        )
        if committed.returncode != 0 or sha256_bytes(committed.stdout) != item["sha256"]:
            fail(f"bundle source does not match source commit for {relative}")
        changed = subprocess.run(
            ["git", "diff", "--quiet", source_commit, "--", relative],
            cwd=repository,
        )
        if changed.returncode != 0:
            fail(f"bundle is stale for source {relative}")

    expected = {item["path"]: item for item in manifest.get("files", [])}
    required = {
        "vadgr-cua-browser-broker.exe",
        "PYTHON-LICENSE.txt",
        "PYINSTALLER-COPYING.txt",
        "VADGR-CUA-LICENSE.txt",
    }
    with zipfile.ZipFile(archive) as bundle:
        actual: set[str] = set()
        for info in bundle.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(info.external_attr >> 16):
                fail(f"unsafe archive member {info.filename!r}")
            if info.is_dir():
                continue
            actual.add(info.filename)
            item = expected.get(info.filename)
            if item is None:
                fail(f"unlisted archive member {info.filename!r}")
            payload = bundle.read(info)
            if len(payload) != item["size"] or sha256_bytes(payload) != item["sha256"]:
                fail(f"archive member failed integrity check: {info.filename}")
    if actual != set(expected):
        fail("manifest lists files absent from the archive")
    if not required.issubset(actual):
        fail("archive omits its executable or required licenses")

    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3" or version not in sbom.get("name", ""):
        fail("SPDX document is absent or stale")
    print(f"windows broker bundle check passed: {manifest['archive_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
