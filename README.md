# vadgr-computer-use

Local MCP server for desktop automation. The LLM takes screenshots, reasons over them, and drives mouse and keyboard through the server. Accessibility APIs (Windows UIA, macOS AX, Linux AT-SPI2) are used when a description can be resolved without vision, and repeated flows are cached so they skip the screenshot-plus-LLM roundtrip after a few successful runs.

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

The default loop is the one that already works well in practice:

1. Agent calls `screenshot()` — server returns a downscaled PNG.
2. Agent reasons over the image and picks coordinates.
3. Agent calls `click(x, y)` / `type_text(...)` / `key_press(...)`.
4. Agent calls `screenshot()` again to verify the effect.

On top of that loop, three shortcuts reduce latency when the agent knows what it is doing:

- `find_element("Save button")` — resolves a description to screen coordinates through the OS accessibility API. Returns a point the agent can click, no vision required. Falls back to an optional LLM-vision provider when accessibility cannot answer.
- `navigate_to` / `navigate_chain` — replays cached click paths for targets the agent has hit 3+ times. Skips screenshots entirely for known UI.
- `create_template` / `execute_template` — records a named multi-step flow (click, type, key, wait) and replays it without screenshots.

Cache and templates are stored locally under `$AGENT_FORGE_DATA` (default: OS-appropriate data dir).

## Platform support

| Platform | Screenshots | Mouse / keyboard | Accessibility backend |
|----------|-------------|------------------|------------------------|
| Linux / X11 | `mss` | `xdotool` | AT-SPI2 (via `python3-gi` + `gir1.2-atspi-2.0`) |
| WSL2 → Windows host | PowerShell bridge | PowerShell bridge | Windows UI Automation |
| Windows native | Win32 GDI | SendInput | Windows UI Automation |
| macOS | `screencapture` | `osascript` / `cliclick` | AX API |

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

Cached navigation (skips LLM roundtrips for repeated targets)
- `navigate_to(target_hint, target_app="", current_hint="")`
- `navigate_chain(hints, app_name="")`

Reusable templates
- `create_template(name, app_name, steps)`
- `execute_template(name)` / `list_templates(app_name="")` / `delete_template(name)`

Platform info
- `get_platform()` / `get_platform_info()` / `get_screen_size()`

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
| `AGENT_FORGE_CACHE_ENABLED` | Set to `0` to disable navigation cache and templates |
| `AGENT_FORGE_DATA` | Override data directory for cache, templates, debug |
| `AGENT_FORGE_DEBUG` | Set to `1` to dump screenshots to `$AGENT_FORGE_DATA/screenshots/` |

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
