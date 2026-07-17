# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Loopback-TCP transport: discovery file, handshake, op round-trip.

Drives the listener with an in-process fake shim (a raw TCP client that
speaks the native-messaging framing) — no real Chrome, no real cua. Proves a
full ``hello`` + one op round-trips, auth-token rejection, and clean errors
when the listener is down.
"""

import json
import socket
import struct
import threading

import pytest

from computer_use.browser import server as S
from computer_use.browser.native_host import read_message, write_message
from computer_use.browser.protocol import BrowserError, BrowserErrorCode


# --- a fake "extension over the shim": a raw TCP client speaking the framing ---

class _FakeShim:
    """Connects to the listener, performs the extension half of the dialog."""

    def __init__(self, port: int, token: str | None):
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        self._file = self._sock.makefile("rwb")
        self._token = token
        self.handler = None  # set by test: op-name -> result

    def auth(self) -> None:
        if self._token is not None:
            write_message(self._file, {"type": "auth", "token": self._token})

    def hello(self, supported_ops, *, profile_id=None, profile=None):
        # cua sends its hello first; read it, then reply with ours.
        cua_hello = read_message(self._file)
        assert cua_hello["type"] == "hello"
        msg = {
            "type": "hello",
            "proto": cua_hello["proto"],
            "ext_version": "0.4.0",
            "browser": "chrome",
            "supported_ops": list(supported_ops),
        }
        if profile_id is not None:
            msg["profile_id"] = profile_id
        if profile is not None:
            msg["profile"] = profile
        write_message(self._file, msg)
        return cua_hello

    def serve_one_op(self):
        """Read one op request, answer it via ``self.handler``."""
        msg = read_message(self._file)
        if msg is None or msg.get("type") != "op":
            return
        try:
            result = self.handler(msg["op"], msg.get("params", {}))
            write_message(
                self._file,
                {"type": "result", "id": msg["id"], "ok": True, "result": result},
            )
        except Exception as e:  # pragma: no cover - defensive
            write_message(
                self._file,
                {"type": "result", "id": msg["id"], "ok": False,
                 "error": {"code": "op_failed", "message": str(e)}},
            )

    def serve_one_op_prefixed_with_stray(self):
        """Read one op, then emit stray frames BEFORE the real result.

        Simulates the two ways the op stream stops being 1:1: a reconnect
        ``hello`` re-announced mid-stream, and a late result carrying a PRIOR
        op's id. ``request`` must discard both and return the id-matched reply.
        """
        msg = read_message(self._file)
        if msg is None or msg.get("type") != "op":
            return
        write_message(
            self._file,
            {"type": "hello", "proto": 1, "ext_version": "0.5.0",
             "browser": "chrome", "supported_ops": []},
        )
        write_message(
            self._file,
            {"type": "result", "id": msg["id"] - 1, "ok": True,
             "result": {"stale": True}},
        )
        result = self.handler(msg["op"], msg.get("params", {}))
        write_message(
            self._file,
            {"type": "result", "id": msg["id"], "ok": True, "result": result},
        )

    def close(self):
        try:
            self._file.close()
        finally:
            self._sock.close()


class TestDiscoveryFile:
    def test_write_and_read_roundtrip(self, tmp_path):
        path = tmp_path / "browser.port"
        S.write_discovery(4242, "tok-abc", path=path)
        port, token = S.read_discovery(path=path)
        assert port == 4242
        assert token == "tok-abc"

    def test_read_missing_returns_none(self, tmp_path):
        assert S.read_discovery(path=tmp_path / "nope.port") == (None, None)

    def test_token_is_generated_when_not_given(self):
        t1 = S.generate_token()
        t2 = S.generate_token()
        assert t1 and t2 and t1 != t2
        assert len(t1) >= 16

    def test_wsl_discovery_path_is_under_mnt_c(self):
        p = S.wsl_discovery_path(windows_user="alice")
        assert str(p).startswith("/mnt/c/Users/alice/")
        assert p.name == "browser.port"

    def test_write_discovery_wsl_also_writes_windows_copy(self, tmp_path):
        linux = tmp_path / "linux" / "browser.port"
        win = tmp_path / "win" / "browser.port"
        S.write_discovery(7000, "tk", path=linux, windows_copy=win)
        assert S.read_discovery(path=linux) == (7000, "tk")
        assert S.read_discovery(path=win) == (7000, "tk")

    def test_resolve_discovery_path_honors_env(self, monkeypatch, tmp_path):
        # issue #26: the server must honor the same env the native host reads, so
        # concurrent cua instances get their own file instead of clobbering one.
        custom = tmp_path / "session-a" / "browser.port"
        monkeypatch.setenv("VADGR_CUA_BROWSER_DISCOVERY", str(custom))
        assert S.resolve_discovery_path() == custom

    def test_resolve_discovery_path_defaults_when_unset(self, monkeypatch):
        monkeypatch.delenv("VADGR_CUA_BROWSER_DISCOVERY", raising=False)
        assert S.resolve_discovery_path() == S.discovery_path()

    def test_ensure_server_writes_to_env_path(self, monkeypatch, tmp_path):
        # ensure_server must pass the env-resolved discovery path to BrowserServer
        # (the read-side override was previously dead — the server ignored it).
        custom = tmp_path / "session-b" / "browser.port"
        monkeypatch.setenv("VADGR_CUA_BROWSER_DISCOVERY", str(custom))
        monkeypatch.setattr(S, "_SERVER", None)
        captured = {}

        class FakeServer:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def start(self):
                return 12345

        monkeypatch.setattr(S, "BrowserServer", FakeServer)
        S.ensure_server()
        assert captured["discovery_path"] == custom


class TestListener:
    def test_full_hello_plus_navigate_roundtrip(self, tmp_path):
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, token = S.read_discovery(path=tmp_path / "browser.port")
            assert port == srv.port

            shim = _FakeShim(port, token)
            shim.auth()
            shim.handler = lambda op, params: {"url": params["url"], "title": "Home"}
            shim.hello(["navigate", "query"])

            # the listener should have registered a live session
            session = _wait_for_session(srv)
            assert "navigate" in session.supported_ops

            t = threading.Thread(target=shim.serve_one_op, daemon=True)
            t.start()
            result = session.request("navigate", {"url": "https://example.com"})
            t.join(timeout=2)

            assert result == {"url": "https://example.com", "title": "Home"}
            shim.close()
        finally:
            srv.stop()

    def test_query_roundtrip(self, tmp_path):
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, token = S.read_discovery(path=tmp_path / "browser.port")
            shim = _FakeShim(port, token)
            shim.auth()
            shim.handler = lambda op, params: [{"tag": "a", "text": "hi", "attrs": {}}]
            shim.hello(["query"])
            session = _wait_for_session(srv)

            t = threading.Thread(target=shim.serve_one_op, daemon=True)
            t.start()
            result = session.request("query", {"selector": "a"})
            t.join(timeout=2)
            assert result == [{"tag": "a", "text": "hi", "attrs": {}}]
            shim.close()
        finally:
            srv.stop()

    def test_request_matches_reply_by_id_skipping_stray_frames(self, tmp_path):
        # Regression: a reconnect `hello` or a late/stale result must NOT be
        # consumed as this op's reply. Before the id-match, one stray frame
        # desynced every subsequent reply by one (permanent off-by-one).
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, token = S.read_discovery(path=tmp_path / "browser.port")
            shim = _FakeShim(port, token)
            shim.auth()
            shim.handler = lambda op, params: {"ok": "real"}
            shim.hello(["query"])
            session = _wait_for_session(srv)

            t = threading.Thread(
                target=shim.serve_one_op_prefixed_with_stray, daemon=True
            )
            t.start()
            result = session.request("query", {"selector": "a"})
            t.join(timeout=2)

            # The stray hello and the stale-id result are dropped; only the
            # id-matched reply is returned.
            assert result == {"ok": "real"}
            shim.close()
        finally:
            srv.stop()

    def test_bad_auth_token_is_rejected(self, tmp_path):
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, _token = S.read_discovery(path=tmp_path / "browser.port")
            shim = _FakeShim(port, token="wrong-token")
            shim.auth()
            # The listener drops the connection on a bad token: no session,
            # and the socket closes (read returns EOF / empty).
            shim._sock.settimeout(2)
            data = shim._sock.recv(64)
            assert data == b""  # connection closed, no hello sent
            assert _active(srv) is None
            shim.close()
        finally:
            srv.stop()

    def test_listener_down_gives_clean_connect_error(self, tmp_path):
        # Nothing listening on a closed port -> the shim helper surfaces a
        # clean ConnectionError rather than hanging.
        free = _free_port()
        with pytest.raises((ConnectionRefusedError, OSError)):
            socket.create_connection(("127.0.0.1", free), timeout=1)

    def test_request_without_session_raises_not_connected(self, tmp_path):
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            assert _active(srv) is None
        finally:
            srv.stop()

    def test_two_profile_connections_are_kept_and_keyed(self, tmp_path):
        # 0.6.1: the accept loop keeps BOTH connections, keyed by profile_id,
        # instead of a single-listener bond.
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, token = S.read_discovery(path=tmp_path / "browser.port")
            work = _FakeShim(port, token)
            work.auth()
            work.hello(["navigate", "profiles"], profile_id="work-uuid",
                       profile={"window_count": 1, "tab_count": 2,
                                "sample_tab_titles": ["Work Gmail"]})
            home = _FakeShim(port, token)
            home.auth()
            home.hello(["navigate", "profiles"], profile_id="home-uuid",
                       profile={"window_count": 1, "tab_count": 1,
                                "sample_tab_titles": ["Personal Gmail"]})
            _wait_for_count(srv, 2)
            keys = set(srv.bridge._sessions.keys())
            assert ("chrome", "work-uuid") in keys
            assert ("chrome", "home-uuid") in keys
            work.close()
            home.close()
        finally:
            srv.stop()

    def test_missing_profile_id_registers_as_default(self, tmp_path):
        srv = S.BrowserServer(discovery_path=tmp_path / "browser.port")
        srv.start()
        try:
            port, token = S.read_discovery(path=tmp_path / "browser.port")
            shim = _FakeShim(port, token)
            shim.auth()
            shim.hello(["navigate"])  # a 0.6.0 extension: no profile_id
            _wait_for_session(srv)
            assert ("chrome", "default") in srv.bridge._sessions
            shim.close()
        finally:
            srv.stop()


# --- helpers ---

def _active(srv):
    return srv.bridge._active_session() if srv.bridge else None


def _wait_for_session(srv, timeout=2.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sess = srv.bridge._active_session()
        if sess is not None:
            return sess
        time.sleep(0.01)
    raise AssertionError("no session registered in time")


def _wait_for_count(srv, n, timeout=2.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(srv.bridge._sessions) >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"expected {n} sessions; got {len(srv.bridge._sessions)}")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
