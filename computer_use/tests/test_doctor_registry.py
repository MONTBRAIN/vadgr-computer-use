# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""`vadgr-cua doctor` must verify the new registry per ARCHITECTURE.md §10.1.

The JSON output gains: tool_count, tier_breakdown, registry_loaded.
"""

import json
from unittest.mock import MagicMock, patch


class TestDoctorReportsRegistry:
    def test_doctor_includes_tool_count(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {"daemon_running": False}
        with patch.object(mcp_server, "_get_supervisor", return_value=supervisor):
            rc = mcp_server._cmd_doctor(MagicMock())

        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "tool_count" in parsed
        assert parsed["tool_count"] >= 13

    def test_doctor_includes_tier_breakdown(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {"daemon_running": False}
        with patch.object(mcp_server, "_get_supervisor", return_value=supervisor):
            mcp_server._cmd_doctor(MagicMock())

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "tier_breakdown" in parsed
        # JSON keys are strings; expect all 13 pixel tools in tier "2".
        assert parsed["tier_breakdown"].get("2", 0) >= 13

    def test_doctor_includes_registry_loaded_flag(self, capsys):
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {"daemon_running": False}
        with patch.object(mcp_server, "_get_supervisor", return_value=supervisor):
            mcp_server._cmd_doctor(MagicMock())

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed.get("registry_loaded") is True

    def test_doctor_preserves_daemon_fields(self, capsys):
        """Existing daemon_running / port fields stay in the output."""
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {
            "daemon_running": True,
            "port": 19542,
            "daemon_hash": "abc",
        }
        with patch.object(mcp_server, "_get_supervisor", return_value=supervisor):
            mcp_server._cmd_doctor(MagicMock())

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["daemon_running"] is True
        assert parsed["port"] == 19542
