import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "E2E" / "0.7.9" / "harness" / "windows_session.py"
FIXTURE = ROOT / "E2E" / "0.7.9" / "harness" / "windows_fixture.py"


def load_helper():
    helper_parent = str(HELPER.parent)
    sys.path.insert(0, helper_parent)
    try:
        spec = importlib.util.spec_from_file_location("windows_session_079", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(helper_parent)


def load_fixture():
    spec = importlib.util.spec_from_file_location("windows_fixture_079", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_product_child_environment_excludes_ambient_credentials(tmp_path):
    helper = load_helper()
    source = {
        "PATH": "system-path",
        "SYSTEMROOT": r"C:\Windows",
        "ANTHROPIC_API_KEY": "must-not-cross-boundary",
        "OPENAI_API_KEY": "must-not-cross-boundary",
    }

    value = helper.environment(tmp_path, source)

    assert value["PATH"] == "system-path"
    assert value["SYSTEMROOT"] == r"C:\Windows"
    assert "ANTHROPIC_API_KEY" not in value
    assert "OPENAI_API_KEY" not in value
    assert value["USERPROFILE"] == str(tmp_path / "home")
    assert value["VADGR_CUA_BROKER_ENDPOINT"].startswith(str(tmp_path))


def test_driver_environment_keeps_login_paths_but_excludes_provider_keys():
    helper = load_helper()
    source = {
        "PATH": "system-path",
        "USERPROFILE": r"C:\Users\tester",
        "APPDATA": r"C:\Users\tester\AppData\Roaming",
        "ANTHROPIC_API_KEY": "must-not-reach-subscription-driver",
        "OPENAI_API_KEY": "must-not-reach-subscription-driver",
    }

    value = helper.driver_environment(source)

    assert value["PATH"] == "system-path"
    assert value["USERPROFILE"] == r"C:\Users\tester"
    assert value["APPDATA"] == r"C:\Users\tester\AppData\Roaming"
    assert "ANTHROPIC_API_KEY" not in value
    assert "OPENAI_API_KEY" not in value


def test_released_fixture_environment_excludes_ambient_credentials(tmp_path):
    fixture = load_fixture()
    source = {
        "PATH": "system-path",
        "SYSTEMROOT": r"C:\Windows",
        "ANTHROPIC_API_KEY": "must-not-cross-boundary",
        "OPENAI_API_KEY": "must-not-cross-boundary",
    }

    value = fixture.child_environment(tmp_path, tmp_path / "broker.json", source)

    assert value["PATH"] == "system-path"
    assert value["LOCALAPPDATA"] == str(tmp_path / "appdata")
    assert value["VADGR_CUA_BROKER_ENDPOINT"] == str(tmp_path / "broker.json")
    assert "ANTHROPIC_API_KEY" not in value
    assert "OPENAI_API_KEY" not in value


def test_pid_reuse_fault_changes_only_creation_identity_and_restores_exact_bytes(
    tmp_path, monkeypatch
):
    fixture = load_fixture()
    controls = []
    monkeypatch.setattr(fixture, "_validate_fixture_process", lambda root, pid, created: None)
    monkeypatch.setattr(
        fixture, "_set_process_suspended", lambda pid, suspended: controls.append((pid, suspended))
    )
    endpoint = tmp_path / "state/browser-broker.json"
    endpoint.parent.mkdir()
    original = {
        "pid": 1234,
        "process_created_filetime": "999",
        "token": "private-token-must-survive-without-output",
        "epoch": "fixture",
    }
    original_bytes = (json.dumps(original, sort_keys=True) + "\n").encode()
    endpoint.write_bytes(original_bytes)

    public_fault = fixture.pid_reuse_fault(tmp_path)
    changed = json.loads(endpoint.read_text(encoding="utf-8"))

    assert public_fault == {
        "event": "pid_reuse_fault_applied",
        "pid": 1234,
        "creation_identity_changed": True,
    }
    assert changed == {**original, "process_created_filetime": "1000"}
    assert "private-token" not in json.dumps(public_fault)
    assert controls == [(1234, True)]

    public_restore = fixture.pid_reuse_restore(tmp_path)

    assert public_restore == {"event": "pid_reuse_endpoint_restored", "pid": 1234}
    assert endpoint.read_bytes() == original_bytes
    assert not (tmp_path / fixture.PID_REUSE_BACKUP).exists()
    assert not (tmp_path / fixture.PID_REUSE_PROCESS).exists()
    assert controls == [(1234, True), (1234, False)]


def test_browser_command_requires_cft_and_a_fresh_profile(tmp_path):
    helper = load_helper()
    case = tmp_path / "case"
    case.mkdir()
    cft = tmp_path / "chrome-win64" / "chrome.exe"
    cft.parent.mkdir()
    cft.write_bytes(b"reviewed cft fixture")
    extension = tmp_path / "extension"
    extension.mkdir()

    command = helper.browser_command(case, cft, extension, "http://127.0.0.1/")

    assert command[0] == str(cft)
    assert f"--user-data-dir={case / 'browser-profile'}" in command
    assert f"--load-extension={extension}" in command
    assert "--remote-debugging-port=0" in command

    owner_chrome = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    owner_chrome.parent.mkdir(parents=True)
    owner_chrome.write_bytes(b"owner browser fixture")
    with pytest.raises(ValueError, match="Chrome for Testing"):
        helper.browser_command(case, owner_chrome, extension, "about:blank")

    (case / "browser-profile").mkdir()
    with pytest.raises(ValueError, match="fresh profile"):
        helper.browser_command(case, cft, extension, "about:blank")


def test_public_endpoint_never_records_browser_token():
    helper = load_helper()

    assert helper.public_endpoint({"port": 1234, "token": "secret"}) == {"port": 1234}


def test_observer_records_only_registration_hashes_not_raw_values():
    source = HELPER.read_text(encoding="utf-8")

    assert '"default_value_sha256"' in source
    assert '"manifest_sha256"' in source
    assert '"endpoint_sha256"' in source
    assert '"registration_value"' not in source


def test_cleanup_source_binds_pid_to_process_start_time():
    source = HELPER.read_text(encoding="utf-8")

    assert "Get-Process -Id" in source
    assert "StartTime.ToUniversalTime().ToString('o')" in source
    assert "Stop-Process -InputObject $p" in source


def test_async_driver_receipt_and_control_bind_pid_to_start_identity():
    source = HELPER.read_text(encoding="utf-8")

    assert '"agent-start"' in source
    assert '"agent-observe"' in source
    assert '"agent-stop"' in source
    assert 'save(output / "driver.json", {"pid": process.pid, "created": created})' in source
    assert "root_identity_matches" in source
    assert "StartTime.ToUniversalTime().ToString('o') -ne" in source


def test_agent_entry_override_uses_exact_installed_entry_and_scoped_environment(tmp_path):
    helper = load_helper()
    case = tmp_path / "case"
    output = tmp_path / "output"
    entry = tmp_path / "installed/vadgr-cua.exe"
    (case / "work").mkdir(parents=True)
    output.mkdir()
    entry.parent.mkdir()
    entry.write_bytes(b"installed entry fixture")

    config = helper.agent_config(case, output, entry)
    value = json.loads(config.read_text(encoding="utf-8"))
    server = value["mcpServers"]["cua"]

    assert server["command"] == str(entry.resolve())
    assert server["args"] == ["--transport", "stdio"]
    assert server["env"]["USERPROFILE"] == str(case / "home")
    assert "ANTHROPIC_API_KEY" not in server["env"]
    assert "OPENAI_API_KEY" not in server["env"]
