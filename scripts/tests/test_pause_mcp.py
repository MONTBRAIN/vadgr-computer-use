"""Scheduling faults refuse unrelated processes and retain an independent resume."""

import importlib.util
import os
import select
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/pause_mcp.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("pause_mcp", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("seconds", [0, -1, 121, float("inf"), float("nan"), True])
def test_invalid_duration_fails_closed(helper, seconds):
    with pytest.raises(ValueError):
        helper.duration(seconds)


def test_windows_refuses_before_inspection(helper, monkeypatch):
    monkeypatch.setattr(helper.os, "name", "nt")
    with pytest.raises(ValueError, match="POSIX"):
        helper.validate(Path("unused"), 12, 13)


def test_validation_requires_exact_installed_entry_and_parent(helper, monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX identity")
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-pause-test-") as directory:
        root = Path(directory).resolve()
        binary = root / "runtime/bin"
        binary.mkdir(parents=True)
        (binary / "python").touch()
        (binary / "vadgr-cua").touch()
        identity = (
            12,
            13,
            os.getuid(),
            "start",
            (str(binary / "python"), str(binary / "vadgr-cua")),
        )
        monkeypatch.setattr(helper, "inspect_process", lambda pid: identity)
        assert helper.validate(root, 12, 13) == identity
        with pytest.raises(ValueError):
            helper.validate(root, 12, 14)
        for command in [("python", "owner.py"), (*identity[-1], "browser-setup")]:
            monkeypatch.setattr(
                helper, "inspect_process", lambda pid, command=command: (*identity[:4], command)
            )
            with pytest.raises(ValueError):
                helper.validate(root, 12, 13)


def test_watchdog_resumes_after_wait_exception(helper, monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX signals")
    identity = (12, 13, os.getuid(), "start", ())
    kill = Mock()
    monkeypatch.setattr(helper.os, "kill", kill)
    monkeypatch.setattr(helper, "inspect_process", lambda pid: identity)
    monkeypatch.setattr(helper.time, "sleep", Mock(side_effect=InterruptedError))
    monkeypatch.setattr(helper, "emit", Mock())
    with pytest.raises(InterruptedError):
        helper.pause_and_resume(identity, 1)
    assert kill.call_args_list[0].args == (12, signal.SIGSTOP)
    assert kill.call_args_list[-1].args == (12, signal.SIGCONT)


def test_changed_identity_is_never_signaled(helper, monkeypatch):
    identity = (12, 13, 42, "start", ())
    kill = Mock()
    monkeypatch.setattr(helper.os, "kill", kill)
    monkeypatch.setattr(helper, "inspect_process", lambda pid: (*identity[:3], "replacement", ()))
    with pytest.raises(ValueError):
        helper.pause_and_resume(identity, 1)
    kill.assert_not_called()


def test_replaced_pid_is_not_resumed(helper, monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX signals")
    identity = (12, 13, os.getuid(), "start", ())
    observed = iter([identity, (*identity[:3], "replacement", ())])
    kill = Mock()
    monkeypatch.setattr(helper.os, "kill", kill)
    monkeypatch.setattr(helper, "inspect_process", lambda pid: next(observed))
    monkeypatch.setattr(helper.time, "sleep", Mock())
    monkeypatch.setattr(helper, "emit", Mock())
    helper.pause_and_resume(identity, 1)
    kill.assert_called_once_with(12, signal.SIGSTOP)


@pytest.mark.skipif(os.name != "posix", reason="POSIX isolated subprocess fixture")
def test_detached_watchdog_resumes_after_calling_helper_is_killed():
    import json

    with tempfile.TemporaryDirectory(prefix="vadgr-cua-pause-test-") as directory:
        root = Path(directory)
        binary = root / "runtime/bin"
        binary.mkdir(parents=True)
        (binary / "python").symlink_to(sys.executable)
        entry = binary / "vadgr-cua"
        entry.write_text("import time\ntime.sleep(20)\n")
        target = subprocess.Popen([str(binary / "python"), str(entry)])
        caller = None
        try:
            caller = subprocess.Popen(
                [
                    sys.executable,
                    str(HELPER),
                    "--root",
                    str(root),
                    "--pid",
                    str(target.pid),
                    "--parent-pid",
                    str(os.getpid()),
                    "--seconds",
                    "0.4",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            events = []
            while "paused" not in events:
                ready, _, _ = select.select([caller.stdout], [], [], 5)
                assert ready, "watchdog did not produce a bounded startup event"
                line = caller.stdout.readline()
                assert line, (events, caller.stderr.read(), caller.wait())
                events.append(json.loads(line)["event"])
            caller.kill()
            output, error = caller.communicate(timeout=5)
            assert not error
            assert "resumed" in [json.loads(line)["event"] for line in output.splitlines()]
            state = subprocess.run(
                ["ps", "-p", str(target.pid), "-o", "stat="],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            assert "T" not in state
        finally:
            if caller is not None and caller.poll() is None:
                caller.kill()
                caller.wait(timeout=5)
            if target.poll() is None:
                target.send_signal(signal.SIGCONT)
                target.terminate()
            target.wait(timeout=5)
