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
bytes of UTF-8 JSON. This module owns that framing and is the thin
**stdio<->TCP shim**: it reads the discovery file cua wrote
(``~/.vadgr-cua/browser.port`` — port + auth token), connects to cua's
loopback-TCP listener, sends the auth frame, then pumps native-messaging
frames both ways between Chrome's stdio and cua.

Loopback TCP (not a unix socket) is deliberate — it is the one transport that
also crosses the WSL<->Windows boundary (see ``server.py``).

The framing helpers (``read_message`` / ``write_message``) and ``_connect_cua``
are pure/unit-tested; ``main`` needs a real Chrome and is exercised by the
manual spike + the in-process e2e shim test.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO

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


def _connect_cua(discovery: Path | None = None) -> tuple[socket.socket, str | None]:
    """Connect to the running cua's loopback-TCP listener.

    Reads the discovery file cua wrote (port + auth token), connects over TCP,
    and returns ``(socket, token)``. Raises ``ConnectionError`` if cua is not
    running / not registered, so the host surfaces a clean error rather than
    hanging. The discovery path is overridable via
    ``VADGR_CUA_BROWSER_DISCOVERY`` (set by the launcher per platform).
    """
    # Imported lazily so the framing helpers stay import-cheap.
    from computer_use.browser.server import read_discovery

    if discovery is None:
        env = os.environ.get("VADGR_CUA_BROWSER_DISCOVERY")
        discovery = Path(env) if env else None
    port, token = read_discovery(path=discovery)
    if port is None:
        raise ConnectionError(
            "cua is not running (no browser discovery file); start cua first"
        )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("127.0.0.1", int(port)))
    except (ConnectionRefusedError, OSError) as e:
        sock.close()
        raise ConnectionError(
            f"cua is not listening on 127.0.0.1:{port}; start cua first"
        ) from e
    return sock, token


def _pump(src, dst) -> None:
    """Forward framed messages from ``src`` to ``dst`` until EOF."""
    try:
        while True:
            msg = read_message(src)
            if msg is None:
                return
            write_message(dst, msg)
    except (OSError, ValueError, EOFError):
        return


def _relay(chrome_in, chrome_out, cua_sock_file) -> None:
    """Pump frames both ways between the Chrome stdio pair and the cua socket.

    Two independent pumps (Chrome->cua and cua->Chrome) so the handshake — where
    both sides may send proactively — and the ordered op stream both work.
    Returns when either direction closes.
    """
    up = threading.Thread(
        target=_pump, args=(chrome_in, cua_sock_file), daemon=True
    )
    up.start()
    _pump(cua_sock_file, chrome_out)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - live spike
    """Entry point Chrome launches. Bridges Chrome stdio <-> running cua.

    Not unit-covered: requires a real Chrome handshake and a running cua. The
    in-process e2e shim test + the manual spike exercise this path.
    """
    chrome_in = sys.stdin.buffer
    chrome_out = sys.stdout.buffer
    try:
        cua_sock, token = _connect_cua()
    except ConnectionError as e:
        # Surface a clean error back to the extension, then exit.
        write_message(
            chrome_out,
            {"type": "result", "ok": False,
             "error": {"code": "not_connected", "message": str(e)}},
        )
        return 1
    with cua_sock, cua_sock.makefile("rwb") as cua_file:
        # Authenticate to the listener before relaying Chrome frames.
        if token:
            write_message(cua_file, {"type": "auth", "token": token})
        _relay(chrome_in, chrome_out, cua_file)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
