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
    if sys.platform == "win32":
        with pytest.raises(ValueError, match="owner-only Windows ACL"):
            relay_module.write_alias(isolated, source, alias, endpoint, 23456)
        assert not alias.exists()
        assert json.loads(source.read_text()) == endpoint
        return
    relay_module.write_alias(isolated, source, alias, endpoint, 23456)
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
    (isolated / "escape").symlink_to(isolated.parent, target_is_directory=True)
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
    if sys.platform == "win32":
        assert result.returncode != 0
        assert "owner-only Windows ACL" in result.stderr
        assert not alias.exists()
        assert "fixture-credential" not in result.stdout + result.stderr
        return
    assert result.returncode == 0, result.stderr
    assert not alias.exists()
    assert json.loads(original.read_text()) == endpoint
    assert "fixture-credential" not in result.stdout + result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[0]["event"] == "ready"
    assert events[-1]["event"] == "stopped"


def test_windows_refuses_before_creating_credential_alias(isolated, monkeypatch):
    source = isolated / "original.json"
    alias = isolated / "alias.json"
    endpoint = {"host": "127.0.0.1", "port": 12345, "token": "test-secret"}
    source.write_text(json.dumps(endpoint))
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(ValueError, match="owner-only Windows ACL"):
        relay_module.write_alias(isolated, source, alias, endpoint, 23456)
    assert not alias.exists()
    assert json.loads(source.read_text()) == endpoint
