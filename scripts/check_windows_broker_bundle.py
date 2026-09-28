#!/usr/bin/env python3
"""Verify the committed Windows browser broker without executing it."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

import tomllib

RELEASED_078_ARCHIVE_SHA256 = "cb8d47ede577c76683576a7bb4f8e5251eaa884b66bd50a2a35ad394966ce39d"
RELEASED_078_SOURCE_COMMIT = "eb8df48e8873e4ac0609c5d20343c9d3e8291dd8"


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
    historical_fixture = manifest.get("version") == "0.7.8"
    if manifest.get("version") != version and not historical_fixture:
        fail("manifest version is neither current nor the exact released predecessor")
    raw_archive = archive.read_bytes()
    if manifest.get("archive_sha256") != sha256_bytes(raw_archive):
        fail("archive SHA-256 differs from its manifest")
    if manifest.get("archive_size") != len(raw_archive):
        fail("archive size differs from its manifest")
    if historical_fixture and (
        manifest.get("archive_sha256") != RELEASED_078_ARCHIVE_SHA256
        or manifest.get("source_commit") != RELEASED_078_SOURCE_COMMIT
        or manifest.get("target") != "x86_64-pc-windows-msvc"
    ):
        fail("the retained 0.7.8 predecessor fixture differs from its released identity")
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
    if "computer_use/browser/private_file.py" not in {item.get("path") for item in source_files}:
        fail("private publication source is absent from the bundle inventory")
    source_commit = manifest.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        fail("source commit is absent or malformed")
    if not historical_fixture:
        for item in source_files:
            relative = str(item["path"])
            path = repository / relative
            if not path.is_file():
                fail(f"bundle source is absent: {relative}")
            if sha256_bytes(path.read_bytes()) != item["sha256"]:
                fail(f"bundle source does not match its manifest for {relative}")

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
    expected_sbom_version = str(manifest["version"])
    if (
        sbom.get("spdxVersion") != "SPDX-2.3"
        or expected_sbom_version not in sbom.get("name", "")
    ):
        fail("SPDX document is absent or stale")
    print(f"windows broker bundle check passed: {manifest['archive_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
