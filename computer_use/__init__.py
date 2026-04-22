"""Computer Use Engine: gives MCP clients (and Python callers) eyes and hands.

Usage:
    from computer_use import ComputerUseEngine
    engine = ComputerUseEngine()
    screen = engine.screenshot()
    engine.click(500, 300)
    engine.type_text("hello")

The package is also an MCP server (see `vadgr-cua` console script).
"""

from computer_use.core.engine import ComputerUseEngine
from computer_use.core.errors import (
    ActionError,
    ActionTimeoutError,
    ComputerUseError,
    PlatformNotSupportedError,
    ScreenCaptureError,
)
from computer_use.core.types import (
    Platform,
    Region,
    ScreenState,
)

__all__ = [
    "ComputerUseEngine",
    "Platform",
    "Region",
    "ScreenState",
    "ComputerUseError",
    "ScreenCaptureError",
    "ActionError",
    "ActionTimeoutError",
    "PlatformNotSupportedError",
]
