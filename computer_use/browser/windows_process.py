# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prove and replace an exact released Windows browser broker."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path, PurePosixPath

BROKER_EXECUTABLE = "vadgr-cua-browser-broker.exe"
UPGRADE_UNSAFE = "browser_broker_upgrade_unsafe"
UPGRADE_TIMEOUT = "browser_broker_upgrade_timeout"
_WAIT_MS = 10_000
_REPARSE_POINT = 0x400
_ERROR_MORE_DATA = 234
_RM_SESSION_KEY_LENGTH = 32


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _RmUniqueProcess(ctypes.Structure):
    _fields_ = [("pid", wintypes.DWORD), ("started", _FileTime)]


class _RmProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", _RmUniqueProcess),
        ("app_name", wintypes.WCHAR * 256),
        ("service_name", wintypes.WCHAR * 64),
        ("application_type", ctypes.c_int),
        ("status", wintypes.ULONG),
        ("terminal_session_id", wintypes.DWORD),
        ("restartable", wintypes.BOOL),
    ]


class UpgradeHandoffError(OSError):
    """A safe public result from a refused Windows broker handoff."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(message)
        self.code = code
        self.remediation = remediation


class _ProcessExited(OSError):
    pass


def _unsafe() -> UpgradeHandoffError:
    return UpgradeHandoffError(
        UPGRADE_UNSAFE,
        "the running browser broker could not be proved as an allowed released Vadgr broker",
        "run vadgr-cua doctor; close only the broker it identifies, then retry",
    )


def _timeout() -> UpgradeHandoffError:
    return UpgradeHandoffError(
        UPGRADE_TIMEOUT,
        "the verified browser broker did not exit before the upgrade deadline",
        "run vadgr-cua doctor; retry after the identified broker exits",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordinary(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    if not predicate(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        raise _unsafe()
    if not directory and info.st_nlink != 1:
        raise _unsafe()
    return info


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _below(path: Path, root: Path) -> bool:
    try:
        normalized_path = os.path.normcase(os.path.abspath(path))
        normalized_root = os.path.normcase(os.path.abspath(root))
        return os.path.commonpath((normalized_path, normalized_root)) == normalized_root
    except ValueError:
        return False


def _target(architecture: str) -> str:
    try:
        return {
            "x86_64": "x86_64-pc-windows-msvc",
            "aarch64": "aarch64-pc-windows-msvc",
        }[architecture]
    except KeyError as error:
        raise _unsafe() from error


def _load_catalog(path: Path, *, target: str) -> dict[str, object]:
    _ordinary(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _unsafe() from error
    if (
        value.get("schema") != 1
        or value.get("target") != target
        or not isinstance(value.get("releases"), list)
    ):
        raise _unsafe()
    return value


def _adoption_row(adoption: dict[str, object], bundle: Path, *, target: str) -> dict[str, object]:
    """Construct one predecessor row from an authenticated exact transition.

    The caller must authenticate the authorization record before invoking the
    native handoff. This function still checks its complete closed shape and
    binds it to the candidate architecture and content-addressed predecessor.
    """
    required = {
        "direction",
        "architecture",
        "cua_version",
        "source_commit",
        "input_closure",
        "final_closure",
    }
    if not isinstance(adoption, dict) or set(adoption) != required:
        raise _unsafe()
    architecture = adoption.get("architecture")
    if (
        adoption.get("direction") != "unsigned-to-signed"
        or not isinstance(architecture, str)
        or _target(architecture) != target
        or adoption.get("cua_version") != bundle.parent.name
        or not isinstance(adoption.get("source_commit"), str)
        or len(adoption["source_commit"]) != 40
        or any(character not in "0123456789abcdef" for character in adoption["source_commit"])
    ):
        raise _unsafe()
    closures = []
    for name in ("input_closure", "final_closure"):
        closure = adoption.get(name)
        if not isinstance(closure, dict) or set(closure) != {
            "relay_sha256",
            "archive_sha256",
            "manifest_sha256",
        }:
            raise _unsafe()
        for value in closure.values():
            if (
                not isinstance(value, str)
                or len(value) != 64
                or value == "0" * 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise _unsafe()
        closures.append(closure)
    predecessor = closures[0]
    if predecessor["archive_sha256"] != bundle.name:
        raise _unsafe()
    return {
        "version": adoption["cua_version"],
        "archive_sha256": predecessor["archive_sha256"],
        "broker_relative_path": BROKER_EXECUTABLE,
        "broker_sha256": None,
        "manifest_sha256": predecessor["manifest_sha256"],
        "protocol_min": 1,
        "protocol_max": 1,
    }


def _catalog_row(
    catalog: dict[str, object],
    bundle: Path,
    *,
    target: str,
    adoption: dict[str, object] | None = None,
) -> dict[str, object]:
    version = bundle.parent.name
    archive_hash = bundle.name
    rows = [
        row
        for row in catalog["releases"]
        if isinstance(row, dict)
        and row.get("version") == version
        and row.get("archive_sha256") == archive_hash
    ]
    if not rows and adoption is not None:
        return _adoption_row(adoption, bundle, target=target)
    if len(rows) != 1:
        raise _unsafe()
    row = rows[0]
    required = ("broker_relative_path", "broker_sha256", "manifest_sha256")
    if any(not isinstance(row.get(name), str) or not row[name] for name in required):
        raise _unsafe()
    if row.get("protocol_min") != 1 or row.get("protocol_max") != 1:
        raise _unsafe()
    return row


def _verify_bundle(bundle: Path, row: dict[str, object], *, target: str) -> Path:
    root = bundle.resolve(strict=True)
    _ordinary(root, directory=True)
    manifest_path = root / "bundle-manifest.json"
    _ordinary(manifest_path)
    raw_manifest = manifest_path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != row["manifest_sha256"]:
        raise _unsafe()
    try:
        manifest = json.loads(raw_manifest)
    except ValueError as error:
        raise _unsafe() from error
    if (
        manifest.get("version") != row["version"]
        or manifest.get("target") != target
        or manifest.get("archive_sha256") != row["archive_sha256"]
        or not isinstance(manifest.get("files"), list)
    ):
        raise _unsafe()

    expected: dict[str, dict[str, object]] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise _unsafe()
        raw_relative = item.get("path")
        relative = PurePosixPath(raw_relative) if isinstance(raw_relative, str) else None
        if (
            relative is None
            or relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.as_posix() in expected
            or not isinstance(item.get("size"), int)
            or not isinstance(item.get("sha256"), str)
        ):
            raise _unsafe()
        expected[relative.as_posix()] = item

    actual: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            _ordinary(path, directory=True)
            continue
        _ordinary(path)
        if relative == "bundle-manifest.json":
            continue
        if relative not in expected or not _below(path.resolve(strict=True), root):
            raise _unsafe()
        item = expected[relative]
        if path.stat().st_size != item["size"] or _sha256(path) != item["sha256"]:
            raise _unsafe()
        actual.add(relative)
    if actual != set(expected):
        raise _unsafe()

    broker_relative = str(row["broker_relative_path"])
    broker = root / broker_relative
    broker_record = expected.get(broker_relative)
    expected_broker_sha = row["broker_sha256"]
    if expected_broker_sha is None:
        if broker_record is None or not isinstance(broker_record.get("sha256"), str):
            raise _unsafe()
        expected_broker_sha = broker_record["sha256"]
    if not _below(broker.resolve(strict=True), root) or _sha256(broker) != expected_broker_sha:
        raise _unsafe()
    return broker


def _read_endpoint(lock_path: Path) -> dict[str, object] | None:
    path = lock_path.with_name("browser-broker.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _verify_owner_and_system(path: Path) -> None:
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import verify_owner_and_system

        verify_owner_and_system(path)


def _current_user_sid() -> str:
    from computer_use.browser.windows_acl import current_user_sid

    return current_user_sid()


def _restart_manager_lock_owners(path: Path) -> tuple[tuple[int, int], ...]:
    """Return the processes that Windows reports as using one exact lock file."""
    if sys.platform != "win32":
        raise OSError("Windows Restart Manager is unavailable")
    manager = ctypes.WinDLL("Rstrtmgr", use_last_error=True)
    manager.RmStartSession.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        wintypes.LPWSTR,
    ]
    manager.RmRegisterResources.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        ctypes.POINTER(wintypes.LPCWSTR),
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.c_void_p,
    ]
    manager.RmGetList.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(_RmProcessInfo),
        ctypes.POINTER(wintypes.DWORD),
    ]
    manager.RmEndSession.argtypes = [wintypes.DWORD]
    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(_RM_SESSION_KEY_LENGTH + 1)
    result = manager.RmStartSession(ctypes.byref(session), 0, key)
    if result:
        raise OSError(result, "failed to start Windows lock-owner query")
    try:
        absolute = os.path.abspath(path)
        resources = (wintypes.LPCWSTR * 1)(absolute)
        result = manager.RmRegisterResources(session, 1, resources, 0, None, 0, None)
        if result:
            raise OSError(result, "failed to register the broker lock")
        for _attempt in range(4):
            needed = wintypes.UINT()
            count = wintypes.UINT()
            reasons = wintypes.DWORD()
            result = manager.RmGetList(
                session,
                ctypes.byref(needed),
                ctypes.byref(count),
                None,
                ctypes.byref(reasons),
            )
            if result == 0 and needed.value == 0:
                return ()
            if result != _ERROR_MORE_DATA or needed.value == 0:
                raise OSError(result, "failed to size the broker lock-owner query")
            values = (_RmProcessInfo * needed.value)()
            count.value = needed.value
            result = manager.RmGetList(
                session,
                ctypes.byref(needed),
                ctypes.byref(count),
                values,
                ctypes.byref(reasons),
            )
            if result == _ERROR_MORE_DATA:
                continue
            if result:
                raise OSError(result, "failed to read the broker lock owners")
            return tuple(
                (
                    int(item.process.pid),
                    (int(item.process.started.high) << 32) | int(item.process.started.low),
                )
                for item in values[: count.value]
            )
        raise OSError(_ERROR_MORE_DATA, "broker lock owners changed during query")
    finally:
        manager.RmEndSession(session)


class _WindowsProcess:
    def __init__(self, pid: int) -> None:
        if sys.platform != "win32":
            raise OSError("Windows process inspection is unavailable")
        self.pid = pid
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._api = ctypes.WinDLL("advapi32", use_last_error=True)
        self._kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel.OpenProcess.restype = wintypes.HANDLE
        access = 0x1000 | 0x00100000 | 0x0001
        self._handle = self._kernel.OpenProcess(access, False, pid)
        if not self._handle:
            error = ctypes.get_last_error()
            if error == 87:
                raise _ProcessExited("the broker process exited")
            raise ctypes.WinError(error)

    def image_path(self) -> Path:
        self._kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not self._kernel.QueryFullProcessImageNameW(self._handle, 0, buffer, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return Path(buffer.value)

    def user_sid(self) -> str:
        self._api.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self._api.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._api.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        token = wintypes.HANDLE()
        sid_text = ctypes.c_void_p()
        try:
            if not self._api.OpenProcessToken(self._handle, 8, ctypes.byref(token)):
                raise ctypes.WinError(ctypes.get_last_error())
            size = wintypes.DWORD()
            self._api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not self._api.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            if not self._api.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.wstring_at(sid_text)
        finally:
            if token:
                self._kernel.CloseHandle(token)
            if sid_text:
                self._kernel.LocalFree(sid_text)

    def creation_filetime(self) -> int:
        class FileTime(ctypes.Structure):
            _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

        self._kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        ]
        created, exited, kernel, user = FileTime(), FileTime(), FileTime(), FileTime()
        if not self._kernel.GetProcessTimes(
            self._handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return (created.high << 32) | created.low

    def is_running(self) -> bool:
        self._kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        code = wintypes.DWORD()
        if not self._kernel.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value == 259

    def terminate(self) -> None:
        self._kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        if not self._kernel.TerminateProcess(self._handle, 0xC000013A):
            raise ctypes.WinError(ctypes.get_last_error())

    def wait(self, timeout_ms: int) -> bool:
        self._kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        return self._kernel.WaitForSingleObject(self._handle, timeout_ms) == 0

    def close(self) -> None:
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None


def _open_process(pid: int) -> _WindowsProcess:
    return _WindowsProcess(pid)


@contextmanager
def _candidate_guard(path: Path, deadline: float) -> Iterator[None]:
    if sys.platform != "win32":
        yield
        return
    import msvcrt

    from computer_use.browser.private_file import open_private_lock, private_directory

    private_directory(path.parent)
    descriptor = open_private_lock(path)
    file = os.fdopen(descriptor, "r+", encoding="utf-8")
    acquired = False
    try:
        if os.path.getsize(path) == 0:
            file.write("0")
            file.flush()
        while time.monotonic() < deadline:
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
                break
            except OSError:
                time.sleep(0.05)
        if not acquired:
            raise _timeout()
        yield
    finally:
        if acquired:
            try:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        file.close()


def perform_upgrade_handoff(
    *,
    lock_path: Path,
    candidate_bundle: Path,
    catalog_path: Path,
    architecture: str = "x86_64",
    adoption: dict[str, object] | None = None,
    timeout_ms: int = _WAIT_MS,
) -> dict[str, object]:
    """Replace one fully proved predecessor or leave all uncertain state intact."""
    if not lock_path.exists():
        return {"state": "no_predecessor"}
    deadline = time.monotonic() + timeout_ms / 1000
    with _candidate_guard(lock_path.with_name("browser-broker-upgrade.lock"), deadline):
        if not lock_path.exists():
            return {"state": "no_predecessor"}
        process = None
        try:
            _verify_owner_and_system(lock_path.parent)
            _verify_owner_and_system(lock_path)
            owners = _restart_manager_lock_owners(lock_path)
            if not owners:
                return {"state": "already_exited"}
            if len(owners) != 1:
                raise _unsafe()
            owner_pid, owner_created = owners[0]
            try:
                process = _open_process(owner_pid)
            except _ProcessExited:
                return {"state": "already_exited"}
            if process.user_sid() != _current_user_sid():
                raise _unsafe()
            image = process.image_path()
            created = process.creation_filetime()
            if created != owner_created:
                raise _unsafe()
            if not process.is_running():
                return {"state": "already_exited"}

            candidate_executable = candidate_bundle / BROKER_EXECUTABLE
            if _same_path(image, candidate_executable):
                if (
                    process.creation_filetime() != created
                    or not _same_path(process.image_path(), image)
                    or not process.is_running()
                ):
                    raise _unsafe()
                return {
                    "state": "candidate_ready",
                    "process_created_filetime": str(created),
                }

            common_root = candidate_bundle.parents[1]
            if not _below(image, common_root):
                raise _unsafe()
            bundle = image.parent
            target = _target(architecture)
            catalog = _load_catalog(catalog_path, target=target)
            row = _catalog_row(catalog, bundle, target=target, adoption=adoption)
            broker = _verify_bundle(bundle, row, target=target)
            if not _same_path(image, broker):
                raise _unsafe()
            endpoint = _read_endpoint(lock_path)
            if endpoint is not None and (
                endpoint.get("pid") != process.pid
                or endpoint.get("bundle_hash") != row["archive_sha256"]
                or endpoint.get("process_created_filetime") != str(created)
            ):
                raise _unsafe()
            if (
                _restart_manager_lock_owners(lock_path) != ((process.pid, created),)
                or process.creation_filetime() != created
                or not _same_path(process.image_path(), image)
                or not process.is_running()
            ):
                raise _unsafe()
            try:
                process.terminate()
            except OSError as error:
                if not process.is_running():
                    return {"state": "already_exited"}
                raise _timeout() from error
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if not process.wait(remaining_ms):
                raise _timeout()
            return {
                "state": "replaced",
                "version": row["version"],
                "process_created_filetime": str(created),
            }
        except UpgradeHandoffError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise _unsafe() from error
        finally:
            if process is not None:
                process.close()


def current_process_creation_filetime() -> str:
    """Return the creation identity for the current Windows process."""
    process = _open_process(os.getpid())
    try:
        return str(process.creation_filetime())
    finally:
        process.close()
