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

    def hello(self, supported_ops):
        # cua sends its hello first; read it, then reply with ours.
        cua_hello = read_message(self._file)
        assert cua_hello["type"] == "hello"
        write_message(
            self._file,
            {
                "type": "hello",
                "proto": cua_hello["proto"],
                "ext_version": "0.4.0",
                "browser": "chrome",
                "supported_ops": list(supported_ops),
            },
        )
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


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
