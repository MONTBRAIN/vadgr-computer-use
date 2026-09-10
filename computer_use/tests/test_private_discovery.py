"""Each discovery case uses fresh synthetic files and no real browser."""

import json
import os
import stat

import pytest

from computer_use.browser import server


@pytest.mark.skipif(os.name == "nt", reason="POSIX creation modes")
def test_discovery_serializes_only_after_storage_is_private(tmp_path, monkeypatch):
    destination = tmp_path / "discovery" / "browser.port"
    original = json.dump
    seen = []

    def inspect(value, file, *args, **kwargs):
        temporary = next(destination.parent.glob(".*.tmp"))
        assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(temporary.stat().st_mode) == 0o600
        assert temporary.stat().st_size == 0
        seen.append(True)
        return original(value, file, *args, **kwargs)

    monkeypatch.setattr(json, "dump", inspect)
    server.write_discovery(1234, "synthetic", path=destination)
    assert seen == [True]


def test_discovery_symlink_refused_and_target_unchanged(tmp_path):
    target = tmp_path / "other"
    target.write_text("unchanged")
    destination = tmp_path / "browser.port"
    try:
        destination.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(OSError):
        server.write_discovery(1234, "synthetic", path=destination)
    assert target.read_text() == "unchanged"


def test_discovery_copy_failure_is_not_silently_accepted(tmp_path, monkeypatch):
    destination, copy = tmp_path / "original" / "browser.port", tmp_path / "copy" / "browser.port"
    original = server._write_one

    def refuse(path, payload):
        if path == copy:
            raise PermissionError("synthetic protection failure")
        original(path, payload)

    monkeypatch.setattr(server, "_write_one", refuse)
    with pytest.raises(PermissionError):
        server.write_discovery(1234, "synthetic", path=destination, windows_copy=copy)


def test_discovery_failure_closes_listener_without_starting_thread(tmp_path, monkeypatch):
    instance = server.BrowserServer(discovery_path=tmp_path / "browser.port")

    def refuse(*args, **kwargs):
        raise PermissionError("synthetic protection failure")

    monkeypatch.setattr(server, "write_discovery", refuse)
    with pytest.raises(PermissionError):
        instance.start()
    try:
        assert instance._thread is None
        assert instance._sock.fileno() == -1
    finally:
        instance.stop()
