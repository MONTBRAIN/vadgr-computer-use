# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Detached per-user browser broker shared by every local CUA client."""

from __future__ import annotations

import copy
import json
import os
import secrets
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from computer_use.browser.bridge import NativeMessagingBridge
from computer_use.browser.ownership import OwnershipConflict, OwnershipRegistry
from computer_use.browser.protocol import BrowserError, BrowserErrorCode
from computer_use.browser.server import BrowserServer, wsl_discovery_path

HEARTBEAT_SECONDS = 5.0
MISSED_HEARTBEATS = 3
LEASE_GRACE_SECONDS = 30.0
IDLE_EXIT_SECONDS = 300.0
PROCESS_STARTED_NS = os.environ.get("VADGR_CUA_BROKER_STARTED_NS")
BUNDLE_HASH = os.environ.get("VADGR_CUA_BROKER_BUNDLE_HASH")


def broker_root() -> Path:
    override = os.environ.get("VADGR_CUA_BROKER_ROOT")
    return Path(override) if override else Path.home() / ".vadgr-cua"


def broker_endpoint_path() -> Path:
    override = os.environ.get("VADGR_CUA_BROKER_ENDPOINT")
    if override:
        return Path(override)
    root_override = os.environ.get("VADGR_CUA_BROKER_ROOT")
    if root_override:
        return Path(root_override) / "browser-broker.json"
    shared = windows_broker_endpoint_path()
    return shared if shared is not None else broker_root() / "browser-broker.json"


def broker_lock_path() -> Path:
    return broker_endpoint_path().with_name("browser-broker.lock")


def windows_broker_endpoint_path() -> Path | None:
    try:
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA")
            base = Path(local) if local else Path.home() / "AppData" / "Local"
            return base / "vadgr-cua" / "browser-broker.json"
        from computer_use.browser.bridge import windows_user_home_mnt
        from computer_use.core.types import Platform
        from computer_use.platform.detect import detect_platform

        if detect_platform() != Platform.WSL2:
            return None
        return windows_user_home_mnt() / "AppData" / "Local" / "vadgr-cua" / "browser-broker.json"
    except Exception:
        return None


def _write_private(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import protect_owner_and_system

        protect_owner_and_system(path)


def read_endpoint(path: Path | None = None) -> dict[str, Any] | None:
    try:
        value = json.loads((path or broker_endpoint_path()).read_text(encoding="utf-8"))
        if value.get("host") != "127.0.0.1" or not isinstance(value.get("port"), int):
            return None
        return value
    except (OSError, ValueError):
        return None


@dataclass
class ClientState:
    client_id: str
    secret: str
    profile_id: str | None = None
    window_id: int | None = None
    tab_id: int | None = None
    revision: int | None = None
    connected: bool = True
    last_seen: float = field(default_factory=time.monotonic)
    lost_at: float | None = None
    active_requests: int = 0


class BrowserBroker:
    """Route exact targets and keep one extension registry for all clients."""

    _LIST_ONLY = {("tabs", "list"), ("windows", "list")}
    _NO_TARGET = {"profiles", "status"}

    def __init__(
        self,
        bridge: NativeMessagingBridge | None = None,
        *,
        recovered_epoch: bool = False,
    ) -> None:
        self.bridge = bridge or NativeMessagingBridge()
        self.ownership = OwnershipRegistry(orphan_on_first_observe=recovered_epoch)
        self.epoch = secrets.token_hex(8)
        self.clients: dict[str, ClientState] = {}
        self._lock = threading.RLock()

    def connect(self, client_id: str | None, secret: str | None) -> ClientState:
        with self._lock:
            if client_id and secret:
                state = self.clients.get(client_id)
                if state and secrets.compare_digest(state.secret, secret):
                    if (
                        state.lost_at is None
                        or time.monotonic() - state.lost_at <= LEASE_GRACE_SECONDS
                    ):
                        state.connected = True
                        state.lost_at = None
                        state.last_seen = time.monotonic()
                        return state
            state = ClientState(secrets.token_hex(8), secrets.token_hex(24))
            self.clients[state.client_id] = state
            return state

    def touch(self, state: ClientState) -> None:
        state.last_seen = time.monotonic()

    def disconnect(self, state: ClientState) -> None:
        with self._lock:
            state.connected = False
            state.lost_at = time.monotonic()

    def reap(self) -> None:
        now = time.monotonic()
        with self._lock:
            for state in self.clients.values():
                if (
                    state.connected
                    and state.active_requests == 0
                    and now - state.last_seen > HEARTBEAT_SECONDS * MISSED_HEARTBEATS
                ):
                    state.connected = False
                    state.lost_at = now
                if (
                    not state.connected
                    and state.lost_at is not None
                    and now - state.lost_at > LEASE_GRACE_SECONDS
                ):
                    self.ownership.orphan_client(state.client_id)
                    state.lost_at = None

    def _profiles(self, state: ClientState) -> dict[str, Any]:
        result = self.bridge.send("profiles", op="list")
        for profile in result.get("profiles", []):
            profile["is_current"] = profile.get("profile_id") == state.profile_id
        return result

    def _profile(self, state: ClientState) -> str:
        profiles = self._profiles(state).get("profiles", [])
        if state.profile_id and not any(
            item.get("profile_id") == state.profile_id for item in profiles
        ):
            # An MV3 worker restart briefly removes only its profile session. If
            # another profile remains connected, falling through to the
            # single-profile convenience would silently retarget this client
            # and make its still-valid lease look foreign. Keep the explicit
            # profile sticky while bounded recovery gives that worker time to
            # reconnect.
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline:
                time.sleep(0.1)
                profiles = self._profiles(state).get("profiles", [])
                if any(item.get("profile_id") == state.profile_id for item in profiles):
                    return state.profile_id
            raise BrowserError(
                BrowserErrorCode.RECOVERY_TIMEOUT,
                f"the selected profile {state.profile_id!r} did not reconnect during bounded recovery",
                remediation="reopen that browser profile, then retry once",
            )
        if not profiles and self.bridge.status().reason == "waking":
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline and not profiles:
                time.sleep(0.1)
                profiles = self._profiles(state).get("profiles", [])
            if not profiles:
                raise BrowserError(
                    BrowserErrorCode.RECOVERY_TIMEOUT,
                    "the enabled browser extension did not reconnect during bounded recovery",
                    remediation="reopen the browser, then retry once",
                )
        if not profiles:
            status = self.bridge.status()
            if status.reason == "not_set_up":
                raise BrowserError(
                    BrowserErrorCode.NOT_SET_UP,
                    "no native-host registration exists for the browser",
                    remediation="run vadgr-cua browser-setup",
                )
            if status.reason == "extension_disabled":
                raise BrowserError(
                    BrowserErrorCode.EXTENSION_DISABLED,
                    "the browser extension is installed but disabled",
                    remediation="enable the vadgr-cua extension",
                )
            if status.reason == "extension_missing":
                raise BrowserError(
                    BrowserErrorCode.EXTENSION_MISSING,
                    "the native host exists but the browser extension is not installed",
                    remediation="install the vadgr-cua extension",
                )
            raise BrowserError(BrowserErrorCode.NOT_CONNECTED, "no browser profile is connected")
        if state.profile_id and any(
            item.get("profile_id") == state.profile_id for item in profiles
        ):
            return state.profile_id
        if len(profiles) == 1:
            state.profile_id = str(profiles[0]["profile_id"])
            return state.profile_id
        raise BrowserError(
            BrowserErrorCode.PROFILE_AMBIGUOUS,
            "more than one browser profile is connected and this client has not selected one",
            remediation="call profiles(op='use', profile_id=...)",
        )

    def _use_profile(self, state: ClientState, requested: str) -> dict[str, Any]:
        profiles = self._profiles(state).get("profiles", [])
        matches = [
            item
            for item in profiles
            if str(item.get("profile_id", "")).startswith(requested)
        ]
        if len(matches) != 1:
            raise BrowserError(
                BrowserErrorCode.PROFILE_AMBIGUOUS,
                f"profile {requested!r} is not unique",
            )
        selected = matches[0]
        profile_id = str(selected["profile_id"])
        if state.profile_id != profile_id:
            state.window_id = state.tab_id = state.revision = None
        state.profile_id = profile_id
        return {
            "profile_id": profile_id,
            "browser": selected.get("browser"),
            "is_current": True,
        }

    def _send_profile(self, profile_id: str, operation: str, /, **params: Any) -> Any:
        # TcpBrowserSession correlates concurrent replies by request id. A
        # profile-wide lock would make one paced type operation freeze every
        # other client's independent window in that same browser profile.
        return self.bridge.send(operation, profile_id=profile_id, **params)

    def _decorate_tabs(
        self, state: ClientState, profile_id: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        result = copy.deepcopy(result)
        windows = result.get("windows", [])
        self.ownership.observe(profile_id, windows)
        for window in windows:
            wid = int(window["window_id"])
            own = self.ownership.describe(profile_id, wid, None, state.client_id)
            window["ownership"] = own
            window["owned"] = own["state"] == "mine"
            for tab in window.get("tabs", []):
                tid = int(tab["tab_id"])
                own = self.ownership.describe(profile_id, wid, tid, state.client_id)
                tab["ownership"] = own
                tab["owned"] = own["state"] == "mine"
                tab["is_current"] = state.tab_id == tid
        return result

    def _list_tabs(self, state: ClientState, profile_id: str) -> dict[str, Any]:
        result = self._send_profile(profile_id, "tabs", op="list")
        return self._decorate_tabs(state, profile_id, result)

    def _select(
        self, state: ClientState, profile_id: str, target: dict[str, Any], scope: str
    ) -> dict[str, Any]:
        window_id = int(target["window_id"])
        tab_id = int(target["tab_id"])
        if scope == "window":
            lease = self.ownership.claim_window(profile_id, window_id, state.client_id)
        else:
            lease = self.ownership.claim_tab(profile_id, window_id, tab_id, state.client_id)
        state.profile_id = profile_id
        state.window_id = window_id
        state.tab_id = tab_id
        state.revision = lease.revision
        result = dict(target)
        result["ownership"] = self.ownership.describe(
            profile_id, window_id, tab_id, state.client_id
        )
        return result

    def _ensure_target(self, state: ClientState, profile_id: str) -> None:
        if state.window_id is not None and state.tab_id is not None:
            self.ownership.require(
                profile_id, state.window_id, state.tab_id, state.client_id, state.revision
            )
            return
        target = self._send_profile(profile_id, "windows", op="open", focused=False)
        self._select(state, profile_id, target, "window")

    @staticmethod
    def _listed_target(
        listed: dict[str, Any], *, window_id: int | None, tab_id: int | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        for window in listed.get("windows", []):
            if window_id is not None and int(window["window_id"]) != window_id:
                continue
            for tab in window.get("tabs", []):
                if tab_id is None or int(tab["tab_id"]) == tab_id:
                    return window, tab
        target = f"tab {tab_id}" if tab_id is not None else f"window {window_id}"
        raise BrowserError(BrowserErrorCode.TARGET_LOST, f"{target} not found")

    def _owned_target(self, state: ClientState, profile_id: str) -> dict[str, Any]:
        listed = self._list_tabs(state, profile_id)
        if state.window_id is not None and state.tab_id is not None:
            ownership = self.ownership.describe(
                profile_id, state.window_id, state.tab_id, state.client_id
            )
            if ownership["state"] == "mine" and ownership["scope"] == "window":
                return {
                    "window_id": state.window_id,
                    "tab_id": state.tab_id,
                    "created": False,
                    "ownership": ownership,
                }
        for window in listed.get("windows", []):
            tabs = window.get("tabs", [])
            ownership = window.get("ownership", {})
            if ownership.get("state") != "mine" or ownership.get("scope") != "window" or not tabs:
                continue
            active = next((tab for tab in tabs if tab.get("active")), tabs[0])
            state.window_id = int(window["window_id"])
            state.tab_id = int(active["tab_id"])
            state.revision = int(ownership["revision"])
            return {
                "window_id": state.window_id,
                "tab_id": state.tab_id,
                "created": False,
                "ownership": ownership,
            }
        target = self._send_profile(profile_id, "windows", op="open", focused=False)
        selected = self._select(state, profile_id, target, "window")
        selected["created"] = True
        return selected

    def request(
        self,
        state: ClientState,
        op: str,
        params: dict[str, Any],
        *,
        cancelled=None,
    ) -> Any:
        self.touch(state)
        if op == "status":
            result = self.bridge.status().as_dict()
            result.update({"broker_epoch": self.epoch, "client_id": state.client_id})
            return result
        if op == "profiles":
            if params.get("op", "list") == "list":
                return self._profiles(state)
            if params.get("op") == "use":
                return self._use_profile(state, str(params.get("profile_id", "")))
        if op == "use_target" and params.get("profile_id") is not None:
            self._use_profile(state, str(params.pop("profile_id")))
        profile_id = self._profile(state)
        sub = str(params.get("op", ""))
        if (op, sub) in self._LIST_ONLY:
            listed = self._list_tabs(state, profile_id)
            if op == "tabs":
                return listed
            return {
                "windows": [
                    {key: value for key, value in window.items() if key != "tabs"}
                    for window in listed.get("windows", [])
                ]
            }
        if op == "windows" and sub == "claim":
            wid = int(params["window_id"])
            listed = self._list_tabs(state, profile_id)
            window = next(
                (item for item in listed["windows"] if int(item["window_id"]) == wid), None
            )
            if not window or not window.get("tabs"):
                raise BrowserError(BrowserErrorCode.TARGET_LOST, f"window {wid} not found")
            return self._select(
                state,
                profile_id,
                {"window_id": wid, "tab_id": int(window["tabs"][0]["tab_id"])},
                "window",
            )
        if op == "tabs" and sub == "claim":
            tid = int(params["tab_id"])
            listed = self._list_tabs(state, profile_id)
            for window in listed["windows"]:
                if any(int(tab["tab_id"]) == tid for tab in window.get("tabs", [])):
                    if params.get("window_id") is not None and int(params["window_id"]) != int(
                        window["window_id"]
                    ):
                        raise BrowserError(
                            BrowserErrorCode.TARGET_LOST,
                            f"tab {tid} is not in window {int(params['window_id'])}",
                        )
                    return self._select(
                        state,
                        profile_id,
                        {"window_id": int(window["window_id"]), "tab_id": tid},
                        "tab",
                    )
            raise BrowserError(BrowserErrorCode.TARGET_LOST, f"tab {tid} not found")
        if op == "windows" and sub == "release":
            window_id = int(params["window_id"])
            revision = self.ownership.release_window(profile_id, window_id, state.client_id)
            return {"released": True, "window_id": window_id, "revision": revision}
        if op == "tabs" and sub == "release":
            revision = self.ownership.release_tab(
                profile_id, int(params["tab_id"]), state.client_id
            )
            return {"released": True, "tab_id": int(params["tab_id"]), "revision": revision}
        if op == "windows" and sub == "open":
            target = self._send_profile(profile_id, op, **params)
            return self._select(state, profile_id, target, "window")
        if op == "tabs" and sub == "open":
            requested_window = params.get("window_id")
            if requested_window is None:
                self._ensure_target(state, profile_id)
                params["window_id"] = state.window_id
                assert state.window_id is not None and state.tab_id is not None
                window_id, tab_id = state.window_id, state.tab_id
            else:
                window_id = int(requested_window)
                listed = self._list_tabs(state, profile_id)
                _window, tab = self._listed_target(listed, window_id=window_id, tab_id=None)
                tab_id = int(tab["tab_id"])
            ownership = self.ownership.describe(profile_id, window_id, tab_id, state.client_id)
            if ownership["state"] == "other":
                raise OwnershipConflict(
                    str(ownership["scope"] or "window"),
                    window_id if ownership["scope"] == "window" else tab_id,
                    str(ownership["owner_id"]),
                )
            if ownership["state"] == "orphaned":
                raise OwnershipConflict("window", window_id, "orphaned")
            scope = ownership["scope"] if ownership["state"] == "mine" else None
            if scope != "window" and params.get("background", True) is False:
                raise OwnershipConflict("window", window_id, "shared-user-window")
            target = self._send_profile(profile_id, op, **params)
            return self._select(state, profile_id, target, "window" if scope == "window" else "tab")
        if op == "windows" and sub in ("focus", "close"):
            window_id = int(params["window_id"])
            listed = self._list_tabs(state, profile_id)
            window = next(
                (item for item in listed["windows"] if int(item["window_id"]) == window_id),
                None,
            )
            if not window or not window.get("tabs"):
                raise BrowserError(BrowserErrorCode.TARGET_LOST, f"window {window_id} not found")
            tab_id = int(window["tabs"][0]["tab_id"])
            lease = self.ownership.require(profile_id, window_id, tab_id, state.client_id)
            if (
                self.ownership.describe(profile_id, window_id, tab_id, state.client_id)["scope"]
                != "window"
            ):
                raise OwnershipConflict("window", window_id, lease.owner_id or "none")
            result = self._send_profile(profile_id, op, **params)
            if sub == "close" and state.window_id == window_id:
                state.window_id = state.tab_id = state.revision = None
            return result
        if op == "tabs" and sub in ("switch", "close"):
            tab_id = int(params["tab_id"])
            listed = self._list_tabs(state, profile_id)
            window = next(
                (
                    item
                    for item in listed["windows"]
                    if any(int(tab["tab_id"]) == tab_id for tab in item.get("tabs", []))
                ),
                None,
            )
            if not window:
                raise BrowserError(BrowserErrorCode.TARGET_LOST, f"tab {tab_id} not found")
            window_id = int(window["window_id"])
            lease = self.ownership.require(profile_id, window_id, tab_id, state.client_id)
            scope = self.ownership.describe(profile_id, window_id, tab_id, state.client_id)["scope"]
            if sub == "switch" and scope != "window":
                raise OwnershipConflict("window", window_id, lease.owner_id or "none")
            result = self._send_profile(profile_id, op, **params)
            if sub == "switch":
                state.window_id, state.tab_id, state.revision = window_id, tab_id, lease.revision
            elif state.tab_id == tab_id:
                state.window_id = state.tab_id = state.revision = None
            return result
        if op == "use_target":
            mode = str(params.get("mode", "owned"))
            if mode not in ("owned", "attach"):
                raise ValueError("mode must be 'owned' or 'attach'")
            if mode == "owned" and params.get("window_id") is None and params.get("tab_id") is None:
                return self._owned_target(state, profile_id)
            if params.get("window_id") is not None or params.get("tab_id") is not None:
                window_id = (
                    int(params["window_id"]) if params.get("window_id") is not None else None
                )
                tab_id = int(params["tab_id"]) if params.get("tab_id") is not None else None
                listed = self._list_tabs(state, profile_id)
                window, tab = self._listed_target(listed, window_id=window_id, tab_id=tab_id)
                target = {
                    "window_id": int(window["window_id"]),
                    "tab_id": int(tab["tab_id"]),
                    "created": False,
                }
            else:
                target = self._send_profile(profile_id, op, **params)
            return self._select(
                state,
                profile_id,
                target,
                "tab" if mode == "attach" else "window",
            )

        self._ensure_target(state, profile_id)
        assert state.window_id is not None and state.tab_id is not None
        lease = self.ownership.require(
            profile_id, state.window_id, state.tab_id, state.client_id, state.revision
        )
        params["_target"] = {
            "window_id": state.window_id,
            "tab_id": state.tab_id,
        }
        params["_ownership_revision"] = lease.revision
        if cancelled is None:
            result = self.bridge.send(op, profile_id=profile_id, **params)
        else:
            result = self.bridge.send(
                op,
                profile_id=profile_id,
                _cancelled=cancelled,
                **params,
            )
        if isinstance(result, dict):
            result["ownership_revision"] = lease.revision
        return result


class BrokerServer:
    def __init__(self) -> None:
        self.broker = BrowserBroker(recovered_epoch=read_endpoint() is not None)
        self.auth_token = secrets.token_hex(24)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(32)
        self._sock.settimeout(0.5)
        self.port = int(self._sock.getsockname()[1])
        self._stop = threading.Event()
        self._requests: dict[tuple[str, int], threading.Event] = {}
        self._requests_lock = threading.Lock()
        self._last_activity = time.monotonic()
        win_copy = wsl_discovery_path() if sys.platform != "win32" and windows_broker_endpoint_path() is not None else None
        self.browser_server = BrowserServer(bridge=self.broker.bridge, windows_copy=win_copy)

    @staticmethod
    def _read_line(file) -> dict[str, Any] | None:
        line = file.readline()
        return json.loads(line) if line else None

    @staticmethod
    def _write_line(file, value: dict[str, Any]) -> None:
        file.write((json.dumps(value, separators=(",", ":")) + "\n").encode())
        file.flush()

    def _serve_client(self, conn: socket.socket) -> None:
        state: ClientState | None = None
        try:
            with conn, conn.makefile("rwb") as file:
                hello = self._read_line(file)
                if not hello or hello.get("token") != self.auth_token:
                    return
                if hello.get("cancel_only"):
                    client_id = str(hello.get("client_id", ""))
                    secret = str(hello.get("secret", ""))
                    known = self.broker.clients.get(client_id)
                    if known is None or not secrets.compare_digest(known.secret, secret):
                        return
                    self._write_line(file, {"ok": True})
                    message = self._read_line(file)
                    if message and message.get("type") == "cancel":
                        key = (client_id, int(message.get("request_id", -1)))
                        with self._requests_lock:
                            event = self._requests.get(key)
                        if event is not None:
                            event.set()
                        self._write_line(file, {"ok": event is not None})
                    return
                state = self.broker.connect(hello.get("client_id"), hello.get("secret"))
                self._write_line(
                    file,
                    {
                        "ok": True,
                        "client_id": state.client_id,
                        "secret": state.secret,
                        "epoch": self.broker.epoch,
                        "pid": os.getpid(),
                        "process_started_ns": PROCESS_STARTED_NS,
                        "bundle_hash": BUNDLE_HASH,
                    },
                )
                while not self._stop.is_set():
                    message = self._read_line(file)
                    if message is None:
                        break
                    self._last_activity = time.monotonic()
                    if message.get("type") == "heartbeat":
                        self.broker.touch(state)
                        self._write_line(file, {"ok": True})
                        continue
                    request_key: tuple[str, int] | None = None
                    try:
                        request_id = int(message.get("id", -1))
                        cancellation = threading.Event()
                        request_key = (state.client_id, request_id)
                        with self._requests_lock:
                            self._requests[request_key] = cancellation
                        with self.broker._lock:
                            state.active_requests += 1
                        result = self.broker.request(
                            state,
                            str(message.get("op")),
                            dict(message.get("params") or {}),
                            cancelled=cancellation.is_set,
                        )
                        self._write_line(
                            file, {"ok": True, "id": message.get("id"), "result": result}
                        )
                    except OwnershipConflict as error:
                        self._write_line(
                            file,
                            {
                                "ok": False,
                                "id": message.get("id"),
                                "error": {"code": error.code, "message": str(error)},
                            },
                        )
                    except BrowserError as error:
                        self._write_line(
                            file,
                            {
                                "ok": False,
                                "id": message.get("id"),
                                "error": {
                                    "code": error.code.value,
                                    "message": error.message,
                                    "remediation": error.remediation,
                                },
                            },
                        )
                    except Exception as error:
                        self._write_line(
                            file,
                            {
                                "ok": False,
                                "id": message.get("id"),
                                "error": {"code": "op_failed", "message": str(error)},
                            },
                        )
                    finally:
                        if request_key is not None:
                            with self._requests_lock:
                                self._requests.pop(request_key, None)
                            with self.broker._lock:
                                state.active_requests = max(0, state.active_requests - 1)
                                state.last_seen = time.monotonic()
        except (OSError, ValueError):
            pass
        finally:
            if state is not None:
                self.broker.disconnect(state)

    def run(self) -> None:
        self.browser_server.start()
        endpoint = {
            "host": "127.0.0.1",
            "port": self.port,
            "token": self.auth_token,
            "pid": os.getpid(),
            "platform": sys.platform,
            "epoch": self.broker.epoch,
            "process_started_ns": PROCESS_STARTED_NS,
            "bundle_hash": BUNDLE_HASH,
        }
        _write_private(broker_endpoint_path(), endpoint)
        windows_path = windows_broker_endpoint_path()
        if windows_path is not None and windows_path != broker_endpoint_path():
            _write_private(windows_path, endpoint)
        try:
            while not self._stop.is_set():
                self.broker.reap()
                try:
                    conn, _ = self._sock.accept()
                except TimeoutError:
                    if (
                        not any(state.connected for state in self.broker.clients.values())
                        and not self.broker.bridge.has_sessions()
                        and time.monotonic() - self._last_activity > IDLE_EXIT_SECONDS
                    ):
                        break
                    continue
                threading.Thread(target=self._serve_client, args=(conn,), daemon=True).start()
        finally:
            self.browser_server.stop()
            self._sock.close()
            for path in (broker_endpoint_path(), windows_path):
                if path is not None:
                    try:
                        current = read_endpoint(path)
                        if current and current.get("epoch") == self.broker.epoch:
                            path.unlink()
                    except (OSError, ValueError):
                        pass


def main() -> int:
    lock = broker_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import msvcrt

        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR)
        file = os.fdopen(descriptor, "r+", encoding="utf-8")
        try:
            from computer_use.browser.windows_acl import protect_owner_and_system

            protect_owner_and_system(lock)
            if os.path.getsize(lock) == 0:
                file.write("0")
                file.flush()
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return 0
            file.seek(0)
            file.truncate()
            file.write(str(os.getpid()))
            file.flush()
            BrokerServer().run()
        finally:
            try:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            file.close()
            try:
                lock.unlink()
            except OSError:
                pass
        return 0
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return 0
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(str(os.getpid()))
    try:
        BrokerServer().run()
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
