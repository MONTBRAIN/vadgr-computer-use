"""Computer Use Engine: local MCP eyes and hands.

Public imports stay backward compatible while loading lazily. The Windows
browser broker freezes only its stdlib browser modules and must not import
pixel backends or their optional platform dependencies at process startup.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ActionError",
    "ActionTimeoutError",
    "ComputerUseEngine",
    "ComputerUseError",
    "Platform",
    "PlatformNotSupportedError",
    "Region",
    "ScreenCaptureError",
    "ScreenState",
]


def __getattr__(name: str) -> Any:
    if name == "ComputerUseEngine":
        from computer_use.core.engine import ComputerUseEngine

        return ComputerUseEngine
    if name in {"Platform", "Region", "ScreenState"}:
        from computer_use.core import types

        return getattr(types, name)
    if name in {
        "ActionError",
        "ActionTimeoutError",
        "ComputerUseError",
        "PlatformNotSupportedError",
        "ScreenCaptureError",
    }:
        from computer_use.core import errors

        return getattr(errors, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
