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
from collections.abc import Callable

from computer_use.core.typing import TypingCancelled, TypingPlan


def consume_typing_plan(
    plan: TypingPlan,
    emit: Callable[[str], bool],
    *,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    """Run one absolute schedule and return the number of fallback units.

    ``emit`` returns true when it used a composition or text-insertion fallback.
    Cancellation is observed only between complete units, so an emitter must
    release any modifier it presses before it returns.
    """
    started = time.monotonic()
    scheduled = 0.0
    fallback_units = 0
    for completed, unit in enumerate(plan.units):
        if cancelled is not None and cancelled():
            raise TypingCancelled(completed)
        scheduled += unit.delay_before_ms / 1000
        while (remaining := started + scheduled - time.monotonic()) > 0:
            if cancelled is not None and cancelled():
                raise TypingCancelled(completed)
            time.sleep(min(remaining, 0.02))
        fallback_units += int(emit(unit.text))
    return fallback_units


class ActionExecutor(ABC):
    """Abstract base for executing mouse and keyboard actions."""

    @abstractmethod
    def move_mouse(self, x: int, y: int) -> None:
        """Move mouse cursor to absolute screen position."""
        ...

    @abstractmethod
    def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at position. button: 'left', 'right', 'middle'."""
        ...

    @abstractmethod
    def double_click(self, x: int, y: int) -> None:
        """Double-click at position."""
        ...

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type a string character by character."""
        ...

    def type_text_plan(
        self,
        plan: TypingPlan,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> int:
        """Consume one shared human-paced schedule.

        Backends can override this to keep one native input session open. The
        default stays correct for backends whose existing ``type_text`` call is
        already event-level.
        """
        return consume_typing_plan(
            plan,
            lambda text: bool(self.type_text(text)) if text else False,
            cancelled=cancelled,
        )

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
    ) -> None:
        """Drag from start to end position."""
        ...
