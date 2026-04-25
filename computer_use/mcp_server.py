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
        "coordinates, and retry."
    ),
)

_MAX_WIDTH = int(os.environ.get("CU_MAX_WIDTH", "0"))  # 0 = auto-detect

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


def _downscale(png_bytes: bytes, offset_x: int = 0, offset_y: int = 0) -> bytes:
    """Resize screenshot to fit _MAX_WIDTH, update global scale/offset state."""
    global _scale_x, _scale_y, _display_w, _display_h, _offset_x, _offset_y

    _offset_x = offset_x
    _offset_y = offset_y

    img = PILImage.open(io.BytesIO(png_bytes))
    real_w, real_h = img.size

    if real_w <= _MAX_WIDTH:
        _scale_x, _scale_y = 1.0, 1.0
        _display_w, _display_h = real_w, real_h
        return png_bytes

    ratio = _MAX_WIDTH / real_w
    new_w = _MAX_WIDTH
    new_h = int(real_h * ratio)

    _scale_x = real_w / new_w
    _scale_y = real_h / new_h
    _display_w, _display_h = new_w, new_h

    img = img.resize((new_w, new_h), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    logger.debug("Downscaled %dx%d -> %dx%d (scale %.2fx)", real_w, real_h, new_w, new_h, _scale_x)
    return buf.getvalue()


def _to_real(x: int, y: int) -> tuple[int, int]:
    """Convert display coordinates to absolute screen coordinates."""
    return int(x * _scale_x) + _offset_x, int(y * _scale_y) + _offset_y


@mcp.tool()
def screenshot() -> Image:
    """Capture the full virtual screen (all monitors). Returns PNG image.

    IMPORTANT: The image pixel dimensions ARE the coordinate space for all
    tools (click, screenshot_region, etc.). Use get_screen_size() to know
    the dimensions. If the image is 1366x853, coordinates range from
    (0,0) to (1366,853).
    """
    engine = _get_engine()
    state = engine.screenshot()
    data = _downscale(state.image_bytes, state.offset_x, state.offset_y)
    _debug_save(data, "screenshot")
    return Image(data=data, format="png")


@mcp.tool()
def screenshot_region(x: int, y: int, width: int, height: int) -> Image:
    """Capture a rectangular region of the screen. Coordinates are in display space."""
    engine = _get_engine()
    rx, ry = _to_real(x, y)
    rw, rh = int(width * _scale_x), int(height * _scale_y)
    state = engine.screenshot_region(rx, ry, rw, rh)
    # Don't pass through _downscale — it would clobber the global scale factors
    # that screenshot() established. Just return the raw region bytes.
    _debug_save(state.image_bytes, "region")
    return Image(data=state.image_bytes, format="png")


@mcp.tool()
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
def double_click(x: int, y: int) -> str:
    """Double-click at screen coordinates."""
    engine = _get_engine()
    engine.double_click(*_to_real(x, y))
    return f"Double-clicked at ({x}, {y})"


@mcp.tool()
def right_click(x: int, y: int) -> str:
    """Right-click at screen coordinates."""
    engine = _get_engine()
    engine.right_click(*_to_real(x, y))
    return f"Right-clicked at ({x}, {y})"


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """Move the mouse without clicking."""
    engine = _get_engine()
    engine.move_mouse(*_to_real(x, y))
    return f"Mouse moved to ({x}, {y})"


@mcp.tool()
def scroll(x: int, y: int, amount: int) -> str:
    """Scroll at position. Positive = up, negative = down."""
    engine = _get_engine()
    engine.scroll(*_to_real(x, y), amount)
    direction = "up" if amount > 0 else "down"
    return f"Scrolled {direction} {abs(amount)} notches at ({x}, {y})"


@mcp.tool()
def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> str:
    """Drag from one point to another."""
    engine = _get_engine()
    engine.drag(*_to_real(start_x, start_y), *_to_real(end_x, end_y), duration)
    return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"


@mcp.tool()
def type_text(text: str) -> str:
    """Type text into the focused field."""
    engine = _get_engine()
    engine.type_text(text)
    preview = text[:50] + "..." if len(text) > 50 else text
    return f"Typed: {preview}"


@mcp.tool()
def key_press(keys: str) -> str:
    """Press a key combo, e.g. "ctrl+c", "alt+tab", "enter"."""
    engine = _get_engine()
    key_list = [k.strip() for k in keys.split("+")]
    engine.key_press(*key_list)
    return f"Pressed: {keys}"


@mcp.tool()
def get_screen_size() -> str:
    """Returns "WIDTHxHEIGHT" in display pixels (the coordinate space for all tools)."""
    if _display_w > 0 and _display_h > 0:
        return f"{_display_w}x{_display_h}"
    # No screenshot taken yet — compute what the display size would be.
    engine = _get_engine()
    w, h = engine.get_screen_size()
    if w <= _MAX_WIDTH:
        return f"{w}x{h}"
    ratio = _MAX_WIDTH / w
    return f"{_MAX_WIDTH}x{int(h * ratio)}"


@mcp.tool()
def get_platform() -> str:
    """Returns detected platform: wsl2, linux, windows, or macos."""
    engine = _get_engine()
    return engine.get_platform().value


@mcp.tool()
def get_platform_info() -> dict:
    """Returns platform details."""
    engine = _get_engine()
    return engine.get_platform_info()


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


def _cmd_doctor(args) -> int:
    """Print structured status of the bridge daemon.

    Exits 0 regardless of daemon state -- callers parse the JSON.
    """
    import json as _json

    status = _get_supervisor().status()
    print(_json.dumps(status, indent=2))
    return 0


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
        "install-daemon",
        help="Deploy and launch the Windows bridge daemon (WSL2 only)",
    )
    sub.add_parser("stop-daemon", help="Stop the Windows bridge daemon")
    sub.add_parser("restart-daemon", help="Stop then start the daemon")

    return parser


def _run_mcp_server(args) -> int:
    """Run the FastMCP server with the parsed CLI args."""
    global _MAX_WIDTH
    _MAX_WIDTH = args.max_width

    logger.info(
        "Starting Computer Use MCP server (transport=%s, max_width=%s)",
        args.transport,
        _MAX_WIDTH or "auto",
    )

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
