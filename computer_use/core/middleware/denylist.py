# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Denylist middleware: refuses calls that mention any blocked substring.

The blocklist is configurable (constructor argument). The default empty list
is the safe fallback for 0.2.0 — tighter defaults land alongside the Tier 0
filesystem/shell tools in 0.3.0.
"""

from __future__ import annotations

from typing import Any, Sequence

from computer_use.core.middleware.base import ToolCall


class DenylistMiddleware:
    """Block calls whose stringified args/kwargs contain a denied substring."""

    def __init__(self, patterns: Sequence[str]):
        self._patterns: list[str] = list(patterns)

    def before(self, call: ToolCall) -> ToolCall:
        if not self._patterns:
            return call
        haystack = " ".join(str(a) for a in call.args)
        haystack += " " + " ".join(f"{k}={v}" for k, v in call.kwargs.items())
        for pat in self._patterns:
            if pat in haystack:
                raise PermissionError(
                    f"denylist: tool {call.name!r} refused — matches {pat!r}"
                )
        return call

    def after(self, call: ToolCall, result: Any) -> Any:
        return result
