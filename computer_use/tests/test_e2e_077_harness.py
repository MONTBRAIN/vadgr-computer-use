import importlib.util
import json
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.7/harness/lifecycle_probe.py"
SPEC = importlib.util.spec_from_file_location("lifecycle_probe_077", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_safe_identity_never_emits_token(tmp_path):
    root = tmp_path / "vadgr-cua-077-test"
    root.mkdir()
    endpoint = root / "state" / "browser-broker.json"
    endpoint.parent.mkdir()
    endpoint.write_text(
        json.dumps(
            {
                "platform": "win32",
                "host": "127.0.0.1",
                "port": 12345,
                "token": "must-not-escape",
                "pid": 41,
                "process_started_ns": "42",
                "epoch": "fixture",
                "bundle_hash": "a" * 64,
            }
        )
    )

    _root, checked = MODULE.checked_paths(str(root), str(endpoint))
    result = MODULE.safe_identity(checked)
    assert result["token_present"] is True
    assert "must-not-escape" not in json.dumps(result)


def test_faults_change_only_validated_endpoint(tmp_path):
    root = tmp_path / "vadgr-cua-077-test"
    root.mkdir()
    endpoint = root / "browser-broker.json"
    endpoint.write_text(json.dumps({"bundle_hash": "a" * 64}))
    outside = tmp_path / "outside.json"
    outside.write_text("owner")

    MODULE.fault(endpoint, "mismatch")
    assert MODULE.read_endpoint(endpoint)["bundle_hash"] == "f" * 64
    MODULE.fault(endpoint, "corrupt")
    assert endpoint.read_text() == "{invalid\n"
    MODULE.fault(endpoint, "remove")
    assert not endpoint.exists()
    assert outside.read_text() == "owner"
    with pytest.raises(ValueError, match="outside"):
        MODULE.checked_paths(str(root), str(outside))
