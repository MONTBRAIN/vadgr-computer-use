# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Verify, deploy, and launch the self-contained Windows browser broker."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import BinaryIO

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


def _distribution_root() -> Path:
    """Return the wheel root used by profile-manifest ``wheel_path`` values."""
    return Path(__file__).resolve().parents[2]


def _profile_path(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise OSError("the Windows browser broker profile path is invalid")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise OSError("the Windows browser broker profile path escapes its package")
    return candidate


def _profile_bundle_inputs() -> tuple[Path, Path, dict[str, object]]:
    from computer_use.browser.profile import load_input_manifest, select_profile

    profile = select_profile()
    if not profile.windows_helpers:
        raise OSError("this release profile does not carry a Windows browser broker")
    profile_manifest = load_input_manifest(profile)
    helpers = profile_manifest.get("helpers")
    if not isinstance(helpers, dict) or helpers.get("architecture") != profile.architecture:
        raise OSError("the Windows browser broker helper profile is invalid")
    archive_record = helpers.get("archive")
    manifest_record = helpers.get("member_manifest")
    required = {"path", "size", "sha256"}
    if (
        not isinstance(archive_record, dict)
        or set(archive_record) != required
        or not isinstance(manifest_record, dict)
        or set(manifest_record) != required
    ):
        raise OSError("the Windows browser broker helper records are invalid")
    root = _distribution_root()
    archive = _profile_path(root, archive_record["path"])
    manifest_path = _profile_path(root, manifest_record["path"])
    for path, record in ((archive, archive_record), (manifest_path, manifest_record)):
        if (
            not path.is_file()
            or path.stat().st_size != record["size"]
            or _sha256(path) != record["sha256"]
        ):
            raise OSError("the Windows browser broker profile payload changed")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OSError("the Windows browser broker manifest is invalid") from error
    if (
        manifest.get("architecture") != profile.architecture
        or manifest.get("archive_sha256") != archive_record["sha256"]
    ):
        raise OSError("the Windows browser broker identities disagree")
    return archive, manifest_path, manifest


def _validate_authorization_descriptor(descriptor: int) -> None:
    if not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
        raise OSError("managed authorization requires a read-only pipe")
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetFileType.argtypes = [wintypes.HANDLE]
        kernel.GetFileType.restype = wintypes.DWORD
        native = ctypes.WinDLL("ntdll")
        native.NtQueryObject.argtypes = [
            wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p,
            wintypes.ULONG, ctypes.POINTER(wintypes.ULONG),
        ]
        native.NtQueryObject.restype = wintypes.LONG
        information = (wintypes.ULONG * 14)()
        returned = wintypes.ULONG()
        if (
            kernel.GetFileType(handle) != 3
            or native.NtQueryObject(handle, 0, information, ctypes.sizeof(information),
                                    ctypes.byref(returned)) != 0
            or not information[1] & 1
            or information[1] & 2
        ):
            raise OSError("managed authorization requires a read-only pipe")
    else:
        import fcntl

        if fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            raise OSError("managed authorization requires a read-only pipe")
        # Linux exposes anonymous pipes separately from filesystem FIFO paths.
        if sys.platform == "linux" and not os.readlink(f"/proc/self/fd/{descriptor}").startswith("pipe:["):
            raise OSError("managed authorization requires an anonymous pipe")


def _managed_authorization_pipe() -> BinaryIO:
    """Open only the inherited anonymous channel selected by the trusted parent."""
    descriptor = os.environ.pop("VADGR_CUA_LAUNCH_AUTHORIZATION_FD", None)
    handle = os.environ.pop("VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE", None)
    if bool(descriptor) == bool(handle):
        raise OSError("managed CUA requires exactly one inherited authorization channel")
    try:
        if descriptor is not None:
            fd = int(descriptor)
            _validate_authorization_descriptor(fd)
            return os.fdopen(fd, "rb", closefd=True)
        if sys.platform != "win32":
            raise OSError("a Windows authorization handle is invalid on this platform")
        import msvcrt

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd = msvcrt.open_osfhandle(int(handle), flags)
        try:
            _validate_authorization_descriptor(fd)
            return os.fdopen(fd, "rb", closefd=True)
        except Exception:
            os.close(fd)
            raise
    except (OSError, TypeError, ValueError) as error:
        raise OSError("the managed authorization channel is invalid") from error


def _managed_bundle_inputs(
    profile: object, *, pipe: BinaryIO | None = None
) -> tuple[Path, Path, dict[str, object]]:
    from computer_use.browser.managed_authorization import (
        canonical_json,
        managed_launch_authorization,
        sha256,
    )

    if pipe is None:
        envelope, manifest = managed_launch_authorization(
            _managed_authorization_pipe, profile=str(profile.value)
        )
    else:
        from computer_use.browser.managed_authorization import read_managed_authorization

        envelope, manifest = read_managed_authorization(
            pipe, profile=str(profile.value)
        )
    from computer_use.browser.offline_attestation import local_path

    root = local_path(str(envelope["installed_root"]))
    archive = _profile_path(root, manifest["archive"]["path"])
    manifest_path = archive.parent / "broker-final-manifest.json"
    raw_manifest = canonical_json(manifest)
    if (
        not archive.is_file()
        or archive.stat().st_size != manifest["archive"]["size"]
        or _sha256(archive) != manifest["archive"]["sha256"]
        or not manifest_path.is_file()
        or manifest_path.read_bytes() != raw_manifest
        or sha256(raw_manifest) != _sha256(manifest_path)
    ):
        raise OSError("the installed managed helper closure changed")
    return archive, manifest_path, manifest


def _handoff_authorization() -> tuple[Path, str] | None:
    """Return only the fixed authenticated helper authorization for handoff."""
    from computer_use.browser.profile import (
        ProfileRefusal,
        load_package_trust,
        select_profile,
    )

    try:
        trust = load_package_trust()
        profile = select_profile()
        if not profile.windows_helpers:
            return None
        if trust["mode"] == "standalone-input":
            from computer_use.browser.standalone_adoption import resolve

            adopted = resolve()
            if adopted is None:
                return None
            return Path(adopted["authorization_path"]), str(
                adopted["authorization_sha256"]
            )
        from computer_use.browser.managed_authorization import (
            managed_launch_authorization,
        )

        envelope, _manifest = managed_launch_authorization(
            _managed_authorization_pipe, profile=profile.value
        )
        from computer_use.browser.offline_attestation import local_path

        root = local_path(str(envelope["installed_root"]))
        relative = (
            Path("managed-helpers")
            / profile.architecture
            / "helper-closure-authorization.json"
        )
        authorization = _profile_path(root, relative.as_posix())
        expected = str(envelope["helper_closure_authorization_sha256"])
        if not authorization.is_file() or _sha256(authorization) != expected:
            raise OSError("the installed helper authorization changed")
        return authorization, expected
    except ProfileRefusal as error:
        repository = Path(__file__).resolve().parents[2]
        if error.code == "missing-package-trust" and (repository / ".git").exists():
            return None
        raise


def _bundle_inputs() -> tuple[Path, Path, dict[str, object]]:
    from computer_use.browser.profile import (
        ProfileRefusal,
        load_package_trust,
        select_profile,
    )

    try:
        trust = load_package_trust()
        profile = select_profile()
        if trust["mode"] == "managed":
            expected = trust.get("release_profile")
            if expected != profile.value:
                raise OSError("the managed package does not match this native host")
            return _managed_bundle_inputs(profile)
        from computer_use.browser.standalone_adoption import resolve

        adopted = resolve()
        if adopted is not None:
            return adopted["archive"], adopted["manifest_path"], adopted["manifest"]
        return _profile_bundle_inputs()
    except ProfileRefusal as error:
        repository = Path(__file__).resolve().parents[2]
        if error.code != "missing-package-trust" or not (repository / ".git").exists():
            raise
        # Source-only released predecessor fixture. Installed 0.7.9 wheels do
        # not fall back to these x64 bytes.
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
    local_app_data = environment.pop("LOCALAPPDATA", None)
    if local_app_data:
        environment["VADGR_CUA_WINDOWS_LOCAL_APP_DATA"] = _windows_path(
            Path(local_app_data)
        )
    forwarded = [entry for entry in environment.get("WSLENV", "").split(":") if entry]
    forwarded_names = {entry.split("/", 1)[0] for entry in forwarded}
    for name in (
        "VADGR_CUA_WINDOWS_LOCAL_APP_DATA",
        "VADGR_CUA_BROKER_ENDPOINT",
        "VADGR_CUA_BROWSER_DISCOVERY",
        "VADGR_CUA_BROWSER_DISCOVERY_WINDOWS",
    ):
        value = environment.get(name)
        if value:
            if name != "VADGR_CUA_WINDOWS_LOCAL_APP_DATA":
                environment[name] = _windows_path(Path(value))
            if name not in forwarded_names:
                forwarded.append(name)
    environment["WSLENV"] = ":".join(forwarded)
    return environment


def deployed_bundle() -> tuple[str, dict[str, object]]:
    """Install or reverify one immutable bundle entirely on Windows."""
    from computer_use.browser.profile import ProfileRefusal, load_package_trust
    from computer_use.browser.standalone_adoption import resolve

    try:
        trust = load_package_trust()
        if trust["mode"] == "standalone-input":
            adopted = resolve()
            if adopted is not None:
                return adopted["destination"], adopted["manifest"]
    except ProfileRefusal as error:
        if error.code != "missing-package-trust" or not (_distribution_root() / ".git").exists():
            raise
    archive, manifest_path, manifest = _bundle_inputs()
    managed = manifest.get("mode") == "managed-signed"
    installer = _package_root() / "winbroker" / (
        "install-managed.ps1" if managed else "install.ps1"
    )
    if not installer.is_file():
        raise FileNotFoundError("the Windows browser broker installer is missing")
    command = [
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
    ]
    environment = _windows_child_environment()
    if managed:
        from computer_use.browser.managed_authorization import (
            managed_launch_authorization,
            sha256,
        )
        from computer_use.browser.profile import load_package_trust, select_profile

        profile = str(load_package_trust()["release_profile"])
        selected = select_profile()
        envelope, _authorized_manifest = managed_launch_authorization(
            _managed_authorization_pipe, profile=profile
        )
        from computer_use.browser.offline_attestation import local_path

        root = local_path(str(envelope["installed_root"]))
        reports = _profile_path(
            root,
            f"managed-helpers/{selected.architecture}/signature-reports.json",
        )
        if not reports.is_file():
            raise OSError("the installed helper signature reports are missing")
        command.extend(
            [
                "-ExpectedManifestSha256",
                sha256(manifest_path.read_bytes()),
                "-SignatureReports",
                _windows_path(reports),
            ]
        )
        environment["VADGR_CUA_RELEASE_PROFILE"] = profile
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=environment,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise OSError("the Windows browser broker failed verified deployment")
    output = result.stdout.strip().splitlines()[-1]
    if managed:
        try:
            receipt = json.loads(output)
            destination = str(receipt["destination"])
        except (KeyError, TypeError, ValueError) as error:
            raise OSError("the managed broker returned an invalid deployment receipt") from error
        if (
            receipt.get("archive_sha256") != manifest["archive"]["sha256"]
            or receipt.get("broker_final_manifest_sha256") != _sha256(manifest_path)
            or receipt.get("member_count") != len(manifest["files"])
        ):
            raise OSError("the managed broker deployment receipt does not match its input")
        version = manifest["cua_version"]
        archive_hash = manifest["archive"]["sha256"]
    else:
        destination = output
        version = manifest["version"]
        archive_hash = manifest["archive_sha256"]
    expected_suffix = f"\\{version}\\{archive_hash}"
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
    if manifest.get("mode") == "managed-signed":
        return str(manifest["archive"]["sha256"])
    return str(manifest["archive_sha256"])


def _run_upgrade_handoff(bundle: str) -> dict[str, object]:
    executable = f"{bundle}\\{BROKER_EXECUTABLE}"
    authorization = _handoff_authorization()
    command = (
        "$env:PSModulePath = $PSHOME + '\\Modules'; "
        "$Spec = [Console]::In.ReadToEnd() | ConvertFrom-Json; "
        "$Arguments = @('upgrade-handoff'); "
        "if ($null -ne $Spec.authorization) { "
        "$Arguments += @('--authorization', $Spec.authorization.path, "
        "'--authorization-sha256', $Spec.authorization.sha256) }; "
        "& $Spec.executable @Arguments"
    )
    authorization_spec = None
    if authorization is not None:
        authorization_spec = {
            "path": _windows_path(authorization[0]),
            "sha256": authorization[1],
        }
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        input=json.dumps(
            {"executable": executable, "authorization": authorization_spec},
            separators=(",", ":"),
        ),
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
