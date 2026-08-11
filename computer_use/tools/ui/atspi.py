# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The Linux structured tier: an AT-SPI2 backend over pure-python D-Bus.

There is no off-the-shelf pure-python AT-SPI2 client, so this is a from-scratch
one, scoped to only the interfaces the four ui_* tools need: Accessible (walk,
role, name, state), Component (extents, focus), Action (click and friends) and
EditableText (set_text). It speaks D-Bus with dbus-fast because the packaged
alternatives do not fit this repo's install contract: pyatspi is not on PyPI and
gi.Atspi needs system PyGObject, which an isolated venv (no system site packages)
cannot import. dbus-fast is a plain wheel, so a plain ``pip install`` gets it.

The backend depends on a small synchronous ``_Client`` seam, not on D-Bus
directly. The real client wraps dbus-fast on a private event-loop thread; a fake
client stands in for the unit tests, so the ref lifecycle, the verb-to-interface
mapping and the error names are all provable without a live accessibility bus.

Two facts about the tree the backend is built around, both observed on a real
GNOME 50 / Wayland box and not assumed:

- **On Wayland the compositor withholds a client's global surface position**, so
  Component extents come back window-relative with origin (0, 0). Grounding a
  Tier 2 pixel click on them is therefore an X11-only capability, and the
  capability block reports ``coordinate_trust`` so a caller never aims a pixel at
  a Wayland origin.
- **The action a button exposes is named "Click", capitalised**, and toolkits
  differ, so verbs are matched against the element's own action list
  case-insensitively rather than by a hard-coded string.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from typing import Protocol

from computer_use.platform.resolver.session import SessionContext
from computer_use.tools.ui.backend import (
    AT_SPI_UNAVAILABLE,
    ELEMENT_GONE,
    NO_TREE,
    UNAVAILABLE_REMEDY,
    UNSUPPORTED_ACTION,
    Bounds,
    Element,
    StructuredError,
)

# AT-SPI D-Bus interface and object names. The desktop root is a fixed well-known
# address; every other accessible is addressed by (bus_name, object_path) read
# off the tree.
_ACCESSIBLE = "org.a11y.atspi.Accessible"
_COMPONENT = "org.a11y.atspi.Component"
_ACTION = "org.a11y.atspi.Action"
_EDITABLE_TEXT = "org.a11y.atspi.EditableText"
_APPLICATION = "org.a11y.atspi.Application"
_PROPERTIES = "org.freedesktop.DBus.Properties"
_REGISTRY_BUS = "org.a11y.atspi.Registry"
_ROOT_PATH = "/org/a11y/atspi/accessible/root"
_A11Y_BUS = "org.a11y.Bus"
_A11Y_BUS_PATH = "/org/a11y/bus"

# SCREEN coordinate type for Component.GetExtents (the other is WINDOW).
_COORD_SCREEN = 0

# AtspiStateType, in enum order. GetState returns two uint32 words: word 0 holds
# states 0..31, word 1 holds 32..63. The names are the contract the model reads,
# so they track the AT-SPI enum rather than being renamed.
_STATE_NAMES = (
    "invalid", "active", "armed", "busy", "checked", "collapsed", "defunct",
    "editable", "enabled", "expandable", "expanded", "focusable", "focused",
    "has_tooltip", "horizontal", "iconified", "modal", "multi_line",
    "multiselectable", "opaque", "pressed", "resizable", "selectable",
    "selected", "sensitive", "showing", "single_line", "stale", "transient",
    "vertical", "visible", "manages_descendants", "indeterminate", "required",
    "truncated", "animated", "invalid_entry", "supports_autocompletion",
    "selectable_text", "is_default", "visited", "checkable", "has_popup",
    "read_only",
)

# A hard cap on tree/find traversal. The structured tier's whole argument is that
# it returns small text fast; an unbounded walk of a pathological tree would give
# that back. Depth is the caller's knob; this is the safety net on total nodes.
_MAX_NODES = 2000

# ui_wait polls find() rather than subscribing to registry signals: a bounded
# poll is simpler, needs no signal plumbing, and cannot outlive its timeout.
_WAIT_POLL_SECONDS = 0.1


def _proc_comm(pid: int) -> str:
    """The process command name from /proc, or empty. Best effort by design."""
    if pid <= 0:
        return ""
    try:
        with open(f"/proc/{pid}/comm") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def decode_states(word_low: int, word_high: int) -> tuple[str, ...]:
    """Turn AT-SPI's two-word state bitfield into sorted state names.

    Verified against a real GTK4 toggle button: a DoAction("click") set bit 20
    (``pressed``) in word 0, and word 1 bit 10 was ``has_popup`` (state 42).
    """
    names: list[str] = []
    for word, base in ((word_low, 0), (word_high, 32)):
        for bit in range(32):
            if word & (1 << bit):
                index = base + bit
                if index < len(_STATE_NAMES):
                    names.append(_STATE_NAMES[index])
    return tuple(names)


# A node is an opaque (bus_name, object_path) pair. The backend never parses it;
# it hands it back to the client, which is the only code that knows it is D-Bus.
Node = tuple[str, str]


class ElementGone(Exception):
    """The client raises this when a node no longer resolves on the bus.

    It is the single truthful answer to "act on where something used to be":
    the backend turns it into the ``element_gone`` error and never a coordinate
    fallback.
    """


class _Client(Protocol):
    """The synchronous accessibility-tree operations the backend needs.

    One method per AT-SPI capability the four tools use. The real implementation
    is D-Bus; the fake one in the tests is a plain in-memory tree. Any method may
    raise ElementGone when the node is stale.
    """

    def reachable(self) -> bool: ...
    def is_enabled(self) -> bool: ...
    def root(self) -> Node: ...
    def children(self, node: Node) -> list[Node]: ...
    def role_name(self, node: Node) -> str: ...
    def name(self, node: Node) -> str: ...
    def states(self, node: Node) -> tuple[str, ...]: ...
    def extents(self, node: Node) -> tuple[int, int, int, int] | None: ...
    def interfaces(self, node: Node) -> tuple[str, ...]: ...
    def actions(self, node: Node) -> list[str]: ...
    def do_action(self, node: Node, index: int) -> bool: ...
    def set_text(self, node: Node, text: str) -> bool: ...
    def grab_focus(self, node: Node) -> bool: ...
    def toolkits(self) -> tuple[str, ...]: ...
    def pid(self, node: Node) -> int: ...


# The verbs ui_act accepts, mapped to how each is performed. click/toggle/expand
# resolve to an Action by name; focus is a Component grab; set_text is an
# EditableText write. toggle and expand are click-like actions whose value is in
# the re-read, which the backend does for every verb.
_ACTION_VERBS = {
    "click": ("click",),
    "toggle": ("click",),
    "expand": ("expand", "activate", "click"),
}
_SUPPORTED_VERBS = ("click", "focus", "set_text", "toggle", "expand")


class AtspiBackend:
    """A StructuredBackend over an AT-SPI ``_Client``.

    Holds the per-session ref table so a ref handed out by find/tree resolves in
    a later act/wait. The table is why the backend is a session singleton rather
    than rebuilt per call: a fresh table would make every ref look stale.
    """

    def __init__(self, client: _Client, session: SessionContext) -> None:
        self._client = client
        self._session = session
        # A ref is opaque and session-scoped. The dict is the only thing that
        # maps it to a node, so a ref from a previous process (or an invented
        # one) simply is not present, which is exactly element_gone.
        self._refs: dict[str, Node] = {}
        self._rev: dict[Node, str] = {}
        self._counter = 0

    # -- ref bookkeeping ---------------------------------------------------

    def _ref_for(self, node: Node) -> str:
        existing = self._rev.get(node)
        if existing is not None:
            return existing
        self._counter += 1
        ref = f"atspi:{self._counter:x}"
        self._refs[ref] = node
        self._rev[node] = ref
        return ref

    def _node_for(self, ref: str) -> Node:
        node = self._refs.get(ref)
        if node is None:
            raise StructuredError(ELEMENT_GONE, "ref does not resolve")
        return node

    # -- capability --------------------------------------------------------

    def _coordinate_trust(self) -> str:
        # X11 hands out true screen extents; Wayland withholds the surface
        # origin, so its extents are window-relative and must not be used to aim
        # a pixel click. "real" versus "none" is that distinction, named.
        return "real" if self._session.server == "x11" else "none"

    def capability(self) -> dict:
        reachable = self._client.reachable()
        cap = {
            "backend": "atspi",
            "bus_reachable": reachable,
            "is_enabled": self._client.is_enabled() if reachable else False,
            "coordinate_trust": self._coordinate_trust(),
            "toolkits_seen": list(self._client.toolkits()) if reachable else [],
        }
        return cap

    def _require_bus(self) -> None:
        if not self._client.reachable():
            raise StructuredError(AT_SPI_UNAVAILABLE, remedy=UNAVAILABLE_REMEDY)

    # -- the focused window ------------------------------------------------

    def _active_window(self) -> Node:
        """Find the active top-level window across all applications.

        The tree is desktop -> applications -> windows; the focused one carries
        the ``active`` state. No active window is a real, nameable condition
        (nothing focused, or a toolkit that exposes none), so it is no_tree
        rather than an empty success.
        """
        root = self._client.root()
        for app in self._client.children(root):
            try:
                windows = self._client.children(app)
            except ElementGone:
                continue
            for window in windows:
                try:
                    if "active" in self._client.states(window):
                        return window
                except ElementGone:
                    continue
        raise StructuredError(NO_TREE, "no active window exposes a tree")

    # -- reading -----------------------------------------------------------

    def _element(self, node: Node) -> Element:
        extents = self._client.extents(node)
        bounds = Bounds(*extents) if extents is not None else None
        return Element(
            ref=self._ref_for(node),
            role=self._client.role_name(node),
            name=self._client.name(node),
            bounds=bounds,
            states=self._client.states(node),
        )

    def _node_dict(self, node: Node, depth: int, budget: list[int]) -> dict:
        """A tree node as a plain dict, its children recursed to ``depth``."""
        element = self._element(node)
        out = element.as_dict()
        children: list[dict] = []
        if depth > 0 and budget[0] > 0:
            for child in self._client.children(node):
                if budget[0] <= 0:
                    break
                budget[0] -= 1
                try:
                    children.append(self._node_dict(child, depth - 1, budget))
                except ElementGone:
                    continue
        out["children"] = children
        return out

    def tree(self, depth: int) -> dict:
        self._require_bus()
        window = self._active_window()
        budget = [_MAX_NODES]
        try:
            root = self._node_dict(window, max(depth, 0), budget)
        except ElementGone:
            raise StructuredError(NO_TREE, "the focused window's tree went away")
        return {"root": root, "depth": depth}

    def _matches(self, node: Node, role: str, name: str) -> bool:
        # role is an exact (case-insensitive) role-name match; name is a
        # case-insensitive substring so "Save" finds "Save As" too. An empty
        # argument matches anything, so find(role=...) and find(name=...) both
        # work without a sentinel.
        if role and self._client.role_name(node).lower() != role.lower():
            return False
        if name and name.lower() not in self._client.name(node).lower():
            return False
        return True

    def _search(self, role: str, name: str) -> list[Element]:
        window = self._active_window()
        found: list[Element] = []
        stack: list[Node] = [window]
        visited = 0
        while stack and visited < _MAX_NODES:
            node = stack.pop()
            visited += 1
            try:
                if self._matches(node, role, name):
                    found.append(self._element(node))
                stack.extend(reversed(self._client.children(node)))
            except ElementGone:
                continue
        return found

    def find(self, role: str, name: str) -> list[Element]:
        self._require_bus()
        return self._search(role, name)

    # -- acting ------------------------------------------------------------

    def _do_named_action(self, node: Node, candidates: tuple[str, ...]) -> None:
        actions = self._client.actions(node)
        lowered = [a.lower() for a in actions]
        for candidate in candidates:
            if candidate in lowered:
                self._client.do_action(node, lowered.index(candidate))
                return
        raise StructuredError(
            UNSUPPORTED_ACTION,
            "element does not support this action",
            supported=actions,
        )

    def act(self, ref: str, action: str, text: str) -> dict:
        self._require_bus()
        node = self._node_for(ref)
        # Confirm the ref still resolves before doing anything: a stale node is
        # element_gone, never a click on a remembered coordinate.
        try:
            self._client.role_name(node)
        except ElementGone:
            raise StructuredError(ELEMENT_GONE, "ref no longer resolves")

        verb = action.lower()
        if verb not in _SUPPORTED_VERBS:
            raise StructuredError(
                UNSUPPORTED_ACTION,
                f"unknown verb {action!r}",
                supported=list(_SUPPORTED_VERBS),
            )

        try:
            if verb in _ACTION_VERBS:
                self._do_named_action(node, _ACTION_VERBS[verb])
            elif verb == "focus":
                if _COMPONENT not in self._client.interfaces(node):
                    raise StructuredError(
                        UNSUPPORTED_ACTION, "element is not focusable",
                        supported=list(_SUPPORTED_VERBS),
                    )
                self._client.grab_focus(node)
            elif verb == "set_text":
                if _EDITABLE_TEXT not in self._client.interfaces(node):
                    raise StructuredError(
                        UNSUPPORTED_ACTION, "element has no editable text",
                        supported=list(_SUPPORTED_VERBS),
                    )
                self._client.set_text(node, text)
        except ElementGone:
            raise StructuredError(ELEMENT_GONE, "ref went away mid-action")

        # The re-read is the point of the tier: return what the element became,
        # so a toggle that did not toggle is visible now, not three turns later.
        try:
            state = self._element(node).as_dict()
        except ElementGone:
            raise StructuredError(ELEMENT_GONE, "element gone after acting")
        return {"action": verb, "state": state}

    # -- waiting -----------------------------------------------------------

    def wait(self, role: str, name: str, timeout_ms: int) -> Element | None:
        self._require_bus()
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
        while True:
            matches = self._search(role, name)
            if matches:
                return matches[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(_WAIT_POLL_SECONDS)

    # -- foreground window (for the platform layer) ------------------------

    def foreground_window(self):
        """The active top-level window as a ForegroundWindow, or None.

        This is the Wayland foreground-window path the platform layer used to
        get from gi.Atspi. On Wayland the extents are window-relative (origin
        withheld by the compositor), which is the same limitation the pixel
        tools already carry there; the app name, title and pid are the useful
        part. The last active window wins, matching GNOME's most-recently-focused
        ordering.
        """
        from computer_use.core.types import ForegroundWindow

        if not self._client.reachable():
            return None
        result = None
        for app in self._client.children(self._client.root()):
            try:
                app_name = self._client.name(app)
                for window in self._client.children(app):
                    if "active" not in self._client.states(window):
                        continue
                    extents = self._client.extents(window) or (0, 0, 0, 0)
                    pid = self._client.pid(app)
                    name = _proc_comm(pid) or app_name
                    result = ForegroundWindow(
                        app_name=name,
                        title=self._client.name(window) or "",
                        x=extents[0], y=extents[1],
                        width=extents[2], height=extents[3],
                        pid=pid,
                    )
            except ElementGone:
                continue
        return result


# ---------------------------------------------------------------------------
# The real client: dbus-fast on a private event-loop thread
# ---------------------------------------------------------------------------


class _AtspiBus:
    """Owns the asyncio loop and the two D-Bus connections the client speaks on.

    dbus-fast is asyncio-only (its glib backend needs PyGObject, the thing this
    tier avoids), and the ui_* tools are synchronous. So the loop runs on a
    daemon thread and every call is submitted to it and waited on: the tools stay
    synchronous and dbus-fast keeps its single owning loop.
    """

    def __init__(self, call_timeout: float = 5.0) -> None:
        self._timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._a11y = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=loop.run_forever, name="atspi-dbus", daemon=True
                )
                thread.start()
                self._loop = loop
            return self._loop

    def run(self, coro):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(self._timeout)

    def close(self) -> None:
        # For one-shot probes (reachability, enable) that must not leave a loop
        # thread running for the life of the process. The persistent backend
        # never calls this: it wants its connections kept warm.
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop = None
                self._session = None
                self._a11y = None

    async def _ensure_connected(self) -> None:
        if self._a11y is not None:
            return
        from dbus_fast import BusType, Message
        from dbus_fast.aio import MessageBus

        self._session = await MessageBus(bus_type=BusType.SESSION).connect()
        reply = await self._session.call(
            Message(
                destination=_A11Y_BUS, path=_A11Y_BUS_PATH,
                interface=_A11Y_BUS, member="GetAddress",
            )
        )
        address = reply.body[0]
        self._a11y = await MessageBus(bus_address=address).connect()

    async def call(self, dest, path, iface, member, signature="", body=None):
        from dbus_fast import Message

        await self._ensure_connected()
        reply = await self._a11y.call(
            Message(
                destination=dest, path=path, interface=iface, member=member,
                signature=signature, body=list(body) if body else [],
            )
        )
        return reply

    async def session_call(self, dest, path, iface, member, signature="", body=None):
        from dbus_fast import Message

        await self._ensure_connected()
        return await self._session.call(
            Message(
                destination=dest, path=path, interface=iface, member=member,
                signature=signature, body=list(body) if body else [],
            )
        )


def _is_error(reply) -> bool:
    from dbus_fast import MessageType

    return reply.message_type == MessageType.ERROR


class _DbusClient:
    """The AT-SPI ``_Client`` implemented over dbus-fast.

    Every read is one D-Bus round trip. A D-Bus error that means the object is
    gone (``UnknownObject``, ``ServiceUnknown``, ``UnknownMethod`` with the
    "Object does not exist" body observed on GTK) is raised as ElementGone; the
    backend maps that to element_gone, and no other error is silently swallowed.
    """

    _GONE_ERRORS = frozenset({
        "org.freedesktop.DBus.Error.ServiceUnknown",
        "org.freedesktop.DBus.Error.UnknownObject",
        "org.freedesktop.DBus.Error.UnknownMethod",
        "org.freedesktop.DBus.Error.NoReply",
    })

    def __init__(self, bus: _AtspiBus) -> None:
        self._bus = bus

    def _check(self, reply):
        if _is_error(reply):
            if reply.error_name in self._GONE_ERRORS:
                raise ElementGone(reply.error_name)
            raise StructuredError(
                NO_TREE, f"AT-SPI call failed: {reply.error_name}"
            )
        return reply

    def _call(self, node: Node, iface, member, signature="", body=None):
        bus_name, path = node
        reply = self._bus.run(
            self._bus.call(bus_name, path, iface, member, signature, body)
        )
        return self._check(reply)

    def _prop(self, node: Node, iface, name):
        bus_name, path = node
        reply = self._bus.run(
            self._bus.call(
                bus_name, path, _PROPERTIES, "Get", "ss", [iface, name]
            )
        )
        self._check(reply)
        return reply.body[0].value

    # -- probe -------------------------------------------------------------

    def reachable(self) -> bool:
        try:
            reply = self._bus.run(
                self._bus.session_call(
                    _A11Y_BUS, _A11Y_BUS_PATH, _A11Y_BUS, "GetAddress"
                )
            )
        except Exception:
            return False
        return not _is_error(reply)

    def is_enabled(self) -> bool:
        try:
            reply = self._bus.run(
                self._bus.session_call(
                    _A11Y_BUS, _A11Y_BUS_PATH, _PROPERTIES, "Get", "ss",
                    ["org.a11y.Status", "IsEnabled"],
                )
            )
            if _is_error(reply):
                return False
            return bool(reply.body[0].value)
        except Exception:
            return False

    # -- tree --------------------------------------------------------------

    def root(self) -> Node:
        return (_REGISTRY_BUS, _ROOT_PATH)

    def children(self, node: Node) -> list[Node]:
        reply = self._call(node, _ACCESSIBLE, "GetChildren")
        return [(bn, pp) for (bn, pp) in reply.body[0]]

    def role_name(self, node: Node) -> str:
        reply = self._call(node, _ACCESSIBLE, "GetRoleName")
        return reply.body[0]

    def name(self, node: Node) -> str:
        try:
            return self._prop(node, _ACCESSIBLE, "Name") or ""
        except ElementGone:
            raise
        except Exception:
            return ""

    def states(self, node: Node) -> tuple[str, ...]:
        reply = self._call(node, _ACCESSIBLE, "GetState")
        words = list(reply.body[0])
        low = words[0] if len(words) > 0 else 0
        high = words[1] if len(words) > 1 else 0
        return decode_states(low, high)

    def extents(self, node: Node) -> tuple[int, int, int, int] | None:
        reply = self._bus.run(
            self._bus.call(
                node[0], node[1], _COMPONENT, "GetExtents", "u", [_COORD_SCREEN]
            )
        )
        if _is_error(reply):
            if reply.error_name in self._GONE_ERRORS:
                raise ElementGone(reply.error_name)
            return None  # no Component interface: the element has no bounds
        x, y, w, h = reply.body[0]
        return (int(x), int(y), int(w), int(h))

    def interfaces(self, node: Node) -> tuple[str, ...]:
        reply = self._call(node, _ACCESSIBLE, "GetInterfaces")
        return tuple(reply.body[0])

    def actions(self, node: Node) -> list[str]:
        reply = self._bus.run(
            self._bus.call(node[0], node[1], _ACTION, "GetActions")
        )
        if _is_error(reply):
            if reply.error_name in self._GONE_ERRORS:
                raise ElementGone(reply.error_name)
            return []
        return [entry[0] for entry in reply.body[0]]

    def do_action(self, node: Node, index: int) -> bool:
        reply = self._call(node, _ACTION, "DoAction", "i", [index])
        return bool(reply.body[0])

    def set_text(self, node: Node, text: str) -> bool:
        reply = self._call(
            node, _EDITABLE_TEXT, "SetTextContents", "s", [text]
        )
        return bool(reply.body[0])

    def grab_focus(self, node: Node) -> bool:
        reply = self._bus.run(
            self._bus.call(node[0], node[1], _COMPONENT, "GrabFocus")
        )
        if _is_error(reply):
            return False
        return bool(reply.body[0])

    def pid(self, node: Node) -> int:
        # The app's OS pid, read from the a11y bus daemon by its connection name.
        # AT-SPI has no GetProcessId over D-Bus, but the app is a bus peer, so its
        # connection's unix pid is the app's pid.
        reply = self._bus.run(
            self._bus.call(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s",
                [node[0]],
            )
        )
        if _is_error(reply):
            return 0
        return int(reply.body[0])

    def toolkits(self) -> tuple[str, ...]:
        # Best effort: read each application's ToolkitName. A capability read
        # should never fail because one app misbehaves, so a bad app is skipped.
        seen: list[str] = []
        try:
            apps = self.children(self.root())
        except Exception:
            return ()
        for app in apps:
            try:
                toolkit = self._prop(app, _APPLICATION, "ToolkitName")
            except Exception:
                continue
            if toolkit and toolkit not in seen:
                seen.append(toolkit)
        return tuple(seen)


# ---------------------------------------------------------------------------
# Enablement: a layer distinct from reading the tree
# ---------------------------------------------------------------------------
#
# Enabling the accessibility bus and enabling each application's tree are two
# separate things. The bus is enabled once, per session, by setting
# org.a11y.Status.IsEnabled. A toolkit is enabled per launched process, by the
# environment or flags below, because an app cua starts inherits none of the
# desktop's own accessibility settings. GTK4 exposes its tree without any of
# this on a stock GNOME session; Qt and Chromium need to be told.
_QT_A11Y_ENV = ("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "1")
_CHROMIUM_A11Y_FLAGS = ("--force-renderer-accessibility",)


def accessibility_launch_env(base: dict | None = None) -> dict:
    """Environment for launching a Qt app so it exposes its accessible tree.

    Qt gates AT-SPI behind QT_LINUX_ACCESSIBILITY_ALWAYS_ON; a Qt app cua spawns
    without it is invisible to the structured tier however healthy the bus is.
    """
    env = dict(os.environ if base is None else base)
    env[_QT_A11Y_ENV[0]] = _QT_A11Y_ENV[1]
    return env


def chromium_accessibility_flags() -> list[str]:
    """Command-line flags that make Chromium and Electron expose their tree."""
    return list(_CHROMIUM_A11Y_FLAGS)


def bus_reachable(timeout: float = 2.0) -> bool:
    """Whether the accessibility bus answers, for the deps diagnosis.

    A one-shot probe that never raises and cleans up its loop thread: off Linux,
    or with no dbus-fast, or with no bus, it is simply False.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        import dbus_fast  # noqa: F401
    except Exception:
        return False
    probe = _AtspiBus(call_timeout=timeout)
    try:
        return _DbusClient(probe).reachable()
    except Exception:
        return False
    finally:
        probe.close()


def enable_bus(timeout: float = 2.0) -> bool:
    """Set org.a11y.Status.IsEnabled true. Returns whether the bus accepted it.

    One-shot and self-cleaning like bus_reachable. This is the bus half of
    enablement; the toolkit half is the env and flags above.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        import dbus_fast  # noqa: F401
        from dbus_fast.signature import Variant
    except Exception:
        return False
    probe = _AtspiBus(call_timeout=timeout)
    try:
        reply = probe.run(
            probe.session_call(
                _A11Y_BUS, _A11Y_BUS_PATH, _PROPERTIES, "Set", "ssv",
                ["org.a11y.Status", "IsEnabled", Variant("b", True)],
            )
        )
        return not _is_error(reply)
    except Exception:
        return False
    finally:
        probe.close()


def foreground_window():
    """The active window via AT-SPI, or None. Reuses the cached backend.

    The platform layer calls this on Wayland, where the compositor gives no
    global window geometry to the pixel path. It reuses resolve_backend's warm
    connections rather than opening a new bus per query (the foreground window is
    polled), and never raises: any failure is None, and the caller falls back.
    """
    from computer_use.tools.ui.backend import resolve_backend

    backend = resolve_backend()
    if backend is None:
        return None
    try:
        return backend.foreground_window()
    except Exception:
        return None


def build_atspi_backend() -> AtspiBackend | None:
    """Build the AT-SPI backend for this session, or None off Linux.

    Returns a backend on Linux whenever dbus-fast imports, even if the bus is
    not currently reachable: reachability is reported per call (and by the
    capability block), so a box whose bus comes up later is not stuck. Off Linux
    there is no AT-SPI, so there is no backend and the tools say so.
    """
    if not sys.platform.startswith("linux"):
        return None
    # Import here so a non-Linux import of this module never needs dbus-fast, and
    # a Linux box without it degrades through resolve_backend's own guard.
    import dbus_fast  # noqa: F401

    session = SessionContext.detect()
    return AtspiBackend(_DbusClient(_AtspiBus()), session)
