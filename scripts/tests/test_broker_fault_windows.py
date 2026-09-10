"""Windows coordination tests never launch an agent or invoke product operations."""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_three_installed_clients_keep_restart_pair_direct(tmp_path):
    helper = load("coordinate_broker_fault_windows")
    tmp_path = tmp_path / "root with spaces"
    runtime = tmp_path / "runtime/Scripts/vadgr-cua.exe"
    gate = tmp_path / "b09-gate-private.json"
    command = helper.driver_command(tmp_path, gate, runtime, "codex.cmd")
    assert command[:10] == ["codex.cmd", "--yolo", "exec", "--json", "--ephemeral",
                            "--ignore-user-config", "--skip-git-repo-check", "--model",
                            "gpt-5.6-luna", "-c"]
    settings = {}
    for index, item in enumerate(command):
        if item == "-c":
            key, value = command[index + 1].split("=", 1)
            settings[key] = json.loads(value)
    assert settings["model_reasoning_effort"] == "medium"
    for name in ("cua_two", "cua_three"):
        assert settings[f"mcp_servers.{name}.command"] == str(runtime)
        assert settings[f"mcp_servers.{name}.env.VADGR_CUA_BROKER_ENDPOINT"] == str(
            tmp_path / "broker/browser-broker.json")
    assert settings["mcp_servers.cua_one.args"] == [
        str(HARNESS / "broker_stdio_gate_windows.py"), str(gate), str(runtime)]
    assert "mcp_servers.cua_one.env.VADGR_CUA_BROKER_ENDPOINT" not in settings
    for name in ("cua_one", "cua_two", "cua_three"):
        for key, relative in (("LOCALAPPDATA", "local"), ("APPDATA", "roaming"),
                              ("VADGR_CUA_BROKER_ROOT", "broker"),
                              ("VADGR_CUA_BROWSER_DISCOVERY", "discovery.json")):
            assert settings[f"mcp_servers.{name}.env.{key}"] == str(tmp_path / relative)


def test_claude_driver_uses_strict_private_mcp_config(tmp_path):
    helper = load("coordinate_broker_fault_windows")
    root = tmp_path / "root with spaces"
    runtime = root / "runtime/Scripts/vadgr-cua.exe"
    gate = root / "b09-gate-private.json"
    config = root / "claude-mcp-private.json"

    command = helper.driver_command(root, gate, runtime, "claude.cmd", "claude", config)
    mcp = helper.mcp_configuration(root, gate, runtime)

    assert command == [
        "claude.cmd",
        "--dangerously-skip-permissions",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        "claude-sonnet-5",
        "--mcp-config",
        str(config),
        "--strict-mcp-config",
        "-p",
    ]
    assert set(mcp["mcpServers"]) == {"cua_one", "cua_two", "cua_three"}
    assert mcp["mcpServers"]["cua_one"]["command"] == sys.executable
    assert mcp["mcpServers"]["cua_one"]["args"] == [
        str(HARNESS / "broker_stdio_gate_windows.py"),
        str(gate),
        str(runtime),
    ]
    assert mcp["mcpServers"]["cua_two"]["command"] == str(runtime)


def test_atomic_control_json_replaces_without_bom(tmp_path):
    helper = load("coordinate_broker_fault_windows")
    path = tmp_path / "request.json"
    helper.write_json(path, {"sequence": 1, "cut_seconds": 8})
    helper.write_json(path, {"sequence": 2, "cut_seconds": 46})
    assert json.loads(path.read_bytes()) == {"sequence": 2, "cut_seconds": 46}
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def restored_state(sequence=1, seconds=8):
    return {"sequence": sequence, "event": "restored", "connections_opened": 1,
            "cut": {"event": "cut", "monotonic": 11, "seconds": seconds, "connection_count": 1},
            "restored": {"event": "restored", "monotonic": 11 + seconds}}


@pytest.mark.parametrize("field,value", [("monotonic", 9), ("monotonic", float("nan")),
                                         ("seconds", 46), ("connection_count", 0)])
def test_control_rejects_stale_wrong_and_disconnected_cuts(field, value):
    helper = load("control_broker_fault_windows")
    state = restored_state()
    state["cut"][field] = value
    with pytest.raises(ValueError):
        helper.restoration(state, 1, 8, 10)


def test_control_returns_only_safe_actual_timing():
    helper = load("control_broker_fault_windows")
    state = restored_state()
    state["restored"]["private_path"] = "must-not-escape"
    result = helper.restoration(state, 1, 8, 10)
    assert result["restored_minus_cut_seconds"] == 8
    assert "must-not-escape" not in json.dumps(result)
    assert helper.restoration(state, 2, 46, 20) is None


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows handshake")
@pytest.mark.parametrize("sequence,seconds", [(1, 8), (2, 46)])
def test_one_call_waits_through_requested_and_cut_states(
    tmp_path, monkeypatch, capsys, sequence, seconds,
):
    helper = load("control_broker_fault_windows")
    coordinator = load("coordinate_broker_fault_windows")
    monkeypatch.setattr(coordinator, "checked_root", lambda root: root)
    monkeypatch.setattr(helper, "coordinator", lambda: coordinator)
    state_path = tmp_path / "b09-state.json"
    initial = {"sequence": 0, "event": "ready", "connections_opened": 1}
    if sequence == 2:
        initial = restored_state()
        initial["cut"]["monotonic"] = 1
        initial["restored"]["monotonic"] = 9
    coordinator.write_json(state_path, initial)
    clock = [10.0]
    monkeypatch.setattr(helper.time, "monotonic", lambda: clock[0])
    steps = []

    def tick(delay):
        request = json.loads((tmp_path / "b09-request.json").read_text())
        assert request == {"sequence": sequence, "cut_seconds": seconds}
        clock[0] += 1
        steps.append(clock[0])
        state = restored_state(sequence, seconds)
        if clock[0] < 11 + seconds:
            state.pop("restored")
            state["event"] = "cut"
        coordinator.write_json(state_path, state)

    monkeypatch.setattr(helper.time, "sleep", tick)
    result = helper.run(tmp_path, sequence, seconds)
    assert len(steps) == seconds + 1
    assert result["elapsed_seconds"] == seconds + 1
    assert json.loads(capsys.readouterr().out)["restored_monotonic"] == 11 + seconds
    assert (tmp_path / f"b09-control-{sequence}.lock").is_file()
    with pytest.raises(ValueError):
        helper.run(tmp_path, sequence, seconds)


@pytest.mark.parametrize("sequence,seconds,timeout", [(1, 46, 58), (2, 8, 58), (1, 8, 8),
                                                     (1, 8, 61), (True, 8, 58)])
def test_control_rejects_bad_sequence_and_bound(tmp_path, sequence, seconds, timeout):
    helper = load("control_broker_fault_windows")
    with pytest.raises(ValueError):
        helper.run(tmp_path, sequence, seconds, timeout)
    assert list(tmp_path.iterdir()) == []


def test_relay_retention_preserves_original_and_alias_on_exit():
    root = Path(tempfile.mkdtemp(prefix="vadgr-cua-retention-test-"))
    source, alias = root / "original.json", root / "alias.json"
    source.write_text(json.dumps({"host": "127.0.0.1", "port": 12345, "token": "fixture"}))
    process = subprocess.run([sys.executable, str(HARNESS / "broker_fault_relay.py"),
                              "--root", str(root), "--endpoint", str(source),
                              "--alias", str(alias), "--retain-alias"],
                             input='{"stop":true}\n', capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert source.is_file() and alias.is_file()
    assert json.loads(alias.read_text())["token"] == "fixture"
    assert "fixture" not in process.stdout
    assert json.loads(process.stdout.splitlines()[-1])["event"] == "stopped"


def test_failed_alias_write_is_retained_without_changing_original(monkeypatch):
    helper = load("broker_fault_relay")
    root = Path(tempfile.mkdtemp(prefix="vadgr-cua-retention-failure-test-"))
    source, alias = root / "original.json", root / "alias.json"
    source.write_text("original")

    def failed_write(payload, stream):
        stream.write("partial fixture")
        raise OSError("fixture write failure")

    monkeypatch.setattr(helper.json, "dump", failed_write)
    with pytest.raises(OSError):
        helper.write_alias(root, source, alias, {"port": 12345}, 23456, retain=True)
    assert alias.read_text() == "partial fixture"
    assert source.read_text() == "original"


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows DACL")
def test_retention_keeps_empty_file_on_acl_verification_failure(tmp_path, monkeypatch):
    helper = load("broker_fault_relay")
    destination = tmp_path / "failed-private-alias.json"
    monkeypatch.setattr(helper, "windows_owner_only_dacl", lambda descriptor, sid: False)
    with pytest.raises(ValueError, match="not owner-only"):
        helper.windows_private_fd(destination, retain_on_failure=True)
    assert destination.is_file()
    assert destination.read_bytes() == b""


def test_coordinator_has_no_artifact_deletion_or_product_import():
    source = (HARNESS / "coordinate_broker_fault_windows.py").read_text(encoding="utf-8")
    assert ".unlink(" not in source and ".rmdir(" not in source and "rmtree(" not in source
    assert "from computer_use" not in source and "import computer_use" not in source
    assert '"--retain-alias"' in source


def test_gate_abort_does_not_spawn_a_child(tmp_path, monkeypatch):
    helper = load("broker_stdio_gate_windows")
    gate = tmp_path / "gate.json"
    gate.write_text('{"abort":true}')
    monkeypatch.setattr(helper.sys, "argv", ["gate", str(gate), str(tmp_path / "runtime.exe")])
    monkeypatch.setattr(helper.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected child"))
    assert helper.main() == 2
