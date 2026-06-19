# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""cua's loopback-TCP listener — the real browser-tier transport.

The extension calls ``chrome.runtime.connectNative``, so Chrome spawns the
host shim (``native_host.py``) *on Chrome's own OS*. The shim is a thin
stdio<->TCP relay: it connects to this listener on ``127.0.0.1:<port>`` and
pumps length-prefixed native-messaging frames both ways.

Loopback TCP (not a unix socket) is deliberate — it is the one transport that
also crosses the WSL<->Windows boundary, so cua-in-WSL drives Windows Chrome by
reusing the bridge-daemon foothold.

On a connection the listener:

1. reads an optional ``auth`` frame and checks the token (mismatch -> drop);
2. sends cua's ``hello`` and reads the extension's ``hello`` (proto negotiated);
3. registers a :class:`TcpBrowserSession` carrying the negotiated capability
   list — the bridge then routes ops to it; each op is sent over the live
   connection and the matching ``result`` is awaited.

The chosen port + an auth token are written to a discovery file
(``~/.vadgr-cua/browser.port``) the shim reads. On WSL a Windows-readable copy
is written under ``/mnt/c/...`` so the Windows-side shim can find it too.
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
from pathlib import Path
from typing import Any

from computer_use.browser.bridge import BrowserSession, NativeMessagingBridge
from computer_use.browser.native_host import read_message, write_message
from computer_use.browser.protocol import (
    BrowserError,
    BrowserErrorCode,
    PROTOCOL_VERSION,
    client_hello,
    op_message,
    parse_result,
    parse_server_hello,
)

CUA_VERSION = "0.4.0"


def discovery_path() -> Path:
    """The well-known file the shim reads to find the listener (port + token)."""
    return Path.home() / ".vadgr-cua" / "browser.port"


def wsl_discovery_path(windows_user: str | None = None) -> Path:
    """A Windows-readable copy of the discovery file (under ``/mnt/c``).

    On WSL the Windows-side relay shim reads the discovery file from the Windows
    filesystem, so cua-in-WSL also writes a copy the shim can ``CreateFile`` on
    the Windows side.
    """
    from computer_use.browser.bridge import windows_user_home_mnt

    return (
        windows_user_home_mnt(windows_user)
        / "AppData" / "Local" / "vadgr-cua" / "browser.port"
    )


def generate_token() -> str:
    """A fresh per-run auth token. Loopback is local, but a token stops any
    other local process from hijacking the listener."""
    return secrets.token_hex(16)


def _write_one(dest: Path, payload: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(payload, encoding="utf-8")
    try:
        dest.chmod(0o600)
    except OSError:  # pragma: no cover - non-posix best-effort
        pass


def write_discovery(
    port: int,
    token: str,
    *,
    path: Path | None = None,
    windows_copy: Path | None = None,
) -> Path:
    """Write ``{port, token}`` JSON to the discovery file (0600).

    On WSL, ``windows_copy`` also writes a Windows-readable copy under
    ``/mnt/c`` so the Windows-side relay shim can find the listener.
    """
    dest = Path(path) if path is not None else discovery_path()
    payload = json.dumps({"port": port, "token": token})
    _write_one(dest, payload)
    if windows_copy is not None:
        try:
            _write_one(Path(windows_copy), payload)
        except OSError:  # pragma: no cover - /mnt/c may be unavailable
            pass
    return dest


def read_discovery(*, path: Path | None = None) -> tuple[int | None, str | None]:
    """Read the discovery file. Returns ``(None, None)`` if it is absent/bad."""
    src = Path(path) if path is not None else discovery_path()
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return data.get("port"), data.get("token")


class TcpBrowserSession(BrowserSession):
    """A live session backed by one TCP connection to the shim.

    ``request`` sends an op envelope and blocks for the matching ``result``.
    The extension serializes ops over the one native port, so a per-connection
    lock + a monotonic id is enough; replies arrive in order.
    """

    def __init__(self, conn_file, *, browser: str, ext_version: str,
                 supported_ops: list[str]) -> None:
        super().__init__(browser=browser, ext_version=ext_version,
                         supported_ops=supported_ops)
        self._file = conn_file
        self._lock = threading.Lock()
        self._next_id = 0

    def request(self, op: str, params: dict[str, Any]) -> Any:
        with self._lock:
            self._next_id += 1
            msg_id = self._next_id
            try:
                write_message(self._file, op_message(msg_id, op, params))
                reply = read_message(self._file)
            except (OSError, ValueError) as e:
                raise BrowserError(
                    BrowserErrorCode.NOT_CONNECTED,
                    f"browser session connection lost: {e}",
                ) from e
        if reply is None:
            raise BrowserError(
                BrowserErrorCode.NOT_CONNECTED,
                "browser session closed before replying",
            )
        return parse_result(reply)


class BrowserServer:
    """The loopback-TCP listener cua runs; the shim connects to it.

    Binds ``127.0.0.1:0`` (a free port), writes the discovery file, and accepts
    connections on a background thread. Each accepted connection runs the
    auth + handshake and, on success, registers a :class:`TcpBrowserSession`
    on the shared :class:`NativeMessagingBridge`.
    """

    def __init__(
        self,
        *,
        bridge: NativeMessagingBridge | None = None,
        discovery_path: Path | None = None,
        windows_copy: Path | None = None,
        host: str = "127.0.0.1",
    ) -> None:
        self.bridge = bridge if bridge is not None else NativeMessagingBridge()
        self._discovery_path = discovery_path
        self._windows_copy = windows_copy
        self._host = host
        self.token = generate_token()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.port: int | None = None

    def start(self) -> int:
        """Bind, write the discovery file, and start accepting. Returns the port."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, 0))
        self._sock.listen(8)
        self._sock.settimeout(0.25)
        self.port = self._sock.getsockname()[1]
        write_discovery(
            self.port, self.token,
            path=self._discovery_path, windows_copy=self._windows_copy,
        )
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        return self.port

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            ).start()

    def _handle_conn(self, conn: socket.socket) -> None:
        conn.settimeout(None)
        conn_file = conn.makefile("rwb")
        try:
            self._handshake(conn_file)
        except (OSError, ValueError, BrowserError):
            try:
                conn_file.close()
            finally:
                conn.close()

    def _handshake(self, conn_file) -> None:
        """auth -> cua hello -> extension hello -> register session."""
        # First frame may be an auth frame; if a token is in play it is required.
        first = read_message(conn_file)
        if first is None:
            raise ValueError("connection closed before handshake")
        if first.get("type") == "auth":
            if first.get("token") != self.token:
                # Reject: drop the connection, register nothing.
                raise BrowserError(
                    BrowserErrorCode.NOT_CONNECTED, "bad auth token"
                )
            first = None  # consumed; the next frame is the extension hello (after ours)

        # cua sends its hello first, then reads the extension's.
        write_message(conn_file, client_hello(CUA_VERSION))
        ext = first if first is not None else read_message(conn_file)
        if ext is None:
            raise ValueError("connection closed before extension hello")
        hello = parse_server_hello(ext)  # raises proto_mismatch on a bad envelope
        session = TcpBrowserSession(
            conn_file,
            browser=hello.browser or "chrome",
            ext_version=hello.ext_version,
            supported_ops=hello.supported_ops,
        )
        self.bridge.register_session(session)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)


# --- module-level convenience: one shared server for the running cua ----------

_SERVER: BrowserServer | None = None


def ensure_server(bridge: NativeMessagingBridge | None = None) -> BrowserServer:
    """Start (once) and return the process-wide listener.

    Best-effort: callers may guard with try/except so a transport failure never
    breaks the rest of cua. On WSL it also drops a Windows-readable discovery
    copy so the Windows relay shim can reach the listener.
    """
    global _SERVER
    if _SERVER is None:
        win_copy = None
        try:
            from computer_use.platform.detect import detect_platform
            from computer_use.core.types import Platform

            if detect_platform() == Platform.WSL2:
                win_copy = wsl_discovery_path()
        except Exception:
            win_copy = None
        _SERVER = BrowserServer(bridge=bridge, windows_copy=win_copy)
        _SERVER.start()
    return _SERVER
