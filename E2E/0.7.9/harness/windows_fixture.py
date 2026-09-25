"""Reuse released Windows fixture preparation for unsigned 0.7.9 slices."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

SAFE_PROCESS_ENVIRONMENT = (
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL",
    "PROCESSOR_REVISION",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
)


def child_environment(root: Path, endpoint: Path, source=None) -> dict[str, str]:
    """Build a fixture environment without inheriting ambient credentials."""
    source = os.environ if source is None else source
    environment = {name: source[name] for name in SAFE_PROCESS_ENVIRONMENT if name in source}
    environment.update(
        {
            "HOME": str(root / "home"),
            "USERPROFILE": str(root / "home"),
            "APPDATA": str(root / "roaming"),
            "LOCALAPPDATA": str(root / "appdata"),
            "XDG_CONFIG_HOME": str(root / "home/.config"),
            "XDG_STATE_HOME": str(root / "state"),
            "VADGR_CUA_BROKER_ENDPOINT": str(endpoint),
        }
    )
    return environment


SOURCE = Path(__file__).resolve().parents[2] / "0.7.8/harness/upgrade_fixture.py"
spec = importlib.util.spec_from_file_location("released_fixture", SOURCE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.EXPECTED["0.7.8"] = {
    "wheel": "1c905c200d0e2190bb3512ecf0c58f1b683900ad15288cef00c14a732fb10535",
    "archive": "cb8d47ede577c76683576a7bb4f8e5251eaa884b66bd50a2a35ad394966ce39d",
}
fixture.child_environment = child_environment

PID_REUSE_BACKUP = ".pid-reuse-endpoint.private.json"
PID_REUSE_PROCESS = ".pid-reuse-process.private.json"


def _validate_fixture_process(root: Path, pid: int, created: str) -> None:
    from computer_use.browser.windows_process import _WindowsProcess

    process = _WindowsProcess(pid)
    try:
        executable = process.image_path().resolve(strict=True)
        if root not in executable.parents or executable.name.lower() != fixture.EXECUTABLE:
            raise ValueError("pid-reuse process is outside the validated fixture")
        if str(process.creation_filetime()) != created or not process.is_running():
            raise ValueError("pid-reuse process identity is stale")
    finally:
        process.close()


def _set_process_suspended(pid: int, suspended: bool) -> None:
    if fixture.sys.platform != "win32":
        raise ValueError("pid-reuse process control requires native Windows")
    import ctypes
    from ctypes import wintypes

    access = 0x0800 | 0x1000  # PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    function = ntdll.NtSuspendProcess if suspended else ntdll.NtResumeProcess
    function.argtypes = (wintypes.HANDLE,)
    function.restype = wintypes.LONG
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        status = int(function(handle))
        if status < 0:
            raise OSError(
                f"process {'suspend' if suspended else 'resume'} failed: NTSTATUS {status:#x}"
            )
    finally:
        kernel32.CloseHandle(handle)


def pid_reuse_fault(root: Path) -> dict[str, object]:
    endpoint = root / "state/browser-broker.json"
    backup = root / PID_REUSE_BACKUP
    process_backup = root / PID_REUSE_PROCESS
    if endpoint.is_symlink() or backup.exists() or process_backup.exists():
        raise ValueError("pid-reuse fixture must be a regular, unrestored endpoint")
    value = json.loads(endpoint.read_text(encoding="utf-8"))
    pid = value.get("pid")
    created = value.get("process_created_filetime")
    if (
        not isinstance(pid, int)
        or pid < 1
        or not isinstance(created, str)
        or not created.isdecimal()
    ):
        raise ValueError("pid-reuse fixture requires a complete live process identity")
    _validate_fixture_process(root, pid, created)
    _set_process_suspended(pid, True)
    try:
        raw = endpoint.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if value.get("pid") != pid or value.get("process_created_filetime") != created:
            raise ValueError("pid-reuse endpoint changed before suspension completed")
        descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
        descriptor = os.open(process_backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"pid": pid, "process_created_filetime": created}, output)
            output.write("\n")
        value["process_created_filetime"] = str(int(created) + 1)
        replacement = endpoint.with_suffix(".tmp")
        replacement.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(replacement, endpoint)
    except BaseException:
        _set_process_suspended(pid, False)
        endpoint.with_suffix(".tmp").unlink(missing_ok=True)
        process_backup.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        raise
    return {"event": "pid_reuse_fault_applied", "pid": pid, "creation_identity_changed": True}


def pid_reuse_restore(root: Path) -> dict[str, object]:
    endpoint = root / "state/browser-broker.json"
    backup = root / PID_REUSE_BACKUP
    process_backup = root / PID_REUSE_PROCESS
    if endpoint.is_symlink() or backup.is_symlink() or process_backup.is_symlink():
        raise ValueError("pid-reuse paths cannot be symbolic links")
    raw = backup.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    pid = value.get("pid")
    process_identity = json.loads(process_backup.read_text(encoding="utf-8"))
    if (
        not isinstance(pid, int)
        or pid < 1
        or process_identity.get("pid") != pid
        or process_identity.get("process_created_filetime") != value.get("process_created_filetime")
    ):
        raise ValueError("pid-reuse backup has no process identity")
    created = str(process_identity["process_created_filetime"])
    _validate_fixture_process(root, pid, created)
    replacement = endpoint.with_suffix(".tmp")
    replacement.write_bytes(raw)
    os.replace(replacement, endpoint)
    _set_process_suspended(pid, False)
    process_backup.unlink()
    backup.unlink()
    return {"event": "pid_reuse_endpoint_restored", "pid": pid}


original_fault = fixture.fault


def fault(root: Path, action: str) -> int:
    if action == "pid-reuse":
        fixture.emit(pid_reuse_fault(root))
        return 0
    if action == "pid-restore":
        fixture.emit(pid_reuse_restore(root))
        return 0
    return original_fault(root, action)


fixture.fault = fault


def main() -> int:
    parser = fixture.argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "init",
            "prepare",
            "start",
            "observe",
            "fault",
            "stop",
            "extension-start",
            "extension-serve",
            "extension-observe",
        ),
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--release", choices=tuple(fixture.EXPECTED))
    parser.add_argument("--wheel")
    parser.add_argument("--action", choices=("remove", "corrupt", "pid-reuse", "pid-restore"))
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    root = fixture.checked_root(args.root, create=args.command == "init")
    if args.command == "init":
        fixture.emit({"event": "initialized"})
        return 0
    if args.command == "prepare":
        if args.release is None or args.wheel is None:
            parser.error("prepare requires --release and --wheel")
        return fixture.prepare(root, args.release, args.wheel)
    if args.command == "start":
        if args.release is None:
            parser.error("start requires --release")
        return fixture.start(root, args.release, synthetic=args.synthetic)
    if args.command == "observe":
        fixture.emit(fixture.safe_identity(root / "state/browser-broker.json"))
        return 0
    if args.command == "extension-start":
        return fixture.extension_start(root)
    if args.command == "extension-serve":
        return fixture.extension_serve(root)
    if args.command == "extension-observe":
        return fixture.extension_observe(root)
    if args.command == "fault":
        if args.action is None:
            parser.error("fault requires --action")
        return fault(root, args.action)
    return fixture.stop(root)


if __name__ == "__main__":
    raise SystemExit(main())
