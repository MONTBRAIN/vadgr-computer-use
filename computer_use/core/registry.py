# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""ToolRegistry: import-time auto-registration + introspection.

Single point of truth for "what tools exist". The MCP server reads from
here; nothing else owns the tool list.
"""

from __future__ import annotations

from typing import Iterable

from computer_use.core.risk import Risk
from computer_use.core.tier import Tier
from computer_use.core.tool import Tool


def _same_origin(a, b) -> bool:
    """True if two callables come from the same `(module, qualname)`.

    Used to keep registration idempotent across module reimports without
    masking real duplicates from unrelated code.
    """
    return (
        getattr(a, "__module__", None) == getattr(b, "__module__", None)
        and getattr(a, "__qualname__", None) == getattr(b, "__qualname__", None)
    )


class ToolRegistry:
    """In-process store of registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # --- Registration ---

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError on duplicate name.

        Idempotent for module re-imports: if a tool with the same name is
        being registered from the same `(module, qualname)`, replace
        silently. This lets tests that delete and re-import a tool module
        work without leaking state.
        """
        existing = self._tools.get(tool.name)
        if existing is not None and not _same_origin(existing.func, tool.func):
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    # --- Lookup ---

    def get(self, name: str) -> Tool | None:
        """Return the tool with the given name, or None."""
        return self._tools.get(name)

    def all(self) -> Iterable[Tool]:
        """Iterate over every registered tool."""
        return self._tools.values()

    def by_tier(self, tier: Tier) -> Iterable[Tool]:
        """Tools at exactly the given tier."""
        return (t for t in self._tools.values() if t.tier == tier)

    def by_risk(self, risk: Risk) -> Iterable[Tool]:
        """Tools at exactly the given risk level."""
        return (t for t in self._tools.values() if t.risk == risk)

    # --- Aggregates ---

    def count(self) -> int:
        return len(self._tools)

    def tier_breakdown(self) -> dict[Tier, int]:
        """Map each Tier value to the count of registered tools at that tier."""
        out: dict[Tier, int] = {t: 0 for t in Tier}
        for tool in self._tools.values():
            out[tool.tier] = out.get(tool.tier, 0) + 1
        return out

    # --- Test helpers ---

    def clear(self) -> None:
        """Remove every registered tool. Tests only."""
        self._tools.clear()
