"""Each case owns a fresh temporary root; no broker or browser is started."""

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from computer_use.browser import broker


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_first_write_is_private_and_parent_does_not_change_home(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"
    initial = stat.S_IMODE(tmp_path.stat().st_mode)
    original_dump = json.dump
    original_dumps = json.dumps
    observations = []

    def inspect():
        files = list(endpoint.parent.iterdir()) if endpoint.parent.exists() else []
        observations.append(files)
        assert stat.S_IMODE(endpoint.parent.stat().st_mode) == 0o700
        assert len(files) == 1
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
        assert files[0].stat().st_size == 0

    def dump(value, file, *args, **kwargs):
        inspect()
        return original_dump(value, file, *args, **kwargs)

    def dumps(value, *args, **kwargs):
        inspect()
        return original_dumps(value, *args, **kwargs)

    monkeypatch.setattr(json, "dump", dump)
    monkeypatch.setattr(json, "dumps", dumps)
    old_umask = os.umask(0o022)
    try:
        broker._write_private(endpoint, {"fixture": "value"})
    finally:
        os.umask(old_umask)
    assert observations
    assert stat.S_IMODE(tmp_path.stat().st_mode) == initial
    assert list(endpoint.parent.iterdir()) == [endpoint]


def test_endpoint_symlink_is_refused_without_touching_target(tmp_path):
    target = tmp_path / "other"
    target.write_text("unchanged")
    endpoint = tmp_path / "browser-broker.json"
    try:
        endpoint.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(OSError):
        broker._write_private(endpoint, {"fixture": "value"})
    assert target.read_text() == "unchanged"
    assert endpoint.is_symlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX home and symlink protection")
def test_home_alias_cannot_change_home_permissions(tmp_path, monkeypatch):
    from computer_use.browser.private_file import private_directory

    home = tmp_path / "home"
    home.mkdir(mode=0o755)
    home.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(PermissionError):
        private_directory(home / ".." / "home")
    assert stat.S_IMODE(home.stat().st_mode) == 0o755
    alias = tmp_path / "alias"
    alias.symlink_to(home, target_is_directory=True)
    with pytest.raises(PermissionError):
        private_directory(alias / "state")
    assert not (home / "state").exists()


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_lock_links_are_refused_without_target_mutation(tmp_path, link_kind):
    from computer_use.browser.private_file import open_private_lock

    target, lock = tmp_path / "other", tmp_path / "browser-broker.lock"
    target.write_text("unchanged")
    if link_kind == "symbolic":
        try:
            lock.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation unavailable")
    else:
        os.link(target, lock)
    with pytest.raises(PermissionError):
        open_private_lock(lock)
    assert target.read_text() == "unchanged"


def test_preexisting_temporary_collision_is_not_followed_or_deleted(tmp_path, monkeypatch):
    from computer_use.browser import private_file

    endpoint = tmp_path / "state" / "browser-broker.json"
    private_file.private_directory(endpoint.parent)
    temporary = endpoint.with_name(f".{endpoint.name}.collision.tmp")
    temporary.write_text("unchanged")
    monkeypatch.setattr(private_file.secrets, "token_hex", lambda size: "collision")
    with pytest.raises(FileExistsError):
        private_file.write_private(endpoint, {"generation": 1})
    assert temporary.read_text() == "unchanged"
    assert not endpoint.exists()


def test_existing_endpoint_replacement_is_atomic(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"
    broker._write_private(endpoint, {"generation": 1})
    original = os.replace
    calls = []

    def replace(source, destination, *args, **kwargs):
        assert json.loads(endpoint.read_text()) == {"generation": 1}
        calls.append(True)
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    broker._write_private(endpoint, {"generation": 2})
    assert calls == [True]
    assert json.loads(endpoint.read_text()) == {"generation": 2}


def test_failed_replace_preserves_original_and_cleans_temporary(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"
    broker._write_private(endpoint, {"generation": 1})

    def refuse(*args, **kwargs):
        raise PermissionError("fixture refusal")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(PermissionError):
        broker._write_private(endpoint, {"generation": 2})
    assert json.loads(endpoint.read_text()) == {"generation": 1}
    assert list(endpoint.parent.iterdir()) == [endpoint]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_failure_to_protect_parent_stops_before_token_write(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"

    def refuse(*args, **kwargs):
        raise PermissionError("fixture refusal")

    monkeypatch.setattr(os, "fchmod", refuse)
    monkeypatch.setattr(Path, "chmod", refuse)
    with pytest.raises(PermissionError):
        broker._write_private(endpoint, {"fixture": "value"})
    assert not endpoint.exists()
    assert not list(endpoint.parent.iterdir())


def test_publication_failure_closes_started_servers_and_preserves_stale_endpoint(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"
    broker._write_private(endpoint, {"host": "127.0.0.1", "port": 1234, "epoch": "stale"})
    events = []
    server = broker.BrokerServer.__new__(broker.BrokerServer)
    server.browser_server = SimpleNamespace(start=lambda: events.append("start"),
                                            stop=lambda: events.append("stop"))
    server._sock = SimpleNamespace(close=lambda: events.append("close"))
    server.port, server.auth_token = 1235, "fixture"
    server.broker = SimpleNamespace(epoch="replacement")
    monkeypatch.setattr(broker, "broker_endpoint_path", lambda: endpoint)
    monkeypatch.setattr(broker, "windows_broker_endpoint_path", lambda: None)

    def refuse(*args):
        events.append("publication")
        raise PermissionError("fixture refusal")

    monkeypatch.setattr(broker, "_write_private", refuse)
    with pytest.raises(PermissionError):
        server.run()
    assert events == ["start", "publication", "stop", "close"]
    assert json.loads(endpoint.read_text())["epoch"] == "stale"
