# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Middleware protocol + ToolCall record.

Two-method protocol (`before` / `after`) keeps the surface small.
Middlewares are interchangeable behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """One inbound tool invocation."""

    name: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)


@runtime_checkable
class Middleware(Protocol):
    """Cross-cutting concern that wraps a tool call.

    `before` may mutate or replace the ToolCall, or raise to block dispatch.
    `after` may mutate or replace the result.
    """

    def before(self, call: ToolCall) -> ToolCall: ...

    def after(self, call: ToolCall, result: Any) -> Any: ...
