import hashlib
import json
from pathlib import Path

import pytest

from computer_use.browser import windows_broker


def _fake_bundle(root: Path) -> tuple[Path, dict[str, object]]:
    package = root / "winbroker"
    package.mkdir()
    archive = package / windows_broker.BUNDLE_ARCHIVE
    archive.write_bytes(b"verified bundle")
    manifest = {
        "version": "0.7.6",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": [{"path": "broker.exe", "sha256": "0" * 64}],
    }
    (package / windows_broker.BUNDLE_MANIFEST).write_text(json.dumps(manifest))
    return archive, manifest


def test_bundle_input_rejects_archive_tampering(tmp_path, monkeypatch):
    archive, _manifest = _fake_bundle(tmp_path)
    monkeypatch.setattr(windows_broker, "_package_root", lambda: tmp_path)
    archive.write_bytes(b"altered bundle")

    with pytest.raises(OSError, match="integrity verification"):
        windows_broker._bundle_inputs()


def test_endpoint_identity_requires_the_exact_packaged_bundle(tmp_path, monkeypatch):
    _archive, manifest = _fake_bundle(tmp_path)
    monkeypatch.setattr(windows_broker, "_package_root", lambda: tmp_path)
    endpoint = {
        "platform": "win32",
        "host": "127.0.0.1",
        "bundle_hash": manifest["archive_sha256"],
        "pid": 123,
        "process_started_ns": "456",
    }
    assert windows_broker.validate_endpoint(endpoint) == manifest["archive_sha256"]

    endpoint["bundle_hash"] = "f" * 64
    with pytest.raises(OSError, match="identity verification"):
        windows_broker.validate_endpoint(endpoint)


def test_windows_mount_path_is_converted_without_a_shell():
    assert windows_broker._windows_path(Path("/mnt/c/Users/Owner/file.zip")) == (
        "C:\\Users\\Owner\\file.zip"
    )
