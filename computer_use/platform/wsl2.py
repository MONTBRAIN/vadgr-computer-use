# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""WSL2 platform backend using PowerShell bridge to control Windows desktop."""

import atexit
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import ForegroundWindow, Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.wsl2")

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

# One-time DPI awareness init for the persistent PowerShell process.
# Makes all WinForms calls (Screen.Bounds, CopyFromScreen, Cursor.Position)
# return physical pixels instead of DPI-virtualized logical pixels.
# Fallback chain: PerMonitorV2 (-4) -> PerMonitor (2) -> SystemAware (legacy).
_DPI_INIT_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class DpiInit {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);

    [DllImport("shcore.dll", SetLastError=true)]
    public static extern int SetProcessDpiAwareness(int awareness);

    [DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();

    public static void Enable() {
        try { if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return; } catch {}
        try { if (SetProcessDpiAwareness(2) == 0) return; } catch {}
        try { SetProcessDPIAware(); } catch {}
    }
}
'@
[DpiInit]::Enable()
"""


class PersistentPowerShell:
    """One long-lived powershell.exe that we pipe scripts into.

    Scripts go in via stdin, output is read until a unique sentinel line.
    Thread-safe, auto-restarts on crash, cleaned up at exit.
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._started = False
        atexit.register(self.shutdown)

    def _start(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        self._proc = subprocess.Popen(
            [POWERSHELL, "-NoProfile", "-NoLogo", "-NonInteractive", "-Command", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._started = True
        logger.debug("Persistent PowerShell started (pid=%d)", self._proc.pid)

        # Set per-process DPI awareness so all subsequent WinForms calls
        # (screenshot, mouse, screen bounds) use physical pixels.
        # Write directly to stdin (not via self.run) to avoid deadlock
        # since _start() is called from within run() which holds the lock.
        sentinel = f"__SENTINEL_{uuid.uuid4().hex}__"
        self._proc.stdin.write(f"{_DPI_INIT_SCRIPT}\nWrite-Output '{sentinel}'\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line or line.rstrip("\r\n") == sentinel:
                break

    def run(self, script: str, timeout: float = 15.0) -> str:
        with self._lock:
            if not self._started or self._proc is None or self._proc.poll() is not None:
                self._start()

            sentinel = f"__SENTINEL_{uuid.uuid4().hex}__"
            wrapped = f"{script}\nWrite-Output '{sentinel}'\n"

            try:
                self._proc.stdin.write(wrapped)
                self._proc.stdin.flush()
            except (OSError, BrokenPipeError) as e:
                logger.warning("Persistent PS stdin write failed: %s. Restarting.", e)
                self._start()
                self._proc.stdin.write(wrapped)
                self._proc.stdin.flush()

            lines: list[str] = []
            import time

            deadline = time.monotonic() + timeout
            while True:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Persistent PowerShell timed out after {timeout}s"
                    )
                if self._proc.poll() is not None:
                    raise RuntimeError("Persistent PowerShell process died unexpectedly")
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("Persistent PowerShell stdout closed")
                stripped = line.rstrip("\r\n")
                if stripped == sentinel:
                    break
                lines.append(stripped)

            return "\n".join(lines).strip()

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def shutdown(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            self._started = False
            logger.debug("Persistent PowerShell shut down")


# Module-level singleton (lazy)
_persistent_ps: PersistentPowerShell | None = None
_persistent_ps_lock = threading.Lock()



def wsl_to_win_path(wsl_path: str) -> str:
    """Convert /mnt/c/Users/... to C:\\Users\\..."""
    if wsl_path.startswith("/mnt/"):
        drive = wsl_path[5]
        rest = wsl_path[6:].replace("/", "\\")
        return f"{drive.upper()}:{rest}"
    return wsl_path


def win_to_wsl_path(win_path: str) -> str:
    """Convert C:\\Users\\... to /mnt/c/Users/..."""
    if len(win_path) >= 2 and win_path[1] == ":":
        drive = win_path[0].lower()
        rest = win_path[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return win_path


def _get_windows_temp_dir() -> str:
    """Get a Windows temp directory accessible from WSL2."""
    user = os.environ.get("USER", "")
    candidates = [
        f"/mnt/c/Users/{user}/AppData/Local/Temp",
        "/mnt/c/Temp",
        "/mnt/c/Windows/Temp",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    # Fallback: ask PowerShell
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", "$env:TEMP"],
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    if result.returncode == 0 and result.stdout.strip():
        return win_to_wsl_path(result.stdout.strip())
    raise ScreenCaptureError("Cannot determine Windows temp directory from WSL2")


def _run_ps_subprocess(script: str, timeout: float = 15.0) -> str:
    """One-shot subprocess fallback for _run_ps."""
    win_temp = _get_windows_temp_dir()
    script_path = os.path.join(win_temp, "cue_temp.ps1")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    try:
        win_script_path = wsl_to_win_path(script_path)
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                win_script_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"PowerShell error (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.strip()
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _run_ps(script: str, timeout: float = 15.0) -> str:
    """Run a PowerShell script, using persistent process with subprocess fallback."""
    global _persistent_ps
    with _persistent_ps_lock:
        if _persistent_ps is None:
            _persistent_ps = PersistentPowerShell()

    try:
        return _persistent_ps.run(script, timeout=timeout)
    except Exception as e:
        logger.debug("Persistent PS failed (%s), falling back to subprocess", e)
        return _run_ps_subprocess(script, timeout=timeout)



# Inline DPI preamble for one-shot subprocess scripts (where the persistent
# PS init hasn't run). Uses the legacy SetProcessDPIAware() for brevity;
# the persistent path uses the full fallback chain above.
_DPI_PREAMBLE = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Dpi {{ [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }}
'@ -ErrorAction SilentlyContinue
[Dpi]::SetProcessDPIAware() | Out-Null
"""

CAPTURE_FULL_SCRIPT = _DPI_PREAMBLE + """
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$scr = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($scr.Width, $scr.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($scr.Location, [System.Drawing.Point]::Empty, $scr.Size)
$bitmap.Save("{output_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "$($scr.Width),$($scr.Height),$($scr.X),$($scr.Y)"
"""

CAPTURE_REGION_SCRIPT = _DPI_PREAMBLE + """
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bitmap = New-Object System.Drawing.Bitmap({width}, {height})
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$src = New-Object System.Drawing.Point({x}, {y})
$dst = [System.Drawing.Point]::Empty
$size = New-Object System.Drawing.Size({width}, {height})
$graphics.CopyFromScreen($src, $dst, $size)
$bitmap.Save("{output_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "{width},{height}"
"""

SCREEN_SIZE_SCRIPT = _DPI_PREAMBLE + """
Add-Type -AssemblyName System.Windows.Forms
$scr = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
Write-Output "$($scr.Width),$($scr.Height)"
"""

SCALE_FACTOR_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("gdi32.dll")] public static extern int GetDeviceCaps(IntPtr hdc, int index);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
    public static float GetScale() {
        IntPtr hdc = GetDC(IntPtr.Zero);
        int dpi = GetDeviceCaps(hdc, 88);
        ReleaseDC(IntPtr.Zero, hdc);
        return dpi / 96.0f;
    }
}
'@
Write-Output ([DpiHelper]::GetScale())
"""


class WSL2ScreenCapture(ScreenCapture):

    def __init__(self):
        self._win_temp = _get_windows_temp_dir()

    def capture_full(self) -> ScreenState:
        output_wsl = os.path.join(self._win_temp, "cue_screenshot.png")
        output_win = wsl_to_win_path(output_wsl)
        script = CAPTURE_FULL_SCRIPT.format(output_path=output_win)

        try:
            result = _run_ps(script)
        except Exception as e:
            raise ScreenCaptureError(f"Full screenshot failed: {e}") from e

        try:
            with open(output_wsl, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            raise ScreenCaptureError(f"Cannot read screenshot file: {e}") from e
        finally:
            try:
                os.unlink(output_wsl)
            except OSError:
                pass

        parts = result.split(",")
        width = int(parts[0])
        height = int(parts[1])
        offset_x = int(parts[2]) if len(parts) > 2 else 0
        offset_y = int(parts[3]) if len(parts) > 3 else 0

        return ScreenState(
            image_bytes=image_bytes,
            width=width,
            height=height,
            scale_factor=self.get_scale_factor(),
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def capture_region(self, region: Region) -> ScreenState:
        output_wsl = os.path.join(self._win_temp, "cue_screenshot_region.png")
        output_win = wsl_to_win_path(output_wsl)
        script = CAPTURE_REGION_SCRIPT.format(
            x=region.x,
            y=region.y,
            width=region.width,
            height=region.height,
            output_path=output_win,
        )

        try:
            _run_ps(script)
        except Exception as e:
            raise ScreenCaptureError(f"Region screenshot failed: {e}") from e

        try:
            with open(output_wsl, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            raise ScreenCaptureError(f"Cannot read screenshot file: {e}") from e
        finally:
            try:
                os.unlink(output_wsl)
            except OSError:
                pass

        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        try:
            result = _run_ps(SCREEN_SIZE_SCRIPT)
            parts = result.split(",")
            return (int(parts[0]), int(parts[1]))
        except Exception as e:
            raise ScreenCaptureError(f"Cannot get screen size: {e}") from e

    def get_scale_factor(self) -> float:
        try:
            result = _run_ps(SCALE_FACTOR_SCRIPT)
            return float(result)
        except Exception:
            return 1.0



SMOOTH_MOVE_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
$start = [System.Windows.Forms.Cursor]::Position
$endX = {x}
$endY = {y}
$steps = {steps}
for ($i = 1; $i -le $steps; $i++) {{
    $t = $i / $steps
    $cx = [int]($start.X + ($endX - $start.X) * $t)
    $cy = [int]($start.Y + ($endY - $start.Y) * $t)
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($cx, $cy)
    Start-Sleep -Milliseconds {delay}
}}
"""

MOUSE_EVENT_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class MouseInput {{
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    public const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
    public const uint MOUSEEVENTF_MIDDLEUP = 0x0040;
    public const uint MOUSEEVENTF_WHEEL = 0x0800;
}}
'@
Add-Type -AssemblyName System.Windows.Forms
$start = [System.Windows.Forms.Cursor]::Position
$endX = {x}
$endY = {y}
$steps = {steps}
for ($i = 1; $i -le $steps; $i++) {{
    $t = $i / $steps
    $cx = [int]($start.X + ($endX - $start.X) * $t)
    $cy = [int]($start.Y + ($endY - $start.Y) * $t)
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($cx, $cy)
    Start-Sleep -Milliseconds {delay}
}}
Start-Sleep -Milliseconds 50
{mouse_actions}
"""

SENDKEYS_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("{text}")
"""

# Virtual key codes for keybd_event (used for keys SendKeys can't handle, like Win)
VK_CODES = {
    "win": 0x5B, "super": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "ctrl": 0xA2, "control": 0xA2, "alt": 0xA4, "shift": 0xA0,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

KEYBD_EVENT_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KeyInput {{
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, IntPtr dwExtraInfo);
    public const uint KEYEVENTF_KEYUP = 0x0002;
}}
'@
{key_actions}
"""

# Mapping from key names to SendKeys format
SENDKEYS_MAP = {
    "enter": "{ENTER}",
    "return": "{ENTER}",
    "tab": "{TAB}",
    "escape": "{ESC}",
    "esc": "{ESC}",
    "backspace": "{BS}",
    "delete": "{DEL}",
    "del": "{DEL}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "f1": "{F1}",
    "f2": "{F2}",
    "f3": "{F3}",
    "f4": "{F4}",
    "f5": "{F5}",
    "f6": "{F6}",
    "f7": "{F7}",
    "f8": "{F8}",
    "f9": "{F9}",
    "f10": "{F10}",
    "f11": "{F11}",
    "f12": "{F12}",
    "space": " ",
}

# Modifier key prefixes for SendKeys
MODIFIER_MAP = {
    "ctrl": "^",
    "control": "^",
    "alt": "%",
    "shift": "+",
}


SMOOTH_MOVE_STEPS = 20
SMOOTH_MOVE_DELAY_MS = 10


class WSL2ActionExecutor(ActionExecutor):

    def move_mouse(self, x: int, y: int) -> None:
        script = SMOOTH_MOVE_SCRIPT.format(
            x=x, y=y, steps=SMOOTH_MOVE_STEPS, delay=SMOOTH_MOVE_DELAY_MS
        )
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Mouse move failed: {e}") from e

    def click(self, x: int, y: int, button: str = "left") -> None:
        if button == "left":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        elif button == "right":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_RIGHTUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        elif button == "middle":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_MIDDLEUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        else:
            raise ActionError(f"Unknown mouse button: {button}")

        script = MOUSE_EVENT_SCRIPT.format(
            x=x, y=y, steps=SMOOTH_MOVE_STEPS, delay=SMOOTH_MOVE_DELAY_MS,
            mouse_actions=actions,
        )
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Click failed at ({x}, {y}): {e}") from e

    def double_click(self, x: int, y: int) -> None:
        actions = (
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)\n"
            "Start-Sleep -Milliseconds 50\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)"
        )
        script = MOUSE_EVENT_SCRIPT.format(
            x=x, y=y, steps=SMOOTH_MOVE_STEPS, delay=SMOOTH_MOVE_DELAY_MS,
            mouse_actions=actions,
        )
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Double-click failed at ({x}, {y}): {e}") from e

    def type_text(self, text: str) -> None:
        # Escape special SendKeys characters: +, ^, %, ~, (, ), {, }, [, ]
        escaped = ""
        for ch in text:
            if ch in ("+", "^", "%", "~", "(", ")", "{", "}", "[", "]"):
                escaped += "{" + ch + "}"
            else:
                escaped += ch
        script = SENDKEYS_SCRIPT.format(text=escaped)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Type text failed: {e}") from e

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return

        # Check if any key requires keybd_event (e.g., Win key)
        needs_keybd = any(k.lower() in ("win", "super", "lwin", "rwin") for k in keys)

        if needs_keybd:
            self._key_press_via_keybd(keys)
        else:
            self._key_press_via_sendkeys(keys)

    def _key_press_via_sendkeys(self, keys: list[str]) -> None:
        modifiers = []
        regular_keys = []
        for key in keys:
            lower = key.lower()
            if lower in MODIFIER_MAP:
                modifiers.append(MODIFIER_MAP[lower])
            elif lower in SENDKEYS_MAP:
                regular_keys.append(SENDKEYS_MAP[lower])
            else:
                regular_keys.append(key)

        prefix = "".join(modifiers)
        if len(regular_keys) > 1:
            keys_str = "(" + "".join(regular_keys) + ")"
        elif regular_keys:
            keys_str = regular_keys[0]
        else:
            keys_str = ""

        sendkeys_str = prefix + keys_str
        script = SENDKEYS_SCRIPT.format(text=sendkeys_str)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Key press failed for {keys}: {e}") from e

    def _key_press_via_keybd(self, keys: list[str]) -> None:
        actions = []
        vk_codes_used = []
        for key in keys:
            lower = key.lower()
            vk = VK_CODES.get(lower)
            if vk is None:
                raise ActionError(f"Unknown key for keybd_event: {key}")
            vk_codes_used.append(vk)
            actions.append(f"[KeyInput]::keybd_event({vk}, 0, 0, [IntPtr]::Zero)")

        actions.append("Start-Sleep -Milliseconds 50")

        for vk in reversed(vk_codes_used):
            actions.append(f"[KeyInput]::keybd_event({vk}, 0, [KeyInput]::KEYEVENTF_KEYUP, [IntPtr]::Zero)")

        script = KEYBD_EVENT_SCRIPT.format(key_actions="\n".join(actions))
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Key press failed for {keys}: {e}") from e

    def scroll(self, x: int, y: int, amount: int) -> None:
        # WHEEL_DELTA is 120 per notch
        wheel_amount = amount * 120
        actions = f"[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_WHEEL, 0, 0, {wheel_amount}, [IntPtr]::Zero)"
        script = MOUSE_EVENT_SCRIPT.format(
            x=x, y=y, steps=SMOOTH_MOVE_STEPS, delay=SMOOTH_MOVE_DELAY_MS,
            mouse_actions=actions,
        )
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Scroll failed at ({x}, {y}): {e}") from e

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        # Compute intermediate steps for smooth drag
        steps = max(int(duration * 60), 10)  # ~60 fps
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps
        sleep_ms = int((duration * 1000) / steps)

        move_lines = []
        for i in range(steps + 1):
            cx = int(start_x + dx * i)
            cy = int(start_y + dy * i)
            move_lines.append(
                f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({cx}, {cy})"
            )
            if i < steps:
                move_lines.append(f"Start-Sleep -Milliseconds {sleep_ms}")

        script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class MouseInput {{
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
}}
'@
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({start_x}, {start_y})
Start-Sleep -Milliseconds 50
[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)
{chr(10).join(move_lines)}
[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)
"""
        try:
            _run_ps(script, timeout=duration + 10.0)
        except Exception as e:
            raise ActionError(
                f"Drag failed from ({start_x},{start_y}) to ({end_x},{end_y}): {e}"
            ) from e

class WSL2Backend(PlatformBackend):

    def __init__(self, supervisor=None):
        self._capture = None
        self._executor = None
        self._bridge = None
        self._use_bridge = None  # None=unchecked, True/False after probe
        # Injected for testability. Default: real DaemonSupervisor.
        # Imported lazily to keep this module import-cheap on non-WSL2 paths.
        if supervisor is None:
            from computer_use.bridge.supervisor import DaemonSupervisor
            supervisor = DaemonSupervisor()
        self._supervisor = supervisor

    def _probe_bridge(self) -> bool:
        """Check if the bridge daemon is available. Launch it if it isn't.

        Result is cached for the lifetime of this backend instance.
        Delegates lifecycle decisions to the injected DaemonSupervisor.
        """
        if self._use_bridge is None:
            self._bridge = self._supervisor.ensure_running()
            self._use_bridge = self._bridge is not None
            if self._use_bridge:
                logger.info("Bridge daemon ready, using fast path")
            else:
                logger.info(
                    "Bridge daemon unavailable, using PowerShell fallback. "
                    "Run `vadgr-cua install-daemon` for a guided setup."
                )
        return self._use_bridge

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            if self._probe_bridge():
                from computer_use.bridge.capture import BridgeScreenCapture
                self._capture = BridgeScreenCapture(self._bridge)
            else:
                self._capture = WSL2ScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            if self._probe_bridge():
                from computer_use.bridge.actions import BridgeActionExecutor
                ps_fallback = WSL2ActionExecutor()
                self._executor = BridgeActionExecutor(self._bridge, fallback=ps_fallback)
            else:
                self._executor = WSL2ActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        # Bridge daemon (native Windows TCP server) is the primary path --
        # it doesn't need powershell.exe on PATH at all.
        if self._probe_bridge():
            return True
        # Fallback: PowerShell subprocess (needs powershell.exe on PATH).
        # On WSL2 with appendWindowsPath=false, shutil.which won't find it.
        return shutil.which("powershell.exe") is not None

    def get_foreground_window(self):
        if self._probe_bridge() and self._bridge is not None:
            try:
                result = self._bridge.call("foreground_window", timeout=2.0)
                if "error" in result:
                    return None
                return ForegroundWindow(
                    app_name=result.get("app_name", ""),
                    title=result.get("title", ""),
                    x=result.get("x", 0),
                    y=result.get("y", 0),
                    width=result.get("width", 0),
                    height=result.get("height", 0),
                    pid=result.get("pid", 0),
                )
            except Exception:
                return None
        return None

