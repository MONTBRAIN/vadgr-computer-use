# Computer Use - Desktop Automation Engine

Captures screenshots and executes mouse/keyboard actions for autonomous desktop interaction.

This module is **standalone** and works independently without `forge/`.

## What It Does

Provides programmatic control of the desktop through:

- **Screenshots** - full screen or region capture
- **Actions** - click, type, scroll, drag, key press
- **Autonomous loop** - screenshot, decide (LLM), act, verify cycle

## Usage

### As a library

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
screen = engine.screenshot()
engine.click(500, 300)
engine.type_text("hello")
```

### Autonomous mode

```python
engine = ComputerUseEngine(provider="anthropic")
results = engine.run_task("Open Notepad and type hello", max_steps=50)
```

### As an MCP server

Exposes 13 tools via Model Context Protocol for any MCP-compatible agent:

```bash
python -m computer_use.mcp_server
```

See `.mcp.json.example` in the repo root for configuration.

### CLI

```bash
python -m computer_use "Open the browser and search for Vadgr"
python -m computer_use --screenshot    # Save a screenshot
python -m computer_use --info          # Show platform info
```

## Setup

### Linux

```bash
bash setup-linux.sh
```

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your LLM provider API key:

```bash
export ANTHROPIC_API_KEY="sk-..."
# or
export OPENAI_API_KEY="sk-..."
```

## Architecture

```
computer_use/
├── core/               # Engine facade, types, actions, loop
├── platform/           # OS backends (Linux, Windows, macOS, WSL2)
├── providers/          # LLM adapters (Anthropic, OpenAI) -- autonomous mode only
├── bridge/             # WSL2 <-> Windows TCP bridge + supervisor
├── tests/              # Unit tests (pytest)
├── mcp_server.py       # MCP server entry point
├── config.yaml         # Default configuration
└── requirements.txt    # Python dependencies
```

## Platform Support

| Platform | Screenshots | Actions |
|----------|-------------|---------|
| Linux/X11 | mss | xdotool |
| Linux/Wayland (GNOME) | gnome-screenshot | Mutter RemoteDesktop |
| Linux/Wayland (wlroots) | grim | evdev |
| WSL2 | TCP bridge daemon (Win32 + mss) | TCP bridge daemon (Win32 SendInput) |
| Windows | Win32 GDI | SendInput |
| macOS | screencapture | osascript/cliclick |

## Configuration

Edit `config.yaml` or use environment variables:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (autonomous mode only) |
| `OPENAI_API_KEY` | OpenAI API key (autonomous mode only) |
| `VADGR_DEBUG` | Enable debug screenshots |
| `VADGR_DATA` | Custom data directory for debug screenshots |
| `CU_MAX_WIDTH` | Max screenshot width sent to the LLM |

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest computer_use/tests/ -v
```
