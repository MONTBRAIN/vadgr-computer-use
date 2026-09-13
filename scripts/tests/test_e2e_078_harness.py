import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "E2E"
    / "0.7.8"
    / "harness"
    / "upgrade_fixture.py"
)


def load_fixture():
    spec = importlib.util.spec_from_file_location("upgrade_fixture_078", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def marked_root(tmp_path: Path) -> Path:
    fixture = load_fixture()
    root = tmp_path / "vadgr-cua-078-unit"
    root.mkdir()
    (root / fixture.MARKER).write_text(
        json.dumps({"root": str(root.resolve()), "schema": 1}) + "\n"
    )
    return root


def test_root_requires_exact_marker_and_prefix(tmp_path):
    fixture = load_fixture()
    root = tmp_path / "vadgr-cua-078-unit"
    root.mkdir()
    with pytest.raises(ValueError, match="marker"):
        fixture.checked_root(str(root))

    (root / fixture.MARKER).write_text('{"root":"wrong","schema":1}\n')
    with pytest.raises(ValueError, match="does not match"):
        fixture.checked_root(str(root))


def test_safe_extract_rejects_parent_escape(tmp_path):
    fixture = load_fixture()
    archive_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside", b"bad")
    destination = tmp_path / "destination"
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(ValueError, match="escapes"):
            fixture.safe_extract(archive, destination)


def test_safe_identity_never_returns_endpoint_token(tmp_path):
    fixture = load_fixture()
    root = marked_root(tmp_path)
    endpoint = root / "state" / "browser-broker.json"
    endpoint.parent.mkdir()
    endpoint.write_text(
        json.dumps(
            {
                "platform": "win32",
                "host": "127.0.0.1",
                "port": 12345,
                "token": "never-record-this",
                "pid": 123,
                "epoch": "epoch",
                "bundle_hash": "a" * 64,
            }
        )
    )

    identity = fixture.safe_identity(endpoint)

    assert "token" not in identity
    assert identity["token_present"] is True
    assert "never-record-this" not in json.dumps(identity)


def test_fault_changes_only_validated_endpoint(tmp_path):
    fixture = load_fixture()
    root = marked_root(tmp_path)
    endpoint = root / "state" / "browser-broker.json"
    endpoint.parent.mkdir()
    endpoint.write_text("{}")

    assert fixture.fault(root, "corrupt") == 0
    assert endpoint.read_text() == "{invalid\n"
    assert fixture.fault(root, "remove") == 0
    assert not endpoint.exists()
