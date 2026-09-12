# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare an opaque loopback transport fault for one isolated B09 client.

Standard input accepts {"cut_seconds": 8} or {"stop": true}. EOF stops the
relay. Standard output contains timing and connection metadata, never bytes.
"""

import argparse
import json
import math
import os
import queue
import select
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def isolated_path(root: Path, path: Path) -> Path:
    root = root.resolve(strict=True)
    temporary_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    if not root.is_dir() or not root.name.startswith("vadgr-cua-"):
        raise ValueError("expected a named isolated CUA directory")
    if not any(root.is_relative_to(base) and root != base for base in temporary_roots):
        raise ValueError("isolated root must be below the system temporary directory")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("endpoint path must be inside the isolated root")
    return resolved


def read_endpoint(root: Path, path: Path) -> dict:
    endpoint = json.loads(isolated_path(root, path).read_text(encoding="utf-8"))
    port = endpoint.get("port")
    if endpoint.get("host") != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("endpoint must name a valid IPv4 loopback port")
    return endpoint


def write_alias(root: Path, source: Path, alias: Path, endpoint: dict, port: int,
                *, retain: bool = False) -> Path:
    destination = isolated_path(root, alias)
    if destination == isolated_path(root, source):
        raise ValueError("alias must not replace the original endpoint")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("relay port is invalid")
    payload = dict(endpoint, port=port)
    fd = (
        windows_private_fd(destination, retain_on_failure=retain) if sys.platform == "win32"
        else os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    )
    identity = os.fstat(fd).st_ino
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
    except BaseException:
        if not retain and destination.exists() and destination.stat().st_ino == identity:
            destination.unlink()
        raise
    return destination


def windows_owner_only_dacl(descriptor, sid) -> bool:
    """Compare permissions, not Windows' version-dependent SDDL formatting."""
    import ctypes
    from ctypes import wintypes

    security = ctypes.WinDLL("advapi32", use_last_error=True)
    pointer = ctypes.c_void_p
    security.GetSecurityDescriptorControl.argtypes = [
        pointer, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
    ]
    security.GetSecurityDescriptorDacl.argtypes = [
        pointer, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(pointer),
        ctypes.POINTER(wintypes.BOOL),
    ]
    security.GetAclInformation.argtypes = [pointer, pointer, wintypes.DWORD, ctypes.c_int]
    security.GetAce.argtypes = [pointer, wintypes.DWORD, ctypes.POINTER(pointer)]
    security.EqualSid.argtypes = [pointer, pointer]

    class AclSize(ctypes.Structure):
        _fields_ = [("count", wintypes.DWORD), ("used", wintypes.DWORD),
                    ("free", wintypes.DWORD)]

    class AllowedAce(ctypes.Structure):
        _fields_ = [("type", wintypes.BYTE), ("flags", wintypes.BYTE),
                    ("size", wintypes.WORD), ("mask", wintypes.DWORD),
                    ("sid_start", wintypes.DWORD)]

    control = wintypes.WORD()
    revision = wintypes.DWORD()
    present = wintypes.BOOL()
    defaulted = wintypes.BOOL()
    dacl = pointer()
    info = AclSize()
    ace_pointer = pointer()
    if not security.GetSecurityDescriptorControl(descriptor, ctypes.byref(control),
                                                 ctypes.byref(revision)):
        return False
    if not control.value & 0x1000:
        return False
    if not security.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                              ctypes.byref(dacl), ctypes.byref(defaulted)):
        return False
    if not present.value or not dacl:
        return False
    if not security.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
        return False
    if info.count != 1 or not security.GetAce(dacl, 0, ctypes.byref(ace_pointer)):
        return False
    ace = ctypes.cast(ace_pointer, ctypes.POINTER(AllowedAce)).contents
    return bool(
        ace.type == 0 and ace.flags == 0 and ace.mask == 0x1F01FF
        and security.EqualSid(ace_pointer.value + AllowedAce.sid_start.offset, sid)
    )


def windows_private_fd(destination: Path, *, retain_on_failure: bool = False) -> int:
    """Create an exclusive empty file with a protected owner-only DACL."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    pointer = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, pointer,
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    security.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(pointer), pointer,
    ]
    security.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
                                        pointer, pointer, pointer, pointer, ctypes.POINTER(pointer)]
    security.GetSecurityInfo.restype = wintypes.DWORD

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("descriptor", pointer),
                    ("inherit", wintypes.BOOL)]

    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(SecurityAttributes), wintypes.DWORD,
                                  wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    token = wintypes.HANDLE()
    sid_text = pointer()
    descriptor = pointer()
    observed = pointer()
    handle = None
    created = False
    try:
        if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ValueError("cannot identify the file owner")
        size = wintypes.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        user = ctypes.create_string_buffer(size.value)
        if not security.GetTokenInformation(token, 1, user, size, ctypes.byref(size)):
            raise ValueError("cannot identify the file owner")
        sid = ctypes.cast(user, ctypes.POINTER(pointer))[0]
        if not security.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise ValueError("cannot identify the file owner")
        # P disables inherited ACEs. The single allow ACE gives only this user
        # full control. No credential bytes exist before this DACL is attached.
        expected = "D:P(A;;FA;;;" + ctypes.wstring_at(sid_text) + ")"
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            expected, 1, ctypes.byref(descriptor), None,
        ):
            raise ValueError("cannot prepare a private alias")
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        handle = kernel.CreateFileW(str(destination), 0x40000000 | 0x00020000,
                                    0, ctypes.byref(attributes), 1, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            handle = None
            if ctypes.get_last_error() in (80, 183):
                raise FileExistsError("alias already exists")
            raise ValueError("cannot create a private alias")
        created = True
        if security.GetSecurityInfo(handle, 1, 4, None, None, None, None,
                                    ctypes.byref(observed)):
            raise ValueError("cannot verify the alias DACL")
        if not windows_owner_only_dacl(observed, sid):
            raise ValueError("alias DACL is not owner-only")
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
        handle = None
        return fd
    except BaseException:
        if handle is not None:
            kernel.CloseHandle(handle)
            handle = None
        if created and not retain_on_failure:
            destination.unlink()
        raise
    finally:
        if token:
            kernel.CloseHandle(token)
        for allocated in (sid_text, descriptor, observed):
            if allocated:
                kernel.LocalFree(allocated)


def duration(command: dict) -> float:
    value = command.get("cut_seconds")
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 120:
        raise ValueError("cut_seconds must be finite and between 0 and 120")
    return float(value)


class Relay:
    def __init__(self, port: int, emit):
        self.upstream = ("127.0.0.1", port)
        self.emit = emit
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.connections = set()
        self.lock = threading.Lock()
        self.until = 0.0
        self.stopped = False

    def close_connections(self):
        with self.lock:
            connections = tuple(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        return len(connections) // 2

    def cut(self, seconds):
        seconds = duration({"cut_seconds": seconds})
        self.until = time.monotonic() + seconds
        count = self.close_connections()
        self.emit("cut", seconds=seconds, connection_count=count)

    def forward(self, downstream, upstream):
        try:
            while not self.stopped:
                ready, _, _ = select.select([downstream, upstream], [], [], 0.1)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is downstream else downstream
                    target.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                self.connections.discard(downstream)
                self.connections.discard(upstream)
            downstream.close()
            upstream.close()

    def tick(self):
        if self.until and time.monotonic() >= self.until:
            self.until = 0.0
            self.emit("restored")
        try:
            downstream, _ = self.listener.accept()
        except TimeoutError:
            return
        if self.until:
            downstream.close()
            self.emit("connection_refused")
            return
        try:
            upstream = socket.create_connection(self.upstream, timeout=2)
        except OSError:
            downstream.close()
            self.emit("upstream_unavailable")
            return
        downstream.settimeout(2)
        with self.lock:
            self.connections.update((downstream, upstream))
        threading.Thread(target=self.forward, args=(downstream, upstream), daemon=True).start()
        self.emit("connection_opened")

    def close(self):
        self.stopped = True
        self.listener.close()
        self.close_connections()


def emit(event, **metadata):
    print(
        json.dumps(
            {
                "event": event,
                "monotonic": time.monotonic(),
                "utc": datetime.now(timezone.utc).isoformat(),
                **metadata,
            }
        ),
        flush=True,
    )


def main():
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--endpoint", required=True, type=Path)
    parser.add_argument("--alias", required=True, type=Path)
    parser.add_argument("--retain-alias", action="store_true",
                        help="retain private alias files, including failed writes")
    args = parser.parse_args()
    endpoint = read_endpoint(args.root, args.endpoint)
    relay = Relay(endpoint["port"], emit)
    alias = None
    commands = queue.Queue()

    def read_commands():
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("command must be an object")
                commands.put(command)
            except ValueError:
                emit("invalid_command")
        commands.put({"stop": True})

    try:
        alias = write_alias(args.root, args.endpoint, args.alias, endpoint, relay.port,
                            retain=args.retain_alias)
        alias_identity = alias.stat().st_ino
        emit("ready", relay_port=relay.port, upstream_port=endpoint["port"])
        threading.Thread(target=read_commands, daemon=True).start()
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None
            if command is not None:
                if command.get("stop") is True:
                    break
                try:
                    relay.cut(duration(command))
                except ValueError:
                    emit("invalid_command")
            relay.tick()
    finally:
        relay.close()
        if (not args.retain_alias and alias is not None and alias.exists()
                and alias.stat().st_ino == alias_identity):
            alias.unlink()
        emit("stopped")


if __name__ == "__main__":
    main()
