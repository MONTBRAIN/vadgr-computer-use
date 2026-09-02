# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Verify, deploy, and launch the self-contained Windows browser broker."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BUNDLE_ARCHIVE = "vadgr-cua-browser-broker-win-x64.zip"
BUNDLE_MANIFEST = "vadgr-cua-browser-broker-win-x64.manifest.json"
BROKER_EXECUTABLE = "vadgr-cua-browser-broker.exe"
PROXY_EXECUTABLE = "vadgr-cua-host.exe"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _bundle_inputs() -> tuple[Path, Path, dict[str, object]]:
    archive = _package_root() / "winbroker" / BUNDLE_ARCHIVE
    manifest_path = _package_root() / "winbroker" / BUNDLE_MANIFEST
    if not archive.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("the packaged Windows browser broker bundle is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OSError("the Windows browser broker manifest is invalid") from error
    if manifest.get("archive_sha256") != _sha256(archive):
        raise OSError("the Windows browser broker archive failed integrity verification")
    return archive, manifest_path, manifest


def _windows_path(path: Path) -> str:
    value = str(path)
    if value.startswith("/mnt/") and len(value) > 6:
        return f"{value[5].upper()}:{value[6:].replace('/', chr(92))}"
    if sys.platform == "win32":
        return value
    result = subprocess.run(
        ["wslpath", "-w", value],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise OSError("failed to resolve a Windows-accessible broker payload path")
    return result.stdout.strip()


def deployed_bundle() -> tuple[str, dict[str, object]]:
    """Install or reverify one immutable bundle entirely on Windows."""
    archive, manifest_path, manifest = _bundle_inputs()
    installer = _package_root() / "winbroker" / "install.ps1"
    if not installer.is_file():
        raise FileNotFoundError("the Windows browser broker installer is missing")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _windows_path(installer),
            "-Archive",
            _windows_path(archive),
            "-Manifest",
            _windows_path(manifest_path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise OSError("the Windows browser broker failed verified deployment")
    destination = result.stdout.strip().splitlines()[-1]
    expected_suffix = f"\\{manifest['version']}\\{manifest['archive_sha256']}"
    if not destination.lower().endswith(expected_suffix.lower()):
        raise OSError("the Windows browser broker installer returned an unexpected path")
    return destination, manifest


def validate_endpoint(endpoint: dict[str, object]) -> str:
    """Return the expected bundle hash or reject an untrusted endpoint."""
    expected = expected_bundle_hash()
    if (
        endpoint.get("platform") != "win32"
        or endpoint.get("host") != "127.0.0.1"
        or endpoint.get("bundle_hash") != expected
        or not isinstance(endpoint.get("pid"), int)
        or not isinstance(endpoint.get("process_started_ns"), str)
    ):
        raise OSError("the Windows browser broker endpoint failed identity verification")
    return expected


def expected_bundle_hash() -> str:
    _archive, _manifest_path, manifest = _bundle_inputs()
    return str(manifest["archive_sha256"])


def launch_windows_broker() -> None:
    """Start the Windows broker detached; its held lock elects one winner."""
    bundle, _manifest = deployed_bundle()
    executable = f"{bundle}\\{BROKER_EXECUTABLE}"
    command = (
        "& { param([string]$Executable, [string]$Directory) "
        "if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { exit 2 }; "
        "Start-Process -FilePath $Executable -ArgumentList @('serve') "
        "-WorkingDirectory $Directory -WindowStyle Hidden }"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
            executable,
            bundle,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    if result.returncode != 0:
        raise OSError("failed to launch the Windows browser broker")


def open_windows_proxy() -> subprocess.Popen:
    """Open one Windows stdio tunnel to the broker's loopback endpoint."""
    proxy = _package_root() / "winhost" / PROXY_EXECUTABLE
    if not proxy.is_file():
        raise FileNotFoundError("the packaged Windows browser proxy is missing")
    return subprocess.Popen(
        [str(proxy), "broker-proxy"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
