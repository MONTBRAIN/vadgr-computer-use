"""Abstract platform backend combining screenshot and action capabilities."""

from abc import ABC, abstractmethod
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import ForegroundWindow


class PlatformBackend(ABC):
    """Combines ScreenCapture and ActionExecutor for a specific OS.
    Each platform module implements this."""

    @abstractmethod
    def get_screen_capture(self) -> ScreenCapture:
        """Return the platform-specific screenshot capturer."""
        ...

    @abstractmethod
    def get_action_executor(self) -> ActionExecutor:
        """Return the platform-specific action executor."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend can run on the current system."""
        ...

    @abstractmethod
    def get_accessibility_info(self) -> dict:
        """Return info about accessibility API availability.

        Returns dict with keys:
            available (bool): Whether the API is usable
            api_name (str): Name of the API (e.g. "UI Automation", "AT-SPI2")
            notes (str): Any relevant notes
        """
        ...

    @abstractmethod
    def get_foreground_window(self) -> Optional[ForegroundWindow]:
        """Return info about the currently focused window.

        Returns ForegroundWindow with app name, title, position, and size.
        Returns None if the information cannot be determined.
        """
        ...
