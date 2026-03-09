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

"""LLM vision-based element locator (fallback when accessibility API fails)."""

import logging
from typing import Optional

from computer_use.core.types import Element, ScreenState
from computer_use.grounding.base import ElementLocator

logger = logging.getLogger("computer_use.grounding.vision")


class VisionLocator(ElementLocator):
    """Use LLM vision to locate elements when accessibility API fails."""

    def __init__(self, provider_name: str, config: dict):
        from computer_use.providers.registry import get_provider

        self._provider = get_provider(provider_name, config)

    def find_element(
        self, description: str, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        if screen is None:
            return None
        return self._provider.locate_element(screen, description)

    def find_all_elements(
        self, screen: Optional[ScreenState] = None
    ) -> list[Element]:
        # Not efficient to ask LLM to enumerate all elements
        return []

    def find_element_at(
        self, x: int, y: int, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        if screen is None:
            return None
        return self._provider.locate_element(
            screen, f"element at coordinates ({x}, {y})"
        )

    def is_available(self) -> bool:
        return True  # Always available if a provider is configured
