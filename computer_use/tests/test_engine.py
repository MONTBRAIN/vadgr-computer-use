"""Tests for the ComputerUseEngine with mocked backends."""

from unittest.mock import MagicMock, patch

import pytest

from computer_use.core.engine import ComputerUseEngine, _PCT_BUCKET, _PASSTHROUGH_APPS
from computer_use.core.types import ForegroundWindow, Platform, Region, ScreenState


@pytest.fixture
def mock_backend():
    """Create a fully mocked platform backend."""
    backend = MagicMock()
    backend.is_available.return_value = True
    backend.get_accessibility_info.return_value = {
        "available": True,
        "api_name": "Mock",
        "notes": "",
    }

    capture = MagicMock()
    capture.capture_full.return_value = ScreenState(
        image_bytes=b"\x89PNG_MOCK",
        width=1920,
        height=1080,
    )
    capture.capture_region.return_value = ScreenState(
        image_bytes=b"\x89PNG_REGION",
        width=200,
        height=100,
    )
    capture.get_screen_size.return_value = (1920, 1080)
    capture.get_scale_factor.return_value = 1.0

    executor = MagicMock()

    backend.get_screen_capture.return_value = capture
    backend.get_action_executor.return_value = executor

    return backend, capture, executor


class TestEngine:
    def _make_engine(self, mock_backend):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_screenshot(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot()
        assert screen.width == 1920
        assert screen.height == 1080
        capture.capture_full.assert_called_once()

    def test_screenshot_region(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot_region(10, 20, 200, 100)
        assert screen.width == 200
        capture.capture_region.assert_called_once()

    def test_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.click(500, 300)
        executor.click.assert_called_once_with(500, 300)

    def test_double_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.double_click(100, 200)
        executor.double_click.assert_called_once_with(100, 200)

    def test_right_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.right_click(100, 200)
        executor.click.assert_called_once_with(100, 200, button="right")

    def test_type_text(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.type_text("hello")
        executor.type_text.assert_called_once_with("hello")

    def test_key_press(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.key_press("ctrl", "c")
        executor.key_press.assert_called_once_with(["ctrl", "c"])

    def test_scroll(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.scroll(100, 200, -3)
        executor.scroll.assert_called_once_with(100, 200, -3)

    def test_get_platform(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        assert engine.get_platform() == Platform.WSL2

    def test_get_screen_size(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        assert engine.get_screen_size() == (1920, 1080)

    def test_get_platform_info(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        info = engine.get_platform_info()
        assert info["platform"] == "wsl2"
        assert info["backend_available"] is True

    def test_run_task_without_provider_raises(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        with pytest.raises(Exception):
            engine.run_task("Open Notepad")


class TestMuscleMemoryIntegration:
    """Tests that the engine's muscle memory cache integrates correctly."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_click_without_hint_auto_learns_layer1(self, mock_backend):
        """No element_hint => Layer 1 synthetic hint => still learns."""
        engine, _, executor = self._make_engine(mock_backend)
        # First click: cache miss, no hit_count
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200)

        # Second click at same coords: cache hit from Layer 1
        executor.reset_mock()
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_click_with_hint_records_and_learns(self, mock_backend):
        """First click with hint records it; second click passes hit_count."""
        engine, _, executor = self._make_engine(mock_backend)

        # First click: cache miss, no hit_count passed
        engine.click(100, 200, element_hint="Save button")
        executor.click.assert_called_with(100, 200)

        executor.reset_mock()
        engine.click(100, 200, element_hint="Save button")
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_double_click_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.double_click(50, 75, element_hint="icon")
        # First call: miss
        executor.double_click.assert_called_with(50, 75)

        executor.reset_mock()
        engine.double_click(50, 75, element_hint="icon")
        executor.double_click.assert_called_once_with(50, 75, hit_count=1)

    def test_right_click_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.right_click(300, 400, element_hint="context target")
        executor.click.assert_called_with(300, 400, button="right")

        executor.reset_mock()
        engine.right_click(300, 400, element_hint="context target")
        executor.click.assert_called_once_with(300, 400, button="right", hit_count=1)

    def test_move_mouse_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.move_mouse(200, 300, element_hint="hover target")
        executor.move_mouse.assert_called_with(200, 300)

        executor.reset_mock()
        engine.move_mouse(200, 300, element_hint="hover target")
        executor.move_mouse.assert_called_once_with(200, 300, hit_count=1)

    def test_hit_count_increments_with_repeated_clicks(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)

        for i in range(5):
            engine.click(100, 200, element_hint="frequent button")

        # Last call should have hit_count=4 (recorded 4 times before the 5th)
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((), {"hit_count": 4}) or last_call == ((100, 200,), {"hit_count": 4})

    def test_different_hints_are_independent(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)

        engine.click(100, 200, element_hint="button A")
        engine.click(100, 200, element_hint="button A")
        engine.click(300, 400, element_hint="button B")

        # button B is first time, should be default path
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((300, 400,), {})


class TestThreeLayerResolution:
    """Tests for the 3-layer cache resolution."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_layer3_overrides_layer1(self, mock_backend):
        """Model-provided hint (Layer 3) takes priority over coord-based Layer 1."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click with hint "File menu"
        engine.click(50, 12, element_hint="File menu")
        engine.click(50, 12, element_hint="File menu")

        # The second click should use the "File menu" hint, not "@50,0"
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((50, 12,), {"hit_count": 1})

    def test_layer1_auto_learns_from_coords(self, mock_backend):
        """Without any hint, Layer 1 uses bucketed coords and still learns."""
        fg = ForegroundWindow(
            app_name="chrome.exe", title="test", x=100, y=50,
            width=1200, height=800,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click at (300, 200) => window-relative (200, 150) => bucket @200,150
        engine.click(300, 200)
        executor.click.assert_called_with(300, 200)

        # Same click again: cache hit
        executor.reset_mock()
        engine.click(300, 200)
        executor.click.assert_called_once_with(300, 200, hit_count=1)

    def test_foreground_failure_falls_back(self, mock_backend):
        """When get_foreground_window() returns None, fall back to platform name."""
        engine, _, executor = self._make_engine(mock_backend, fg_window=None)

        # Should still work with platform name as app and absolute coords
        engine.click(100, 200)
        executor.click.assert_called_with(100, 200)

        executor.reset_mock()
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_window_relative_coords_stored(self, mock_backend):
        """Cache uses window-relative coords so entries survive window moves."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=200, y=100,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click at (300, 200) => window-relative (100, 100)
        engine.click(300, 200, element_hint="my button")

        # Verify it's stored with window-relative coords
        entry = engine._cache.lookup("app.exe", "my button", 100, 100)
        assert entry is not None
        assert entry.hit_count == 1

    def test_real_app_name_used(self, mock_backend):
        """Cache stores real app name from foreground window, not 'wsl2'."""
        fg = ForegroundWindow(
            app_name="firefox.exe", title="Mozilla Firefox", x=0, y=0,
            width=1920, height=1080,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        engine.click(500, 300, element_hint="New Tab")

        # Should be stored under "firefox.exe", not "wsl2"
        entry = engine._cache.lookup("firefox.exe", "New Tab")
        assert entry is not None

        # Should NOT be under "wsl2"
        entry_wsl = engine._cache.lookup("wsl2", "New Tab")
        assert entry_wsl is None

    def test_pct_bucket_alignment(self, mock_backend):
        """Nearby coords in the same pct bucket resolve to the same Layer 1 hint."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1000, height=1000,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # 1000px wide, 3% bucket => 30px per bucket
        # (100, 200) => pct (10%, 20%) => bucket @9%,18%
        # (110, 210) => pct (11%, 21%) => bucket @9%,21% -- different Y bucket!
        # Use coords that are in the same bucket:
        # (100, 200) => 10%, 20% => bucket @9%, 18%
        # (105, 205) => 10.5%, 20.5% => bucket @9%, 18%  (same)
        engine.click(100, 200)
        executor.reset_mock()
        engine.click(105, 205)
        # Should be a cache hit because both map to the same pct bucket
        executor.click.assert_called_once_with(105, 205, hit_count=1)

    def test_resize_survives_with_pct_coords(self, mock_backend):
        """Percentage-based coords survive window resize."""
        backend, capture, executor = mock_backend

        # First: 800x600 window, click at (200, 150) = 25%, 25%
        fg1 = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        backend.get_foreground_window.return_value = fg1
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()

        engine.click(200, 150)  # 25%, 25% -> bucket @24%,24%

        # Simulate resize to 1200x900
        fg2 = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1200, height=900,
        )
        backend.get_foreground_window.return_value = fg2
        engine._fg_window_ts = 0  # force refresh

        executor.reset_mock()
        # Same proportional position: 25% of 1200 = 300, 25% of 900 = 225
        engine.click(300, 225)  # 25%, 25% -> same bucket @24%,24%
        executor.click.assert_called_once_with(300, 225, hit_count=1)

    def test_passthrough_app_excluded(self, mock_backend):
        """RDP and terminal apps are excluded from window-based caching."""
        fg = ForegroundWindow(
            app_name="mstsc.exe", title="Remote Desktop", x=0, y=0,
            width=1920, height=1080,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Should fall back to platform name, not "mstsc.exe"
        engine.click(500, 300, element_hint="test button")
        entry = engine._cache.lookup("mstsc.exe", "test button")
        assert entry is None

        # Should be stored under platform name
        entry = engine._cache.lookup("wsl2", "test button")
        assert entry is not None
