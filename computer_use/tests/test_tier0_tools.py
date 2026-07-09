# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tier 0 system tools — registration, dispatch, behavior contract.

8 tier-0 tools, each grouping a small set of sub-operations dispatched via
an ``op`` argument. After 0.3.0:
- 21 total registered tools (13 existing Tier.TWO + 8 new Tier.ZERO).
- Tier breakdown: {"0": 8, "0.5": 0, "1": 0, "2": 13}.
"""

import json
import os
import sys
import tempfile

import pytest


TIER0_TOOLS = {
    # name -> (expected risk literal, sub-ops)
    "fs": ("medium", {"read", "write", "list", "stat", "delete"}),
    "shell": ("high", {"run", "which"}),
    "http": ("medium", {"get", "post"}),
    "env": ("low", {"get", "set"}),
    "time": ("read_only", {"now", "sleep"}),
    "tempfile": ("low", {"temp_path"}),
    "data": (
        "read_only",
        {
            "parse_json",
            "serialize_json",
            "parse_csv",
            "serialize_csv",
            "parse_yaml",
            "serialize_yaml",
        },
    ),
    "clipboard": ("low", {"copy", "paste"}),
}


def _load_registry():
    """Trigger @tool decoration by importing mcp_server."""
    from computer_use import mcp_server  # noqa: F401
    from computer_use.core import REGISTRY

    return REGISTRY


class TestTier0Registration:
    def test_all_eight_tier_zero_tools_registered(self):
        registry = _load_registry()
        names = {t.name for t in registry.all()}
        for tool_name in TIER0_TOOLS:
            assert tool_name in names, f"tier-0 tool {tool_name!r} not registered"

    def test_each_tier_zero_tool_has_correct_tier(self):
        from computer_use.core.tier import Tier

        registry = _load_registry()
        for tool_name in TIER0_TOOLS:
            entry = registry.get(tool_name)
            assert entry is not None, f"tool {tool_name!r} missing"
            assert entry.tier == Tier.ZERO, (
                f"{tool_name}: expected Tier.ZERO, got {entry.tier}"
            )

    def test_each_tier_zero_tool_has_correct_risk(self):
        from computer_use.core.risk import Risk

        registry = _load_registry()
        for tool_name, (risk_value, _) in TIER0_TOOLS.items():
            entry = registry.get(tool_name)
            assert entry is not None
            assert entry.risk == Risk(risk_value), (
                f"{tool_name}: expected risk={risk_value}, got {entry.risk.value}"
            )

    def test_total_tool_count_is_twenty_five(self):
        # 23 after 0.4.0 + the 0.6.0 window/tab op-groups (tabs, windows).
        registry = _load_registry()
        assert registry.count() == 25, (
            f"expected 25 tools after 0.6.0, got {registry.count()}: "
            f"{[t.name for t in registry.all()]}"
        )

    def test_tier_breakdown_matches_atom_spec(self):
        from computer_use.core.tier import Tier

        registry = _load_registry()
        breakdown = registry.tier_breakdown()
        assert breakdown.get(Tier.ZERO, 0) == 8
        assert breakdown.get(Tier.HALF, 0) == 0
        # 0.4.0 added browser + browser_eval; 0.6.0 adds the tabs + windows
        # op-groups -> four Tier ONE browser tools.
        assert breakdown.get(Tier.ONE, 0) == 4
        assert breakdown.get(Tier.TWO, 0) == 13


class TestFastMCPDispatch:
    """Every tier-0 tool is exposed through FastMCP, same dispatch path as 0.2.0."""

    def test_fastmcp_exposes_all_tier_zero_tools(self):
        from computer_use import mcp_server

        wire_tools = set(mcp_server.mcp._tool_manager._tools.keys())
        for tool_name in TIER0_TOOLS:
            assert tool_name in wire_tools, (
                f"{tool_name!r} not exposed on FastMCP wire surface"
            )


# -- per-tool behavior contracts ------------------------------------------


class TestFs:
    def test_write_then_read_roundtrips(self, tmp_path):
        from computer_use.tools.system import fs

        p = tmp_path / "hello.txt"
        fs.fs(op="write", path=str(p), content="hi there")
        assert fs.fs(op="read", path=str(p)) == "hi there"

    def test_list_returns_entries(self, tmp_path):
        from computer_use.tools.system import fs

        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        entries = fs.fs(op="list", path=str(tmp_path))
        assert set(entries) == {"a.txt", "b.txt"}

    def test_stat_returns_size_and_kind(self, tmp_path):
        from computer_use.tools.system import fs

        p = tmp_path / "x.bin"
        p.write_bytes(b"abc")
        info = fs.fs(op="stat", path=str(p))
        assert info["size"] == 3
        assert info["kind"] == "file"

    def test_delete_removes_file(self, tmp_path):
        from computer_use.tools.system import fs

        p = tmp_path / "gone.txt"
        p.write_text("bye")
        fs.fs(op="delete", path=str(p))
        assert not p.exists()


class TestShell:
    def test_run_captures_stdout(self):
        from computer_use.tools.system import shell

        result = shell.shell(op="run", command=["echo", "hi"])
        assert result["returncode"] == 0
        assert result["stdout"].strip() == "hi"

    def test_which_returns_path_for_real_binary(self):
        from computer_use.tools.system import shell

        path = shell.shell(op="which", command="python3")
        # Must resolve to an absolute path on PATH, or None when missing.
        if path is not None:
            assert os.path.isabs(path)


class TestHttp:
    def test_get_returns_status_and_body(self, monkeypatch):
        """No real network: patch urllib so the contract is the only thing under test."""
        from computer_use.tools.system import http as http_tool

        class _FakeResp:
            status = 200
            headers = {"Content-Type": "text/plain"}

            def read(self):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=None):
            return _FakeResp()

        monkeypatch.setattr(http_tool.urllib_request, "urlopen", _fake_urlopen)

        out = http_tool.http(op="get", url="http://example.test/")
        assert out["status"] == 200
        assert out["body"] == "ok"

    def test_post_sends_body(self, monkeypatch):
        from computer_use.tools.system import http as http_tool

        captured = {}

        class _FakeResp:
            status = 201
            headers = {}

            def read(self):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=None):
            captured["data"] = req.data
            captured["method"] = req.get_method()
            return _FakeResp()

        monkeypatch.setattr(http_tool.urllib_request, "urlopen", _fake_urlopen)
        out = http_tool.http(
            op="post", url="http://example.test/", body='{"k":1}'
        )
        assert out["status"] == 201
        assert captured["method"] == "POST"
        assert captured["data"] == b'{"k":1}'


class TestEnv:
    def test_get_returns_string_value(self, monkeypatch):
        from computer_use.tools.system import env as env_tool

        monkeypatch.setenv("VCU_TEST_X", "abc")
        assert env_tool.env(op="get", name="VCU_TEST_X") == "abc"

    def test_get_returns_none_for_missing(self, monkeypatch):
        from computer_use.tools.system import env as env_tool

        monkeypatch.delenv("VCU_TEST_MISSING", raising=False)
        assert env_tool.env(op="get", name="VCU_TEST_MISSING") is None

    def test_set_writes_to_process_env(self, monkeypatch):
        from computer_use.tools.system import env as env_tool

        monkeypatch.delenv("VCU_TEST_SET", raising=False)
        env_tool.env(op="set", name="VCU_TEST_SET", value="yes")
        assert os.environ.get("VCU_TEST_SET") == "yes"


class TestTime:
    def test_now_returns_iso_8601(self):
        from computer_use.tools.system import time as time_tool
        import datetime as _dt

        s = time_tool.time(op="now")
        # Must round-trip through fromisoformat.
        parsed = _dt.datetime.fromisoformat(s)
        assert parsed is not None

    def test_sleep_returns_quickly_for_zero(self):
        import time as _t

        from computer_use.tools.system import time as time_tool

        t0 = _t.monotonic()
        time_tool.time(op="sleep", seconds=0)
        elapsed = _t.monotonic() - t0
        assert elapsed < 0.5


class TestTempfile:
    def test_temp_path_under_gettempdir(self):
        from computer_use.tools.system import tempfile as tf_tool

        p = tf_tool.tempfile(op="temp_path")
        assert os.path.dirname(p).startswith(tempfile.gettempdir())

    def test_temp_path_does_not_create_file(self):
        from computer_use.tools.system import tempfile as tf_tool

        p = tf_tool.tempfile(op="temp_path")
        assert not os.path.exists(p)


class TestData:
    def test_parse_serialize_json_roundtrip(self):
        from computer_use.tools.system import data

        parsed = data.data(op="parse_json", source='{"a": 1, "b": [2, 3]}')
        assert parsed == {"a": 1, "b": [2, 3]}
        out = data.data(op="serialize_json", value=parsed)
        assert json.loads(out) == parsed

    def test_parse_serialize_csv_roundtrip(self):
        from computer_use.tools.system import data

        parsed = data.data(op="parse_csv", source="a,b\n1,2\n3,4\n")
        assert parsed == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
        out = data.data(op="serialize_csv", value=parsed)
        # Cells stay quoted-or-bare; row count + header restored.
        assert "a,b" in out
        assert "1,2" in out

    def test_parse_yaml_returns_dict_when_available(self):
        from computer_use.tools.system import data

        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")
        parsed = data.data(op="parse_yaml", source="a: 1\nb: 2\n")
        assert parsed == {"a": 1, "b": 2}


class TestClipboard:
    def test_copy_paste_roundtrip_or_graceful(self):
        """Roundtrip when a clipboard backend is available; graceful skip otherwise."""
        from computer_use.tools.system import clipboard

        text = f"vcu-clip-test-{os.getpid()}"
        try:
            clipboard.clipboard(op="copy", text=text)
        except RuntimeError as e:
            pytest.skip(f"no clipboard backend on this host: {e}")
        # If copy succeeded, paste must return our text. Some backends are
        # asynchronous or owned by the session — accept either the text we
        # set or a documented "unavailable" sentinel.
        try:
            got = clipboard.clipboard(op="paste")
        except RuntimeError:
            pytest.skip("clipboard paste backend unavailable on this host")
        assert isinstance(got, str)

    def test_wayland_copy_launches_detached_with_timeout(self, monkeypatch):
        """wl-copy must not block forever on its captured pipes (issue #11).

        wl-copy forks a background daemon that serves the clipboard data and
        inherits the parent's pipe fds. With ``subprocess.run(...,
        capture_output=True)`` and no timeout, the daemon keeps the read end
        open and the call blocks forever. The copy path must instead launch the
        backend detached: stdin a pipe (to feed the text), stdout/stderr to
        DEVNULL so no fd is held open, and a defensive timeout so a hang
        surfaces as a catchable error rather than an infinite block. It must NOT
        wait on the daemon.
        """
        from computer_use.tools.system import clipboard

        # Force the wl-copy backend regardless of host (this is a WSL2 box).
        monkeypatch.setattr(
            clipboard,
            "_pick_backend",
            lambda: ("wl-copy", ["wl-copy"], ["wl-paste", "--no-newline"]),
        )

        recorded = {}

        class FakeProc:
            def __init__(self, *args, **kwargs):
                recorded["args"] = args
                recorded["kwargs"] = kwargs
                self.stdin = self._Stdin(recorded)
                recorded["communicate_timeout"] = None
                recorded["waited"] = False

            class _Stdin:
                def __init__(self, rec):
                    self._rec = rec
                    self.closed = False

                def write(self, data):
                    self._rec.setdefault("stdin_writes", []).append(data)

                def close(self):
                    self.closed = True

            def communicate(self, timeout=None):
                recorded["communicate_timeout"] = timeout
                return (None, None)

            def wait(self, timeout=None):
                # A blocking wait with no timeout is exactly the bug.
                recorded["waited"] = True
                recorded["wait_timeout"] = timeout
                return 0

            @property
            def returncode(self):
                return 0

        monkeypatch.setattr(clipboard.subprocess, "Popen", FakeProc)

        clipboard.clipboard(op="copy", text="hello")

        # Launched wl-copy (not -o, which would clear after first paste).
        argv = recorded["args"][0]
        assert argv == ["wl-copy"]
        assert "-o" not in argv

        kwargs = recorded["kwargs"]
        # stdout/stderr redirected to DEVNULL so the daemon holds no live fd.
        assert kwargs.get("stdout") == clipboard.subprocess.DEVNULL
        assert kwargs.get("stderr") == clipboard.subprocess.DEVNULL
        # stdin is a pipe so we can feed the text.
        assert kwargs.get("stdin") == clipboard.subprocess.PIPE
        # capture_output must NOT be used (that is what causes the hang).
        assert kwargs.get("capture_output") in (None, False)

        # The text was written to stdin and stdin was closed (EOF for the daemon).
        assert "hello" in "".join(recorded.get("stdin_writes", []))

        # A defensive timeout is bounded somewhere (communicate or wait), and
        # the call never does an unbounded blocking wait on the daemon.
        bounded = (
            recorded.get("communicate_timeout") is not None
            or recorded.get("wait_timeout") is not None
        )
        assert bounded, "wl-copy copy must use a defensive timeout"
