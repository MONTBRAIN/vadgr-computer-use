# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""`@tool(name, tier, risk)` decorator.

The decorator:
- Validates inputs.
- Registers the function with the ToolRegistry at import time.
- Returns the function unchanged (so existing MCP `@mcp.tool()` wrappers
  on the same function keep working).
"""

from __future__ import annotations

from typing import Callable

from computer_use.core.registry import ToolRegistry
from computer_use.core.risk import Risk
from computer_use.core.tier import Tier
from computer_use.core.tool import Tool


def _validate_tier(tier) -> Tier:
    if isinstance(tier, Tier):
        return tier
    # Be permissive about raw numerics so callers can pass 0/0.5/1/2.
    if isinstance(tier, (int, float)):
        try:
            return Tier(tier)
        except ValueError as e:
            raise ValueError(f"invalid tier {tier!r}: must be one of {[t.value for t in Tier]}") from e
    raise TypeError(f"tier must be Tier or numeric, got {type(tier).__name__}")


def _validate_risk(risk) -> Risk:
    if isinstance(risk, Risk):
        return risk
    if isinstance(risk, str):
        try:
            return Risk(risk)
        except ValueError as e:
            raise ValueError(
                f"invalid risk {risk!r}: must be one of {[r.value for r in Risk]}"
            ) from e
    raise TypeError(f"risk must be Risk or str, got {type(risk).__name__}")


def _validate_name(name) -> str:
    if not isinstance(name, str):
        raise TypeError(f"name must be str, got {type(name).__name__}")
    if not name.strip():
        raise ValueError("name must be a non-empty string")
    return name


def make_tool_decorator(registry: ToolRegistry) -> Callable:
    """Build a `@tool` decorator bound to the given registry.

    Used both by the public module-level `tool` (bound to the global REGISTRY)
    and by tests that want an isolated registry.
    """

    def decorator(*, name: str, tier, risk):
        clean_name = _validate_name(name)
        clean_tier = _validate_tier(tier)
        clean_risk = _validate_risk(risk)

        def wrap(func: Callable) -> Callable:
            registry.register(
                Tool(
                    name=clean_name,
                    tier=clean_tier,
                    risk=clean_risk,
                    func=func,
                    doc=(func.__doc__ or "").strip(),
                )
            )
            # Return the original function so other decorators (e.g.
            # @mcp.tool()) and direct callers see no behavior change.
            return func

        return wrap

    return decorator
