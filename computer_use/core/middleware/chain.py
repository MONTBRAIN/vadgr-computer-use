# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Middleware chain orchestrator.

Per ARCHITECTURE.md §5.6 / §5.7. Runs middleware `before` hooks in order,
invokes the handler, then runs `after` hooks in reverse order.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from computer_use.core.middleware.base import Middleware, ToolCall


class MiddlewareChain:
    """Ordered, composable chain of middlewares."""

    def __init__(self, middlewares: Sequence[Middleware]):
        self._middlewares: list[Middleware] = list(middlewares)

    def dispatch(self, call: ToolCall, handler: Callable[[], Any]) -> Any:
        """Run every `before` (in order), then handler, then every `after`
        (reverse order). Any middleware may raise to short-circuit dispatch.
        """
        for mw in self._middlewares:
            call = mw.before(call)

        result = handler()

        for mw in reversed(self._middlewares):
            result = mw.after(call, result)
        return result
