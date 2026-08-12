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
import os
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
from computer_use.tools.ui.cache import CacheSnapshot, build_snapshot

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

# The per-application Cache object, and the roles that are a top-level window.
# A frame (23) or window (69) is the app's own top-level; the active one carries
# the active state. Targeting a window by name is choosing one of these frames.
_CACHE = "org.a11y.atspi.Cache"
_CACHE_PATH = "/org/a11y/atspi/cache"
_FRAME_ROLE_ENUMS = frozenset({23, 69})
_FRAME_ROLE_NAMES = frozenset({"frame", "window", "dialog", "alert"})

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

# The largest extent, in pixels, that is ever a real widget. GTK reports
# uninitialised memory as the extents of an unrealised widget (observed: a hidden
# tab panel returning w=612489008 with a correct (iiii) signature), so a value
# past this is toolkit garbage, not a bound, and the element gets no bounds rather
# than a nonsense rectangle a caller might aim a pixel click at.
_MAX_EXTENT = 100000

# Anonymous structural containers GTK stacks between a window and its controls:
# on GTK4 a button can sit sixteen of these deep. They carry no information a
# caller acts on, so they are transparent to ui_tree's depth budget, which is
# what lets a shallow depth still reach the controls (a tree that stops at the
# wrappers is no substitute for a screenshot). A node with a name is never
# structural, whatever its role.
_STRUCTURAL_ROLES = frozenset({
    "filler", "generic", "section", "group", "box", "panel",
    "redundant object", "scroll pane", "viewport", "split pane",
    "layered pane", "tab panel",
})

# Roles whose text content is worth reading. Reading GetText on every node would
# make ui_tree pay a round trip per element for text almost none of them have, so
# only text-bearing roles are asked, and the read is what makes set_text
# confirmable.
_TEXT_ROLES = frozenset({
    "text", "entry", "password text", "text box", "paragraph", "heading",
    "label", "static", "document text", "terminal", "document web",
})

# After a state-changing action, the toolkit updates the element asynchronously:
# a GTK toggle reads its old state for tens of milliseconds after DoAction returns
# (observed: pressed still false immediately, true about 150 ms later). So for the
# verbs whose whole point is the element's own new state, the re-read is a bounded
# poll that returns the moment an observable field changes. A plain click is
# different: its effect is almost always elsewhere (a digit lands in a display, a
# dialog opens), so waiting for the clicked button's own state to change is a pure
# penalty, and click re-reads once instead. The window is short: 150 ms was the
# observed lag, so 400 ms is margin, not a stall.
_ACT_SETTLE_SECONDS = 0.4
_ACT_SETTLE_POLL = 0.03

# Verbs whose signal is the element's own field, so the re-read settles. A plain
# click is deliberately absent: it re-reads once and lets the caller observe the
# effect where it actually lands.
_SETTLE_VERBS = frozenset({"toggle", "expand", "focus", "set_text"})


def _sane_extents(ext: tuple[int, int, int, int] | None):
    """Drop implausible extents (toolkit garbage) so bounds are trustworthy."""
    if ext is None:
        return None
    x, y, w, h = ext
    if w < 0 or h < 0 or w > _MAX_EXTENT or h > _MAX_EXTENT:
        return None
    if abs(x) > _MAX_EXTENT or abs(y) > _MAX_EXTENT:
        return None
    return ext


def _is_meaningful(role: str, name: str) -> bool:
    """Whether a node counts against ui_tree's depth (a named or non-structural node)."""
    if name:
        return True
    return role not in _STRUCTURAL_ROLES


def _role_reads_text(role: str) -> bool:
    return role in _TEXT_ROLES or role.endswith("text")


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
    def warm_caches(self, bus_names: list[str]) -> None: ...
    def invalidate(self, node: Node) -> None: ...
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
    def text(self, node: Node) -> str | None: ...


# The verbs ui_act accepts, mapped to how each is performed. click/toggle/expand
# resolve to an Action by name; focus is a Component grab; set_text is an
# EditableText write. toggle and expand are click-like actions whose value is in
# the re-read, which the backend does for every verb.
_ACTION_VERBS = {
    "click": ("click",),
    "toggle": ("toggle", "click"),
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

    def _apps(self) -> list[Node]:
        try:
            return self._client.children(self._client.root())
        except ElementGone:
            return []

    def _frames_of(self, app: Node) -> list[Node]:
        """The app's top-level windows (its frame children), robust to junk."""
        frames = []
        try:
            children = self._client.children(app)
        except ElementGone:
            return frames
        for child in children:
            try:
                if self._client.role_name(child).lower() in _FRAME_ROLE_NAMES:
                    frames.append(child)
            except ElementGone:
                continue
        return frames

    def _active_window(self) -> Node:
        """Find the active top-level window across all applications.

        The tree is desktop -> applications -> windows; the focused one carries
        the ``active`` state. No active window is a real, nameable condition
        (nothing focused, or a toolkit that exposes none), so it is no_tree
        rather than an empty success.
        """
        for app in self._apps():
            for window in self._frames_of(app):
                try:
                    if "active" in self._client.states(window):
                        return window
                except ElementGone:
                    continue
        raise StructuredError(NO_TREE, "no active window exposes a tree")

    def _resolve_frames(self, app: str) -> list[Node]:
        """The frames a read targets, and warm their caches before the walk.

        ``app=""`` is the active window (unchanged default). ``app="*"`` is every
        open window. Otherwise it is the windows of the applications whose name
        matches, and a name that matches nothing is ``no_tree`` (naming it), not
        an empty success that reads as "found nothing on screen".
        """
        if app == "":
            frames = [self._active_window()]
        elif app == "*":
            frames = [f for a in self._apps() for f in self._frames_of(a)]
        else:
            frames = []
            for a in self._apps():
                try:
                    if app.lower() in self._client.name(a).lower():
                        frames.extend(self._frames_of(a))
                except ElementGone:
                    continue
            if not frames:
                raise StructuredError(NO_TREE, f"no open window for app {app!r}")
        self._client.warm_caches([f[0] for f in frames])
        return frames

    # -- reading -----------------------------------------------------------

    def _element(self, node: Node) -> Element:
        role = self._client.role_name(node)
        extents = _sane_extents(self._client.extents(node))
        bounds = Bounds(*extents) if extents is not None else None
        # Text is only asked of text-bearing roles: it is what makes set_text
        # confirmable, and reading it from every button would be a round trip per
        # node for a field they do not have.
        text = self._client.text(node) if _role_reads_text(role) else None
        return Element(
            ref=self._ref_for(node),
            role=role,
            name=self._client.name(node),
            bounds=bounds,
            states=self._client.states(node),
            text=text,
        )

    def _node_dict(self, node: Node, depth: int, budget: list[int]) -> dict:
        """A tree node as a plain dict, with only its meaningful descendants.

        The anonymous wrappers GTK stacks between a window and its controls carry
        nothing a caller acts on and would bloat the tree past the point of being
        small text (a real file manager returned a quarter of a megabyte before
        this). They are collapsed out: their meaningful descendants are hoisted to
        the same level, so the output is the window and its actual controls.
        ``depth`` counts meaningful nodes only, and non-showing subtrees are
        pruned so an off-screen dialog never surfaces.
        """
        out = self._element(node).as_dict()
        out["children"] = self._collapsed_children(node, depth, budget)
        return out

    def _collapsed_children(
        self, node: Node, depth: int, budget: list[int]
    ) -> list[dict]:
        """Meaningful children of ``node``, hoisting through anonymous wrappers."""
        result: list[dict] = []
        try:
            kids = self._client.children(node)
        except ElementGone:
            return result
        for child in kids:
            if budget[0] <= 0:
                break
            try:
                if "showing" not in self._client.states(child):
                    continue  # off-screen: do not surface it or its subtree
                crole = self._client.role_name(child)
                cname = self._client.name(child)
            except ElementGone:
                continue
            if _is_meaningful(crole, cname):
                if depth <= 0:
                    continue  # a meaningful node past the depth cap
                budget[0] -= 1
                try:
                    result.append(self._node_dict(child, depth - 1, budget))
                except ElementGone:
                    continue
            else:
                # A structural wrapper: emit nothing for it, hoist its meaningful
                # descendants at this same depth.
                result.extend(self._collapsed_children(child, depth, budget))
        return result

    def tree(self, depth: int, app: str = "") -> dict:
        self._require_bus()
        frames = self._resolve_frames(app)

        def one(frame: Node) -> dict:
            budget = [_MAX_NODES]
            return self._node_dict(frame, max(depth, 0), budget)

        try:
            if len(frames) == 1:
                # The default and the by-name single-window case: unchanged shape.
                return {"root": one(frames[0]), "depth": depth}
            return {
                "roots": [one(f) for f in frames],
                "count": len(frames),
                "depth": depth,
            }
        except ElementGone:
            raise StructuredError(NO_TREE, "the target window's tree went away")

    def _matches(self, node: Node, role: str, name: str) -> bool:
        # role is an exact (case-insensitive) role-name match; name is a
        # case-insensitive substring so "Save" finds "Save As" too. An empty
        # argument matches anything, so find(role=...) and find(name=...) both
        # work without a sentinel.
        if role and self._client.role_name(node).lower() != role.lower():
            return False
        return not (name and name.lower() not in self._client.name(node).lower())

    def _search_frame(self, frame: Node, role: str, name: str) -> list[Element]:
        found: list[Element] = []
        # (node, is_root): the root is always walked; every other node is skipped,
        # subtree and all, when it is not showing, so an off-screen dialog's
        # controls never surface as matches (they are the phantoms a screenshot
        # would never show either).
        stack: list[tuple[Node, bool]] = [(frame, True)]
        visited = 0
        while stack and visited < _MAX_NODES:
            node, is_root = stack.pop()
            visited += 1
            try:
                showing = "showing" in self._client.states(node)
                if not is_root and not showing:
                    continue
                if showing and self._matches(node, role, name):
                    found.append(self._element(node))
                children = self._client.children(node)
            except ElementGone:
                continue
            for child in reversed(children):
                stack.append((child, False))
        return found

    def find(self, role: str, name: str, app: str = "") -> list[Element]:
        self._require_bus()
        found: list[Element] = []
        for frame in self._resolve_frames(app):
            found.extend(self._search_frame(frame, role, name))
        return found

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

    def _snapshot(self, node: Node) -> tuple[frozenset, str | None]:
        """The observable fields an action might change, for the settle-poll."""
        role = self._client.role_name(node)
        text = self._client.text(node) if _role_reads_text(role) else None
        return (frozenset(self._client.states(node)), text)

    def _observable(self, node: Node) -> tuple[frozenset, str | None]:
        """Just the fields the settle-poll compares, kept cheap for a tight loop."""
        role = self._client.role_name(node)
        text = self._client.text(node) if _role_reads_text(role) else None
        return (frozenset(self._client.states(node)), text)

    def _reread_after_act(self, node: Node, before: tuple) -> Element:
        """Re-read the element, waiting out the toolkit's async state update.

        Polls only the cheap observable fields (states, and text where it
        applies) so the loop is a couple of round trips per iteration, and
        returns a full read the moment they differ from ``before`` (the common
        case: a toggle flips, a field's text changes, focus lands). If nothing
        changes within the short window, the last read is returned rather than
        stalling.
        """
        deadline = time.monotonic() + _ACT_SETTLE_SECONDS
        while self._observable(node) == before and time.monotonic() < deadline:
            time.sleep(_ACT_SETTLE_POLL)
        return self._element(node)

    def act(self, ref: str, action: str, text: str) -> dict:
        self._require_bus()
        node = self._node_for(ref)
        # Acting is the one operation whose whole value is the element's state
        # around the action, and the warm cache is a snapshot from find-time: a
        # settle poll served from it can never observe the change and returns the
        # pre-action state as if it were the confirmation. Drop this app's
        # snapshot first so the pre-action snapshot, the settle polls and the
        # final re-read are all live reads.
        self._client.invalidate(node)
        # Confirm the ref still resolves before doing anything, and capture the
        # pre-action snapshot: a stale node is element_gone, never a click on a
        # remembered coordinate, and the snapshot is what the re-read compares
        # against so the returned state is the element after acting, not before.
        try:
            before = self._snapshot(node)
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
        # State-changing verbs wait out the toolkit's async update; a plain click
        # re-reads once, because its effect lands elsewhere and polling the
        # button's own state would only stall.
        try:
            if verb in _SETTLE_VERBS:
                state = self._reread_after_act(node, before).as_dict()
            else:
                state = self._element(node).as_dict()
        except ElementGone:
            raise StructuredError(ELEMENT_GONE, "element gone after acting")
        return {"action": verb, "state": state}

    # -- waiting -----------------------------------------------------------

    def wait(
        self, role: str, name: str, timeout_ms: int, app: str = ""
    ) -> Element | None:
        self._require_bus()
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
        while True:
            matches = self.find(role, name, app)
            if matches:
                return matches[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(_WAIT_POLL_SECONDS)

    # -- listing open windows ----------------------------------------------

    def windows(self) -> dict:
        """Every open top-level window across all apps, for the model to target."""
        self._require_bus()
        out = []
        for app in self._apps():
            try:
                app_name = self._client.name(app)
            except ElementGone:
                continue
            for frame in self._frames_of(app):
                try:
                    states = self._client.states(frame)
                    out.append({
                        "app_name": app_name,
                        "title": self._client.name(frame),
                        "active": "active" in states,
                        "ref": self._ref_for(frame),
                    })
                except ElementGone:
                    continue
        return {"windows": out}

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

    async def _gather(self, calls):
        from dbus_fast import Message

        await self._ensure_connected()
        coros = [
            self._a11y.call(Message(
                destination=d, path=p, interface=i, member=m,
                signature=s or "", body=list(b) if b else [],
            ))
            for (d, p, i, m, s, b) in calls
        ]
        return await asyncio.gather(*coros, return_exceptions=True)

    def gather(self, calls):
        """Run several method calls concurrently on the one owning loop.

        The bulk read fans out one GetItems per app at once, so N windows cost one
        round trip's wall time, not N.
        """
        return self.run(self._gather(calls))


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
        # A warm snapshot per application bus name, and the role-enum-to-name map
        # calibrated against GetRoleName so a cached role name is identical to a
        # walked one. Both persist for the process: the cache is kept and the
        # calibration only grows.
        self._cache: dict[str, CacheSnapshot] = {}
        self._role_names: dict[int, str] = {}

    def warm_caches(self, bus_names: list[str]) -> None:
        """Bulk-read each app's exported tree with one concurrent GetItems each.

        An app that does not export Cache (the reply errors) is simply left out of
        the warm set, so its reads stay live: the fast path degrades to the walk
        rather than failing.
        """
        unique = [b for b in dict.fromkeys(bus_names) if b]
        if not unique:
            return
        calls = [(b, _CACHE_PATH, _CACHE, "GetItems", "", None) for b in unique]
        replies = self._bus.gather(calls)
        for bus_name, reply in zip(unique, replies):
            if isinstance(reply, Exception) or _is_error(reply):
                self._cache.pop(bus_name, None)
                continue
            snapshot = build_snapshot(reply.body[0], decode_states)
            self._cache[bus_name] = snapshot
            self._calibrate(snapshot)

    def invalidate(self, node: Node) -> None:
        """Drop one app's snapshot so its next reads are live.

        Called before acting: the snapshot is find-time state, and an act's
        re-read served from it would return the pre-action value forever. The
        next find warms the cache again, so the fast path is only ever skipped
        for the reads that must observe a change.
        """
        self._cache.pop(node[0], None)

    def _calibrate(self, snapshot: CacheSnapshot) -> None:
        # Resolve every role enum in the snapshot to the name GetRoleName gives, so
        # the walk that follows needs no live role reads. One call per new enum,
        # about ten the first time and none after.
        for role_enum in snapshot.role_enums():
            if role_enum in self._role_names:
                continue
            node = snapshot.node_with_role(role_enum)
            if node is None:
                continue
            reply = self._bus.run(
                self._bus.call(node[0], node[1], _ACCESSIBLE, "GetRoleName")
            )
            if not _is_error(reply):
                self._role_names[role_enum] = reply.body[0]

    def _cached(self, node: Node) -> CacheSnapshot | None:
        snapshot = self._cache.get(node[0])
        if snapshot is not None and snapshot.has(node):
            return snapshot
        return None

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
        # Serve from the warm cache only when it holds every child the node
        # declares; an incomplete branch falls to a live read, which also warms
        # the cache for next time, so no child is ever missed.
        snapshot = self._cache.get(node[0])
        if snapshot is not None and snapshot.is_complete(node):
            return snapshot.children(node)
        reply = self._call(node, _ACCESSIBLE, "GetChildren")
        return [(bn, pp) for (bn, pp) in reply.body[0]]

    def role_name(self, node: Node) -> str:
        snapshot = self._cached(node)
        if snapshot is not None:
            name = self._role_names.get(snapshot.item(node).role_enum)
            if name is not None:
                return name
        reply = self._call(node, _ACCESSIBLE, "GetRoleName")
        return reply.body[0]

    def name(self, node: Node) -> str:
        snapshot = self._cached(node)
        if snapshot is not None:
            return snapshot.item(node).name or ""
        try:
            return self._prop(node, _ACCESSIBLE, "Name") or ""
        except ElementGone:
            raise
        except Exception:
            return ""

    def states(self, node: Node) -> tuple[str, ...]:
        snapshot = self._cached(node)
        if snapshot is not None:
            return snapshot.item(node).states
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
        snapshot = self._cached(node)
        if snapshot is not None:
            return snapshot.item(node).interfaces
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

    def text(self, node: Node) -> str | None:
        # org.a11y.atspi.Text.GetText(start, end); end is capped rather than -1 so
        # reading a large document's text box stays bounded. An element without
        # the Text interface returns an error, which is simply "no text".
        reply = self._bus.run(
            self._bus.call(
                node[0], node[1], "org.a11y.atspi.Text", "GetText", "ii",
                [0, 5000],
            )
        )
        if _is_error(reply):
            if reply.error_name in self._GONE_ERRORS:
                raise ElementGone(reply.error_name)
            return None
        return reply.body[0]

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
