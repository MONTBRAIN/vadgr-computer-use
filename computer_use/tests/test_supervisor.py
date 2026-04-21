# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for DaemonSupervisor: dynamic lifecycle of the Windows bridge.

Covers: `ensure_running` decision tree (healthy, missing, launch-fail),
`stop`, `restart`, and `status` introspection. The deployer and the
bridge client are injected -- no real subprocess calls here.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --- Fixtures ---


@pytest.fixture
def fake_deployer(tmp_path):
    """In-memory stand-in for DaemonDeployer."""
    deployer = MagicMock()
    deployer.find_windows_python.return_value = "C:\\Python312\\python.exe"
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    deployer.get_deploy_dir.return_value = deploy_dir
    deployer.ensure.return_value = True
    deployer.current_daemon_hash.return_value = "deadbeef"
    return deployer


@pytest.fixture
def healthy_client():
    """BridgeClient that reports the daemon is alive."""
    client = MagicMock()
    client.is_available.return_value = True
    return client


@pytest.fixture
def dead_client():
    """BridgeClient that reports the daemon is not reachable."""
    client = MagicMock()
    client.is_available.return_value = False
    return client


def _supervisor(fake_deployer, client):
    """Build a supervisor wired to the fake deployer + the given client."""
    from computer_use.bridge.supervisor import DaemonSupervisor
    return DaemonSupervisor(
        deployer=fake_deployer,
        client_factory=lambda: client,
    )


# --- ensure_running: happy paths ---


class TestEnsureRunningHealthy:
    def test_returns_client_when_daemon_already_healthy(
        self, fake_deployer, healthy_client
    ):
        supervisor = _supervisor(fake_deployer, healthy_client)
        result = supervisor.ensure_running()
        assert result is healthy_client

    def test_does_not_redeploy_when_daemon_healthy(
        self, fake_deployer, healthy_client
    ):
        supervisor = _supervisor(fake_deployer, healthy_client)
        supervisor.ensure_running()
        fake_deployer.ensure.assert_not_called()

    def test_does_not_launch_when_daemon_healthy(
        self, fake_deployer, healthy_client
    ):
        supervisor = _supervisor(fake_deployer, healthy_client)
        with patch.object(supervisor, "_launch") as mock_launch:
            supervisor.ensure_running()
            mock_launch.assert_not_called()


# --- ensure_running: auto-launch path ---


class TestEnsureRunningLaunch:
    def test_launches_daemon_when_not_running(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        # After launch, pretend the poll brings the daemon up.
        with (
            patch.object(supervisor, "_launch") as mock_launch,
            patch.object(supervisor, "_poll_for_ready", return_value=dead_client),
        ):
            dead_client.is_available.side_effect = [False, True]
            supervisor.ensure_running()
            mock_launch.assert_called_once()
            fake_deployer.ensure.assert_called_once()

    def test_returns_none_when_no_windows_python(
        self, fake_deployer, dead_client
    ):
        fake_deployer.find_windows_python.return_value = None
        supervisor = _supervisor(fake_deployer, dead_client)
        with patch.object(supervisor, "_launch") as mock_launch:
            assert supervisor.ensure_running() is None
            mock_launch.assert_not_called()

    def test_returns_none_when_deploy_dir_unresolvable(
        self, fake_deployer, dead_client
    ):
        fake_deployer.get_deploy_dir.return_value = None
        supervisor = _supervisor(fake_deployer, dead_client)
        with patch.object(supervisor, "_launch") as mock_launch:
            assert supervisor.ensure_running() is None
            mock_launch.assert_not_called()

    def test_returns_none_when_deployer_ensure_fails(
        self, fake_deployer, dead_client
    ):
        fake_deployer.ensure.return_value = False
        supervisor = _supervisor(fake_deployer, dead_client)
        with patch.object(supervisor, "_launch") as mock_launch:
            assert supervisor.ensure_running() is None
            mock_launch.assert_not_called()

    def test_returns_none_when_poll_times_out(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        with (
            patch.object(supervisor, "_launch"),
            patch.object(supervisor, "_poll_for_ready", return_value=None),
        ):
            assert supervisor.ensure_running() is None


# --- stop ---


class TestStop:
    def test_runs_port_kill_and_cmdline_kill(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        with patch(
            "computer_use.bridge.supervisor.subprocess.run"
        ) as mock_run:
            supervisor.stop()
        # Two powershell calls: one to kill by port, one by command-line.
        assert mock_run.call_count == 2
        cmds = [call.args[0] for call in mock_run.call_args_list]
        # First should target the port, second should target daemon.py
        port_cmd = " ".join(cmds[0])
        cmdline_cmd = " ".join(cmds[1])
        assert "19542" in port_cmd
        assert "daemon.py" in cmdline_cmd

    def test_tolerates_powershell_errors(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        with patch(
            "computer_use.bridge.supervisor.subprocess.run",
            side_effect=Exception("oops"),
        ):
            # Should not raise -- stop is best-effort.
            supervisor.stop()


# --- restart ---


class TestRestart:
    def test_calls_stop_then_ensure_running(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        with (
            patch.object(supervisor, "stop") as mock_stop,
            patch.object(supervisor, "ensure_running") as mock_ensure,
        ):
            supervisor.restart()
            mock_stop.assert_called_once()
            mock_ensure.assert_called_once()


# --- status ---


class TestStatus:
    def test_reports_healthy_daemon(self, fake_deployer, healthy_client):
        supervisor = _supervisor(fake_deployer, healthy_client)
        status = supervisor.status()
        assert status["daemon_running"] is True
        assert status["windows_python"] == "C:\\Python312\\python.exe"
        assert status["daemon_hash"] == "deadbeef"

    def test_reports_missing_daemon(self, fake_deployer, dead_client):
        supervisor = _supervisor(fake_deployer, dead_client)
        status = supervisor.status()
        assert status["daemon_running"] is False

    def test_reports_missing_windows_python(self, fake_deployer, dead_client):
        fake_deployer.find_windows_python.return_value = None
        supervisor = _supervisor(fake_deployer, dead_client)
        status = supervisor.status()
        assert status["windows_python"] is None
