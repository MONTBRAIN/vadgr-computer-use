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
