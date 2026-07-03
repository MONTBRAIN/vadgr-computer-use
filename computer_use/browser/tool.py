# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The ``browser`` + ``browser_eval`` MCP tools — thin clients over the bridge.

``browser`` is op-routed through ``OperationGroup`` (like the Tier-0 ``fs`` /
``clipboard`` tools): each op is a small handler that shapes params and calls
``bridge.send``. Adding an op is a new handler + registration, never a
dispatcher edit.

A ``BrowserError`` from the bridge is mapped to a ``ToolError`` whose message
carries the page reason / remediation and the guided pixel fallback — FastMCP
forwards ``ToolError`` text to the LLM verbatim (generic exceptions get
masked), so the guidance actually reaches the model.
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from computer_use.browser.bridge import (
    PIXEL_FALLBACK,
    BrowserBridge,
    NativeMessagingBridge,
)
from computer_use.browser.protocol import BrowserError
from computer_use.browser.upload import translate_upload_paths
from computer_use.core.ops import OperationGroup

# `screenshot` is a PIXEL tool, not a browser op — the agent mis-tried
# `browser(op="screenshot")`. Redirect it explicitly (browser-native capture is
# a later MINOR).
_SCREENSHOT_HINT = (
    "`screenshot` is not a `browser` op — it is a separate pixel tool. Call the "
    "top-level `screenshot` tool to see the page; browser-native capture is not "
    "available yet."
)


def _upload_platform() -> str:
    """The browser process's OS for `upload` path translation.

    WSL drives *Windows* Chrome, so paths must be rewritten to Windows form even
    though ``sys.platform`` reports ``linux`` in WSL.
    """
    try:
        from computer_use.core.types import Platform
        from computer_use.platform.detect import detect_platform

        return "wsl" if detect_platform() == Platform.WSL2 else sys.platform
    except Exception:  # pragma: no cover - detection best-effort
        return sys.platform

# One default bridge instance, shared by the MCP wrappers. Tests inject a
# FakeBridge explicitly.
_DEFAULT_BRIDGE: BrowserBridge | None = None


def _default_bridge() -> BrowserBridge:
    global _DEFAULT_BRIDGE
    if _DEFAULT_BRIDGE is None:
        _DEFAULT_BRIDGE = NativeMessagingBridge()
    return _DEFAULT_BRIDGE


_ops = OperationGroup("browser")


# --- navigation ---

@_ops.operation("navigate")
def _navigate(bridge: BrowserBridge, url: str, wait: str = "load") -> Any:
    return bridge.send("navigate", url=url, wait=wait)


@_ops.operation("back")
def _back(bridge: BrowserBridge) -> Any:
    return bridge.send("back")


@_ops.operation("forward")
def _forward(bridge: BrowserBridge) -> Any:
    return bridge.send("forward")


@_ops.operation("reload")
def _reload(bridge: BrowserBridge) -> Any:
    return bridge.send("reload")


# --- read ---

@_ops.operation("wait_for")
def _wait_for(
    bridge: BrowserBridge,
    selector: str,
    state: str = "visible",
    timeout: int = 5000,
) -> Any:
    return bridge.send("wait_for", selector=selector, state=state, timeout=timeout)


@_ops.operation("query")
def _query(
    bridge: BrowserBridge,
    selector: str,
    by: str = "css",
    all: bool = False,
    limit: int = 50,
    cursor: int | None = None,
) -> Any:
    # `limit`/`cursor` cap + paginate large match sets so a big page degrades to
    # pages, never a token-budget blowout. Returns {nodes, next_cursor?}.
    return bridge.send(
        "query", selector=selector, by=by, all=all, limit=limit, cursor=cursor
    )


@_ops.operation("read_text")
def _read_text(bridge: BrowserBridge, selector: str | None = None) -> Any:
    return bridge.send("read_text", selector=selector)


@_ops.operation("get_attribute")
def _get_attribute(bridge: BrowserBridge, selector: str, name: str) -> Any:
    return bridge.send("get_attribute", selector=selector, name=name)


# --- act ---

@_ops.operation("click")
def _click(bridge: BrowserBridge, selector: str, by: str = "css",
           force: bool = False) -> Any:
    return bridge.send("click", selector=selector, by=by, force=force)


@_ops.operation("type")
def _type(
    bridge: BrowserBridge,
    selector: str,
    text: str,
    clear: bool = True,
    submit: bool = False,
    force: bool = False,
) -> Any:
    return bridge.send("type", selector=selector, text=text, clear=clear,
                       submit=submit, force=force)


@_ops.operation("fill")
def _fill(
    bridge: BrowserBridge,
    selector: str,
    text: str,
    clear: bool = True,
    submit: bool = False,
    force: bool = False,
) -> Any:
    return bridge.send("fill", selector=selector, text=text, clear=clear,
                       submit=submit, force=force)


@_ops.operation("select")
def _select(bridge: BrowserBridge, selector: str, value: str,
            force: bool = False) -> Any:
    return bridge.send("select", selector=selector, value=value, force=force)


@_ops.operation("scroll")
def _scroll(
    bridge: BrowserBridge,
    selector: str | None = None,
    by: dict | None = None,
) -> Any:
    return bridge.send("scroll", selector=selector, by=by)


# --- CDP universal path (chrome.debugger) ---

@_ops.operation("press")
def _press(bridge: BrowserBridge, key: str, selector: str | None = None) -> Any:
    # A *trusted* key event (via chrome.debugger Input) — for chords / keys that
    # DOM-dispatched events can't trip (Enter on a custom widget, isTrusted-gated).
    return bridge.send("press", key=key, selector=selector)


@_ops.operation("accessibility_tree")
def _accessibility_tree(bridge: BrowserBridge) -> Any:
    # The browser's own semantic model — every control normalized to role/name/
    # value regardless of HTML/framework (via chrome.debugger Accessibility).
    # Deprecated in favor of `snapshot` (paginated + shadow/frame piercing).
    return bridge.send("accessibility_tree")


# --- 0.5.0: session targeting ---

@_ops.operation("use_target")
def _use_target(
    bridge: BrowserBridge,
    window_id: int | None = None,
    tab_id: int | None = None,
    mode: str = "owned",
) -> Any:
    # Explicitly pin the session target. Default owned mode opens a dedicated
    # window; attach mode snapshots the current active tab once; ids select an
    # existing window/tab. Every later op targets it BY ID (focus-proof).
    return bridge.send("use_target", window_id=window_id, tab_id=tab_id, mode=mode)


# --- 0.5.0: the remaining interaction ops (CDP path) ---

@_ops.operation("hover")
def _hover(
    bridge: BrowserBridge,
    selector: str,
    by: str = "css",
    reveals: str | None = None,
) -> Any:
    return bridge.send("hover", selector=selector, by=by, reveals=reveals)


@_ops.operation("dialog")
def _dialog(
    bridge: BrowserBridge,
    action: str = "accept",
    text: str | None = None,
    arm: bool = True,
) -> Any:
    # Arm a one-shot JS-dialog handler BEFORE the op that triggers it — a JS
    # dialog pauses the renderer synchronously, so there is no post-hoc catch.
    return bridge.send("dialog", action=action, text=text, arm=arm)


@_ops.operation("upload")
def _upload(bridge: BrowserBridge, selector: str, files: list[str]) -> Any:
    # Rewrite each path to a Chrome-OS path BEFORE it crosses the wire — on WSL
    # Chrome is Windows Chrome and cannot read a cua-side WSL path. Native Chrome
    # shares cua's filesystem, so paths pass through unchanged.
    chrome_files = translate_upload_paths(files, platform=_upload_platform())
    return bridge.send("upload", selector=selector, files=chrome_files)


@_ops.operation("element_state")
def _element_state(bridge: BrowserBridge, selector: str, by: str = "css") -> Any:
    # The explicit actionability read (visible / receives_events / enabled /
    # focused / editable / checked? / value? / bbox) — check before acting.
    return bridge.send("element_state", selector=selector, by=by)


@_ops.operation("focus")
def _focus(bridge: BrowserBridge, selector: str) -> Any:
    return bridge.send("focus", selector=selector)


@_ops.operation("blur")
def _blur(bridge: BrowserBridge, selector: str) -> Any:
    return bridge.send("blur", selector=selector)


@_ops.operation("clear")
def _clear(bridge: BrowserBridge, selector: str, force: bool = False) -> Any:
    return bridge.send("clear", selector=selector, force=force)


@_ops.operation("get_value")
def _get_value(bridge: BrowserBridge, selector: str, by: str = "css") -> Any:
    return bridge.send("get_value", selector=selector, by=by)


@_ops.operation("snapshot")
def _snapshot(
    bridge: BrowserBridge,
    selector: str | None = None,
    roles: list[str] | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> Any:
    # The paginated, shadow-/frame-piercing AX snapshot (supersedes
    # accessibility_tree). Returns {nodes:[{role,name,state,value,ref}], next_cursor?}.
    return bridge.send(
        "snapshot", selector=selector, roles=roles, cursor=cursor, limit=limit
    )


@_ops.operation("cookies")
def _cookies(
    bridge: BrowserBridge,
    action: str = "get",
    url: str | None = None,
    name: str | None = None,
    value: str | None = None,
) -> Any:
    return bridge.send("cookies", action=action, url=url, name=name, value=value)


@_ops.operation("status")
def _status(bridge: BrowserBridge) -> Any:
    # Pre-flight: never touches a page, just reports bridge availability.
    return bridge.status().as_dict()


def _raise_tool_error(err: BrowserError) -> None:
    """Map a BrowserError to a ToolError whose text reaches the LLM."""
    parts = [f"[{err.code.value}] {err.message}"]
    if err.remediation:
        parts.append(f"To fix: {err.remediation}.")
    parts.append(err.fallback or PIXEL_FALLBACK)
    raise ToolError(" ".join(parts)) from err


def browser(op: str, bridge: BrowserBridge | None = None, **params) -> Any:
    """Dispatch a browser sub-operation through the active bridge."""
    if op == "screenshot":
        # A common agent mistake — redirect to the pixel tool with clear guidance.
        raise ToolError(_SCREENSHOT_HINT)
    b = bridge if bridge is not None else _default_bridge()
    try:
        return _ops.run(op, bridge=b, **params)
    except BrowserError as err:
        _raise_tool_error(err)
    except ValueError as err:
        # Unknown op (OperationGroup) -> a clean ToolError, not a masked crash.
        raise ToolError(str(err)) from err


def browser_eval(expression: str, bridge: BrowserBridge | None = None) -> Any:
    """Run arbitrary JS in the page (HIGH risk). Separate from ``browser``."""
    b = bridge if bridge is not None else _default_bridge()
    try:
        return b.send("eval", expression=expression)
    except BrowserError as err:
        _raise_tool_error(err)
