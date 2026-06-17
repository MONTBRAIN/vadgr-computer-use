# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The native-messaging host Chrome spawns via ``connectNative``.

Chrome talks to this process over stdio in the native-messaging framing:
each message is a 4-byte little-endian length prefix followed by that many
bytes of UTF-8 JSON. This module owns that framing and the relay loop that
bridges the Chrome stdio side to the already-running cua over a local IPC
socket.

The framing helpers (``read_message`` / ``write_message``) are pure and
unit-tested against in-memory byte streams; the live relay (``main``) needs a
real Chrome + a running cua and is exercised by the manual spike, not by the
unit suite.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
from typing import Any, BinaryIO

# Default local-IPC rendezvous between the Chrome-spawned host and the running
# cua. cua's NativeMessagingBridge listens here; the host connects. Overridable
# via the environment so the manifest/launcher can relocate it per platform.
DEFAULT_SOCKET_PATH = os.environ.get(
    "VADGR_CUA_BROWSER_SOCKET",
    os.path.join(os.path.expanduser("~"), ".vadgr-cua", "browser.sock"),
)

_LEN_PREFIX = struct.Struct("<I")


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one length-prefixed JSON message. Returns ``None`` at clean EOF.

    Raises ``EOFError`` if the stream ends mid-message (truncated body).
    """
    header = stream.read(4)
    if not header:
        return None
    if len(header) < 4:
        raise EOFError("truncated length prefix")
    (length,) = _LEN_PREFIX.unpack(header)
    body = stream.read(length)
    if len(body) < length:
        raise EOFError(
            f"truncated message body: expected {length} bytes, got {len(body)}"
        )
    return json.loads(body.decode("utf-8"))


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    """Write one length-prefixed JSON message and flush."""
    raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(_LEN_PREFIX.pack(len(raw)))
    stream.write(raw)
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def _connect_cua(socket_path: str) -> socket.socket:
    """Connect to the running cua's local IPC endpoint.

    Raises ``ConnectionError`` if cua is not running, so the host can surface a
    clean "start cua" message rather than hanging.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(socket_path)
    except (FileNotFoundError, ConnectionRefusedError) as e:
        sock.close()
        raise ConnectionError(
            f"cua is not running (no listener at {socket_path}); start cua first"
        ) from e
    return sock


def _relay(chrome_in, chrome_out, cua_sock_file) -> None:
    """Pump messages both ways between the Chrome stdio pair and the cua socket.

    Single-threaded request/response relay: a message from Chrome is forwarded
    to cua, cua's reply is forwarded back to Chrome. Kept simple on purpose —
    the extension serializes ops over the one native port.
    """
    while True:
        msg = read_message(chrome_in)
        if msg is None:
            return
        write_message(cua_sock_file, msg)
        reply = read_message(cua_sock_file)
        if reply is None:
            return
        write_message(chrome_out, reply)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - live spike
    """Entry point Chrome launches. Bridges Chrome stdio <-> running cua.

    Not unit-covered: requires a real Chrome handshake and a running cua. The
    manual spike exercises this path.
    """
    socket_path = DEFAULT_SOCKET_PATH
    chrome_in = sys.stdin.buffer
    chrome_out = sys.stdout.buffer
    try:
        cua_sock = _connect_cua(socket_path)
    except ConnectionError as e:
        # Surface a clean error back to the extension, then exit.
        write_message(
            chrome_out,
            {"type": "result", "ok": False,
             "error": {"code": "not_connected", "message": str(e)}},
        )
        return 1
    with cua_sock, cua_sock.makefile("rwb") as cua_file:
        _relay(chrome_in, chrome_out, cua_file)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
