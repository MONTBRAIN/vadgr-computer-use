import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "E2E/0.7.9/harness/seal_session.py"
SPEC = importlib.util.spec_from_file_location("seal_session_079", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_clean_redacts_typed_values_tokens_and_unstructured_text():
    value = {
        "input": {"value": "typed secret", "expression": "document.cookie"},
        "result": {"text": '{"connected":true,"token":"secret","value":"page data"}'},
        "prose": {"text": "provider-key-shaped secret"},
    }

    result = MODULE.clean(value, [])

    assert result["input"]["value"] == {"redacted": True, "length": 12}
    assert result["input"]["expression"] == {"redacted": True, "length": 15}
    assert result["result"]["text"] == (
        '{"connected":true,"token":{"redacted":true,"length":6},'
        '"value":{"redacted":true,"length":9}}'
    )
    assert result["prose"]["text"] == {"redacted": True, "length": 26}


def test_clean_removes_private_root_and_sid_but_keeps_public_oracle_fields():
    value = {
        "path": r"C:\Users\owner\fixture\state.json",
        "owner": "S-1-5-21-111-222-333-1001",
        "connected": True,
        "dispatch_count": 1,
    }

    result = MODULE.clean(value, [r"C:\Users\owner"])

    assert result == {
        "path": r"<private-root>\fixture\state.json",
        "owner": "<owner-sid>",
        "connected": True,
        "dispatch_count": 1,
    }


def test_clean_redacts_media_payload():
    result = MODULE.clean(
        {"type": "image", "source": {"type": "base64", "data": "private pixels"}},
        [],
    )

    assert result["source"]["data"] == {"redacted": True, "length": 14}


def test_private_config_files_are_explicitly_excluded_from_sealing():
    source = HELPER.read_text(encoding="utf-8")

    assert 'path.name.endswith(".private.json")' in source
    assert '"registry-backup.json"' in source


def test_artifacts_only_seals_receipts_without_fabricating_agent_stream(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "before.json").write_text(
        json.dumps({"connected": True, "token": "private"}), encoding="utf-8"
    )
    (source / "registry-backup.json").write_text(
        json.dumps({"default_value": r"C:\Users\owner\private-manifest.json"}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--artifacts-only",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(result.stdout)["mode"] == "artifacts-only"
    assert not (destination / "agent.jsonl").exists()
    assert not (destination / "registry-backup.json").exists()
    assert json.loads((destination / "before.json").read_text(encoding="utf-8")) == {
        "connected": True,
        "token": {"redacted": True, "length": 7},
    }
