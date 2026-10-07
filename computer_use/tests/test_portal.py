# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""PortalScreenshotCapture: decode the portal's PNG, crop regions, clean up."""

import io
import os

import pytest

from computer_use.core.errors import ScreenCaptureError
from computer_use.core.types import Region
from computer_use.platform.backends.portal import PortalScreenshotCapture


def _png(tmp_path, w, h, color=(10, 20, 30)):
    from PIL import Image

    p = tmp_path / "shot.png"
    Image.new("RGB", (w, h), color).save(p, format="PNG")
    return str(p)


class FakeClient:
    def __init__(self, path=None, error=None):
        self.path = path
        self.error = error
        self.calls = 0

    def take_screenshot(self):
        self.calls += 1
        if self.error is not None:
            raise ScreenCaptureError(self.error)
        return self.path


class TestCaptureFull:
    def test_returns_screenstate_with_image_dims(self, tmp_path):
        path = _png(tmp_path, 800, 600)
        cap = PortalScreenshotCapture(client=FakeClient(path))
        state = cap.capture_full()
        assert (state.width, state.height) == (800, 600)
        from PIL import Image

        assert Image.open(io.BytesIO(state.image_bytes)).size == (800, 600)

    def test_screen_size_matches(self, tmp_path):
        cap = PortalScreenshotCapture(client=FakeClient(_png(tmp_path, 1366, 768)))
        assert cap.get_screen_size() == (1366, 768)

    def test_failure_raises_screencapture_error(self):
        cap = PortalScreenshotCapture(client=FakeClient(error="portal denied"))
        with pytest.raises(ScreenCaptureError):
            cap.capture_full()

    def test_temp_file_removed(self, tmp_path):
        path = _png(tmp_path, 100, 100)
        PortalScreenshotCapture(client=FakeClient(path)).capture_full()
        assert not os.path.exists(path), "portal screenshot temp file should be cleaned up"


class TestCaptureRegion:
    def test_crops(self, tmp_path):
        cap = PortalScreenshotCapture(client=FakeClient(_png(tmp_path, 800, 600)))
        state = cap.capture_region(Region(x=10, y=20, width=50, height=40))
        assert (state.width, state.height) == (50, 40)


class TestPortalRequestSerialization:
    """GNOME answers only one of several overlapping Screenshot requests; the
    others never get a Response, so each request must hold a per-user lock."""

    def _hold_lock_in_other_process(self, path, seconds):
        import subprocess
        import sys
        import textwrap

        code = textwrap.dedent(f"""
            import fcntl, sys, time
            with open({str(path)!r}, "a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                print("held", flush=True)
                time.sleep({seconds})
        """)
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        assert child.stdout.readline().strip() == "held"
        return child

    def test_lock_waits_for_a_request_in_another_process(self, tmp_path, monkeypatch):
        import time

        from computer_use.platform.backends import portal

        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        child = self._hold_lock_in_other_process(portal._request_lock_path(), 1.0)
        started = time.monotonic()
        with portal._portal_request_lock(timeout=10):
            waited = time.monotonic() - started
        child.wait()
        assert waited >= 0.5

    def test_lock_times_out_with_a_clear_error(self, tmp_path, monkeypatch):
        from computer_use.platform.backends import portal

        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        child = self._hold_lock_in_other_process(portal._request_lock_path(), 3.0)
        try:
            with pytest.raises(ScreenCaptureError, match="another screenshot request"):
                with portal._portal_request_lock(timeout=0.3):
                    pass
        finally:
            child.wait()

    def test_screenshot_request_is_sent_while_holding_the_lock(self, tmp_path, monkeypatch):
        import contextlib

        from computer_use.platform.backends import portal

        events = []

        @contextlib.contextmanager
        def lock(timeout):
            events.append("lock")
            yield
            events.append("unlock")

        class Conn:
            unique_name = ":1.42"

            def filter(self, rule):
                return contextlib.nullcontext("responses")

            def send_and_get_reply(self, message):
                events.append("send")

            def recv_until_filtered(self, responses, timeout):
                class Signal:
                    body = (0, {"uri": ("s", "file:///tmp/shot.png")})
                return Signal()

            def close(self):
                events.append("close")

        class Jeepney:
            class MessageType:
                error = 3

            message_bus = type("Bus", (), {"AddMatch": staticmethod(lambda rule: "add-match")})

            @staticmethod
            def MatchRule(**kwargs):
                return "rule"

            @staticmethod
            def DBusAddress(*args, **kwargs):
                return "address"

            @staticmethod
            def new_method_call(*args):
                return "call"

        monkeypatch.setattr(portal, "_jeepney", Jeepney)
        monkeypatch.setattr(portal, "_open_dbus_connection", lambda bus: Conn())
        monkeypatch.setattr(portal, "_portal_request_lock", lock)
        assert portal.PortalScreenshotClient().take_screenshot() == "/tmp/shot.png"
        assert events[0] == "lock" and events.index("unlock") > max(i for i, e in enumerate(events) if e == "send")
