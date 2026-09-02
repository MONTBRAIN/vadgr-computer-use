#!/usr/bin/env python3
"""Build the pinned self-contained Windows browser-broker bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

EXPECTED_PYTHON = "3.12.14"
EXPECTED_PYINSTALLER = "6.22.2"
VERSION = "0.7.6"
ARCHIVE_NAME = "vadgr-cua-browser-broker-win-x64.zip"
MANIFEST_NAME = "vadgr-cua-browser-broker-win-x64.manifest.json"
SBOM_NAME = "vadgr-cua-browser-broker-win-x64.spdx.json"
FIXED_ZIP_TIME = (2026, 9, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_zip(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            out.writestr(info, path.read_bytes(), compresslevel=9)


def inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def build(source_commit: str, output: Path) -> None:
    if sys.platform != "win32":
        raise SystemExit("the Windows broker must be built on Windows")
    runtime = ".".join(str(part) for part in sys.version_info[:3])
    if runtime != EXPECTED_PYTHON:
        raise SystemExit(f"expected CPython {EXPECTED_PYTHON}, got {runtime}")
    pyinstaller = importlib.metadata.version("pyinstaller")
    if pyinstaller != EXPECTED_PYINSTALLER:
        raise SystemExit(f"expected PyInstaller {EXPECTED_PYINSTALLER}, got {pyinstaller}")

    repository = Path(__file__).resolve().parents[1]
    entry = repository / "computer_use" / "browser" / "windows_broker_entry.py"
    source_paths = [
        repository / "computer_use" / "__init__.py",
        *(
            repository / "computer_use" / "browser" / name
            for name in (
                "bridge.py",
                "broker.py",
                "native_host.py",
                "ownership.py",
                "protocol.py",
                "server.py",
                "windows_acl.py",
                "windows_broker_entry.py",
            )
        ),
        repository / "computer_use" / "setup" / "extension_setup.py",
    ]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-winbroker-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        env = dict(os.environ)
        env.update({"PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "1788220800"})
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
                "--noconsole",
                "--name",
                "vadgr-cua-browser-broker",
                "--distpath",
                str(dist),
                "--workpath",
                str(root / "work"),
                "--specpath",
                str(root / "spec"),
                "--paths",
                str(repository),
                "--hidden-import",
                "computer_use.setup.extension_setup",
                str(entry),
            ],
            cwd=repository,
            env=env,
            check=True,
        )
        bundle = dist / "vadgr-cua-browser-broker"
        executable = bundle / "vadgr-cua-browser-broker.exe"
        if not executable.is_file():
            raise SystemExit("PyInstaller did not produce the broker executable")

        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if not python_license.is_file():
            raise SystemExit("the pinned CPython distribution license is missing")
        shutil.copyfile(python_license, bundle / "PYTHON-LICENSE.txt")
        pyinstaller_distribution = importlib.metadata.distribution("pyinstaller")
        pyinstaller_license_entry = next(
            file
            for file in pyinstaller_distribution.files or ()
            if str(file).replace("\\", "/").endswith("/licenses/COPYING.txt")
        )
        pyinstaller_license = Path(
            pyinstaller_distribution.locate_file(pyinstaller_license_entry)
        )
        if not pyinstaller_license.is_file():
            raise SystemExit("the pinned PyInstaller license is missing")
        shutil.copyfile(pyinstaller_license, bundle / "PYINSTALLER-COPYING.txt")
        shutil.copyfile(repository / "LICENSE", bundle / "VADGR-CUA-LICENSE.txt")

        files = inventory(bundle)
        archive = output / ARCHIVE_NAME
        write_zip(bundle, archive)
        manifest = {
            "schema": 1,
            "name": "vadgr-cua-browser-broker",
            "version": VERSION,
            "target": "x86_64-pc-windows-msvc",
            "source_commit": source_commit,
            "source_files": [
                {
                    "path": path.relative_to(repository).as_posix(),
                    "sha256": sha256(path),
                }
                for path in source_paths
            ],
            "python": {
                "version": EXPECTED_PYTHON,
                "distribution": "python-build-standalone",
                "build": "20260825",
            },
            "builder": {"pyinstaller": EXPECTED_PYINSTALLER, "uv": "0.12.6"},
            "archive_sha256": sha256(archive),
            "archive_size": archive.stat().st_size,
            "files": files,
        }
        (output / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"vadgr-cua-browser-broker-{VERSION}-windows-x64",
            "documentNamespace": (
                "https://github.com/MONTBRAIN/vadgr-computer-use/"
                f"sbom/{VERSION}/{manifest['archive_sha256']}"
            ),
            "creationInfo": {
                "created": "2026-09-01T00:00:00Z",
                "creators": ["Tool: scripts/build_windows_broker.py"],
            },
            "packages": [
                {
                    "name": "vadgr-computer-use",
                    "SPDXID": "SPDXRef-Package-vadgr-cua",
                    "versionInfo": VERSION,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "licenseConcluded": "Apache-2.0",
                    "licenseDeclared": "Apache-2.0",
                },
                {
                    "name": "CPython",
                    "SPDXID": "SPDXRef-Package-CPython",
                    "versionInfo": EXPECTED_PYTHON,
                    "downloadLocation": (
                        "https://github.com/astral-sh/python-build-standalone/"
                        "releases/tag/20260825"
                    ),
                    "filesAnalyzed": False,
                    "licenseConcluded": "Python-2.0",
                    "licenseDeclared": "Python-2.0",
                },
                {
                    "name": "PyInstaller",
                    "SPDXID": "SPDXRef-Package-PyInstaller",
                    "versionInfo": EXPECTED_PYINSTALLER,
                    "downloadLocation": "https://pypi.org/project/pyinstaller/6.22.2/",
                    "filesAnalyzed": False,
                    "licenseConcluded": "GPL-2.0-only WITH Bootloader-exception",
                    "licenseDeclared": "GPL-2.0-only WITH Bootloader-exception",
                },
            ],
        }
        (output / SBOM_NAME).write_text(
            json.dumps(sbom, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("computer_use/browser/winbroker"),
    )
    args = parser.parse_args()
    if len(args.source_commit) != 40 or any(c not in "0123456789abcdef" for c in args.source_commit):
        raise SystemExit("--source-commit must be one lowercase 40-character Git commit")
    build(args.source_commit, args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
