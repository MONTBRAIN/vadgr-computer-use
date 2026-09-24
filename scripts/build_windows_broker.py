#!/usr/bin/env python3
"""Build the pinned self-contained Windows browser-broker bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from broker_sbom import build_sbom, prepare_notices

EXPECTED_PYTHON = "3.12.14"
EXPECTED_PYINSTALLER = "6.22.2"
EXPECTED_GO = "go1.24.0"
VERSION = "0.7.9"
ARCHITECTURES = {
    "x86_64": {
        "machine": {"AMD64", "X86_64"},
        "target": "x86_64-pc-windows-msvc",
        "goarch": "amd64",
        "suffix": "x64",
    },
    "aarch64": {
        "machine": {"ARM64", "AARCH64"},
        "target": "aarch64-pc-windows-msvc",
        "goarch": "arm64",
        "suffix": "arm64",
    },
}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_zip(source: Path, destination: Path) -> None:
    """Write the signing-input archive with one deterministic byte layout."""
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as out:
        out.comment = b""
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.comment = b""
            info.extra = b""
            out.writestr(info, path.read_bytes())


def normalize_embedded_zip(path: Path) -> None:
    """Rewrite a PyInstaller ZIP with stable ordering and metadata."""
    with zipfile.ZipFile(path, "r") as source:
        entries: dict[str, tuple[int, bytes]] = {}
        for info in source.infolist():
            if info.is_dir():
                continue
            if info.filename in entries:
                raise ValueError(f"duplicate embedded ZIP member: {info.filename}")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError(
                    f"unsupported embedded ZIP compression for {info.filename}: "
                    f"{info.compress_type}"
                )
            entries[info.filename] = (info.compress_type, source.read(info))
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w") as out:
            out.comment = b""
            for name in sorted(entries):
                compression, data = entries[name]
                info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
                info.compress_type = compression
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                if compression == zipfile.ZIP_DEFLATED:
                    out.writestr(info, data, compresslevel=9)
                else:
                    out.writestr(info, data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def inventory(root: Path) -> list[dict[str, object]]:
    files = [item for item in root.rglob("*") if item.is_file()]
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix())
    ]


def write_json(path: Path, value: object) -> None:
    """Write canonical cross-platform JSON with LF line endings."""
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")


def artifact_names(architecture: str) -> tuple[str, str, str]:
    try:
        suffix = str(ARCHITECTURES[architecture]["suffix"])
    except KeyError as error:
        raise ValueError(f"unsupported Windows architecture: {architecture}") from error
    stem = f"vadgr-cua-browser-broker-win-{suffix}"
    return f"{stem}.zip", f"{stem}.manifest.json", f"{stem}.spdx.json"


def write_predecessor_catalog(source: Path, destination: Path, architecture: str) -> None:
    """Generate the closed native catalog without claiming cross-architecture releases."""
    configuration = ARCHITECTURES[architecture]
    value = json.loads(source.read_bytes())
    if (
        set(value) != {"schema", "target", "releases"}
        or value["schema"] != 1
        or value["target"] != ARCHITECTURES["x86_64"]["target"]
        or not isinstance(value["releases"], list)
    ):
        raise ValueError("released predecessor catalog is invalid")
    expected_fields = {
        "version",
        "archive_sha256",
        "broker_relative_path",
        "broker_sha256",
        "manifest_sha256",
        "protocol_min",
        "protocol_max",
    }
    versions = []
    for row in value["releases"]:
        if (
            not isinstance(row, dict)
            or set(row) != expected_fields
            or row["broker_relative_path"] != "vadgr-cua-browser-broker.exe"
            or row["protocol_min"] != 1
            or row["protocol_max"] != 1
        ):
            raise ValueError("released predecessor entry is invalid")
        versions.append(row["version"])
        for name in ("archive_sha256", "broker_sha256", "manifest_sha256"):
            digest = row[name]
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or digest == "0" * 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError("released predecessor digest is invalid")
    if versions != ["0.7.6", "0.7.7", "0.7.8"]:
        raise ValueError("released predecessor set is incomplete")
    output = {
        "schema": 1,
        "target": configuration["target"],
        "releases": value["releases"] if architecture == "x86_64" else [],
    }
    write_json(destination, output)


def remove_system_api_set_forwarders(bundle: Path) -> tuple[str, ...]:
    """Remove Windows 10+ system UCRT and virtual API-set contracts."""
    pattern = re.compile(r"(?i)(?:api|ext)-ms-win-[a-z0-9-]+\.dll")
    removed = []
    for path in sorted(bundle.rglob("*")):
        if path.name.lower() != "ucrtbase.dll" and not pattern.fullmatch(path.name):
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("Windows API-set output is not an ordinary file")
        removed.append(path.relative_to(bundle).as_posix())
        path.unlink()
    return tuple(removed)


def require_native_architecture(architecture: str) -> dict[str, object]:
    try:
        configuration = ARCHITECTURES[architecture]
    except KeyError as error:
        raise SystemExit(f"unsupported Windows architecture: {architecture}") from error
    actual = platform.machine().upper()
    if actual not in configuration["machine"]:
        raise SystemExit(
            f"the {architecture} broker must be built on native {architecture} Windows; got {actual}"
        )
    return configuration


def build_relay(repository: Path, output: Path, architecture: str) -> Path:
    """Build the relay on the matching native host without embedding VCS paths."""
    configuration = ARCHITECTURES[architecture]
    destination = output / "vadgr-cua-host.exe"
    environment = dict(os.environ)
    environment.update(
        {
            "GOOS": "windows",
            "GOARCH": str(configuration["goarch"]),
            "CGO_ENABLED": "0",
        }
    )
    version = subprocess.run(
        ["go", "version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
        env=environment,
    ).stdout.split()
    if len(version) < 3 or version[2] != EXPECTED_GO:
        raise SystemExit(f"expected Go {EXPECTED_GO}, got {' '.join(version)}")
    subprocess.run(
        [
            "go",
            "build",
            "-buildvcs=false",
            "-trimpath",
            "-ldflags=-s -w -buildid=",
            "-o",
            str(destination),
            ".",
        ],
        cwd=repository / "computer_use" / "browser" / "winhost",
        env=environment,
        check=True,
    )
    return destination


def build(source_commit: str, output: Path, architecture: str = "x86_64", source_repository: Path | None = None) -> None:
    if sys.platform != "win32":
        raise SystemExit("the Windows broker must be built on Windows")
    configuration = require_native_architecture(architecture)
    runtime = ".".join(str(part) for part in sys.version_info[:3])
    if runtime != EXPECTED_PYTHON:
        raise SystemExit(f"expected CPython {EXPECTED_PYTHON}, got {runtime}")
    pyinstaller = importlib.metadata.version("pyinstaller")
    if pyinstaller != EXPECTED_PYINSTALLER:
        raise SystemExit(f"expected PyInstaller {EXPECTED_PYINSTALLER}, got {pyinstaller}")

    tooling = Path(__file__).resolve().parents[1]
    repository = source_repository.resolve() if source_repository else tooling
    entry = repository / "computer_use" / "browser" / "windows_broker_entry.py"
    source_paths = [
        repository / "computer_use" / "__init__.py",
        *(
            repository / "computer_use" / "browser" / name
            for name in (
                "bridge.py",
                "broker.py",
                "managed_authorization.py",
                "native_host.py",
                "ownership.py",
                "private_file.py",
                "protocol.py",
                "server.py",
                "windows_acl.py",
                "windows_broker_entry.py",
                "windows_process.py",
            )
        ),
        repository / "computer_use" / "setup" / "extension_setup.py",
        repository / "computer_use" / "browser" / "winbroker" / "predecessor-catalog.json",
        repository / "computer_use" / "browser" / "winhost" / "main.go",
        repository / "computer_use" / "browser" / "winhost" / "go.mod",
    ]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-winbroker-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        predecessor_catalog = root / "predecessor-catalog.json"
        write_predecessor_catalog(
            tooling / "packaging/profiles/predecessor-input.json",
            predecessor_catalog,
            architecture,
        )
        env = dict(os.environ)
        env.update(
            {
                "PYTHONHASHSEED": "0",
                "PYTHONNOUSERSITE": "1",
                "PYINSTALLER_CONFIG_DIR": str(root / "pyinstaller-config"),
                "SOURCE_DATE_EPOCH": "1788220800",
            }
        )
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
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
                "--add-data",
                str(
                    predecessor_catalog
                )
                + os.pathsep
                + ".",
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
        remove_system_api_set_forwarders(bundle)
        normalize_embedded_zip(bundle / "_internal" / "base_library.zip")

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
        pyinstaller_license = Path(pyinstaller_distribution.locate_file(pyinstaller_license_entry))
        if not pyinstaller_license.is_file():
            raise SystemExit("the pinned PyInstaller license is missing")
        shutil.copyfile(pyinstaller_license, bundle / "PYINSTALLER-COPYING.txt")
        shutil.copyfile(repository / "LICENSE", bundle / "VADGR-CUA-LICENSE.txt")

        _, source_receipt = prepare_notices(repository, bundle, Path(sys.base_prefix), tooling_repository=tooling)
        files = inventory(bundle)
        archive_name, manifest_name, sbom_name = artifact_names(architecture)
        archive = output / archive_name
        write_zip(bundle, archive)
        relay = build_relay(repository, output, architecture)
        manifest = {
            "schema": 1,
            "name": "vadgr-cua-browser-broker",
            "version": VERSION,
            "architecture": architecture,
            "target": configuration["target"],
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
            "builder": {
                "pyinstaller": EXPECTED_PYINSTALLER,
                "go": EXPECTED_GO,
            },
            "archive_sha256": sha256(archive),
            "archive_size": archive.stat().st_size,
            "relay": {
                "path": relay.name,
                "size": relay.stat().st_size,
                "sha256": sha256(relay),
                "execution_os": "windows",
                "architecture": architecture,
            },
            "files": files,
        }
        write_json(output / manifest_name, manifest)
        toolchain = json.loads((tooling / "packaging/profiles/toolchain.json").read_bytes())
        sbom = build_sbom(
            bundle,
            relay,
            VERSION,
            architecture,
            source_commit,
            toolchain["python_inputs"][architecture],
            source_receipt,
        )
        write_json(output / sbom_name, sbom)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    parser.add_argument("--source-repository", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("computer_use/browser/winbroker"),
    )
    args = parser.parse_args()
    if len(args.source_commit) != 40 or any(
        c not in "0123456789abcdef" for c in args.source_commit
    ):
        raise SystemExit("--source-commit must be one lowercase 40-character Git commit")
    build(args.source_commit, args.output.resolve(), args.architecture, args.source_repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
