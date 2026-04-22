# vadgr-computer-use

Local MCP server for desktop automation. 13 tools for capture, mouse, keyboard, and platform introspection. The calling agent takes a screenshot, reasons over the pixels, and drives mouse/keyboard through the server.

Tested with **Claude Code**, **Codex CLI**, and **Gemini CLI** (same server, same tools, same prompt).

---

## Install

```bash
pip install vadgr-computer-use
```

That ships a console script called `vadgr-cua`. Verify:

```bash
vadgr-cua doctor
# {"daemon_running": false, "windows_python": null, "port": 19542, ...}
```

On WSL2, the bridge daemon auto-launches the first time a tool is called. On other platforms it's a no-op; direct backends handle everything.

---

## Wire it into your agent

Pick your client. The server command is `vadgr-cua --transport stdio` in every case. Each agent launches that stdio process itself, so it needs the full path to the binary unless `vadgr-cua` is already on the agent's `PATH`.

First, find the path:

```bash
which vadgr-cua
# global install: /home/you/.local/bin/vadgr-cua
# venv install:  /path/to/.venv/bin/vadgr-cua
```

Substitute that path in each config below.

### Claude Code

Project-level (`.mcp.json` at the repo root you want to automate from):

```json
{
  "mcpServers": {
    "vadgr-computer-use": {
      "type": "stdio",
      "command": "/path/to/vadgr-cua",
      "args": ["--transport", "stdio"]
    }
  }
}
```

User-level (add to `~/.claude.json` under `mcpServers` with the same shape).

Verify: `claude mcp list` should print `vadgr-computer-use: ... ✓ Connected`.

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.vadgr-computer-use]
command = "/path/to/vadgr-cua"
args = ["--transport", "stdio"]
```

Verify: `codex mcp list` should list `vadgr-computer-use` with status `enabled`.

### Gemini CLI

```bash
gemini mcp add --scope user --trust \
  vadgr-computer-use /path/to/vadgr-cua \
  -- --transport stdio
```

That writes `~/.gemini/settings.json`. Verify by running an interactive session: Gemini shows MCP tool calls inline.

---

## Demo prompt (works in all three)

```
Take a screenshot, tell me in one sentence what application is in focus,
then press Ctrl+A and take another screenshot to confirm the action.
```

Expected behavior across all three clients:

1. Server spawns (stdio), daemon auto-launches on WSL2.
2. Client calls `screenshot()` → gets PNG → reasons.
3. Client calls `key_press("ctrl+a")`.
4. Client calls `screenshot()` again → verifies.

Known-good transcript from Codex (auto-approve mode):

```
$ codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
    "Use the vadgr-computer-use MCP tool get_platform_info. Reply in one sentence."

mcp: vadgr-computer-use/get_platform_info started
mcp: vadgr-computer-use/get_platform_info (completed)
The platform is `wsl2`, and the backend is available.
```

---

## How it works

1. Agent calls `screenshot()` — server returns a downscaled PNG.
2. Agent reasons over the image and picks coordinates.
3. Agent calls `click(x, y)` / `type_text(...)` / `key_press(...)`.
4. Agent calls `screenshot()` again to verify the effect.

The LLM owns the "where to click" decision; the server owns "how to click it precisely". No other abstraction in between.

## Platform support

| Platform | Screenshots | Mouse / keyboard | Status |
|----------|-------------|------------------|--------|
| WSL2 → Windows host | TCP bridge daemon (`mss` on Windows) | TCP bridge daemon (Win32 `SendInput`) | primary, well-tested |
| Linux / X11 | `mss` | `xdotool` | works |
| Windows native | Win32 GDI | SendInput | should work; not in the v0.1.0 CI matrix |
| macOS | `screencapture` | `osascript` / `cliclick` | WIP, not functional yet |

macOS is a work-in-progress: the backend imports but actions and screenshots do not round-trip correctly yet. Fixes welcome.

On WSL2 the bridge daemon is launched automatically on first use and persists across MCP sessions; if it can't be started (e.g. no Windows Python available), the server silently falls back to a slower PowerShell path. See [Daemon management](#daemon-management-wsl2) below.

## MCP tools (13)

Capture (2)
- `screenshot()` — full screen, downscaled to `CU_MAX_WIDTH` (auto-picks 1024 / 1280 / 1366).
- `screenshot_region(x, y, w, h)` — cropped region.

Input (8)
- `click(x, y)` / `double_click(x, y)` / `right_click(x, y)`
- `move_mouse(x, y)` / `drag(start_x, start_y, end_x, end_y, duration=0.5)`
- `scroll(x, y, amount)` — positive = up, negative = down
- `type_text(text)` / `key_press(keys)` — keys like `ctrl+s`, `alt+tab`, `enter`

Platform info (3)
- `get_platform()` / `get_platform_info()` / `get_screen_size()`

## Daemon management (WSL2)

On WSL2 the server reaches Windows through a small background daemon that launches on first use and survives across MCP sessions. Most users never touch it. For when you do:

```bash
vadgr-cua doctor           # JSON: platform, Windows Python, daemon state, port, hash
vadgr-cua install-daemon   # Eager deploy + launch
vadgr-cua stop-daemon      # Kill the running daemon
vadgr-cua restart-daemon   # Stop then start
```

The daemon file is deployed to `%USERPROFILE%\vadgr\daemon.py` and listens on TCP `127.0.0.1:19542`. After `pip install -U vadgr-computer-use`, the next MCP session detects the version-hash drift via a `ping` handshake and redeploys the daemon automatically.

## Library usage

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
shot = engine.screenshot()
engine.click(500, 300)
engine.type_text("hello")
```

The library has no LLM inside. The caller decides what to do. If you want an agent loop, use an MCP client (Claude Code, Codex, Gemini, or your own) and let it drive the server.

## Environment

| Variable | Purpose |
|----------|---------|
| `CU_MAX_WIDTH` | Override screenshot downscale target (default: auto 1024/1280/1366) |
| `CUE_BRIDGE_PORT` | Override WSL2 bridge daemon TCP port (default: 19542) |
| `VADGR_DATA` | Override data directory for debug screenshots |
| `VADGR_DEBUG` | Set to `1` to dump screenshots to `$VADGR_DATA/screenshots/` |

## Tests

```bash
pip install -e ".[dev]"
pytest computer_use/tests -q
```

## License

Apache 2.0. See `LICENSE`.

## Part of Vadgr

- [vadgr](https://github.com/MONTBRAIN/vadgr) — workflow engine (brain)
- **[vadgr-computer-use](https://github.com/MONTBRAIN/vadgr-computer-use)** — desktop automation MCP (eyes)
- [vadgr-agent-os](https://github.com/MONTBRAIN/vadgr-agent-os) — containerized agent runtime
