# vadgr-computer-use

Local MCP server for desktop automation. 13 tools for capture, mouse, keyboard, and platform introspection. The calling agent takes a screenshot, reasons over the pixels, and drives mouse/keyboard through the server.

Tested with **Claude Code**, **Codex CLI**, and **Gemini CLI** (same server, same tools, same prompt).

> **Platforms:** works on **Linux (X11 and Wayland incl. GNOME)**, **Windows native**, and **WSL2**. **macOS support is a work in progress** and not usable yet. See [Platform support](#platform-support) for detail.

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

## Try it

Once the wire-up is done, any of these commands launch the client, which starts `vadgr-cua --transport stdio` in the background via MCP, and drives your desktop. Same prompt, same tools: pick the client you already use.

**Sanity check (focus + Ctrl+A):**

```
Take a screenshot, tell me in one sentence what application is in focus,
then press Ctrl+A and take another screenshot to confirm the action.
```

### Claude Code

Interactive (most common):

```bash
claude --dangerously-skip-permissions
# then paste the prompt at the > cursor
```

Headless one-shot:

```bash
claude --dangerously-skip-permissions -p \
  "Take a screenshot, tell me what app is in focus, then press Ctrl+A and screenshot again."
```

### Codex CLI

Headless one-shot (the usual way to drive Codex):

```bash
codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
  "Take a screenshot, tell me what app is in focus, then press Ctrl+A and screenshot again."
```

Expected output (abbreviated):

```
mcp: vadgr-computer-use/screenshot (completed)
mcp: vadgr-computer-use/key_press (completed)
mcp: vadgr-computer-use/screenshot (completed)
The focused app is <...>; Ctrl+A selected its content.
```

### Gemini CLI

Works end-to-end, but pixel grounding on full-screen shots is weaker than Claude/Codex: first-attempt clicks on small targets can miss by 20-60 px (the model usually recovers via `screenshot_region` crops). **Pass the model explicitly**, since the default may silently fall back to an older Gemini on some accounts:

```bash
gemini -m gemini-3.1-pro-preview -p \
  "Use only vadgr-computer-use tools. Take a screenshot, tell me what app is in focus, then press Ctrl+A and screenshot again." \
  -y --allowed-mcp-server-names vadgr-computer-use
```

---

## Fuller example: play a song on YouTube Music (Codex)

A Chrome window is already open with a "YouTube Music" tab. One call:

```bash
codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
  "Use only vadgr-computer-use MCP tools. In the already-open Chrome,
   switch to the YouTube Music tab, search 'Space Oddity David Bowie',
   and play the first result."
```

Real transcript (trimmed):

```
mcp: vadgr-computer-use/screenshot (completed)
mcp: vadgr-computer-use/click (completed)        # YouTube Music tab
mcp: vadgr-computer-use/click (completed)        # search box
mcp: vadgr-computer-use/type_text (completed)
mcp: vadgr-computer-use/key_press (completed)    # enter
mcp: vadgr-computer-use/click (completed)        # first result
mcp: vadgr-computer-use/click (completed)        # dismiss ad overlay
mcp: vadgr-computer-use/screenshot (completed)   # verify now-playing bar
Yes, "Space Oddity" by David Bowie is now playing.
```

---

## How it works

The LLM owns the "where to click" decision; the server owns "how to click it precisely". No other abstraction in between.

## Platform support

| Platform | Screenshots | Mouse / keyboard | Install notes |
|----------|-------------|------------------|----------------|
| Linux / X11 | `mss` | `xdotool` | `apt install xdotool` (or distro equivalent) |
| Linux / Wayland (GNOME) | `gnome-screenshot` | Mutter RemoteDesktop via `jeepney` | nothing extra; pre-installed on stock GNOME, deps pulled by pip |
| Linux / Wayland (Sway, Hyprland, wlroots) | `grim` | `evdev` | `apt install grim`; `sudo usermod -aG input $USER` then re-login |
| Windows native | Win32 GDI | SendInput | nothing extra |
| WSL2 → Windows host | TCP bridge daemon (`mss` on Windows) | TCP bridge daemon (Win32 `SendInput`) | bridge daemon auto-launches |
| macOS | `screencapture` | `osascript` / `cliclick` | WIP, not functional yet |

`pip install vadgr-computer-use` pulls `jeepney` and `evdev` automatically on Linux (both are pure-Python or shipped as wheels, no `libdbus-1-dev` or compilation needed). Foreground-window detection on Wayland uses AT-SPI2 if available; install with `pip install vadgr-computer-use[linux-atspi]` to enable it.

If the WSL2 daemon can't start (e.g. no Windows Python available), the server falls back to a slower PowerShell path. See [Daemon management](#daemon-management-wsl2) below.

## MCP tools (13)

Capture (2)
- `screenshot()`: full screen, downscaled to `CU_MAX_WIDTH` (auto-picks 1024 / 1280 / 1366).
- `screenshot_region(x, y, w, h)`: cropped region.

Input (8)
- `click(x, y)` / `double_click(x, y)` / `right_click(x, y)`
- `move_mouse(x, y)` / `drag(start_x, start_y, end_x, end_y, duration=0.5)`
- `scroll(x, y, amount)`: positive = up, negative = down
- `type_text(text)` / `key_press(keys)`: keys like `ctrl+s`, `alt+tab`, `enter`

Platform info (3)
- `get_platform()` / `get_platform_info()` / `get_screen_size()`

## Daemon management (WSL2)

Most users never touch this. For when you do:

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

The library is just the input/capture primitives, no LLM or agent loop inside. To drive it with a model, point an MCP client (Claude Code, Codex, Gemini, or your own) at the `vadgr-cua` server as shown above.

## Environment

| Variable | Purpose |
|----------|---------|
| `CU_MAX_WIDTH` | Override screenshot downscale target (default: auto 1024/1280/1366) |
| `CUE_BRIDGE_PORT` | Override WSL2 bridge daemon TCP port (default: 19542) |
| `VADGR_DEBUG` | Set to `1` to dump screenshots to `<package>/.debug/` |

## Tests

```bash
pip install -e ".[dev]"
pytest computer_use/tests -q
```

## License

Apache 2.0. See `LICENSE`.

## Part of Vadgr

- [vadgr](https://github.com/MONTBRAIN/vadgr): workflow engine (brain)
- **[vadgr-computer-use](https://github.com/MONTBRAIN/vadgr-computer-use)**: desktop automation MCP (eyes)
- [vadgr-agent-os](https://github.com/MONTBRAIN/vadgr-agent-os): containerized agent runtime
