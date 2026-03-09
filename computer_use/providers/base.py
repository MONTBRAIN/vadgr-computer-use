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

"""Abstract LLM vision provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from computer_use.core.types import Action, Element, ScreenState


@dataclass
class AgentDecision:
    """What the LLM decided to do after seeing a screenshot."""

    action: Action
    reasoning: str
    is_task_complete: bool
    confidence: float  # 0.0 to 1.0
    error_detected: Optional[str] = None


class VisionProvider(ABC):
    """Abstract base for LLM vision providers.

    Used in autonomous mode where the engine calls the LLM directly,
    and for vision-based grounding fallback.
    """

    @abstractmethod
    def decide_action(
        self,
        screen: ScreenState,
        task: str,
        history: list[dict],
        elements: Optional[list[Element]] = None,
    ) -> AgentDecision:
        """Given a screenshot and task, decide the next action.

        Args:
            screen: Current screenshot.
            task: Natural-language task description.
            history: List of prior actions and outcomes.
            elements: Optional accessibility-grounded UI elements.

        Returns:
            AgentDecision with chosen action and reasoning.
        """
        ...

    @abstractmethod
    def locate_element(
        self, screen: ScreenState, description: str
    ) -> Optional[Element]:
        """Use vision to locate a UI element matching a description."""
        ...

    @abstractmethod
    def verify_action(
        self, before: ScreenState, after: ScreenState, expected: str
    ) -> tuple[bool, str]:
        """Compare before/after screenshots to verify an action succeeded.

        Returns:
            (success, explanation)
        """
        ...
