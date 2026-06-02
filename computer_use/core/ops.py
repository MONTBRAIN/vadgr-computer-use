# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Sub-operation routing for tools that expose an ``op`` argument.

A tool such as ``fs`` or ``time`` accepts an ``op`` name plus the union of
every sub-op's parameters. Each sub-op registers a handler by name; the
dispatch function forwards the call here, which routes to the matching
handler and passes through only the parameters that handler declares.
"""

from __future__ import annotations

import inspect
from typing import Callable


class OperationGroup:
    """Named sub-operations for one tool, routed by name."""

    def __init__(self, tool_name: str) -> None:
        self._tool_name = tool_name
        self._handlers: dict[str, Callable] = {}

    def operation(self, name: str) -> Callable[[Callable], Callable]:
        """Register a handler under ``name``. Rejects duplicates."""

        def register(fn: Callable) -> Callable:
            if name in self._handlers:
                raise ValueError(f"duplicate {self._tool_name} op {name!r}")
            self._handlers[name] = fn
            return fn

        return register

    @property
    def names(self) -> list[str]:
        """Registered op names, sorted."""
        return sorted(self._handlers)

    def run(self, op: str, /, **kwargs):
        """Route ``op`` to its handler, forwarding the kwargs it accepts."""
        handler = self._handlers.get(op)
        if handler is None:
            raise ValueError(
                f"unknown {self._tool_name} op {op!r}; "
                f"expected one of {', '.join(self.names)}"
            )
        accepted = inspect.signature(handler).parameters
        if any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in accepted.values()
        ):
            return handler(**kwargs)
        return handler(**{k: v for k, v in kwargs.items() if k in accepted})
