# Copyright 2026 Victor Santiago Montano Diaz
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

"""macOS platform backend.

Capture: mss (returns logical-point images, matching CGEvent's coordinate
space, so no scale-factor math is needed for clicks).

Input: Quartz CGEvent APIs via pyobjc-framework-Quartz. Permission
prompts (Accessibility + Screen Recording) are fired on backend
construction so the user lands directly in System Settings on first run.
"""

import io
import logging
import random
import subprocess
import sys
import time
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.smooth_move import (
    CursorTracker,
    DRAG_GRAVITY,
    DRAG_MAX_VEL,
    DRAG_WIND,
    PRE_CLICK_BASE,
    PRE_CLICK_RAND,
    PRE_DRAG_BASE,
    PRE_DRAG_RAND,
    generate_delays,
    smooth_move,
    windmouse_path,
)
from computer_use.core.types import ForegroundWindow, Region, ScreenState
from computer_use.platform.base import AvailabilityReport, PlatformBackend

logger = logging.getLogger("computer_use.platform.macos")

try:
    import Quartz as _Quartz  # type: ignore[import-not-found]
except ImportError:
    _Quartz = None  # type: ignore[assignment]

try:
    import HIServices as _HIServices  # type: ignore[import-not-found]
except ImportError:
    _HIServices = None  # type: ignore[assignment]

try:
    import mss as _mss  # type: ignore[import-not-found]
except ImportError:
    _mss = None  # type: ignore[assignment]


# Standard ANSI keycodes. Apple ships these as constants in the headers
# but pyobjc does not export them by name; the values are stable across
# every macOS release since 10.5.
_CGKEYCODE: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "enter": 36, "return": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "tab": 48, "space": 49, " ": 49, "`": 50,
    "backspace": 51, "delete": 51,
    "escape": 53, "esc": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "del": 117,
}


def _modifier_flag(name: str) -> int:
    if _Quartz is None:
        return 0
    name = name.lower()
    if name in ("ctrl", "control"):
        return _Quartz.kCGEventFlagMaskControl
    if name in ("alt", "option"):
        return _Quartz.kCGEventFlagMaskAlternate
    if name == "shift":
        return _Quartz.kCGEventFlagMaskShift
    if name in ("cmd", "command", "super", "win"):
        return _Quartz.kCGEventFlagMaskCommand
    return 0


def _is_modifier(name: str) -> bool:
    return name.lower() in {
        "ctrl", "control", "alt", "option", "shift",
        "cmd", "command", "super", "win",
    }


# ---------------------------------------------------------------------------
# Permission preflight
# ---------------------------------------------------------------------------
#
# Apple does not re-pop the Screen Recording dialog once a TCC entry exists
# for a binary, even if the entry is disabled. To recover from a revoked
# state without forcing the user to hunt through System Settings, we
# preflight every capture/input call and, on denial, deep-link the user
# straight to the relevant Privacy pane via the documented URL scheme,
# then raise a structured error.


def _settings_open(pane: str) -> None:
    url = (
        "x-apple.systempreferences:com.apple.preference.security"
        f"?Privacy_{pane}"
    )
    try:
        subprocess.run(["open", url], capture_output=True, timeout=2.0)
    except Exception as e:
        logger.debug("Failed to open Settings pane %s: %s", pane, e)


def _require_screen_recording() -> None:
    if _Quartz is None:
        return
    try:
        granted = bool(_Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        granted = False
    if granted:
        return
    _settings_open("ScreenCapture")
    raise ScreenCaptureError(
        f"macOS Screen Recording is not granted for {sys.executable}. "
        "System Settings has been opened to Privacy & Security -> "
        "Screen Recording. Enable the entry for this Python interpreter "
        "and retry."
    )


def _require_accessibility() -> None:
    if _HIServices is None:
        return
    try:
        trusted = bool(_HIServices.AXIsProcessTrusted())
    except Exception:
        trusted = False
    if trusted:
        return
    _settings_open("Accessibility")
    raise ActionError(
        f"macOS Accessibility is not granted for {sys.executable}. "
        "System Settings has been opened to Privacy & Security -> "
        "Accessibility. Enable the entry for this Python interpreter "
        "and retry."
    )


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------


def _shot_to_png_bytes(shot, width: int, height: int) -> bytes:
    from PIL import Image

    img = Image.frombytes("RGB", (width, height), shot.bgra, "raw", "BGRX")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class MacOSScreenCapture(ScreenCapture):
    def __init__(self):
        if _mss is None:
            raise ScreenCaptureError(
                "mss is missing. Run: pip install vadgr-computer-use"
            )

    def capture_full(self) -> ScreenState:
        _require_screen_recording()
        with _mss.mss() as m:
            mon = m.monitors[1]
            shot = m.grab(mon)
        png = _shot_to_png_bytes(shot, shot.width, shot.height)
        return ScreenState(
            image_bytes=png,
            width=shot.width,
            height=shot.height,
            scale_factor=self.get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        _require_screen_recording()
        rect = {
            "left": region.x,
            "top": region.y,
            "width": region.width,
            "height": region.height,
        }
        with _mss.mss() as m:
            shot = m.grab(rect)
        png = _shot_to_png_bytes(shot, region.width, region.height)
        return ScreenState(
            image_bytes=png,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        if _Quartz is None:
            raise ScreenCaptureError("Quartz not available")
        bounds = _Quartz.CGDisplayBounds(_Quartz.CGMainDisplayID())
        return (int(bounds.size.width), int(bounds.size.height))

    def get_scale_factor(self) -> float:
        if _Quartz is None:
            return 1.0
        display_id = _Quartz.CGMainDisplayID()
        # CGDisplayPixelsWide returns logical points on macOS 26+, so we
        # read the active display mode's pixel/point widths instead.
        try:
            mode = _Quartz.CGDisplayCopyDisplayMode(display_id)
            pixels = float(_Quartz.CGDisplayModeGetPixelWidth(mode))
            points = float(_Quartz.CGDisplayModeGetWidth(mode))
            if points > 0:
                return pixels / points
        except Exception:
            pass
        return 1.0


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------


class MacOSActionExecutor(ActionExecutor):
    def __init__(self):
        if _Quartz is None:
            raise ActionError(
                "Quartz not available. Run: pip install vadgr-computer-use"
            )
        self._tracker = CursorTracker()
        self._sync_tracker_with_system()

    def _sync_tracker_with_system(self) -> None:
        ev = _Quartz.CGEventCreate(None)
        if ev is not None:
            loc = _Quartz.CGEventGetLocation(ev)
            self._tracker.update(int(loc.x), int(loc.y))

    def _post_mouse(
        self,
        event_type: int,
        x: int,
        y: int,
        button: int = 0,
        click_state: Optional[int] = None,
        flags: Optional[int] = None,
    ) -> None:
        ev = _Quartz.CGEventCreateMouseEvent(None, event_type, (x, y), button)
        if click_state is not None:
            _Quartz.CGEventSetIntegerValueField(
                ev, _Quartz.kCGMouseEventClickState, click_state
            )
        if flags is not None:
            _Quartz.CGEventSetFlags(ev, flags)
        _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev)

    def _raw_move(self, x: int, y: int) -> None:
        self._post_mouse(_Quartz.kCGEventMouseMoved, x, y)
        self._tracker.update(x, y)

    def move_mouse(self, x: int, y: int) -> None:
        _require_accessibility()
        smooth_move(x, y, self._tracker.get_pos, self._raw_move)

    def _button_constants(self, button: str):
        if button == "right":
            return (
                _Quartz.kCGEventRightMouseDown,
                _Quartz.kCGEventRightMouseUp,
                _Quartz.kCGMouseButtonRight,
            )
        if button == "middle":
            return (
                _Quartz.kCGEventOtherMouseDown,
                _Quartz.kCGEventOtherMouseUp,
                _Quartz.kCGMouseButtonCenter,
            )
        return (
            _Quartz.kCGEventLeftMouseDown,
            _Quartz.kCGEventLeftMouseUp,
            _Quartz.kCGMouseButtonLeft,
        )

    def click(self, x: int, y: int, button: str = "left") -> None:
        _require_accessibility()
        self.move_mouse(x, y)
        time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
        down, up, btn = self._button_constants(button)
        self._post_mouse(down, x, y, btn)
        self._post_mouse(up, x, y, btn)

    def double_click(self, x: int, y: int) -> None:
        _require_accessibility()
        self.move_mouse(x, y)
        time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
        btn = _Quartz.kCGMouseButtonLeft
        # macOS recognizes a double-click when the second mouse-down event
        # carries clickState=2; the first pair stays at clickState=1.
        self._post_mouse(_Quartz.kCGEventLeftMouseDown, x, y, btn, click_state=1)
        self._post_mouse(_Quartz.kCGEventLeftMouseUp, x, y, btn, click_state=1)
        self._post_mouse(_Quartz.kCGEventLeftMouseDown, x, y, btn, click_state=2)
        self._post_mouse(_Quartz.kCGEventLeftMouseUp, x, y, btn, click_state=2)

    def type_text(self, text: str) -> None:
        _require_accessibility()
        for ch in text:
            ev_down = _Quartz.CGEventCreateKeyboardEvent(None, 0, True)
            _Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(ch), ch)
            _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev_down)
            ev_up = _Quartz.CGEventCreateKeyboardEvent(None, 0, False)
            _Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
            _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev_up)
            time.sleep(0.005)

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return
        _require_accessibility()

        flags = 0
        keycodes: list[int] = []
        for key in keys:
            if _is_modifier(key):
                flags |= _modifier_flag(key)
                continue
            kc = _CGKEYCODE.get(key.lower())
            if kc is None:
                logger.warning("Unknown key: %s", key)
                continue
            keycodes.append(kc)

        for kc in keycodes:
            ev = _Quartz.CGEventCreateKeyboardEvent(None, kc, True)
            _Quartz.CGEventSetFlags(ev, flags)
            _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev)
        for kc in reversed(keycodes):
            ev = _Quartz.CGEventCreateKeyboardEvent(None, kc, False)
            _Quartz.CGEventSetFlags(ev, flags)
            _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev)

    def scroll(self, x: int, y: int, amount: int) -> None:
        _require_accessibility()
        self._raw_move(x, y)
        time.sleep(0.05)
        ev = _Quartz.CGEventCreateScrollWheelEvent(
            None, _Quartz.kCGScrollEventUnitLine, 1, amount
        )
        _Quartz.CGEventPost(_Quartz.kCGHIDEventTap, ev)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        _require_accessibility()
        self.move_mouse(start_x, start_y)
        time.sleep(PRE_DRAG_BASE + random.random() * PRE_DRAG_RAND)
        btn = _Quartz.kCGMouseButtonLeft
        self._post_mouse(_Quartz.kCGEventLeftMouseDown, start_x, start_y, btn)
        path = windmouse_path(
            start_x, start_y, end_x, end_y,
            gravity=DRAG_GRAVITY, wind=DRAG_WIND, max_vel=DRAG_MAX_VEL,
        )
        delays = generate_delays(len(path), duration)
        for i, (px, py) in enumerate(path):
            self._post_mouse(_Quartz.kCGEventLeftMouseDragged, px, py, btn)
            self._tracker.update(px, py)
            if i < len(delays):
                time.sleep(delays[i])
        self._post_mouse(_Quartz.kCGEventLeftMouseUp, end_x, end_y, btn)


# ---------------------------------------------------------------------------
# Foreground window (kept on AppleScript: cheap, only used for introspection)
# ---------------------------------------------------------------------------


_FG_WINDOW_TTL = 0.1
_fg_window_cache_mac: "Optional[tuple[float, Optional[ForegroundWindow]]]" = None


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
        '  return appName & "\\n" & appPID & "\\n" & winTitle & "\\n"'
        ' & winX & "\\n" & winY & "\\n" & winW & "\\n" & winH\n'
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


# ---------------------------------------------------------------------------
# Permission status (used by `vadgr-cua doctor`)
# ---------------------------------------------------------------------------


_AX_GRANT_POLL_TIMEOUT = 30.0
_AX_GRANT_POLL_INTERVAL = 0.5


def _ax_trusted_safe() -> bool:
    if _HIServices is None:
        return False
    try:
        return bool(_HIServices.AXIsProcessTrusted())
    except Exception:
        return False


def _sr_granted_safe() -> bool:
    if _Quartz is None:
        return False
    try:
        return bool(_Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def _fire_ax_prompt() -> None:
    if _HIServices is None:
        return
    try:
        key = getattr(
            _HIServices, "kAXTrustedCheckOptionPrompt",
            "AXTrustedCheckOptionPrompt",
        )
        _HIServices.AXIsProcessTrustedWithOptions({key: True})
    except Exception as e:
        logger.debug("AXIsProcessTrustedWithOptions failed: %s", e)


def _fire_sr_prompt() -> None:
    if _Quartz is None:
        return
    try:
        _Quartz.CGRequestScreenCaptureAccess()
    except Exception as e:
        logger.debug("CGRequestScreenCaptureAccess failed: %s", e)


def request_permissions() -> None:
    """Fire macOS permission prompts in the correct order.

    macOS shows only one TCC dialog at a time per process, so the AX and
    SR prompts must be serialized. We fire AX first (it always re-pops
    reliably from a non-trusted process), poll for the user to act on
    it, then fire the SR prompt and open the Settings pane as a
    parallel-safe visual fallback.
    """
    if sys.platform != "darwin":
        return
    if _HIServices is None or _Quartz is None:
        return

    ax_trusted = _ax_trusted_safe()
    sr_granted = _sr_granted_safe()
    if ax_trusted and sr_granted:
        return

    if not ax_trusted:
        _fire_ax_prompt()
        deadline = time.monotonic() + _AX_GRANT_POLL_TIMEOUT
        while time.monotonic() < deadline:
            if _ax_trusted_safe():
                break
            time.sleep(_AX_GRANT_POLL_INTERVAL)

    if not sr_granted:
        _fire_sr_prompt()
        _settings_open("ScreenCapture")


def macos_permission_status() -> dict:
    if sys.platform != "darwin" or _Quartz is None:
        return {}
    try:
        ax = bool(_HIServices.AXIsProcessTrusted()) if _HIServices else False
    except Exception:
        ax = False
    try:
        sr = bool(_Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        sr = False
    return {
        "macos_accessibility_granted": ax,
        "macos_screen_recording_granted": sr,
        "python_executable": sys.executable,
    }


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class MacOSBackend(PlatformBackend):
    def __init__(self):
        self._capture: Optional[MacOSScreenCapture] = None
        self._executor: Optional[MacOSActionExecutor] = None
        if sys.platform == "darwin":
            self._request_permissions()

    def _request_permissions(self) -> None:
        request_permissions()

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = MacOSScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = MacOSActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return self.availability_report().available

    def availability_report(self) -> AvailabilityReport:
        if sys.platform != "darwin":
            return AvailabilityReport(
                available=False,
                missing=("darwin",),
                remediation="MacOS backend only runs on macOS.",
            )
        missing: list[str] = []
        if _Quartz is None:
            missing.append("pyobjc-framework-Quartz")
        if _mss is None:
            missing.append("mss")
        if missing:
            return AvailabilityReport(
                available=False,
                missing=tuple(missing),
                remediation=(
                    "Required Python packages are missing. "
                    "Run: pip install vadgr-computer-use"
                ),
            )
        return AvailabilityReport(available=True)

    def get_foreground_window(self) -> Optional[ForegroundWindow]:
        return _get_foreground_window_macos()
