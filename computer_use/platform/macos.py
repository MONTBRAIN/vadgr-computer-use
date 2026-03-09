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

"""macOS platform backend using screencapture and osascript/cliclick."""

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import ForegroundWindow, Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.macos")


class MacOSScreenCapture(ScreenCapture):
    """Screenshot capture using macOS screencapture command."""

    def capture_full(self) -> ScreenState:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", tmp_path],
                capture_output=True,
                timeout=10.0,
            )
            if result.returncode != 0:
                raise ScreenCaptureError(
                    f"screencapture failed: {result.stderr.decode()}"
                )

            with open(tmp_path, "rb") as f:
                image_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        return ScreenState(
            image_bytes=image_bytes,
            width=width,
            height=height,
            scale_factor=self.get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        # screencapture -R x,y,w,h for region capture
        rect = f"{region.x},{region.y},{region.width},{region.height}"
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-R", rect, "-t", "png", tmp_path],
                capture_output=True,
                timeout=10.0,
            )
            if result.returncode != 0:
                raise ScreenCaptureError(
                    f"screencapture region failed: {result.stderr.decode()}"
                )

            with open(tmp_path, "rb") as f:
                image_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        # Use system_profiler to get display resolution
        try:
            result = subprocess.run(
                [
                    "python3", "-c",
                    "from AppKit import NSScreen; s = NSScreen.mainScreen().frame(); "
                    "print(f'{int(s.size.width)},{int(s.size.height)}')",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                return (int(parts[0]), int(parts[1]))
        except Exception:
            pass

        # Fallback: take a screenshot and check dimensions
        screen = self.capture_full()
        return (screen.width, screen.height)

    def get_scale_factor(self) -> float:
        if sys.platform != "darwin":
            return 1.0
        try:
            result = subprocess.run(
                [
                    "python3", "-c",
                    "from AppKit import NSScreen; "
                    "print(NSScreen.mainScreen().backingScaleFactor())",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 2.0  # Default Retina


# AppleScript key code mapping
APPLESCRIPT_KEY_MAP = {
    "enter": 36, "return": 36, "tab": 48,
    "escape": 53, "esc": 53, "backspace": 51,
    "delete": 117, "del": 117,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121,
    "space": 49,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

MODIFIER_APPLESCRIPT = {
    "ctrl": "control down",
    "control": "control down",
    "alt": "option down",
    "option": "option down",
    "shift": "shift down",
    "super": "command down",
    "cmd": "command down",
    "command": "command down",
}


def _run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode != 0:
            raise ActionError(f"AppleScript error: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise ActionError("osascript not found. Are you on macOS?")


class MacOSActionExecutor(ActionExecutor):
    """Action execution using AppleScript and cliclick on macOS."""

    def __init__(self):
        self._has_cliclick = shutil.which("cliclick") is not None

    def move_mouse(self, x: int, y: int) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"m:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to '
                f"set position of mouse to {{{x}, {y}}}"
            )

    def click(self, x: int, y: int, button: str = "left") -> None:
        if self._has_cliclick:
            cmd = {"left": "c", "right": "rc", "middle": "mc"}.get(button, "c")
            subprocess.run(
                ["cliclick", f"{cmd}:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            # AppleScript click
            _run_applescript(
                f'tell application "System Events" to click at {{{x}, {y}}}'
            )

    def double_click(self, x: int, y: int) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"dc:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to double click at {{{x}, {y}}}'
            )

    def type_text(self, text: str) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"t:{text}"],
                capture_output=True,
                timeout=10.0,
            )
        else:
            # Escape for AppleScript
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            _run_applescript(
                f'tell application "System Events" to keystroke "{escaped}"'
            )

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return

        # Separate modifiers from regular keys
        modifiers = []
        regular = []
        for key in keys:
            lower = key.lower()
            if lower in MODIFIER_APPLESCRIPT:
                modifiers.append(MODIFIER_APPLESCRIPT[lower])
            elif lower in APPLESCRIPT_KEY_MAP:
                regular.append(APPLESCRIPT_KEY_MAP[lower])
            elif len(key) == 1:
                regular.append(key)

        modifier_str = ", ".join(modifiers) if modifiers else ""

        if regular and isinstance(regular[0], int):
            # Key code
            using = f" using {{{modifier_str}}}" if modifier_str else ""
            _run_applescript(
                f'tell application "System Events" to key code {regular[0]}{using}'
            )
        elif regular and isinstance(regular[0], str):
            using = f" using {{{modifier_str}}}" if modifier_str else ""
            _run_applescript(
                f'tell application "System Events" to keystroke "{regular[0]}"{using}'
            )

    def scroll(self, x: int, y: int, amount: int) -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        # Use cliclick or AppleScript for scrolling
        if self._has_cliclick:
            # cliclick doesn't support scroll, use AppleScript
            pass
        _run_applescript(
            f'tell application "System Events" to scroll area 1 by {amount}'
        )

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"dd:{start_x},{start_y}", f"du:{end_x},{end_y}"],
                capture_output=True,
                timeout=duration + 5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to click at {{{start_x}, {start_y}}}'
            )
            time.sleep(0.1)
            # AppleScript doesn't natively support drag, would need CGEvent


# TTL cache for foreground window info.
_FG_WINDOW_TTL = 0.1  # 100ms
_fg_window_cache_mac: "Optional[tuple[float, Optional[ForegroundWindow]]]" = None


def _get_foreground_window_macos() -> "Optional[ForegroundWindow]":
    global _fg_window_cache_mac
    now = time.monotonic()
    if _fg_window_cache_mac is not None:
        ts, cached = _fg_window_cache_mac
        if now - ts < _FG_WINDOW_TTL:
            return cached

    result = _query_foreground_window_macos()
    _fg_window_cache_mac = (now, result)
    return result


def _query_foreground_window_macos() -> "Optional[ForegroundWindow]":
    script = (
        'tell application "System Events"\n'
        '  set fp to first process whose frontmost is true\n'
        '  set appName to name of fp\n'
        '  set appPID to unix id of fp\n'
        '  set winTitle to ""\n'
        '  set winX to 0\n'
        '  set winY to 0\n'
        '  set winW to 0\n'
        '  set winH to 0\n'
        '  try\n'
        '    set w to window 1 of fp\n'
        '    set winTitle to name of w\n'
        '    set {winX, winY} to position of w\n'
        '    set {winW, winH} to size of w\n'
        '  end try\n'
        '  return appName & "\\n" & appPID & "\\n" & winTitle & "\\n" & winX & "\\n" & winY & "\\n" & winW & "\\n" & winH\n'
        'end tell'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=2.0,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("\n")
        if len(parts) < 7:
            return None
        return ForegroundWindow(
            app_name=parts[0],
            title=parts[2],
            x=int(parts[3]),
            y=int(parts[4]),
            width=int(parts[5]),
            height=int(parts[6]),
            pid=int(parts[1]) if parts[1].isdigit() else 0,
        )
    except Exception:
        return None


class MacOSBackend(PlatformBackend):
    """macOS platform backend."""

    def __init__(self):
        self._capture = None
        self._executor = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = MacOSScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = MacOSActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return sys.platform == "darwin"

    def get_foreground_window(self) -> "Optional[ForegroundWindow]":
        return _get_foreground_window_macos()

    def get_accessibility_info(self) -> dict:
        try:
            import AppKit

            return {
                "available": True,
                "api_name": "macOS Accessibility API",
                "notes": "pyobjc available. Ensure accessibility permissions are granted in System Preferences.",
            }
        except ImportError:
            return {
                "available": False,
                "api_name": "macOS Accessibility API",
                "notes": "pyobjc not installed. Run: pip install pyobjc-framework-ApplicationServices",
            }
