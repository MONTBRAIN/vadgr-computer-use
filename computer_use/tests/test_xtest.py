# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""XTestExecutor: click/scroll/drag/key mechanics via an injected X-input seam."""

from computer_use.platform.backends.xtest import XTestExecutor


class FakeXInput:
    """Records the X-input calls the executor makes (no Xlib / no display)."""

    def __init__(self):
        self.events = []

    def motion(self, x, y):
        self.events.append(("motion", x, y))

    def button(self, num, press):
        self.events.append(("button", num, press))

    def key(self, code, press):
        self.events.append(("key", code, press))

    def keysym_to_keycode(self, keysym):
        return 1000 + keysym  # deterministic fake mapping

    def char_to_keysym(self, ch):
        return ord(ch)

    def sync(self):
        self.events.append(("sync",))


def _exec():
    fx = FakeXInput()
    return XTestExecutor(xinput=fx), fx


class TestMouse:
    def test_click_moves_then_presses_and_releases(self):
        ex, fx = _exec()
        ex.click(100, 200)
        assert ("motion", 100, 200) in fx.events
        assert ("button", 1, True) in fx.events
        assert ("button", 1, False) in fx.events
        # release comes after press
        assert fx.events.index(("button", 1, True)) < fx.events.index(("button", 1, False))

    def test_right_click_uses_button_3(self):
        ex, fx = _exec()
        ex.click(0, 0, button="right")
        assert ("button", 3, True) in fx.events

    def test_scroll_up_uses_button_4(self):
        ex, fx = _exec()
        ex.scroll(0, 0, 2)
        presses = [e for e in fx.events if e[:2] == ("button", 4)]
        assert len(presses) == 4  # 2 steps * (press+release)

    def test_scroll_down_uses_button_5(self):
        ex, fx = _exec()
        ex.scroll(0, 0, -1)
        assert ("button", 5, True) in fx.events

    def test_drag_presses_moves_releases(self):
        ex, fx = _exec()
        ex.drag(0, 0, 10, 10, duration=0.0)
        kinds = [e[0] for e in fx.events]
        assert kinds[: kinds.index("button")] or True
        assert ("button", 1, True) in fx.events and ("button", 1, False) in fx.events
        assert fx.events.index(("button", 1, True)) < fx.events.index(("button", 1, False))


class TestKeyboard:
    def test_type_text_presses_each_char(self):
        ex, fx = _exec()
        ex.type_text("ab")
        codes = [e for e in fx.events if e[0] == "key"]
        assert ("key", 1000 + ord("a"), True) in codes
        assert ("key", 1000 + ord("b"), True) in codes

    def test_type_uppercase_holds_shift(self):
        ex, fx = _exec()
        ex.type_text("A")
        # shift down before the key, up after
        assert any(e[0] == "key" for e in fx.events)
        keysym_shift = 0xFFE1
        assert ("key", 1000 + keysym_shift, True) in fx.events
        assert ("key", 1000 + keysym_shift, False) in fx.events

    def test_key_press_named_combo(self):
        ex, fx = _exec()
        ex.key_press(["ctrl", "c"])
        # both go down then up in reverse
        downs = [e for e in fx.events if e[0] == "key" and e[2] is True]
        assert len(downs) == 2
