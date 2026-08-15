# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The four structured-tier tools, thin over the resolved backend.

Four tools, not one multiplexed verb: ui_act mutates user state (Risk.MEDIUM) and
the other three only read (Risk.READ_ONLY). A single tool would carry one risk for
both, and the loop's approval reads that field, so multiplexing would either gate
reads behind approval or let writes through without it.
"""

from __future__ import annotations

from computer_use.tools.ui.backend import (
    AT_SPI_UNAVAILABLE,
    TIMEOUT,
    UNAVAILABLE_REMEDY,
    StructuredError,
    resolve_backend,
)


def _unavailable() -> dict:
    return {"ok": False, "error": AT_SPI_UNAVAILABLE, "remedy": UNAVAILABLE_REMEDY}


def ui_tree(depth: int = 6, app: str = "") -> dict:
    """Read an accessible tree, filtered and depth-capped.

    ``app=""`` reads the focused window (unchanged). ``app="Name"`` reads that
    application's window; ``app="*"`` reads every open window.
    """
    backend = resolve_backend()
    if backend is None:
        return _unavailable()
    try:
        return {"ok": True, **backend.tree(depth, app)}
    except StructuredError as e:
        return e.as_dict()


def ui_find(role: str = "", name: str = "", app: str = "") -> dict:
    """Find elements matching role, name, or both. An empty match is ``ok``.

    ``app=""`` searches the focused window (unchanged). ``app="Name"`` searches
    that application's window; ``app="*"`` searches every open window.
    """
    backend = resolve_backend()
    if backend is None:
        return _unavailable()
    try:
        elements = backend.find(role, name, app)
        return {"ok": True, "elements": [e.as_dict() for e in elements]}
    except StructuredError as e:
        return e.as_dict()


def ui_windows() -> dict:
    """List open top-level windows across all apps: app, title, active, ref, pid."""
    backend = resolve_backend()
    if backend is None:
        return _unavailable()
    try:
        return {"ok": True, **backend.windows()}
    except StructuredError as e:
        return e.as_dict()


def ui_act(ref: str, action: str, text: str = "") -> dict:
    """Perform an action on a ref, then re-read and return the element's state.

    The re-read is the point: a structured action that returns ``ok`` without
    observing the result is a pixel click with better manners. A stale ref fails
    ``element_gone``; it never falls back to the element's old coordinates.
    """
    backend = resolve_backend()
    if backend is None:
        return _unavailable()
    try:
        return {"ok": True, **backend.act(ref, action, text)}
    except StructuredError as e:
        return e.as_dict()


def ui_wait(
    role: str = "", name: str = "", timeout_ms: int = 5000, app: str = ""
) -> dict:
    """Block until a matching element appears or the timeout elapses (bounded).

    ``app`` scopes the wait the same way ``ui_find`` does: the focused window by
    default, a named application's window, or ``"*"`` for every open window.
    """
    backend = resolve_backend()
    if backend is None:
        return _unavailable()
    try:
        element = backend.wait(role, name, timeout_ms, app)
        if element is None:
            return {"ok": False, "error": TIMEOUT, "elapsed_ms": timeout_ms}
        return {"ok": True, "element": element.as_dict()}
    except StructuredError as e:
        return e.as_dict()
