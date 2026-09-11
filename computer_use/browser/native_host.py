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
(``~/.vadgr-cua/browser.port`` - port + auth token), connects to cua's
loopback-TCP listener, sends the auth frame, then pumps native-messaging
frames both ways between Chrome's stdio and cua.

Loopback TCP (not a unix socket) is deliberate - it is the one transport that
also crosses the WSL<->Windows boundary (see ``server.py``).

The framing helpers (``read_message`` / ``write_message``) and ``_connect_cua``
are pure/unit-tested. Subprocess tests cover both relay shutdown orders without
Chrome; the live runbook covers the real browser boundary.
"""

from __future__ import annotations

import json
import os
import select
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


def _stream_readable(stream, timeout: float) -> bool:
    """Wait briefly for POSIX input while retaining a cancellation point."""
    ready, _, _ = select.select([stream], [], [], timeout)
    return bool(ready)


def _cancel_windows_io(thread: threading.Thread) -> None:
    """Cancel a synchronous Windows read issued by the exact relay thread."""
    if os.name != "nt" or not thread.is_alive():
        return

    import ctypes
    from ctypes import wintypes

    native_id = thread.native_id
    if native_id is None:
        raise RuntimeError("native input thread has no Windows thread identifier")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
    kernel32.CancelSynchronousIo.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    thread_terminate = 0x0001
    handle = kernel32.OpenThread(thread_terminate, False, native_id)
    if not handle:
        error = ctypes.get_last_error()
        if not thread.is_alive():
            return
        raise OSError(error, os.strerror(error))
    try:
        if not kernel32.CancelSynchronousIo(handle):
            error = ctypes.get_last_error()
            if error != 1168:  # ERROR_NOT_FOUND: no pending read remains.
                raise OSError(error, os.strerror(error))
    finally:
        kernel32.CloseHandle(handle)


class _InterruptibleReader:
    """Exact-size reads which broker shutdown can cancel between pipe chunks."""

    def __init__(self, stream: BinaryIO, stop: threading.Event) -> None:
        self._stream = stream
        self._stop = stop

    def read(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size and not self._stop.is_set():
            if os.name != "nt" and not _stream_readable(self._stream, 0.05):
                continue
            chunk = self._stream.read(size - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)


def _shutdown_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _relay(chrome_in, chrome_out, cua_sock, cua_sock_file) -> None:
    """Pump frames both ways between the Chrome stdio pair and the cua socket.

    Two independent pumps (Chrome->cua and cua->Chrome) so the handshake - where
    both sides may send proactively - and the ordered op stream both work.
    Either EOF cancels the other direction, and the input reader is joined before
    return so interpreter shutdown never races a live standard-input read.
    """
    stop = threading.Event()

    def pump_up() -> None:
        try:
            _pump(_InterruptibleReader(chrome_in, stop), cua_sock_file)
        finally:
            stop.set()
            _shutdown_socket(cua_sock)

    up = threading.Thread(target=pump_up, name="vadgr-cua-native-input")
    up.start()
    try:
        _pump(cua_sock_file, chrome_out)
    finally:
        stop.set()
        _shutdown_socket(cua_sock)
        _cancel_windows_io(up)
        up.join()


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - subprocess
    """Entry point Chrome launches. Bridges Chrome stdio <-> running cua.

    Subprocess lifecycle tests supply the same pipes and a local broker without
    Chrome. The runbook exercises the complete browser launch path.
    """
    # BufferedReader may hold its internal lock while a daemon blocks on stdin,
    # which makes CPython abort during finalization. The relay owns a stoppable,
    # joined reader over the raw native-messaging pipe instead.
    chrome_in = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
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
        _relay(chrome_in, chrome_out, cua_sock, cua_file)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
