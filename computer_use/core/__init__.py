# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""`computer_use.core` — domain types + tool registration framework.

This package contains:
- Existing engine domain (engine, actions, screenshot, types, errors,
  smooth_move) — internal API consumed by mcp_server.
- 0.2.0 framework (tool, tier, risk, registry, decorator, middleware) per
  ARCHITECTURE.md §5.6 / §5.7.

Public framework surface:

    from computer_use.core import tool, Tier, Risk, REGISTRY

    @tool(name="my.tool", tier=Tier.ZERO, risk=Risk.READ_ONLY)
    def my_tool(): ...
"""

from computer_use.core.decorator import make_tool_decorator
from computer_use.core.registry import ToolRegistry
from computer_use.core.risk import Risk
from computer_use.core.tier import Tier
from computer_use.core.tool import Tool

# The process-wide registry. Tool modules register themselves into this
# instance at import time via the `tool` decorator below.
REGISTRY = ToolRegistry()

# Public decorator bound to the global REGISTRY. Use `make_tool_decorator`
# directly in tests that need an isolated registry.
tool = make_tool_decorator(REGISTRY)

__all__ = [
    "tool",
    "make_tool_decorator",
    "REGISTRY",
    "Tool",
    "ToolRegistry",
    "Tier",
    "Risk",
]
