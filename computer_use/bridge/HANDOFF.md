# Bridge Daemon Handoff Context

## What Was Built

A persistent Python TCP daemon that runs on Windows and provides fast desktop automation (screenshots, mouse, keyboard) to the WSL2-based MCP server. Replaces slow PowerShell subprocess calls.

## Architecture

```
Claude Code (WSL2)
  -> MCP Server (computer_use/mcp_server.py)
    -> ComputerUseEngine -> WSL2Backend
      -> BridgeClient (TCP over localhost)
        -> Bridge Daemon (Windows-native Python process)
          -> mss (screenshots)
          -> ctypes SendInput (mouse/keyboard)
```

Fallback: if the daemon isn't running, WSL2Backend falls back to PowerShell subprocess (old behavior).

## Files Created/Modified

### New files (bridge package)
- `computer_use/bridge/__init__.py` - Package init
- `computer_use/bridge/protocol.py` - TCP framing (4-byte length prefix + JSON), port config
- `computer_use/bridge/client.py` - BridgeClient with WSL2 host auto-detection, thread-safe, auto-reconnect
- `computer_use/bridge/capture.py` - BridgeScreenCapture (implements ScreenCapture ABC)
- `computer_use/bridge/actions.py` - BridgeActionExecutor (implements ActionExecutor ABC)
- `computer_use/bridge/daemon.py` - Windows-side daemon (THE FILE THAT NEEDS TESTING)
- `computer_use/tests/test_bridge.py` - 28 tests

### Modified files
- `computer_use/platform/wsl2.py` - WSL2Backend probes bridge daemon, falls back to PowerShell
- `computer_use/mcp_server.py` - Auto-detect MAX_WIDTH from screen size, offset handling, `_compute_max_width()`
- `computer_use/core/types.py` - Comment update (PNG or JPEG)
- `computer_use/tests/test_mcp_server.py` - Offset-aware tests, fixture sets MAX_WIDTH=1024
- `.gitignore` - Global `__pycache__/` pattern

## Current State: 105 tests passing, uncommitted on `feature/computer-use`

### What Works (verified in live testing)
1. **DPI awareness** - daemon.py calls `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` at module load, BEFORE any Win32 API or mss import. This was the root cause of erratic mouse -- Python defaults to DPI-unaware, causing coordinate space mismatch.
2. **Mouse precision** - Uses atomic `SendInput` with `MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK` instead of `SetCursorPos`. Move+click in a single `SendInput` call (3 INPUT structs, no race conditions). Coordinates normalized to 0-65535 range over virtual desktop.
3. **Screenshots** - mss captures at physical resolution, MCP server auto-detects optimal downscale width (picks highest of 1024/1280/1366 that fits the screen). Full screen visible including taskbar.
4. **WSL2 networking** - Client auto-detects Windows host IP via `/proc/net/route` default gateway. Daemon binds `0.0.0.0:19542` (not 127.0.0.1). Port configurable via `CUE_BRIDGE_PORT` env var.
5. **Screen metrics** - Virtual screen bounds queried fresh each call via `GetSystemMetrics` (not cached), so it adapts to RDP resolution changes mid-session.
6. **Scale factor** - Uses `GetDpiForSystem()` -> `GetDpiForMonitor()` -> `GetDeviceCaps()` cascade for reliable detection.
7. **Key presses** - `key_press` works (Ctrl+A, Ctrl+S, Alt+D, Alt+N, Enter, Escape all verified).
8. **Diagnostic logging** - DPI awareness level, screen metrics, and DPI all logged at daemon startup.

### What Does NOT Work Yet
**`type_text` drops characters.** This is the one remaining issue.

The current code in `daemon.py` uses a hybrid approach:
- **Short text (<=3 chars):** per-character `KEYEVENTF_UNICODE` with 10ms delay per char
- **Longer text:** clipboard paste via Win32 API (`GlobalAlloc` + `SetClipboardData`) then `Ctrl+V`

**The clipboard paste approach has NOT been tested.** The daemon was updated but the laptop screen was off (lid closed, user connecting via VS Code tunnel) so live testing was impossible.

Previous attempts that FAILED:
- **VkKeyScanW + key-by-key SendInput** (original): dropped words like "working", keyboard-layout dependent
- **KEYEVENTF_UNICODE all chars in one SendInput call**: only 6 chars got through, rest lost to input queue overflow
- **KEYEVENTF_UNICODE batches of 8 + 5ms delay**: only 16 chars got through

The clipboard paste approach SHOULD work because:
- It bypasses the input queue entirely
- It's how professional automation tools (pyautogui, AutoIt) handle long text
- It works across all keyboard layouts and applications

**If clipboard paste doesn't work, try:**
1. Increase delay after `_set_clipboard()` from 10ms to 50-100ms
2. Add a delay after Ctrl+V before returning
3. Use `WM_PASTE` message instead of Ctrl+V for specific windows

### Also Not Working
- **Win+R** (Super key) - `SendInput` from a background daemon can't trigger Win key combos due to Windows UIPI restrictions. Workaround: use `powershell.exe -Command "Start-Process notepad"` to launch apps.

## How to Run

### Prerequisites on Windows
```
pip install mss Pillow
```

### Start the daemon on Windows
```bash
# Direct:
python daemon.py

# Or from WSL2:
powershell.exe -Command "Copy-Item '\\wsl.localhost\Ubuntu-24.04\home\santiago\Santiago\Common\Agent-Forge\computer_use\bridge\daemon.py' -Destination 'C:\Users\santiagmd11\daemon.py' -Force; python C:\Users\santiagmd11\daemon.py"
```

### Run tests (from WSL2)
```bash
source computer_use/.venv/bin/activate
PYTHONPATH=. python -m pytest computer_use/tests/ -v
```

### MCP server config (.mcp.json at project root)
Already configured. The MCP server auto-detects the bridge daemon on startup and logs "Bridge daemon detected, using fast path".

## Key Technical Details

### Why Mouse Was Erratic (Root Cause Analysis)
The root cause was a **DPI awareness mismatch**:
- Python process defaults to DPI-unaware
- `mss` sets `PROCESS_PER_MONITOR_DPI_AWARE` during its init
- `SetCursorPos` interprets coordinates based on process DPI awareness
- DPI-unaware process on 3x display: `SetCursorPos(1920, 1200)` gets virtualized to physical `(5760, 3600)` -> OFF SCREEN
- DPI-aware process: `SetCursorPos(1920, 1200)` -> physical `(1920, 1200)` -> CORRECT

**Fix:** Call `SetProcessDpiAwarenessContext(-4)` at the very top of daemon.py, before importing mss or any Win32 API.

Additionally, `SetCursorPos` + separate `SendInput` had race conditions (20ms gap where cursor could move). **Fix:** Single atomic `SendInput` call with `MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK`, move+click in one array of 3 INPUT structs.

### Coordinate Pipeline
```
Physical screen: 3840x2400 at 3x DPI (ThinkPad X1 Yoga)
1. mss captures at 3840x2400 (physical, because DPI-aware)
2. MCP server _compute_max_width(3840) -> 1366
3. MCP server downscales to 1366x853 -> these are "display coords"
4. AI model sees 1366x853 image, outputs click at (683, 427)
5. MCP _to_real(): real_x = 683 * (3840/1366) = 1920, real_y = 427 * (2400/853) = 1200
6. Bridge daemon receives (1920, 1200) over TCP
7. InputSender._normalize(): maps to 0-65535 using GetSystemMetrics(SM_CXVIRTUALSCREEN)
8. Atomic SendInput with MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
```

### WSL2 Networking
- Daemon binds `0.0.0.0:19542` (not 127.0.0.1 -- WSL2 has separate network namespace)
- Client discovers Windows host IP via default gateway in `/proc/net/route` (NOT /etc/resolv.conf which returns wrong IP on some configs)
- Windows Firewall may need an inbound rule for port 19542 from WSL2 subnet

## What to Do Next

1. **Test clipboard-based type_text** - restart daemon, open Notepad, verify multi-line text typing works
2. **If clipboard paste fails** - increase delays or try alternative paste methods
3. **Commit** - all changes are uncommitted on branch `feature/computer-use`
4. **Optional improvements:**
   - Win+R alternative via ShellExecuteW
   - patterns/10-computer-use.md pattern doc
   - agent/Prompts/05_Computer_Use_Agent.md
