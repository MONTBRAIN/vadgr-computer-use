# vadgr-computer-use

Local MCP server for desktop automation. The LLM takes screenshots, reasons over them, and drives mouse and keyboard through the server. Accessibility APIs (Windows UIA, macOS AX, Linux AT-SPI2) are used for description-to-coordinate lookup when available.

## Install

```bash
pip install vadgr-computer-use
```

## Run as MCP server

```bash
vadgr-cua --transport stdio
# or over SSE
vadgr-cua --transport sse --port 8000
```

Wire it into any MCP client (Claude Desktop, Cursor, Cline, custom agents).

## How it works

The loop is intentionally simple:

1. Agent calls `screenshot()` — server returns a downscaled PNG.
2. Agent reasons over the image and picks coordinates.
3. Agent calls `click(x, y)` / `type_text(...)` / `key_press(...)`.
4. Agent calls `screenshot()` again to verify the effect.

For supported UIs, `find_element("Save button")` resolves a description to screen coordinates via the OS accessibility API (no vision required), with an optional LLM-vision fallback when accessibility cannot answer.

## Platform support

| Platform | Screenshots | Mouse / keyboard | Accessibility backend |
|----------|-------------|------------------|------------------------|
| Linux / X11 | `mss` | `xdotool` | AT-SPI2 (via `python3-gi` + `gir1.2-atspi-2.0`) |
| WSL2 → Windows host | TCP bridge daemon (`mss` on Windows) | TCP bridge daemon (Win32 `SendInput`) | Windows UI Automation via PowerShell |
| Windows native | Win32 GDI | SendInput | Windows UI Automation |
| macOS | `screencapture` | `osascript` / `cliclick` | AX API |

On WSL2 the bridge daemon is launched automatically on first use and persists across MCP sessions; if it can't be started (e.g. no Windows Python available), the server silently falls back to a slower PowerShell path. See [Daemon management](#daemon-management-wsl2) below.

## MCP tools

Capture
- `screenshot()` — full screen, downscaled to `CU_MAX_WIDTH` (auto-picks 1024 / 1280 / 1366).
- `screenshot_region(x, y, w, h)` — cropped region.

Input
- `click(x, y)` / `double_click(x, y)` / `right_click(x, y)`
- `move_mouse(x, y)` / `drag(x1, y1, x2, y2, duration=0.5)`
- `scroll(x, y, amount)`
- `type_text(text)` / `key_press(keys)` — keys like `ctrl+s`, `alt+tab`, `enter`.

Accessibility-backed lookup
- `find_element(description)` — returns `Found '<name>' (role=<role>) at (x, y)` or `Element not found`.

Platform info
- `get_platform()` / `get_platform_info()` / `get_screen_size()`

## Daemon management (WSL2)

On WSL2 the server reaches Windows through a small background daemon that
launches on first use and survives across MCP sessions — most users never
need to touch it. For when you do:

```bash
vadgr-cua doctor           # JSON: platform, Windows Python, daemon state, port, hash
vadgr-cua install-daemon   # Eager deploy + launch (useful in provisioning scripts)
vadgr-cua stop-daemon      # Kill the running daemon
vadgr-cua restart-daemon   # Stop then start
```

The daemon file is deployed to `%USERPROFILE%\vadgr\daemon.py` and listens on TCP `127.0.0.1:19542`. After `pip install -U vadgr-computer-use`, the next MCP session detects the version-hash drift via a `ping` handshake and redeploys the daemon automatically — no manual restart required.

## Library usage

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
shot = engine.screenshot()
engine.click(500, 300)
engine.type_text("hello")
```

## Environment

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Enables Claude vision fallback for `find_element` |
| `OPENAI_API_KEY` | Enables OpenAI vision fallback for `find_element` |
| `CU_MAX_WIDTH` | Override downscale target (default: auto 1024/1280/1366) |
| `CUE_BRIDGE_PORT` | Override WSL2 bridge daemon TCP port (default: 19542) |
| `VADGR_DATA` | Override data directory for debug screenshots |
| `VADGR_DEBUG` | Set to `1` to dump screenshots to `$VADGR_DATA/screenshots/` |

Vision providers use stdlib `urllib`. No extra dependency is required; just set the API key to enable the fallback.

## Tests

```bash
pip install -e ".[dev]"
pytest computer_use/tests
```

## License

Apache 2.0. See `LICENSE`.

## Part of Vadgr

- [vadgr](https://github.com/MONTBRAIN/vadgr) — workflow engine (brain)
- **[vadgr-computer-use](https://github.com/MONTBRAIN/vadgr-computer-use)** — desktop automation MCP (eyes)
- [vadgr-agent-os](https://github.com/MONTBRAIN/vadgr-agent-os) — containerized agent runtime
