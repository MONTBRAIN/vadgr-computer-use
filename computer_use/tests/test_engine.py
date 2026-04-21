"""Behavior tests for ComputerUseEngine with mocked backends.

Covers the v0.1.0 surface: screenshots, mouse/keyboard, coordinate translation,
accessibility lookup pass-through, and config loading.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from computer_use.core.engine import ComputerUseEngine
from computer_use.core.errors import ConfigError, PlatformNotSupportedError
from computer_use.core.types import (
    Action,
    ActionType,
    Platform,
    Region,
    ScreenState,
)


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.is_available.return_value = True

    capture = MagicMock()
    capture.capture_full.return_value = ScreenState(
        image_bytes=b"\x89PNG_MOCK",
        width=1920,
        height=1080,
        offset_x=0,
        offset_y=0,
    )
    capture.capture_region.return_value = ScreenState(
        image_bytes=b"\x89PNG_REGION",
        width=200,
        height=100,
    )
    capture.get_screen_size.return_value = (1920, 1080)

    executor = MagicMock()

    backend.get_screen_capture.return_value = capture
    backend.get_action_executor.return_value = executor

    return backend, capture, executor


@pytest.fixture
def engine(mock_backend):
    backend, _, _ = mock_backend
    with patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX):
        with patch("computer_use.core.engine.get_backend", return_value=backend):
            return ComputerUseEngine()


class TestInit:
    def test_construction_happy_path(self, engine):
        assert engine.get_platform() == Platform.LINUX

    def test_raises_when_backend_unavailable(self, mock_backend):
        backend, _, _ = mock_backend
        backend.is_available.return_value = False
        with patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX):
            with patch("computer_use.core.engine.get_backend", return_value=backend):
                with pytest.raises(PlatformNotSupportedError):
                    ComputerUseEngine()


class TestScreenshot:
    def test_screenshot_returns_state(self, engine, mock_backend):
        _, capture, _ = mock_backend
        state = engine.screenshot()
        assert state.width == 1920
        assert state.height == 1080
        capture.capture_full.assert_called_once()

    def test_screenshot_region_passes_region(self, engine, mock_backend):
        _, capture, _ = mock_backend
        engine.screenshot_region(10, 20, 200, 100)
        region = capture.capture_region.call_args[0][0]
        assert isinstance(region, Region)
        assert (region.x, region.y, region.width, region.height) == (10, 20, 200, 100)

    def test_screenshot_updates_virtual_screen_offset(self, engine, mock_backend):
        _, capture, executor = mock_backend
        capture.capture_full.return_value = ScreenState(
            image_bytes=b"", width=1920, height=1080,
            offset_x=-1920, offset_y=0,
        )
        engine.screenshot()
        engine.click(100, 200)
        # click translates through offset: (100-1920, 200+0)
        executor.click.assert_called_once_with(-1820, 200)


class TestMouseActions:
    def test_click_forwards_to_executor(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.click(500, 300)
        executor.click.assert_called_once_with(500, 300)

    def test_double_click(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.double_click(50, 60)
        executor.double_click.assert_called_once_with(50, 60)

    def test_right_click(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.right_click(9, 9)
        executor.click.assert_called_once_with(9, 9, button="right")

    def test_move_mouse(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.move_mouse(42, 42)
        executor.move_mouse.assert_called_once_with(42, 42)

    def test_scroll(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.scroll(100, 200, -3)
        executor.scroll.assert_called_once_with(100, 200, -3)

    def test_drag(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.drag(10, 20, 30, 40, duration=0.25)
        executor.drag.assert_called_once_with(10, 20, 30, 40, 0.25)


class TestKeyboard:
    def test_type_text(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.type_text("hello")
        executor.type_text.assert_called_once_with("hello")

    def test_key_press(self, engine, mock_backend):
        _, _, executor = mock_backend
        engine.key_press("ctrl", "c")
        executor.key_press.assert_called_once_with(["ctrl", "c"])


class TestActionDataclass:
    def test_execute_action_routes_to_executor(self, engine, mock_backend):
        _, _, executor = mock_backend
        action = Action(action_type=ActionType.CLICK, x=7, y=8)
        engine.execute_action(action)
        executor.execute_action.assert_called_once_with(action)


class TestPlatformInfo:
    def test_get_screen_size(self, engine):
        assert engine.get_screen_size() == (1920, 1080)

    def test_get_platform_info(self, engine):
        info = engine.get_platform_info()
        assert info["platform"] == "linux"
        assert info["backend_available"] is True
        assert "accessibility" not in info


class TestConfig:
    def test_missing_config_returns_empty(self, mock_backend):
        backend, _, _ = mock_backend
        with patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX):
            with patch("computer_use.core.engine.get_backend", return_value=backend):
                with patch("os.path.exists", return_value=False):
                    engine = ComputerUseEngine()
                    assert engine._config == {}

    def test_invalid_config_raises(self, mock_backend):
        backend, _, _ = mock_backend
        with patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX):
            with patch("computer_use.core.engine.get_backend", return_value=backend):
                with patch("builtins.open", mock_open(read_data="bad: [unclosed")):
                    with pytest.raises(ConfigError):
                        ComputerUseEngine(config_path="fake.yaml")

    def test_provider_from_kwarg_overrides_config(self, mock_backend):
        backend, _, _ = mock_backend
        with patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX):
            with patch("computer_use.core.engine.get_backend", return_value=backend):
                with patch("os.path.exists", return_value=False):
                    engine = ComputerUseEngine(provider="anthropic")
                    assert engine._provider_name == "anthropic"

    def test_run_task_without_provider_raises(self, engine):
        with pytest.raises(ConfigError):
            engine.run_task("do something")
