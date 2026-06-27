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

"""X11 input via XTEST (python-xlib) — the pure-python X11 input path.

XTEST is the universal X11 input-synthesis extension every X11 WM honours
(xdotool/PyAutoGUI use it too), and python-xlib is a pure wheel — so X11 input
needs no ``xdotool`` system package. The real Xlib calls sit behind ``XlibInput``
so the executor mechanics (click = move+press+release, shift handling, scroll,
drag) are unit-tested with a fake seam; the live X server is e2e territory.
"""

from __future__ import annotations

import time

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError

_BUTTONS = {"left": 1, "middle": 2, "right": 3}

# X11 keysyms for named keys (X11/keysymdef.h).
_NAMED_KEYSYMS = {
    "shift": 0xFFE1, "ctrl": 0xFFE3, "control": 0xFFE3, "alt": 0xFFE9,
    "super": 0xFFEB, "meta": 0xFFE7,
    "enter": 0xFF0D, "return": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "esc": 0xFF1B,
    "backspace": 0xFF08, "delete": 0xFFFF, "del": 0xFFFF,
    "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
    "home": 0xFF50, "end": 0xFF57, "pageup": 0xFF55, "pagedown": 0xFF56,
    "space": 0x0020,
    **{f"f{i}": 0xFFBE + (i - 1) for i in range(1, 13)},  # F1..F12
}

# Characters that require Shift on a US layout (uppercase handled separately).
_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?')


class XlibInput:
    """Real XTEST seam over python-xlib (imported lazily so X11 is optional)."""

    def __init__(self):
        try:
            from Xlib import X, display
            from Xlib.ext import xtest
        except ImportError as exc:
            raise ActionError(f"python-xlib not installed: {exc}")
        self._X = X
        self._xtest = xtest
        self._d = display.Display()
        if not self._d.query_extension("XTEST"):
            raise ActionError("X server has no XTEST extension")

    def motion(self, x: int, y: int) -> None:
        self._xtest.fake_input(self._d, self._X.MotionNotify, x=x, y=y)
        self._d.sync()

    def button(self, num: int, press: bool) -> None:
        etype = self._X.ButtonPress if press else self._X.ButtonRelease
        self._xtest.fake_input(self._d, etype, num)
        self._d.sync()

    def key(self, code: int, press: bool) -> None:
        etype = self._X.KeyPress if press else self._X.KeyRelease
        self._xtest.fake_input(self._d, etype, code)
        self._d.sync()

    def keysym_to_keycode(self, keysym: int) -> int:
        return self._d.keysym_to_keycode(keysym)

    def char_to_keysym(self, ch: str) -> int:
        return ord(ch)  # Latin-1 keysyms equal the codepoint

    def sync(self) -> None:
        self._d.sync()


class XTestExecutor(ActionExecutor):
    """ActionExecutor backed by XTEST."""

    def __init__(self, xinput: "XlibInput | None" = None):
        self._x = xinput or XlibInput()

    def _code(self, keysym: int) -> int:
        return self._x.keysym_to_keycode(keysym)

    def move_mouse(self, x: int, y: int) -> None:
        self._x.motion(x, y)

    def click(self, x: int, y: int, button: str = "left") -> None:
        num = _BUTTONS.get(button, 1)
        self._x.motion(x, y)
        self._x.button(num, True)
        self._x.button(num, False)

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        self.click(x, y)

    def type_text(self, text: str) -> None:
        shift = self._code(_NAMED_KEYSYMS["shift"])
        for ch in text:
            if ch == "\n":
                self._tap(self._code(_NAMED_KEYSYMS["enter"]))
                continue
            if ch == "\t":
                self._tap(self._code(_NAMED_KEYSYMS["tab"]))
                continue
            need_shift = ch.isupper() or ch in _SHIFTED
            code = self._code(self._x.char_to_keysym(ch))
            if need_shift:
                self._x.key(shift, True)
            self._tap(code)
            if need_shift:
                self._x.key(shift, False)

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return
        codes = []
        for k in keys:
            keysym = _NAMED_KEYSYMS.get(k.lower())
            if keysym is None and len(k) == 1:
                keysym = self._x.char_to_keysym(k)
            if keysym is None:
                raise ActionError(f"unknown key: {k}")
            codes.append(self._code(keysym))
        for c in codes:
            self._x.key(c, True)
        for c in reversed(codes):
            self._x.key(c, False)

    def scroll(self, x: int, y: int, amount: int) -> None:
        self._x.motion(x, y)
        num = 4 if amount > 0 else 5
        for _ in range(abs(amount)):
            self._x.button(num, True)
            self._x.button(num, False)

    def drag(self, start_x, start_y, end_x, end_y, duration: float = 0.5) -> None:
        self._x.motion(start_x, start_y)
        self._x.button(1, True)
        steps = 10
        for i in range(1, steps + 1):
            px = start_x + (end_x - start_x) * i // steps
            py = start_y + (end_y - start_y) * i // steps
            self._x.motion(px, py)
            if duration:
                time.sleep(duration / steps)
        self._x.button(1, False)

    def _tap(self, code: int) -> None:
        self._x.key(code, True)
        self._x.key(code, False)
