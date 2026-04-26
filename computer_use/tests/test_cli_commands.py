# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the `vadgr-cua` CLI subcommands: doctor, install-daemon,
stop-daemon, restart-daemon. Also covers the default (no-subcommand)
dispatch to the MCP stdio server.
"""

import json
from unittest.mock import MagicMock, patch



# --- Dispatch ---


class TestDispatch:
    def test_no_subcommand_runs_mcp_server(self):
        from computer_use import mcp_server

        with patch.object(mcp_server, "_run_mcp_server") as mock_run:
            mcp_server.main([])
            mock_run.assert_called_once()

    def test_doctor_dispatches_to_doctor_handler(self):
        from computer_use import mcp_server

        with patch.object(
            mcp_server, "_cmd_doctor", return_value=0
        ) as mock_cmd:
            assert mcp_server.main(["doctor"]) == 0
            mock_cmd.assert_called_once()

    def test_install_daemon_dispatches(self):
        from computer_use import mcp_server

        with patch.object(
            mcp_server, "_cmd_install_daemon", return_value=0
        ) as mock_cmd:
            assert mcp_server.main(["install-daemon"]) == 0
            mock_cmd.assert_called_once()

    def test_stop_daemon_dispatches(self):
        from computer_use import mcp_server

        with patch.object(
            mcp_server, "_cmd_stop_daemon", return_value=0
        ) as mock_cmd:
            assert mcp_server.main(["stop-daemon"]) == 0
            mock_cmd.assert_called_once()

    def test_restart_daemon_dispatches(self):
        from computer_use import mcp_server

        with patch.object(
            mcp_server, "_cmd_restart_daemon", return_value=0
        ) as mock_cmd:
            assert mcp_server.main(["restart-daemon"]) == 0
            mock_cmd.assert_called_once()


# --- doctor ---


class TestDoctor:
    def test_prints_status_as_json(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {
            "daemon_running": True,
            "port": 19542,
            "daemon_hash": "abc",
        }
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_doctor(MagicMock())
        out = capsys.readouterr().out
        assert rc == 0
        parsed = json.loads(out)
        assert parsed["daemon_running"] is True
        assert parsed["port"] == 19542


# --- install-daemon ---


class TestInstallDaemon:
    def test_success_returns_zero(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.ensure_running.return_value = MagicMock()  # live client
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_install_daemon(MagicMock())
        assert rc == 0
        assert "running" in capsys.readouterr().out.lower()

    def test_failure_returns_nonzero(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.ensure_running.return_value = None
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_install_daemon(MagicMock())
        assert rc != 0


# --- stop-daemon ---


class TestStopDaemon:
    def test_calls_supervisor_stop(self):
        from computer_use import mcp_server

        supervisor = MagicMock()
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_stop_daemon(MagicMock())
        assert rc == 0
        supervisor.stop.assert_called_once()


# --- restart-daemon ---


class TestRestartDaemon:
    def test_success_returns_zero(self):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.restart.return_value = MagicMock()  # live client
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_restart_daemon(MagicMock())
        assert rc == 0
        supervisor.restart.assert_called_once()

    def test_failure_returns_nonzero(self):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.restart.return_value = None
        with patch.object(
            mcp_server, "_get_supervisor", return_value=supervisor
        ):
            rc = mcp_server._cmd_restart_daemon(MagicMock())
        assert rc != 0


# --- setup ---


class TestSetup:
    def test_dispatches_to_setup_handler(self):
        from computer_use import mcp_server
        with patch.object(mcp_server, "_cmd_setup", return_value=0) as mock_cmd:
            assert mcp_server.main(["setup"]) == 0
            mock_cmd.assert_called_once()

    def test_on_darwin_fires_permission_prompts_and_prints_status(
        self, capsys
    ):
        from computer_use import mcp_server

        request = MagicMock()
        status = {
            "macos_accessibility_granted": False,
            "macos_screen_recording_granted": True,
            "python_executable": "/opt/homebrew/bin/python3.12",
        }
        with patch("sys.platform", "darwin"), \
             patch(
                 "computer_use.platform.macos.request_permissions",
                 request,
             ), \
             patch(
                 "computer_use.platform.macos.macos_permission_status",
                 return_value=status,
             ):
            rc = mcp_server._cmd_setup(MagicMock())

        request.assert_called_once()
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["macos_accessibility_granted"] is False
        assert parsed["macos_screen_recording_granted"] is True
        assert parsed["python_executable"].endswith("python3.12")

    def test_off_darwin_returns_zero_and_marks_not_applicable(self, capsys):
        from computer_use import mcp_server
        with patch("sys.platform", "linux"):
            rc = mcp_server._cmd_setup(MagicMock())
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["applicable"] is False
        assert parsed["platform"] == "linux"

    def test_off_darwin_does_not_call_request_permissions(self):
        from computer_use import mcp_server
        request = MagicMock()
        with patch("sys.platform", "linux"), \
             patch("computer_use.platform.macos.request_permissions", request):
            mcp_server._cmd_setup(MagicMock())
        request.assert_not_called()


# --- legacy flags still work ---


class TestLegacyFlags:
    def test_transport_flag_still_works(self):
        from computer_use import mcp_server

        with patch.object(mcp_server, "_run_mcp_server") as mock_run:
            mcp_server.main(["--transport", "stdio"])
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args.transport == "stdio"
