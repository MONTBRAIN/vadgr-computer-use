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

"""Abstract action execution interface."""

import time
from abc import ABC, abstractmethod

from computer_use.core.types import Action, ActionType


class ActionExecutor(ABC):
    """Abstract base for executing mouse and keyboard actions."""

    @abstractmethod
    def move_mouse(self, x: int, y: int, hit_count: int = 0) -> None:
        """Move mouse cursor to absolute screen position."""
        ...

    @abstractmethod
    def click(self, x: int, y: int, button: str = "left", hit_count: int = 0) -> None:
        """Click at position. button: 'left', 'right', 'middle'."""
        ...

    @abstractmethod
    def double_click(self, x: int, y: int, hit_count: int = 0) -> None:
        """Double-click at position."""
        ...

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type a string character by character."""
        ...

    @abstractmethod
    def key_press(self, keys: list[str]) -> None:
        """Press a key combination. e.g. ['ctrl', 'c'] or ['enter']."""
        ...

    @abstractmethod
    def scroll(self, x: int, y: int, amount: int) -> None:
        """Scroll at position. Positive = up, negative = down."""
        ...

    @abstractmethod
    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
        hit_count: int = 0,
    ) -> None:
        """Drag from start to end position."""
        ...

    def execute_action(self, action: Action) -> None:
        """Route an Action dataclass to the correct method."""
        match action.action_type:
            case ActionType.CLICK:
                self.click(action.x, action.y)
            case ActionType.DOUBLE_CLICK:
                self.double_click(action.x, action.y)
            case ActionType.RIGHT_CLICK:
                self.click(action.x, action.y, button="right")
            case ActionType.TYPE_TEXT:
                self.type_text(action.text)
            case ActionType.KEY_PRESS:
                self.key_press(action.keys)
            case ActionType.SCROLL:
                self.scroll(action.x, action.y, action.scroll_amount)
            case ActionType.MOVE:
                self.move_mouse(action.x, action.y)
            case ActionType.DRAG:
                self.drag(
                    action.x,
                    action.y,
                    action.target_x,
                    action.target_y,
                    action.duration,
                )
            case ActionType.WAIT:
                time.sleep(action.duration)
