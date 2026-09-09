"""The B09 fault relay only forwards opaque bytes inside isolated loopback state."""

import importlib.util
import json
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/broker_fault_relay.py"
spec = importlib.util.spec_from_file_location("fault_relay", HELPER)
relay_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay_module)


@pytest.fixture
def isolated():
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-relay-test-") as directory:
        yield Path(directory)


def test_alias_is_private_and_preserves_original(isolated):
    source = isolated / "original.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "test-secret", "pid": 7}
    source.write_text(json.dumps(endpoint))
    alias = isolated / "alias.json"
    relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    if sys.platform == "win32":
        assert_windows_owner_only(alias)
    else:
        assert stat.S_IMODE(alias.stat().st_mode) == 0o600
    assert json.loads(alias.read_text()) == dict(endpoint, port=23456)
    assert json.loads(source.read_text()) == endpoint
    with pytest.raises(FileExistsError):
        relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    with pytest.raises(ValueError):
        relay_module.write_alias(isolated, source, source, endpoint, 23456)


@pytest.mark.parametrize(
    "host,port", [("example.com", 8), ("127.0.0.1", 0), ("127.0.0.1", 65536), ("127.0.0.1", True)]
)
def test_rejects_non_loopback_and_invalid_ports(isolated, host, port):
    source = isolated / "endpoint.json"
    source.write_text(json.dumps({"host": host, "port": port}))
    with pytest.raises(ValueError):
        relay_module.read_endpoint(isolated, source)


def test_rejects_outside_paths_and_symlinks(isolated):
    with pytest.raises(ValueError):
        relay_module.isolated_path(isolated, isolated.parent / "outside.json")
    escape = isolated / "escape"
    if sys.platform == "win32":
        # A junction exercises resolved-path containment without symlink privileges.
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(escape), str(isolated.parent)],
            check=True, capture_output=True,
        )
    else:
        escape.symlink_to(isolated.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        relay_module.isolated_path(isolated, isolated / "escape/endpoint.json")
    with pytest.raises(ValueError):
        relay_module.isolated_path(Path(tempfile.gettempdir()), isolated / "endpoint.json")


@pytest.mark.parametrize("value", [None, True, 0, -1, 121, float("inf"), float("nan"), "8"])
def test_cut_requires_finite_bounded_duration(value):
    with pytest.raises(ValueError):
        relay_module.duration({"cut_seconds": value})


def test_opaque_forward_cut_and_automatic_restore():
    events = []
    upstream = socket.socket()
    upstream.bind(("127.0.0.1", 0))
    upstream.listen()
    upstream.settimeout(2)
    relay = relay_module.Relay(
        upstream.getsockname()[1], lambda event, **metadata: events.append((event, metadata))
    )
    try:
        client = socket.create_connection(("127.0.0.1", relay.port), timeout=2)
        relay.tick()
        server, _ = upstream.accept()
        server.settimeout(2)
        payload = b"opaque\x00\xffnot-json\n"
        client.sendall(payload)
        assert server.recv(len(payload)) == payload
        server.sendall(payload[::-1])
        assert client.recv(len(payload)) == payload[::-1]
        relay.cut(0.05)
        assert client.recv(1) == b""
        assert server.recv(1) == b""
        client.close()
        server.close()
        refused = socket.create_connection(("127.0.0.1", relay.port), timeout=2)
        relay.tick()
        assert refused.recv(1) == b""
        refused.close()
        time.sleep(0.06)
        restored = socket.create_connection(("127.0.0.1", relay.port), timeout=2)
        relay.tick()
        restored_server, _ = upstream.accept()
        restored_server.settimeout(2)
        restored.sendall(payload)
        assert restored_server.recv(len(payload)) == payload
        restored.close()
        restored_server.close()
        assert "restored" in [event for event, _ in events]
        assert "connection_refused" in [event for event, _ in events]
        assert "opaque" not in repr(events)
    finally:
        relay.close()
        upstream.close()


def test_close_releases_listener():
    relay = relay_module.Relay(12345, lambda *args, **kwargs: None)
    port = relay.port
    relay.close()
    with socket.socket() as replacement:
        replacement.bind(("127.0.0.1", port))


def test_cli_eof_cleans_alias_without_logging_credentials(isolated):
    original = isolated / "original.json"
    alias = isolated / "alias.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "fixture-credential"}
    original.write_text(json.dumps(endpoint))
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--root",
            str(isolated),
            "--endpoint",
            str(original),
            "--alias",
            str(alias),
        ],
        input='{"cut_seconds":0.01}\n',
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert not alias.exists()
    assert json.loads(original.read_text()) == endpoint
    assert "fixture-credential" not in result.stdout + result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[0]["event"] == "ready"
    assert events[-1]["event"] == "stopped"


def test_windows_acl_failure_never_writes_credential(isolated, monkeypatch):
    source = isolated / "original.json"
    alias = isolated / "alias.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "test-secret"}
    source.write_text(json.dumps(endpoint))
    monkeypatch.setattr(sys, "platform", "win32")

    def unavailable(path):
        raise ValueError("owner-only Windows ACL unavailable")

    monkeypatch.setattr(relay_module, "windows_private_fd", unavailable)
    with pytest.raises(ValueError, match="Windows ACL unavailable"):
        relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    assert not alias.exists()
    assert json.loads(source.read_text()) == endpoint


def assert_windows_owner_only(path):
    # Independent .NET ACL read-back emits no SID or owner-private path.
    script = (
        "$ErrorActionPreference='Stop';"
        "$a=[System.IO.File]::GetAccessControl($args[0]);"
        "$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;"
        "$rules=@($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]));"
        "@{protected=$a.AreAccessRulesProtected;count=$rules.Count;"
        "owner_only=($rules.Count -eq 1 -and $rules[0].IdentityReference -eq $sid "
        "-and $rules[0].AccessControlType -eq 'Allow' "
        "-and $rules[0].FileSystemRights -eq 'FullControl')}|ConvertTo-Json -Compress"
    )
    # Feed the path as data, without interpolating it into executable shell text.
    encoded = json.dumps(str(path.resolve(strict=True)))
    script = "$target=ConvertFrom-Json ([Console]::In.ReadToEnd());" + script.replace(
        "$args[0]", "$target"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        input=encoded, text=True, capture_output=True, timeout=10, check=True,
    )
    assert json.loads(result.stdout) == {"protected": True, "count": 1, "owner_only": True}


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL")
def test_native_private_file_is_empty_when_dacl_verification_finishes(isolated):
    import os

    alias = isolated / "empty.json"
    fd = relay_module.windows_private_fd(alias)
    try:
        assert os.fstat(fd).st_size == 0
    finally:
        os.close(fd)
    assert_windows_owner_only(alias)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL")
def test_native_dacl_verification_failure_removes_empty_alias(isolated, monkeypatch):
    import ctypes
    from unittest.mock import Mock

    original_loader = ctypes.WinDLL
    source = isolated / "original.json"
    alias = isolated / "alias.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "test-secret"}
    source.write_text(json.dumps(endpoint))
    writes = Mock()

    def fail_verification(name, **kwargs):
        library = original_loader(name, **kwargs)
        if name == "advapi32":
            library.GetSecurityInfo = Mock(return_value=5)
        return library

    monkeypatch.setattr(ctypes, "WinDLL", fail_verification)
    monkeypatch.setattr(relay_module.json, "dump", writes)
    with pytest.raises(ValueError, match="verify the alias DACL"):
        relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    writes.assert_not_called()
    assert not alias.exists()
    assert json.loads(source.read_text()) == endpoint


def test_failed_write_removes_only_new_alias(isolated, monkeypatch):
    source = isolated / "original.json"
    alias = isolated / "alias.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "test-secret"}
    source.write_text(json.dumps(endpoint))

    def fail(*args):
        raise OSError("fixture write failure")

    monkeypatch.setattr(relay_module.json, "dump", fail)
    with pytest.raises(OSError, match="fixture write failure"):
        relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    assert not alias.exists()
    assert json.loads(source.read_text()) == endpoint


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows security descriptors")
@pytest.mark.parametrize("sddl,expected", [
    ("D:P(A;;FA;;;SY)", True),
    ("D:PAI(A;;FA;;;SY)", True),
    ("D:P(A;;FA;;;S-1-5-18)", True),
    ("D:(A;;FA;;;SY)", False),
    ("D:P(A;;FA;;;WD)", False),
    ("D:P(A;;FA;;;SY)(A;;FA;;;WD)", False),
    ("D:P(A;ID;FA;;;SY)", False),
    ("D:P(A;;FR;;;SY)", False),
    ("D:P(D;;FA;;;SY)", False),
    ("D:P", False),
])
def test_native_dacl_checks_permissions_not_sddl_spelling(sddl, expected):
    import ctypes
    from ctypes import wintypes

    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    security.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(pointer)]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(pointer), pointer,
    ]
    sid = pointer()
    descriptor = pointer()
    try:
        assert security.ConvertStringSidToSidW("S-1-5-18", ctypes.byref(sid))
        assert security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None,
        )
        assert relay_module.windows_owner_only_dacl(descriptor, sid) is expected
    finally:
        for allocated in (sid, descriptor):
            if allocated:
                kernel.LocalFree(allocated)
