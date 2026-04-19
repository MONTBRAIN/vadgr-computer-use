# vadgr-computer-use

Local-first MCP server for desktop automation. Accessibility-first (UIA / AT-SPI / AX) with vision fallback (OmniParser YOLO). No cloud calls. Works on CPU.

## Install

```bash
pip install vadgr-computer-use
```

Optional extras:

```bash
pip install "vadgr-computer-use[vision]"     # OmniParser / YOLO
pip install "vadgr-computer-use[anthropic]"  # Claude vision fallback
pip install "vadgr-computer-use[openai]"     # GPT-4V vision fallback
```

## Run as MCP server

```bash
vadgr-cua --transport stdio
# or for SSE
vadgr-cua --transport sse --port 8000
```

Wire it up in any MCP client (Claude Desktop, Cursor, Cline, custom agents).

## What it does

- Detects UI elements via OS accessibility APIs (Windows UIA, Linux AT-SPI2, macOS AX)
- Falls back to vision (OmniParser YOLO) when accessibility is unavailable
- Invokes actions programmatically (no mouse movement when possible)
- Supports: click, type, key combos, scroll, drag, annotated screenshots
- Records and replays multi-step trajectories
- Works across: WSL2, Windows native, Linux (X11/Wayland), macOS

## Platform support

| Platform | Screenshots | Input | Accessibility |
|----------|-------------|-------|---------------|
| Linux / X11 | mss | xdotool | AT-SPI2 |
| Linux / Wayland (GNOME) | gnome-screenshot | Mutter RemoteDesktop | AT-SPI2 |
| WSL2 → Windows | PowerShell bridge | PowerShell bridge | UI Automation |
| Windows native | Win32 GDI | SendInput | UI Automation |
| macOS | screencapture | osascript / cliclick | AX API |

## Library usage

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
screen = engine.screenshot()
engine.click(500, 300)
engine.type_text("hello")
```

## MCP tools exposed

- `screenshot` / `screenshot_region`
- `find_elements` / `find_element`
- `interact` (accessibility-first; no coord guessing)
- `click` / `double_click` / `right_click`
- `type_text` / `key_press`
- `scroll` / `drag` / `move_mouse`
- `annotated_screenshot` / `click_element_number`
- `start_recording` / `stop_recording` / `replay`
- `create_template` / `execute_template`
- `navigate_to` / `navigate_chain`

## Environment

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude vision provider |
| `OPENAI_API_KEY` | OpenAI vision provider |
| `AGENT_FORGE_DEBUG` | Enable debug screenshots |
| `AGENT_FORGE_DATA` | Custom data directory |
| `CU_MAX_WIDTH` | Max screenshot width for vision models |

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
