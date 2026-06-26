"""MCP server for the computer use engine.

Run: python -m computer_use.mcp_server [--transport stdio|sse] [--max-width 1366]
"""

import argparse
import io
import logging
import os
import sys
from typing import Optional

_DEBUG = os.environ.get("VADGR_DEBUG", "") == "1"

logging.basicConfig(
    level=logging.DEBUG if _DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("computer_use.mcp_server")
_DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".debug")
_debug_counter = 0


def _debug_save(data: bytes, prefix: str = "screenshot") -> None:
    """Save PNG to .debug/ when VADGR_DEBUG=1."""
    if not _DEBUG:
        return
    global _debug_counter
    os.makedirs(_DEBUG_DIR, exist_ok=True)
    _debug_counter += 1
    path = os.path.join(_DEBUG_DIR, f"{prefix}_{_debug_counter:04d}.png")
    with open(path, "wb") as f:
        f.write(data)
    logger.info("Debug screenshot saved: %s", path)

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

from computer_use.core import REGISTRY, Risk, Tier, tool

mcp = FastMCP(
    name="computer-use",
    instructions=(
        "Desktop automation engine. Use screenshot() to see the screen, "
        "then click/type/scroll to interact with UI elements.\n\n"
        "CRITICAL RULES:\n"
        "1. ALWAYS take a screenshot BEFORE clicking or typing to verify "
        "the target is where you expect it to be.\n"
        "2. ALWAYS take a screenshot AFTER clicking to confirm the action "
        "had the intended effect (correct window opened, right element selected, etc.).\n"
        "3. NEVER click based on assumed coordinates from memory -- always "
        "use the latest screenshot to identify precise coordinates.\n"
        "4. When clicking on a list item, aim for the CENTER of the item's text, "
        "not near its edge, to avoid hitting adjacent items.\n"
        "5. If a click lands on the wrong target, take a screenshot, reassess "
        "coordinates, and retry.\n"
        "6. Screenshots are point-in-time. Don't rely on older screenshots from "
        "earlier turns -- the UI may have changed. Take a fresh one when needed.\n"
        "7. The `browser` tool (Tier 1, MV3 extension) verifies differently: the "
        "DOM is the ground truth, so after ANY mutating browser op "
        "(click/type/fill/select) CONFIRM the effect with a structured read-back "
        "-- the op's returned `ok`/`checked`, or get_attribute/read_text/query/"
        "wait_for -- not a screenshot (web state changes too fast to screenshot "
        "reliably). Never continue on an unverified browser action."
    ),
)

_MAX_WIDTH = int(os.environ.get("CU_MAX_WIDTH", "0"))  # 0 = auto-detect

# Hard ceiling: stay under Anthropic's 2000px per-image dimension cap that
# trips many-image requests (see anthropics/claude-code#37461, #46656).
_MAX_DIMENSION_CEILING = 1600

# Thumbnail mode: aggressive shrink for sanity-check screenshots in long flows.
_THUMBNAIL_WIDTH = 640
_JPEG_QUALITY = 70
_THUMBNAIL_QUALITY = 40

# Coordinate mapping state. Updated after each screenshot.
# Display coords (what the agent sees) get mapped to real screen coords via _to_real().
_scale_x = 1.0
_scale_y = 1.0
_display_w = 0
_display_h = 0
_offset_x = 0  # primary monitor X origin in virtual screen space
_offset_y = 0  # primary monitor Y origin in virtual screen space

_engine = None


def _compute_max_width(real_width: int) -> int:
    """Pick the largest target width that keeps coordinates accurate for vision models.

    Returns the highest standard resolution that is <= the real screen width.
    Standard targets (most universal across vision models): 1024, 1280, 1366.
    """
    targets = [1024, 1280, 1366]
    for t in reversed(targets):
        if real_width >= t:
            return t
    return real_width  # screen is smaller than 1024, no downscale


def _get_engine():
    global _engine, _MAX_WIDTH
    if _engine is None:
        from computer_use.core.engine import ComputerUseEngine
        _engine = ComputerUseEngine()
        logger.info("Engine initialized (platform=%s)", _engine.get_platform().value)
        if _MAX_WIDTH == 0:
            w, _ = _engine.get_screen_size()
            _MAX_WIDTH = _compute_max_width(w)
            logger.info("Auto-detected max width: %d (screen=%d)", _MAX_WIDTH, w)
    return _engine


def _resolve_format(fmt: str) -> str:
    """Normalize the user-facing format string. Raises ValueError on unknown."""
    f = (fmt or "jpeg").lower()
    if f == "jpg":
        f = "jpeg"
    if f not in ("jpeg", "png", "thumbnail"):
        raise ValueError(
            f"Unsupported format: {fmt!r}. Use 'jpeg' (default), 'png', or 'thumbnail'."
        )
    return f


def _encode_image(img: "PILImage.Image", fmt: str) -> tuple[bytes, str]:
    """Encode a PIL image to bytes in the given format.

    Returns (bytes, image_format) where image_format is what FastMCP's
    Image() constructor expects ("jpeg" or "png").
    """
    buf = io.BytesIO()
    if fmt == "png":
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png"
    # jpeg or thumbnail
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    quality = _THUMBNAIL_QUALITY if fmt == "thumbnail" else _JPEG_QUALITY
    rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), "jpeg"


def _downscale(
    png_bytes: bytes,
    offset_x: int = 0,
    offset_y: int = 0,
    fmt: str = "jpeg",
) -> tuple[bytes, str]:
    """Resize screenshot, encode in requested format, update scale/offset state.

    Width is determined by:
    - thumbnail format: min(_THUMBNAIL_WIDTH, real_w)
    - other formats:    min(_MAX_WIDTH-or-real_w, _MAX_DIMENSION_CEILING)

    The dimension ceiling is a hard safety cap to stay below Anthropic's
    2000px per-image limit even if a caller passes _MAX_WIDTH > 2000.

    Returns (image_bytes, image_format) where image_format is "jpeg" or "png".
    """
    global _scale_x, _scale_y, _display_w, _display_h, _offset_x, _offset_y

    _offset_x = offset_x
    _offset_y = offset_y

    img = PILImage.open(io.BytesIO(png_bytes))
    real_w, real_h = img.size

    if fmt == "thumbnail":
        target_w = min(_THUMBNAIL_WIDTH, real_w)
    else:
        configured = _MAX_WIDTH if _MAX_WIDTH > 0 else real_w
        target_w = min(configured, _MAX_DIMENSION_CEILING, real_w)

    if target_w >= real_w:
        _scale_x, _scale_y = 1.0, 1.0
        _display_w, _display_h = real_w, real_h
        data, image_format = _encode_image(img, fmt)
        logger.debug(
            "No resize (%dx%d), encoded as %s, %d bytes",
            real_w, real_h, fmt, len(data),
        )
        return data, image_format

    ratio = target_w / real_w
    new_w = target_w
    new_h = int(real_h * ratio)

    _scale_x = real_w / new_w
    _scale_y = real_h / new_h
    _display_w, _display_h = new_w, new_h

    img = img.resize((new_w, new_h), PILImage.LANCZOS)
    data, image_format = _encode_image(img, fmt)
    logger.debug(
        "Resized %dx%d -> %dx%d (scale %.2fx) as %s, %d bytes",
        real_w, real_h, new_w, new_h, _scale_x, fmt, len(data),
    )
    return data, image_format


def _to_real(x: int, y: int) -> tuple[int, int]:
    """Convert display coordinates to absolute screen coordinates."""
    return int(x * _scale_x) + _offset_x, int(y * _scale_y) + _offset_y


@mcp.tool()
@tool(name="screenshot", tier=Tier.TWO, risk=Risk.READ_ONLY)
def screenshot(format: str = "jpeg") -> Image:
    """Capture the full virtual screen (all monitors). Default is JPEG (~5x smaller than PNG).

    Format options:
    - "jpeg" (default): JPEG quality 70. Best balance of size and fidelity for
      UI grounding. ~80 KB for a 1366px-wide desktop.
    - "png": Lossless. ~5x larger payload. Use when you need pixel-perfect
      detail (icons, tiny text, color verification).
    - "thumbnail": ~640px wide JPEG quality 40. Tiny (~15-20 KB). Use for
      sanity-check screenshots in long sessions to keep context light.

    IMPORTANT:
    - The image pixel dimensions ARE the coordinate space for all tools
      (click, screenshot_region, etc.). Use get_screen_size() to know
      the dimensions. If the image is 1366x853, coordinates range from
      (0,0) to (1366,853). The same coordinate space holds across formats.
    - Output width is hard-capped at 1600 px to stay under the Anthropic
      many-image dimension limit (2000 px), so a single screenshot can
      never block a Claude Code session.
    """
    engine = _get_engine()
    state = engine.screenshot()
    fmt = _resolve_format(format)
    data, image_format = _downscale(
        state.image_bytes, state.offset_x, state.offset_y, fmt=fmt
    )
    _debug_save(data, "screenshot")
    return Image(data=data, format=image_format)


@mcp.tool()
@tool(name="screenshot_region", tier=Tier.TWO, risk=Risk.READ_ONLY)
def screenshot_region(
    x: int, y: int, width: int, height: int, format: str = "jpeg"
) -> Image:
    """Capture a rectangular region of the screen. Coordinates are in display space.

    Format options match screenshot(): "jpeg" (default), "png", "thumbnail".
    A region is small to begin with, so the size win is modest, but JPEG
    stays consistent with screenshot() and avoids a per-image PNG payload.
    """
    engine = _get_engine()
    rx, ry = _to_real(x, y)
    rw, rh = int(width * _scale_x), int(height * _scale_y)
    state = engine.screenshot_region(rx, ry, rw, rh)
    # Don't pass through _downscale -- that would clobber the global scale
    # factors that screenshot() established. Just re-encode the raw bytes.
    fmt = _resolve_format(format)
    img = PILImage.open(io.BytesIO(state.image_bytes))
    data, image_format = _encode_image(img, fmt)
    _debug_save(data, "region")
    return Image(data=data, format=image_format)


@mcp.tool()
@tool(name="click", tier=Tier.TWO, risk=Risk.MEDIUM)
def click(x: int, y: int) -> str:
    """Left-click at screen coordinates (pixels).

    Always take a screenshot() first to confirm the target element's position.
    After clicking, take another screenshot() to verify the click landed
    correctly. Aim for the center of the target element.
    """
    engine = _get_engine()
    engine.click(*_to_real(x, y))
    return f"Clicked at ({x}, {y})"


@mcp.tool()
@tool(name="double_click", tier=Tier.TWO, risk=Risk.MEDIUM)
def double_click(x: int, y: int) -> str:
    """Double-click at screen coordinates."""
    engine = _get_engine()
    engine.double_click(*_to_real(x, y))
    return f"Double-clicked at ({x}, {y})"


@mcp.tool()
@tool(name="right_click", tier=Tier.TWO, risk=Risk.MEDIUM)
def right_click(x: int, y: int) -> str:
    """Right-click at screen coordinates."""
    engine = _get_engine()
    engine.right_click(*_to_real(x, y))
    return f"Right-clicked at ({x}, {y})"


@mcp.tool()
@tool(name="move_mouse", tier=Tier.TWO, risk=Risk.MEDIUM)
def move_mouse(x: int, y: int) -> str:
    """Move the mouse without clicking."""
    engine = _get_engine()
    engine.move_mouse(*_to_real(x, y))
    return f"Mouse moved to ({x}, {y})"


@mcp.tool()
@tool(name="scroll", tier=Tier.TWO, risk=Risk.MEDIUM)
def scroll(x: int, y: int, amount: int) -> str:
    """Scroll at position. Positive = up, negative = down."""
    engine = _get_engine()
    engine.scroll(*_to_real(x, y), amount)
    direction = "up" if amount > 0 else "down"
    return f"Scrolled {direction} {abs(amount)} notches at ({x}, {y})"


@mcp.tool()
@tool(name="drag", tier=Tier.TWO, risk=Risk.MEDIUM)
def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> str:
    """Drag from one point to another."""
    engine = _get_engine()
    engine.drag(*_to_real(start_x, start_y), *_to_real(end_x, end_y), duration)
    return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"


@mcp.tool()
@tool(name="type_text", tier=Tier.TWO, risk=Risk.MEDIUM)
def type_text(text: str) -> str:
    """Type text into the focused field."""
    engine = _get_engine()
    engine.type_text(text)
    preview = text[:50] + "..." if len(text) > 50 else text
    return f"Typed: {preview}"


@mcp.tool()
@tool(name="key_press", tier=Tier.TWO, risk=Risk.MEDIUM)
def key_press(keys: str) -> str:
    """Press a key combo, e.g. "ctrl+c", "alt+tab", "enter"."""
    engine = _get_engine()
    key_list = [k.strip() for k in keys.split("+")]
    engine.key_press(*key_list)
    return f"Pressed: {keys}"


@mcp.tool()
@tool(name="get_screen_size", tier=Tier.TWO, risk=Risk.READ_ONLY)
def get_screen_size() -> str:
    """Returns "WIDTHxHEIGHT" in display pixels (the coordinate space for all tools)."""
    if _display_w > 0 and _display_h > 0:
        return f"{_display_w}x{_display_h}"
    # No screenshot taken yet -- compute what the display size would be.
    # Mirror the logic in _downscale so the answer is consistent with the
    # first screenshot's actual dimensions.
    engine = _get_engine()
    w, h = engine.get_screen_size()
    configured = _MAX_WIDTH if _MAX_WIDTH > 0 else w
    target_w = min(configured, _MAX_DIMENSION_CEILING, w)
    if target_w >= w:
        return f"{w}x{h}"
    ratio = target_w / w
    return f"{target_w}x{int(h * ratio)}"


@mcp.tool()
@tool(name="get_platform", tier=Tier.TWO, risk=Risk.READ_ONLY)
def get_platform() -> str:
    """Returns detected platform: wsl2, linux, windows, or macos."""
    engine = _get_engine()
    return engine.get_platform().value


@mcp.tool()
@tool(name="get_platform_info", tier=Tier.TWO, risk=Risk.READ_ONLY)
def get_platform_info() -> dict:
    """Returns platform details."""
    engine = _get_engine()
    return engine.get_platform_info()


# --- Tier 0 system tools (0.3.0) ---
#
# Each module under `computer_use.tools.system` exposes one dispatch
# function. The wrappers below apply both `@mcp.tool()` (for the wire
# surface) and `@tool(...)` (for the registry), matching the 0.2.0
# pattern used by the pixel tools above.

from computer_use.tools.system import clipboard as _clipboard_impl
from computer_use.tools.system import data as _data_impl
from computer_use.tools.system import env as _env_impl
from computer_use.tools.system import fs as _fs_impl
from computer_use.tools.system import http as _http_impl
from computer_use.tools.system import shell as _shell_impl
from computer_use.tools.system import tempfile as _tempfile_impl
from computer_use.tools.system import time as _time_impl

from computer_use.browser import tool as _browser_impl


@mcp.tool()
@tool(name="fs", tier=Tier.ZERO, risk=Risk.MEDIUM)
def fs(op: str, path: str, content: str = "", recursive: bool = False):
    """Filesystem ops: read, write, list, stat, delete.

    Sub-ops:
    - read(path) -> str
    - write(path, content) -> {path, written}
    - list(path) -> [str]
    - stat(path) -> {path, size, kind, mtime}
    - delete(path, recursive=False) -> {path, deleted}
    """
    return _fs_impl.fs(op=op, path=path, content=content, recursive=recursive)


@mcp.tool()
@tool(name="shell", tier=Tier.ZERO, risk=Risk.HIGH)
def shell(
    op: str,
    command=None,
    shell_mode: bool = False,
    timeout: int = 30,
    cwd: str = None,
):
    """Subprocess + PATH lookup.

    Sub-ops:
    - run(command, shell_mode=False, timeout=30, cwd=None)
      -> {returncode, stdout, stderr}
    - which(command) -> path or None

    Classified HIGH risk: shell.run can mutate anything on the host.
    """
    return _shell_impl.shell(
        op=op, command=command, shell_mode=shell_mode, timeout=timeout, cwd=cwd
    )


@mcp.tool()
@tool(name="http", tier=Tier.ZERO, risk=Risk.MEDIUM)
def http(
    op: str,
    url: str,
    body: str = None,
    headers: dict = None,
    timeout: int = 30,
):
    """HTTP GET / POST via stdlib urllib.

    Sub-ops:
    - get(url, headers={}, timeout=30) -> {status, headers, body}
    - post(url, body=..., headers={}, timeout=30) -> {status, headers, body}
    """
    return _http_impl.http(
        op=op, url=url, body=body, headers=headers, timeout=timeout
    )


@mcp.tool()
@tool(name="env", tier=Tier.ZERO, risk=Risk.LOW)
def env(op: str, name: str, value: str = None):
    """Process-scoped environment variables.

    Sub-ops:
    - get(name) -> str or None
    - set(name, value) -> {name, value}  (does NOT persist)
    """
    return _env_impl.env(op=op, name=name, value=value)


@mcp.tool()
@tool(name="time", tier=Tier.ZERO, risk=Risk.READ_ONLY)
def time(op: str, seconds: float = 0, tz: str = None):
    """Clock + sleep.

    Sub-ops:
    - now(tz=None) -> ISO-8601 string (default UTC)
    - sleep(seconds) -> {slept: float}  (capped at 60s)
    """
    return _time_impl.time(op=op, seconds=seconds, tz=tz)


@mcp.tool()
@tool(name="tempfile", tier=Tier.ZERO, risk=Risk.LOW)
def tempfile(op: str = "temp_path", prefix: str = "vcu-", suffix: str = ""):
    """Allocate a unique temporary-file path (the file is NOT created).

    Sub-ops:
    - temp_path(prefix='vcu-', suffix='') -> absolute path str
    """
    return _tempfile_impl.tempfile(op=op, prefix=prefix, suffix=suffix)


@mcp.tool()
@tool(name="data", tier=Tier.ZERO, risk=Risk.READ_ONLY)
def data(op: str, source: str = None, value=None):
    """JSON / CSV / YAML parse + serialize.

    Sub-ops:
    - parse_json(source) / serialize_json(value)
    - parse_csv(source)  / serialize_csv(value)
    - parse_yaml(source) / serialize_yaml(value)  (requires PyYAML)
    """
    return _data_impl.data(op=op, source=source, value=value)


@mcp.tool()
@tool(name="clipboard", tier=Tier.ZERO, risk=Risk.LOW)
def clipboard(op: str, text: str = None):
    """Read / write the system clipboard.

    Sub-ops:
    - copy(text) -> {backend, bytes}
    - paste() -> str

    Backend chain: clip.exe (Windows/WSL2), pbcopy (macOS), wl-copy
    (Wayland), xclip (X11). Raises RuntimeError if none are on PATH.
    """
    return _clipboard_impl.clipboard(op=op, text=text)


# --- Tier 1: browser (MV3 extension + native messaging) ---
#
# One op-routed `browser` tool plus the separate HIGH-risk `browser_eval`.
# Both are thin clients over a BrowserBridge; they are always registered (the
# *action* fails with a guided error when no browser is connected, never the
# registration).

@mcp.tool()
@tool(name="browser", tier=Tier.ONE, risk=Risk.MEDIUM)
def browser(
    op: str,
    url: str = None,
    selector: str = None,
    name: str = None,
    text: str = None,
    value: str = None,
    by: str = "css",
    state: str = "visible",
    wait: str = "load",
    action: str = "get",
    all: bool = False,
    clear: bool = True,
    submit: bool = False,
    timeout: int = 5000,
    scroll_by: dict = None,
    key: str = None,
    force: bool = False,
):
    """Drive the browser by selector, through the MV3 extension (Tier 1).

    Sub-ops:
    - navigate(url, wait="load") / back / forward / reload -> {url, title}
    - wait_for(selector, state="visible"|"hidden"|"attached", timeout) -> {matched}
    - query(selector, by="css"|"xpath", all=False) -> [{tag, text, attrs}]
    - read_text(selector=None) -> str
    - get_attribute(selector, name) -> live value/checked/selected/disabled, else attr
    - click(selector, by="css") -> {clicked, checked?}
    - type / fill(selector, text, clear=True, submit=False) -> {typed, value, ok}
    - select(selector, value) -> {selected, value, ok}
    - scroll(selector=None | scroll_by={x,y}) -> {ok}
    - press(key, selector=None) -> {pressed}  (trusted key via chrome.debugger)
    - accessibility_tree() -> {nodes:[{role, name, value}]}  (semantic snapshot)
    - cookies(action="get"|"set"|"clear", url, name, value)
    - status() -> {connected, browsers, setup, reason}  (pre-flight; no page)

    VERIFY EVERY MUTATING OP — the DOM is the ground truth; never assume an
    action worked (this is the web equivalent of screenshot-before/after):
    - type/fill -> check the returned `ok` (or get_attribute(selector,"value")
      equals what you typed).
    - checkbox/radio click -> the returned `checked` (or get_attribute
      "checked") flipped to the state you intended.
    - select -> the returned `ok` (or get_attribute(selector,"value") is the
      chosen option).
    - a click that should change the page -> wait_for the expected element, then
      read_text/query to confirm the new state; a click that navigates returns
      {navigated, url} — confirm the destination is right.
    If the read-back does NOT match, the action did NOT take effect — retry or
    stop; do not continue on an unverified action.

    ACTIONABILITY: a mutating op refuses a non-actionable target (hidden / covered
    / disabled) with op_failed — act on the VISIBLE element, not a hidden mirror
    (e.g. some pages have a hidden form-field twin of the real editor). Pass
    force=True only to bypass this for a deliberately-hidden real control.

    On a terminal browser error (not set up / not connected / op unsupported)
    the tool raises with a guided pixel fallback — prefer this tool; degrade to
    the pixel tools only when it says so.
    """
    params = {
        "url": url, "selector": selector, "name": name, "text": text,
        "value": value, "state": state, "wait": wait, "action": action,
        "all": all, "clear": clear, "submit": submit, "timeout": timeout,
        "key": key, "force": force,
    }
    # `by` is the css/xpath selector mode for most ops, but the {x,y} offset for
    # `scroll`. The MCP surface keeps them distinct (`by` vs `scroll_by`); the
    # op handler reads `by` either way.
    if op == "scroll":
        if scroll_by is not None:
            params["by"] = scroll_by
    else:
        params["by"] = by
    params = {k: v for k, v in params.items() if v is not None}
    return _browser_impl.browser(op=op, **params)


@mcp.tool()
@tool(name="browser_eval", tier=Tier.ONE, risk=Risk.HIGH)
def browser_eval(expression: str):
    """Run arbitrary JavaScript in the active page (HIGH risk).

    Returns the evaluated value. Separate from `browser` so the common ops keep
    a lower risk ceiling; this is the escape hatch for anything not yet a
    first-class op.
    """
    return _browser_impl.browser_eval(expression=expression)


# --- CLI: management subcommands ---
#
# The package ships a single entry point (`vadgr-cua`). With no arguments
# it starts the MCP stdio server (the hot path). With a subcommand it
# exposes daemon lifecycle controls that used to live in external tooling.
# Keeping every subcommand as a small function makes them unit-testable
# without spinning up argparse or touching sys.argv.

def _get_supervisor():
    """Build a DaemonSupervisor on demand.

    Importing the supervisor pulls in `fcntl`, which doesn't exist on native
    Windows. The stdio MCP server (the hot path) doesn't need it; only the
    daemon subcommands do, and those run on WSL2/Linux.
    """
    from computer_use.bridge.supervisor import DaemonSupervisor
    return DaemonSupervisor()


def _registry_status() -> dict:
    """Snapshot of the ToolRegistry for `doctor` output.

    Returns three fields per ARCHITECTURE.md §10.1:
    - `registry_loaded`: True once the registry import succeeded.
    - `tool_count`: total number of registered tools.
    - `tier_breakdown`: map of tier-string -> count (e.g. {"2": 13}).
    """
    return {
        "registry_loaded": True,
        "tool_count": REGISTRY.count(),
        "tier_breakdown": {
            str(tier): count for tier, count in REGISTRY.tier_breakdown().items()
        },
    }


def _cmd_doctor(args) -> int:
    """Print structured status of the bridge daemon and the tool registry.

    Exits 0 regardless of daemon state -- callers parse the JSON.
    """
    import json as _json

    status = _get_supervisor().status()
    if sys.platform == "darwin":
        from computer_use.platform.macos import macos_permission_status
        status.update(macos_permission_status())
    status.update(_registry_status())
    if sys.platform == "linux":
        status["platform_backends"] = _platform_backends_status()
    print(_json.dumps(status, indent=2))
    return 0


def _platform_backends_status() -> dict:
    """Resolved capture/input backends for the live Linux session (for doctor).

    Reports which backend the resolver selects and which candidates applied, so a
    user (or agent) can see why a tier is or isn't available. Best-effort: any
    failure degrades to an error string rather than breaking doctor.
    """
    try:
        from computer_use.platform.linux_providers import describe_backends

        return describe_backends()
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": str(exc)}


def _cmd_install_daemon(args) -> int:
    """Eager deploy + launch. Returns non-zero if the daemon can't come up."""
    client = _get_supervisor().ensure_running()
    if client is None:
        print(
            "Daemon install failed. Run `vadgr-cua doctor` for diagnostics.",
            file=sys.stderr,
        )
        return 1
    print("Daemon installed and running.")
    return 0


def _cmd_setup(args) -> int:
    """One-time post-install permission prompt (macOS).

    Fires the Accessibility and Screen Recording prompts so the user can
    grant them before wiring up an agent. Prints permission state as
    JSON. No-op on non-macOS platforms.
    """
    import json as _json

    if sys.platform != "darwin":
        print(_json.dumps({"platform": sys.platform, "applicable": False}))
        return 0

    from computer_use.platform.macos import (
        macos_permission_status,
        request_permissions,
    )
    request_permissions()
    print(_json.dumps(macos_permission_status(), indent=2))
    return 0


def _cmd_browser_setup(args) -> int:
    """Self-register the browser-tier native host and print the load steps.

    Writes the native-host manifest (+ registry on Windows/WSL) so Chrome can
    spawn the host shim, then prints how to sideload the extension. Best-effort
    on the registration, explicit on the instructions.
    """
    from computer_use.setup.extension_setup import ensure_registered, load_steps

    result = ensure_registered()
    print(f"native host registered for: {', '.join(result['browsers'])}")
    print(f"host: {result['host_path']}\n")
    print(load_steps())
    return 0


def _cmd_stop_daemon(args) -> int:
    """Best-effort stop. Always returns 0 -- stop is idempotent."""
    _get_supervisor().stop()
    print("Daemon stopped.")
    return 0


def _cmd_restart_daemon(args) -> int:
    """Stop then start. Returns non-zero if the restart didn't come up."""
    client = _get_supervisor().restart()
    if client is None:
        print("Daemon restart failed.", file=sys.stderr)
        return 1
    print("Daemon restarted.")
    return 0


# Command -> module-level function name. Resolved via globals() at
# dispatch time so tests that patch the module attribute see the fake.
_SUBCOMMAND_NAMES: dict = {
    "doctor": "_cmd_doctor",
    "setup": "_cmd_setup",
    "browser-setup": "_cmd_browser_setup",
    "install-daemon": "_cmd_install_daemon",
    "stop-daemon": "_cmd_stop_daemon",
    "restart-daemon": "_cmd_restart_daemon",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vadgr-cua", description="Computer Use MCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=_MAX_WIDTH,
        help="Max screenshot width in pixels (0=auto, env: CU_MAX_WIDTH)",
    )

    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("doctor", help="Print daemon status as JSON")
    sub.add_parser(
        "setup",
        help="Fire macOS permission prompts and print state (no-op elsewhere)",
    )
    sub.add_parser(
        "browser-setup",
        help="Register the browser-tier native host and print the load steps",
    )
    sub.add_parser(
        "install-daemon",
        help="Deploy and launch the Windows bridge daemon (WSL2 only)",
    )
    sub.add_parser("stop-daemon", help="Stop the Windows bridge daemon")
    sub.add_parser("restart-daemon", help="Stop then start the daemon")

    return parser


def _start_browser_tier() -> None:
    """Best-effort: self-register the native host and start the TCP listener.

    Registering at startup (not only lazily on first browser use) means the
    extension's load order never matters — Chrome can spawn the host shim and
    reach a live listener whenever the user enables the extension. Wrapped so a
    transport/registration failure never blocks the MCP server from coming up.
    """
    try:
        from computer_use.setup.extension_setup import ensure_registered

        ensure_registered()
    except Exception as e:  # best-effort — never break startup
        logger.debug("browser-tier self-registration skipped: %s", e)
    try:
        from computer_use.browser import tool as browser_tool
        from computer_use.browser.server import ensure_server

        # Share the tool's bridge so the session the listener registers is the
        # one the `browser` tool routes ops to.
        ensure_server(bridge=browser_tool._default_bridge())
    except Exception as e:
        logger.debug("browser-tier listener not started: %s", e)


def _run_mcp_server(args) -> int:
    """Run the FastMCP server with the parsed CLI args."""
    global _MAX_WIDTH
    _MAX_WIDTH = args.max_width

    logger.info(
        "Starting Computer Use MCP server (transport=%s, max_width=%s)",
        args.transport,
        _MAX_WIDTH or "auto",
    )

    _start_browser_tier()

    if args.transport == "sse":
        mcp.settings.port = args.port
        logger.info("SSE server on port %d", args.port)

    mcp.run(transport=args.transport)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    handler_name = _SUBCOMMAND_NAMES.get(args.command)
    if handler_name is not None:
        return globals()[handler_name](args)
    return _run_mcp_server(args)


if __name__ == "__main__":
    sys.exit(main())
