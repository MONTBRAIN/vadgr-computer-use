import hashlib
import json
from pathlib import Path

import pytest

from computer_use.browser import windows_process


class FakeProcess:
    def __init__(self, pid: int, image: Path, *, sid: str = "owner", created: int = 42):
        self.pid = pid
        self._image = image
        self._sid = sid
        self._created = created
        self.running = True
        self.terminated = False
        self.closed = False

    def image_path(self) -> Path:
        return self._image

    def user_sid(self) -> str:
        return self._sid

    def creation_filetime(self) -> int:
        return self._created

    def is_running(self) -> bool:
        return self.running

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def wait(self, _timeout_ms: int) -> bool:
        return not self.running

    def close(self) -> None:
        self.closed = True


def _cataloged_bundle(root: Path) -> tuple[Path, dict[str, object]]:
    bundle = root / "browser-broker" / "0.7.7" / ("a" * 64)
    bundle.mkdir(parents=True)
    broker = bundle / "vadgr-cua-browser-broker.exe"
    broker.write_bytes(b"released broker")
    payload = bundle / "payload.bin"
    payload.write_bytes(b"released payload")
    manifest = {
        "version": "0.7.7",
        "target": "x86_64-pc-windows-msvc",
        "archive_sha256": "a" * 64,
        "files": [
            {
                "path": broker.name,
                "size": broker.stat().st_size,
                "sha256": hashlib.sha256(broker.read_bytes()).hexdigest(),
            },
            {
                "path": payload.name,
                "size": payload.stat().st_size,
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
            },
        ],
    }
    raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    (bundle / "bundle-manifest.json").write_bytes(raw)
    catalog = {
        "schema": 1,
        "target": "x86_64-pc-windows-msvc",
        "releases": [
            {
                "version": "0.7.7",
                "archive_sha256": "a" * 64,
                "broker_relative_path": broker.name,
                "broker_sha256": hashlib.sha256(broker.read_bytes()).hexdigest(),
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "protocol_min": 1,
                "protocol_max": 1,
            }
        ],
    }
    return bundle, catalog


def _run(tmp_path, monkeypatch, process, bundle, catalog, endpoint=None):
    lock = tmp_path / "state" / "browser-broker.lock"
    lock.parent.mkdir()
    lock.write_text(str(process.pid))
    candidate = bundle.parents[1] / "0.7.8" / ("b" * 64)
    candidate.mkdir(parents=True)
    candidate_exe = candidate / "vadgr-cua-browser-broker.exe"
    candidate_exe.write_bytes(b"candidate")
    catalog_path = candidate / "predecessor-catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    if endpoint is not None:
        (lock.parent / "browser-broker.json").write_text(json.dumps(endpoint))
    monkeypatch.setattr(windows_process, "_verify_owner_and_system", lambda _path: None)
    monkeypatch.setattr(windows_process, "_current_user_sid", lambda: "owner")
    monkeypatch.setattr(windows_process, "_open_process", lambda pid: process)
    return windows_process.perform_upgrade_handoff(
        lock_path=lock,
        candidate_bundle=candidate,
        catalog_path=catalog_path,
    )


def test_exact_cataloged_predecessor_is_replaced(tmp_path, monkeypatch):
    bundle, catalog = _cataloged_bundle(tmp_path)
    process = FakeProcess(123, bundle / "vadgr-cua-browser-broker.exe")
    endpoint = {"pid": 123, "bundle_hash": "a" * 64, "process_started_ns": "legacy"}

    result = _run(tmp_path, monkeypatch, process, bundle, catalog, endpoint)

    assert result["state"] == "replaced"
    assert result["version"] == "0.7.7"
    assert result["process_created_filetime"] == "42"
    assert process.terminated is True
    assert process.closed is True


@pytest.mark.parametrize("change", ["owner", "hash", "path", "creation"])
def test_ambiguous_predecessor_fails_closed(tmp_path, monkeypatch, change):
    bundle, catalog = _cataloged_bundle(tmp_path)
    image = bundle / "vadgr-cua-browser-broker.exe"
    process = FakeProcess(123, image)
    endpoint = {"pid": 123, "bundle_hash": "a" * 64, "process_started_ns": "legacy"}
    if change == "owner":
        process._sid = "other"
    elif change == "hash":
        image.write_bytes(b"changed")
    elif change == "path":
        process._image = tmp_path / "lookalike" / image.name
    elif change == "creation":
        first = True

        def changing_creation():
            nonlocal first
            value = 42 if first else 43
            first = False
            return value

        process.creation_filetime = changing_creation

    with pytest.raises(windows_process.UpgradeHandoffError) as caught:
        _run(tmp_path, monkeypatch, process, bundle, catalog, endpoint)

    assert caught.value.code == "browser_broker_upgrade_unsafe"
    assert process.terminated is False
    assert process.closed is True


def test_unknown_catalog_entry_fails_closed(tmp_path, monkeypatch):
    bundle, catalog = _cataloged_bundle(tmp_path)
    catalog["releases"] = []
    process = FakeProcess(123, bundle / "vadgr-cua-browser-broker.exe")

    with pytest.raises(windows_process.UpgradeHandoffError) as caught:
        _run(tmp_path, monkeypatch, process, bundle, catalog)

    assert caught.value.code == "browser_broker_upgrade_unsafe"
    assert process.terminated is False


def test_current_candidate_is_left_running(tmp_path, monkeypatch):
    bundle, catalog = _cataloged_bundle(tmp_path)
    candidate = bundle.parents[1] / "0.7.8" / ("b" * 64)
    process = FakeProcess(123, candidate / "vadgr-cua-browser-broker.exe")

    result = _run(tmp_path, monkeypatch, process, bundle, catalog)

    assert result["state"] == "candidate_ready"
    assert process.terminated is False
    assert process.closed is True


def test_missing_lock_needs_no_handoff(tmp_path, monkeypatch):
    candidate = tmp_path / "browser-broker" / "0.7.8" / ("b" * 64)
    candidate.mkdir(parents=True)
    catalog = candidate / "predecessor-catalog.json"
    catalog.write_text('{"schema":1,"target":"x86_64-pc-windows-msvc","releases":[]}')

    result = windows_process.perform_upgrade_handoff(
        lock_path=tmp_path / "missing.lock",
        candidate_bundle=candidate,
        catalog_path=catalog,
    )

    assert result == {"state": "no_predecessor"}


def test_predecessor_exit_before_handle_open_restarts_election(tmp_path, monkeypatch):
    bundle, catalog = _cataloged_bundle(tmp_path)
    process = FakeProcess(123, bundle / "vadgr-cua-browser-broker.exe")
    lock = tmp_path / "state" / "browser-broker.lock"
    lock.parent.mkdir()
    lock.write_text(str(process.pid))
    candidate = bundle.parents[1] / "0.7.8" / ("b" * 64)
    candidate.mkdir(parents=True)
    catalog_path = candidate / "predecessor-catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    monkeypatch.setattr(windows_process, "_verify_owner_and_system", lambda _path: None)
    monkeypatch.setattr(
        windows_process,
        "_open_process",
        lambda _pid: (_ for _ in ()).throw(windows_process._ProcessExited()),
    )

    assert windows_process.perform_upgrade_handoff(
        lock_path=lock,
        candidate_bundle=candidate,
        catalog_path=catalog_path,
    ) == {"state": "already_exited"}
