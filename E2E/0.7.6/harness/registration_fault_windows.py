# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Temporarily remove only test registration defaults, then restore their exact types."""

import argparse
import base64
import ctypes
import importlib.util
import json
import math
import os
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

SUBKEYS = (
    r"Software\Google\Chrome\NativeMessagingHosts\com.vadgr.cua",
    r"Software\Microsoft\Edge\NativeMessagingHosts\com.vadgr.cua",
)


def private_file(path):
    location = Path(__file__).with_name("broker_fault_relay.py")
    spec = importlib.util.spec_from_file_location("registration_private_file", location)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.windows_private_fd(path)


def acl_bytes(handle):
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    security.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
                                        pointer, pointer, pointer, pointer, ctypes.POINTER(pointer)]
    security.GetSecurityInfo.restype = wintypes.DWORD
    security.GetSecurityDescriptorLength.argtypes = [pointer]
    security.GetSecurityDescriptorLength.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    descriptor = pointer()
    if security.GetSecurityInfo(int(handle), 4, 7, None, None, None, None,
                                ctypes.byref(descriptor)):
        raise ValueError("cannot snapshot registration permissions")
    try:
        return ctypes.string_at(descriptor, security.GetSecurityDescriptorLength(descriptor))
    finally:
        kernel.LocalFree(descriptor)


def read_default(registry, handle):
    try:
        value, kind = registry.QueryValueEx(handle, "")
        return {"present": True, "kind": kind, "value": value}
    except FileNotFoundError:
        return {"present": False}


def encode(value):
    if isinstance(value, bytes):
        return {"bytes_base64": base64.b64encode(value).decode("ascii")}
    raise TypeError("unsupported registration snapshot type")


def fault(root, snapshot, ready, done, seconds, *, subkeys=SUBKEYS):
    import winreg

    records = []
    try:
        for subkey in subkeys:
            try:
                handle = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0,
                                       winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | 0x20000)
            except FileNotFoundError:
                records.append({"subkey": subkey, "exists": False})
                continue
            record = {"subkey": subkey, "exists": True, "handle": handle}
            records.append(record)
            record.update(default=read_default(winreg, handle), acl=acl_bytes(handle))
        # File creation attaches and verifies the owner-only DACL before bytes.
        fd = private_file(snapshot)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump([{key: value for key, value in record.items() if key != "handle"}
                       for record in records], stream, default=encode)
            stream.flush()
            os.fsync(stream.fileno())
        mutated = []
        try:
            for record in records:
                if record["exists"] and record["default"]["present"]:
                    # A retained handle identifies the exact key. No key is
                    # deleted or recreated, so other values and ACLs stay intact.
                    mutated.append(record)
                    winreg.DeleteValue(record["handle"], "")
            if any(record["exists"] and read_default(winreg, record["handle"])["present"]
                   for record in records):
                raise ValueError("registration fault did not take effect")
            with ready.open("x", encoding="utf-8") as stream:
                json.dump({"event": "ready", "removed_count": len(mutated),
                           "monotonic": time.monotonic()}, stream)
            deadline = time.monotonic() + seconds
            while not done.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("registration fault window ended")
                time.sleep(.1)
        finally:
            failed = False
            for record in reversed(records):
                if not record["exists"]:
                    continue
                try:
                    original = record["default"]
                    if original["present"]:
                        winreg.SetValueEx(record["handle"], "", 0,
                                         original["kind"], original["value"])
                    else:
                        try:
                            winreg.DeleteValue(record["handle"], "")
                        except FileNotFoundError:
                            pass
                except OSError:
                    failed = True
            for record in records:
                if record["exists"]:
                    try:
                        if (read_default(winreg, record["handle"]) != record["default"]
                                or acl_bytes(record["handle"]) != record["acl"]):
                            failed = True
                    except OSError:
                        failed = True
                else:
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, record["subkey"]):
                            failed = True
                    except FileNotFoundError:
                        pass
            if failed:
                raise ValueError("registration restore verification failed")
    finally:
        for record in records:
            if "handle" in record:
                winreg.CloseKey(record["handle"])


def validate(root, snapshot, ready, done, seconds):
    if sys.platform != "win32":
        raise ValueError("native Windows is required")
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 180:
        raise ValueError("fault window must be between 0 and 180 seconds")
    root = root.resolve(strict=True)
    bases = (Path(tempfile.gettempdir()).resolve(), Path(__file__).resolve().parents[4] / ".tmp")
    if (not root.is_dir() or not root.name.startswith(("vadgr-cua-", "cua-"))
            or not any(root != base and root.is_relative_to(base.resolve()) for base in bases)):
        raise ValueError("expected an isolated temporary CUA root")
    paths = [path.resolve() for path in (snapshot, ready, done)]
    if len(set(paths)) != 3 or any(
        not path.is_relative_to(root) or path == root or path.exists() for path in paths
    ):
        raise ValueError("fault files must be fresh and inside the isolated root")
    return root, *paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot-file", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--done-file", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=180)
    args = parser.parse_args()
    try:
        paths = validate(args.root, args.snapshot_file, args.ready_file, args.done_file, args.seconds)
        fault(*paths, args.seconds)
        print(json.dumps({"event": "restored", "verified": True}))
        return 0
    except (OSError, ValueError):
        print(json.dumps({"event": "fault_failed", "inspect_private_snapshot": True}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
