# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Synchronous browser bridge client for the detached per-user broker."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import Any

from computer_use.browser.bridge import BridgeStatus
from computer_use.browser.broker import broker_lock_path, read_endpoint
from computer_use.browser.protocol import BrowserError, BrowserErrorCode


class _DuplexPipe:
    """The file-like half of a Windows proxy subprocess."""

    def __init__(self, process: subprocess.Popen) -> None:
        if process.stdin is None or process.stdout is None:
            raise ValueError("browser broker proxy pipes are unavailable")
        self._process = process
        self._stdin = process.stdin
        self._stdout = process.stdout

    def write(self, value: bytes) -> int:
        return self._stdin.write(value)

    def flush(self) -> None:
        self._stdin.flush()

    def readline(self) -> bytes:
        return self._stdout.readline()

    def close(self) -> None:
        for stream in (self._stdin, self._stdout):
            try:
                stream.close()
            except OSError:
                pass
        if self._process.poll() is None:
            self._process.terminate()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _running_under_wsl() -> bool:
    try:
        from computer_use.core.types import Platform
        from computer_use.platform.detect import detect_platform

        return detect_platform() == Platform.WSL2
    except Exception:
        return False


def _endpoint_host(endpoint: dict[str, Any]) -> str:
    return str(endpoint["host"])


def _endpoint_pid_alive(_endpoint: dict[str, Any] | None, pid: int) -> bool:
    return _pid_alive(pid)


class BrokerClient:
    def __init__(self, *, connect_timeout: float = 10.0) -> None:
        self._connect_timeout = connect_timeout
        self._client_id: str | None = None
        self._secret: str | None = None
        self._transport: socket.socket | subprocess.Popen | None = None
        self._file = None
        self._lock = threading.RLock()
        self._request_id = 0
        self._heartbeat_stop = threading.Event()
        self._broker_identity: dict[str, object] = {}

    @staticmethod
    def _write(file, value: dict[str, Any]) -> None:
        file.write((json.dumps(value, separators=(",", ":")) + "\n").encode())
        file.flush()

    @staticmethod
    def _read(file) -> dict[str, Any] | None:
        line = file.readline()
        return json.loads(line) if line else None

    def _start_broker(self) -> None:
        if sys.platform == "win32" or _running_under_wsl():
            from computer_use.browser.windows_broker import launch_windows_broker

            launch_windows_broker()
            return
        lock = broker_lock_path()
        endpoint = read_endpoint()
        if lock.exists():
            try:
                pid = int(lock.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pid = 0
            if not _endpoint_pid_alive(endpoint, pid):
                try:
                    lock.unlink()
                except OSError:
                    pass
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, "-m", "computer_use.browser.broker"], **kwargs)

    @staticmethod
    def _open_transport(endpoint: dict[str, Any]):
        if endpoint.get("platform") == "win32" and _running_under_wsl():
            from computer_use.browser.windows_broker import open_windows_proxy

            process = open_windows_proxy()
            return process, _DuplexPipe(process)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((_endpoint_host(endpoint), endpoint["port"]))
        return sock, sock.makefile("rwb")

    def _connect(self) -> None:
        if _running_under_wsl():
            self._connect_through_windows_proxy()
            return
        deadline = time.monotonic() + self._connect_timeout
        started = False
        while time.monotonic() < deadline:
            endpoint = read_endpoint()
            if (
                endpoint
                and (sys.platform == "win32" or _running_under_wsl())
                and endpoint.get("platform") != "win32"
            ):
                endpoint = None
            if endpoint:
                transport = None
                file = None
                try:
                    expected_bundle = None
                    if endpoint.get("platform") == "win32":
                        from computer_use.browser.windows_broker import validate_endpoint

                        expected_bundle = validate_endpoint(endpoint)
                    transport, file = self._open_transport(endpoint)
                    self._write(
                        file,
                        {
                            "token": endpoint["token"],
                            "client_id": self._client_id,
                            "secret": self._secret,
                        },
                    )
                    reply = self._read(file)
                    if (
                        reply
                        and reply.get("ok")
                        and reply.get("epoch") == endpoint.get("epoch")
                        and reply.get("pid") == endpoint.get("pid")
                        and reply.get("process_started_ns")
                        == endpoint.get("process_started_ns")
                        and reply.get("bundle_hash") == expected_bundle
                    ):
                        if isinstance(transport, socket.socket):
                            transport.settimeout(None)
                        self._transport, self._file = transport, file
                        self._client_id = str(reply["client_id"])
                        self._secret = str(reply["secret"])
                        self._broker_identity = {
                            "broker_pid": reply.get("pid"),
                            "broker_process_started_ns": reply.get("process_started_ns"),
                            "broker_bundle_hash": reply.get("bundle_hash"),
                        }
                        self._start_heartbeat()
                        return
                except (OSError, ValueError):
                    pass
                try:
                    if file is not None:
                        file.close()
                except OSError:
                    pass
                if transport is not None:
                    try:
                        if isinstance(transport, socket.socket):
                            transport.close()
                        else:
                            transport.terminate()
                    except OSError:
                        pass
            if not started:
                self._start_broker()
                started = True
            time.sleep(0.05)
        raise BrowserError(BrowserErrorCode.NOT_CONNECTED, "browser broker did not become ready")

    def _connect_through_windows_proxy(self) -> None:
        from computer_use.browser.windows_broker import expected_bundle_hash

        expected_bundle = expected_bundle_hash()
        deadline = time.monotonic() + self._connect_timeout
        self._start_broker()
        while time.monotonic() < deadline:
            transport = None
            file = None
            try:
                transport, file = self._open_transport({"platform": "win32"})
                self._write(
                    file,
                    {
                        "token": None,
                        "client_id": self._client_id,
                        "secret": self._secret,
                    },
                )
                reply = self._read(file)
                if (
                    reply
                    and reply.get("ok")
                    and reply.get("bundle_hash") == expected_bundle
                    and isinstance(reply.get("pid"), int)
                    and isinstance(reply.get("process_started_ns"), str)
                    and isinstance(reply.get("epoch"), str)
                ):
                    self._transport, self._file = transport, file
                    self._client_id = str(reply["client_id"])
                    self._secret = str(reply["secret"])
                    self._broker_identity = {
                        "broker_pid": reply.get("pid"),
                        "broker_process_started_ns": reply.get(
                            "process_started_ns"
                        ),
                        "broker_bundle_hash": reply.get("bundle_hash"),
                    }
                    self._start_heartbeat()
                    return
            except (OSError, ValueError):
                pass
            if file is not None:
                file.close()
            if transport is not None and transport.poll() is None:
                transport.terminate()
            time.sleep(0.05)
        raise BrowserError(
            BrowserErrorCode.NOT_CONNECTED,
            "the Windows browser broker did not become ready through the WSL proxy",
            remediation="enable Windows interop and retry; cua never changes WSL networking",
        )

    def _start_heartbeat(self) -> None:
        if getattr(self, "_heartbeat_thread", None) and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()

        def heartbeat() -> None:
            while not self._heartbeat_stop.wait(5.0):
                try:
                    with self._lock:
                        if self._file is None:
                            return
                        self._write(self._file, {"type": "heartbeat"})
                        if not self._read(self._file):
                            return
                except (OSError, ValueError):
                    self._close()
                    return

        self._heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def _close(self) -> None:
        file, transport = self._file, self._transport
        self._file = self._transport = None
        for value in (file, transport):
            try:
                if value is not None:
                    if isinstance(value, subprocess.Popen):
                        if value.poll() is None:
                            value.terminate()
                    else:
                        value.close()
            except OSError:
                pass

    def send(self, op: str, /, **params: Any) -> Any:
        cancelled = params.pop("_cancelled", None)
        with self._lock:
            if self._file is None:
                self._connect()
            self._request_id += 1
            request_id = self._request_id
            monitor_stop = threading.Event()
            if cancelled is not None:

                def monitor() -> None:
                    while not monitor_stop.wait(0.02):
                        if cancelled():
                            self._send_cancel(request_id)
                            return

                threading.Thread(target=monitor, daemon=True).start()
            try:
                self._write(self._file, {"id": request_id, "op": op, "params": params})
                reply = self._read(self._file)
            except (OSError, ValueError) as error:
                # Once dispatch may have reached the broker, replay is unsafe:
                # typing, clicks, navigation and JS can all have side effects.
                # Reconnect only prepares the *next* caller-controlled request.
                self._close()
                raise BrowserError(
                    BrowserErrorCode.NOT_CONNECTED,
                    "browser broker connection was lost after dispatch; the operation was not replayed",
                    remediation="inspect the target state before deciding whether to retry",
                ) from error
            finally:
                monitor_stop.set()
            if not reply:
                self._close()
                raise BrowserError(
                    BrowserErrorCode.NOT_CONNECTED, "browser broker connection closed"
                )
            if reply.get("ok"):
                return reply.get("result")
            error = reply.get("error") or {}
            raw_code = str(error.get("code", "op_failed"))
            try:
                code = BrowserErrorCode(raw_code)
            except ValueError:
                code = BrowserErrorCode.OP_FAILED
            raise BrowserError(
                code,
                str(error.get("message", "operation failed")),
                remediation=error.get("remediation"),
            )

    def _send_cancel(self, request_id: int) -> None:
        endpoint = {"platform": "win32", "token": None} if _running_under_wsl() else read_endpoint()
        if not endpoint or not self._client_id or not self._secret:
            return
        transport = None
        file = None
        try:
            transport, file = self._open_transport(endpoint)
            self._write(
                file,
                {
                    "token": endpoint["token"],
                    "client_id": self._client_id,
                    "secret": self._secret,
                    "cancel_only": True,
                },
            )
            if not (self._read(file) or {}).get("ok"):
                return
            self._write(file, {"type": "cancel", "request_id": request_id})
            self._read(file)
        except (OSError, ValueError):
            return
        finally:
            if file is not None:
                file.close()
            if isinstance(transport, socket.socket):
                transport.close()
            elif transport is not None and transport.poll() is None:
                transport.terminate()

    def status(self) -> BridgeStatus:
        result = self.send("status")
        return BridgeStatus(
            connected=bool(result.get("connected")),
            browsers=list(result.get("browsers") or []),
            setup=bool(result.get("setup")),
            reason=result.get("reason"),
            profiles=list(result.get("profiles") or []),
            broker_epoch=result.get("broker_epoch"),
            client_id=result.get("client_id"),
            broker_pid=self._broker_identity.get("broker_pid"),
            broker_process_started_ns=self._broker_identity.get(
                "broker_process_started_ns"
            ),
            broker_bundle_hash=self._broker_identity.get("broker_bundle_hash"),
        )
