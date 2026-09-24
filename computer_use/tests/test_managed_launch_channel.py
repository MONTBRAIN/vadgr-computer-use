"""Validate native channel types without reading ambient authorization files."""

import ctypes
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from computer_use.browser import windows_broker


def _select(monkeypatch, fd):
    monkeypatch.delenv("VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE", raising=False)
    monkeypatch.setenv("VADGR_CUA_LAUNCH_AUTHORIZATION_FD", str(fd))


def test_authorization_accepts_only_read_end(monkeypatch):
    read, write = os.pipe()
    try:
        _select(monkeypatch, write)
        with pytest.raises(OSError, match="channel is invalid"):
            windows_broker._managed_authorization_pipe()
        _select(monkeypatch, read)
        os.write(write, b"authenticated channel")
        os.close(write)
        write = None
        with windows_broker._managed_authorization_pipe() as stream:
            read = None
            assert stream.read() == b"authenticated channel"
    finally:
        for fd in (read, write):
            if fd is not None:
                os.close(fd)


def test_authorization_refuses_ordinary_file(monkeypatch):
    with Path(__file__).open("rb") as ordinary:
        _select(monkeypatch, ordinary.fileno())
        with pytest.raises(OSError, match="channel is invalid"):
            windows_broker._managed_authorization_pipe()
        assert ordinary.tell() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows inherited handle")
@pytest.mark.parametrize("kind", ["read", "write", "file"])
def test_authorization_checks_windows_handle_before_read(monkeypatch, kind):
    import msvcrt
    from ctypes import wintypes

    read, write = os.pipe()
    with Path(__file__).open("rb") as ordinary:
        fd = {"read": read, "write": write, "file": ordinary.fileno()}[kind]
        native = ctypes.WinDLL("kernel32", use_last_error=True)
        native.GetCurrentProcess.restype = wintypes.HANDLE
        native.DuplicateHandle.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
            ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        ]
        current = native.GetCurrentProcess()
        duplicate = wintypes.HANDLE()
        assert native.DuplicateHandle(current, msvcrt.get_osfhandle(fd), current,
                                      ctypes.byref(duplicate), 0, True, 2)
        os.close(read)
        os.close(write)
        monkeypatch.delenv("VADGR_CUA_LAUNCH_AUTHORIZATION_FD", raising=False)
        monkeypatch.setenv("VADGR_CUA_LAUNCH_AUTHORIZATION_HANDLE", str(duplicate.value))
        if kind == "read":
            with windows_broker._managed_authorization_pipe() as stream:
                assert stream.read() == b""
        else:
            with pytest.raises(OSError, match="channel is invalid"):
                windows_broker._managed_authorization_pipe()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux named FIFO")
def test_authorization_refuses_named_fifo(tmp_path, monkeypatch):
    path = tmp_path / "authorization"
    os.mkfifo(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        _select(monkeypatch, fd)
        with pytest.raises(OSError, match="channel is invalid"):
            windows_broker._managed_authorization_pipe()
    finally:
        os.close(fd)


def test_handoff_translates_authenticated_windows_root(tmp_path, monkeypatch):
    profile = SimpleNamespace(value="wsl-x86_64", architecture="x86_64", windows_helpers=True)
    path = tmp_path / "managed-helpers/x86_64/helper-closure-authorization.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"authorization")
    root = "C:\\installed\\lib\\cua"
    monkeypatch.setattr("computer_use.browser.profile.load_package_trust", lambda: {"mode": "managed"})
    monkeypatch.setattr("computer_use.browser.profile.select_profile", lambda: profile)
    monkeypatch.setattr(
        "computer_use.browser.managed_authorization.managed_launch_authorization",
        lambda *args, **kwargs: ({"installed_root": root,
                                 "helper_closure_authorization_sha256": windows_broker._sha256(path)}, {}),
    )
    translated = []

    def local_path(value):
        translated.append(value)
        return tmp_path

    monkeypatch.setattr("computer_use.browser.offline_attestation.local_path", local_path)
    assert windows_broker._handoff_authorization() == (path, windows_broker._sha256(path))
    assert translated == [root]
