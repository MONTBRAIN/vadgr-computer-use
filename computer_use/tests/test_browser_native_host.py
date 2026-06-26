# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Native-messaging stdio framing (length-prefixed JSON), no browser."""

import io
import json
import socket
import struct
import threading

import pytest

from computer_use.browser import native_host as NH
from computer_use.browser import server as S


def _framed(obj) -> bytes:
    raw = json.dumps(obj).encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


class TestWriteFrame:
    def test_writes_4_byte_le_length_prefix_then_json(self):
        buf = io.BytesIO()
        NH.write_message(buf, {"a": 1})
        data = buf.getvalue()
        (length,) = struct.unpack("<I", data[:4])
        assert length == len(data) - 4
        assert json.loads(data[4:]) == {"a": 1}


class TestReadFrame:
    def test_reads_one_framed_message(self):
        buf = io.BytesIO(_framed({"type": "hello", "proto": 1}))
        msg = NH.read_message(buf)
        assert msg == {"type": "hello", "proto": 1}

    def test_eof_returns_none(self):
        assert NH.read_message(io.BytesIO(b"")) is None

    def test_truncated_body_raises(self):
        # Declares 50 bytes but supplies fewer.
        bad = struct.pack("<I", 50) + b"{}"
        with pytest.raises(EOFError):
            NH.read_message(io.BytesIO(bad))

    def test_roundtrip_multiple_messages(self):
        buf = io.BytesIO()
        NH.write_message(buf, {"id": 1})
        NH.write_message(buf, {"id": 2})
        buf.seek(0)
        assert NH.read_message(buf) == {"id": 1}
        assert NH.read_message(buf) == {"id": 2}
        assert NH.read_message(buf) is None


class TestConnectCua:
    def test_reads_discovery_file_and_connects_over_tcp(self, tmp_path):
        # A bare TCP listener standing in for cua.
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        disc = tmp_path / "browser.port"
        S.write_discovery(port, "tok-1", path=disc)

        sock, token = NH._connect_cua(discovery=disc)
        try:
            assert token == "tok-1"
            conn, _ = srv.accept()
            conn.close()
        finally:
            sock.close()
            srv.close()

    def test_missing_discovery_raises_connection_error(self, tmp_path):
        with pytest.raises(ConnectionError):
            NH._connect_cua(discovery=tmp_path / "nope.port")

    def test_listener_down_raises_connection_error(self, tmp_path):
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()  # nothing listening now
        disc = tmp_path / "browser.port"
        S.write_discovery(port, "tok", path=disc)
        with pytest.raises(ConnectionError):
            NH._connect_cua(discovery=disc)


class TestEndToEndShim:
    """Drive the real listener with the real shim relay over fake Chrome stdio.

    Proves: auth frame sent, full hello, one op round-trips end to end through
    native_host._relay <-> BrowserServer — no real Chrome, no real cua.
    """

    def test_hello_plus_navigate_through_the_shim(self, tmp_path):
        disc = tmp_path / "browser.port"
        srv = S.BrowserServer(discovery_path=disc)
        srv.start()
        try:
            # Connect the shim to the listener exactly as main() would.
            cua_sock, token = NH._connect_cua(discovery=disc)
            cua_file = cua_sock.makefile("rwb")

            # The shim sends the auth frame before relaying Chrome frames.
            NH.write_message(cua_file, {"type": "auth", "token": token})

            # Chrome stdin: the extension's hello, then it waits for cua's hello.
            # Emulate the extension half on a background thread driving the shim.
            chrome_to_shim = _Pipe()
            shim_to_chrome = _Pipe()

            relay = threading.Thread(
                target=NH._relay,
                args=(chrome_to_shim.reader, shim_to_chrome.writer, cua_file),
                daemon=True,
            )
            relay.start()

            # cua sends hello first (over the socket); the listener handshake
            # then reads the extension hello. The extension (here) must reply.
            # Read cua's hello as it arrives back at "Chrome".
            # Drive: the extension posts its hello, which the shim forwards to cua.
            NH.write_message(
                chrome_to_shim.writer,
                {"type": "hello", "proto": 1, "ext_version": "0.4.0",
                 "browser": "chrome", "supported_ops": ["navigate"]},
            )

            session = _wait_for_session(srv)
            assert session.supported_ops == ["navigate"]

            # Now issue an op from cua's side; the extension answers via the shim.
            ext = threading.Thread(
                target=_extension_answer_one,
                args=(chrome_to_shim, shim_to_chrome,
                      {"url": "https://x", "title": "X"}),
                daemon=True,
            )
            ext.start()
            result = session.request("navigate", {"url": "https://x"})
            ext.join(timeout=2)
            assert result == {"url": "https://x", "title": "X"}
            cua_sock.close()
        finally:
            srv.stop()


# --- helpers for the e2e shim test ---

class _Pipe:
    """A blocking in-memory byte pipe with file-like reader/writer ends."""

    def __init__(self):
        r, w = socket.socketpair()
        self._r = r
        self._w = w
        self.reader = r.makefile("rb")
        self.writer = w.makefile("wb")


def _extension_answer_one(chrome_to_shim, shim_to_chrome, result):
    # The shim forwards cua's frames onto "Chrome" (shim_to_chrome). cua's hello
    # arrives first; skip it and answer the first op.
    while True:
        msg = NH.read_message(shim_to_chrome.reader)
        if msg is None:
            return
        if msg.get("type") == "op":
            break
    NH.write_message(
        chrome_to_shim.writer,
        {"type": "result", "id": msg["id"], "ok": True, "result": result},
    )


def _wait_for_session(srv, timeout=2.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sess = srv.bridge._active_session()
        if sess is not None:
            return sess
        time.sleep(0.01)
    raise AssertionError("no session registered in time")
