# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Abstract element locator interface."""

from abc import ABC, abstractmethod
from typing import Optional

from computer_use.core.types import Element, ScreenState


class ElementLocator(ABC):
    """Abstract base for finding UI elements on screen."""

    @abstractmethod
    def find_element(
        self, description: str, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        """Find a single element matching a natural-language description.
        Returns None if not found."""
        ...

    @abstractmethod
    def find_all_elements(
        self, screen: Optional[ScreenState] = None
    ) -> list[Element]:
        """Enumerate all visible/accessible UI elements."""
        ...

    @abstractmethod
    def find_element_at(
        self, x: int, y: int, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        """Identify the element at a given screen coordinate."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this locator's backend is available."""
        ...
