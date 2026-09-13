# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Verify, deploy, and launch the self-contained Windows browser broker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BUNDLE_ARCHIVE = "vadgr-cua-browser-broker-win-x64.zip"
BUNDLE_MANIFEST = "vadgr-cua-browser-broker-win-x64.manifest.json"
BROKER_EXECUTABLE = "vadgr-cua-browser-broker.exe"
PROXY_EXECUTABLE = "vadgr-cua-host.exe"


class WindowsBrokerStateError(OSError):
    """A verified Windows broker lifecycle failure with a public diagnosis."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = code
        self.remediation = remediation


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
    value = str(path).replace("\\", "/")
    if value.startswith("/mnt/") and len(value) > 6:
        return f"{value[5].upper()}:{value[6:].replace('/', chr(92))}"
    if sys.platform == "win32":
        return str(path)
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


def _windows_child_environment() -> dict[str, str]:
    """Translate explicit WSL isolation paths for native Windows children."""
    environment = dict(os.environ)
    if sys.platform == "win32":
        return environment
    for name in (
        "LOCALAPPDATA",
        "VADGR_CUA_BROKER_ENDPOINT",
        "VADGR_CUA_BROWSER_DISCOVERY",
        "VADGR_CUA_BROWSER_DISCOVERY_WINDOWS",
    ):
        value = environment.get(name)
        if value:
            environment[name] = _windows_path(Path(value))
    return environment


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
        env=_windows_child_environment(),
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
        or not isinstance(endpoint.get("pid"), int)
        or endpoint["pid"] < 1
        or not isinstance(endpoint.get("process_started_ns"), str)
        or not endpoint["process_started_ns"]
        or not isinstance(endpoint.get("process_created_filetime"), str)
        or not endpoint["process_created_filetime"].isdecimal()
        or not isinstance(endpoint.get("epoch"), str)
        or not endpoint["epoch"]
        or not isinstance(endpoint.get("token"), str)
        or not endpoint["token"]
        or not isinstance(endpoint.get("port"), int)
        or not 1 <= endpoint["port"] <= 65535
        or not isinstance(endpoint.get("bundle_hash"), str)
        or not endpoint["bundle_hash"]
    ):
        raise WindowsBrokerStateError(
            "browser_broker_discovery_invalid",
            "the Windows browser broker discovery record failed identity verification",
            "run vadgr-cua doctor and repair the owner-local CUA install if instructed",
        )
    if endpoint["bundle_hash"] != expected:
        raise WindowsBrokerStateError(
            "browser_broker_bundle_mismatch",
            "the Windows browser broker does not match the installed CUA payload",
            "complete the CUA update and retry",
        )
    return expected


def expected_bundle_hash() -> str:
    _archive, _manifest_path, manifest = _bundle_inputs()
    return str(manifest["archive_sha256"])


def _run_upgrade_handoff(bundle: str) -> dict[str, object]:
    executable = f"{bundle}\\{BROKER_EXECUTABLE}"
    command = (
        "$env:PSModulePath = $PSHOME + '\\Modules'; "
        "$Spec = [Console]::In.ReadToEnd() | ConvertFrom-Json; "
        "& $Spec.executable upgrade-handoff"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        input=json.dumps({"executable": executable}),
        capture_output=True,
        env=_windows_child_environment(),
        text=True,
        timeout=20,
    )
    try:
        reply = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as error:
        raise WindowsBrokerStateError(
            "browser_broker_upgrade_unsafe",
            "the running browser broker could not be proved as an allowed released Vadgr broker",
            "run vadgr-cua doctor; close only the broker it identifies, then retry",
        ) from error
    if result.returncode != 0 or not isinstance(reply, dict):
        raise WindowsBrokerStateError(
            "browser_broker_upgrade_unsafe",
            "the running browser broker could not be proved as an allowed released Vadgr broker",
            "run vadgr-cua doctor; close only the broker it identifies, then retry",
        )
    if reply.get("state") == "refused":
        code = str(reply.get("code"))
        if code not in {"browser_broker_upgrade_unsafe", "browser_broker_upgrade_timeout"}:
            code = "browser_broker_upgrade_unsafe"
        raise WindowsBrokerStateError(
            code,
            str(reply.get("message") or "the Windows browser broker upgrade was refused"),
            str(reply.get("remediation") or "run vadgr-cua doctor"),
        )
    if reply.get("state") not in {
        "no_predecessor",
        "already_exited",
        "replaced",
        "candidate_ready",
    }:
        raise WindowsBrokerStateError(
            "browser_broker_upgrade_unsafe",
            "the Windows browser broker returned an invalid upgrade result",
            "run vadgr-cua doctor; close only the broker it identifies, then retry",
        )
    return reply


def launch_windows_broker() -> None:
    """Start the Windows broker detached; its held lock elects one winner."""
    bundle, _manifest = deployed_bundle()
    handoff = _run_upgrade_handoff(bundle)
    if handoff.get("state") == "candidate_ready":
        return
    executable = f"{bundle}\\{BROKER_EXECUTABLE}"
    # Windows PowerShell reparses trailing -Command arguments as source. Send
    # paths as ASCII JSON on stdin so spaces, quotes and Unicode stay data on
    # native Windows and through WSL's executable boundary.
    command = (
        # Python can inherit PowerShell 7 modules that Windows PowerShell cannot
        # load. Restrict only this child to its own built-in modules.
        "$env:PSModulePath = $PSHOME + '\\Modules'; "
        "$Launch = [Console]::In.ReadToEnd() | ConvertFrom-Json; "
        "if (-not (Test-Path -LiteralPath $Launch.executable -PathType Leaf)) { exit 2 }; "
        "Start-Process -FilePath $Launch.executable -ArgumentList @('serve') "
        "-WorkingDirectory $Launch.directory -WindowStyle Hidden -ErrorAction Stop"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        input=json.dumps({"executable": executable, "directory": bundle}),
        env=_windows_child_environment(),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    if result.returncode != 0:
        raise OSError("failed to launch the Windows browser broker")


def open_windows_proxy() -> subprocess.Popen:
    """Open one Windows stdio tunnel to the broker's loopback endpoint."""
    from computer_use.setup.extension_setup import ensure_relay_exe

    proxy = ensure_relay_exe()
    return subprocess.Popen(
        [str(proxy), "broker-proxy"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=_windows_child_environment(),
    )
