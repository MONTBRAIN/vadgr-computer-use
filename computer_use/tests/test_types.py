"""Tests for core data types."""

from computer_use.core.types import (
    ForegroundWindow,
    Platform,
    Region,
    ScreenState,
)


class TestForegroundWindow:
    def test_creation(self):
        fw = ForegroundWindow(
            app_name="notepad.exe",
            title="Untitled - Notepad",
            x=100, y=50, width=800, height=600, pid=1234,
        )
        assert fw.app_name == "notepad.exe"
        assert fw.title == "Untitled - Notepad"
        assert fw.x == 100
        assert fw.y == 50
        assert fw.width == 800
        assert fw.height == 600
        assert fw.pid == 1234

    def test_default_pid(self):
        fw = ForegroundWindow(
            app_name="app", title="t", x=0, y=0, width=100, height=100,
        )
        assert fw.pid == 0

    def test_frozen(self):
        fw = ForegroundWindow(
            app_name="app", title="t", x=0, y=0, width=100, height=100,
        )
        try:
            fw.x = 5
            assert False, "Should raise"
        except AttributeError:
            pass


class TestRegion:
    def test_center(self):
        r = Region(x=10, y=20, width=100, height=50)
        assert r.center == (60, 45)

    def test_center_origin(self):
        r = Region(x=0, y=0, width=200, height=100)
        assert r.center == (100, 50)

    def test_frozen(self):
        r = Region(x=0, y=0, width=10, height=10)
        try:
            r.x = 5
            assert False, "Should raise"
        except AttributeError:
            pass


class TestScreenState:
    def test_creation(self):
        s = ScreenState(
            image_bytes=b"\x89PNG",
            width=1920,
            height=1080,
        )
        assert s.width == 1920
        assert s.height == 1080
        assert s.scale_factor == 1.0
        assert s.timestamp > 0


class TestPlatform:
    def test_values(self):
        assert Platform.WINDOWS.value == "windows"
        assert Platform.MACOS.value == "macos"
        assert Platform.LINUX.value == "linux"
        assert Platform.WSL2.value == "wsl2"
