"""Shared data types for the computer use engine."""

from dataclasses import dataclass, field
from enum import Enum
import time


class Platform(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    WSL2 = "wsl2"


@dataclass(frozen=True)
class ForegroundWindow:
    """Info about the currently focused window."""

    app_name: str   # "notepad.exe", "firefox"
    title: str      # "Untitled - Notepad"
    x: int          # window top-left X (screen coords)
    y: int          # window top-left Y
    width: int
    height: int
    pid: int = 0


@dataclass(frozen=True)
class Region:
    """A rectangular region on screen."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class ScreenState:
    """A captured screenshot with metadata."""

    image_bytes: bytes  # image bytes (PNG or JPEG)
    width: int
    height: int
    timestamp: float = field(default_factory=time.time)
    scale_factor: float = 1.0  # for HiDPI displays
    offset_x: int = 0  # virtual screen X origin (for multi-monitor)
    offset_y: int = 0  # virtual screen Y origin (for multi-monitor)
