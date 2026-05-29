# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Regression tests: after the 0.2.0 foundation refactor, every existing
MCP tool is registered in the ToolRegistry with the correct tier and risk.

The MCP wire surface is unchanged; this asserts the new internal
registration mechanism wraps the same 13 tools (per ARCHITECTURE.md §10.1).
"""


EXPECTED_TOOLS = frozenset(
    {
        "screenshot",
        "screenshot_region",
        "click",
        "double_click",
        "right_click",
        "move_mouse",
        "drag",
        "scroll",
        "type_text",
        "key_press",
        "get_screen_size",
        "get_platform",
        "get_platform_info",
    }
)

# Per ARCHITECTURE.md §5.1: all existing 13 tools are pixel-layer -> Tier 2.
EXPECTED_TIER_FOR_ALL = 2

# Risk mapping fixed in §10.1 plan: read-only for query tools, medium for
# input-mutating tools.
EXPECTED_READ_ONLY = frozenset(
    {
        "screenshot",
        "screenshot_region",
        "get_screen_size",
        "get_platform",
        "get_platform_info",
    }
)
EXPECTED_MEDIUM_RISK = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "move_mouse",
        "drag",
        "scroll",
        "type_text",
        "key_press",
    }
)


def _load_registry():
    # Triggers @tool decoration at module import.
    from computer_use import mcp_server  # noqa: F401
    from computer_use.core import REGISTRY

    return REGISTRY


class TestAllToolsRegistered:
    def test_registry_count_is_thirteen(self):
        registry = _load_registry()
        names = {t.name for t in registry.all()}
        # Filter to the expected set in case other tests added throwaway tools.
        existing = names & EXPECTED_TOOLS
        assert existing == EXPECTED_TOOLS, (
            f"missing: {EXPECTED_TOOLS - existing}, "
            f"extra: {names - EXPECTED_TOOLS}"
        )

    def test_registry_count_method_includes_thirteen(self):
        registry = _load_registry()
        assert registry.count() >= 13


class TestToolTierAndRisk:
    def test_every_tool_is_tier_two(self):
        from computer_use.core.tier import Tier

        registry = _load_registry()
        for name in EXPECTED_TOOLS:
            entry = registry.get(name)
            assert entry is not None, f"tool {name!r} not registered"
            assert entry.tier == Tier.TWO, (
                f"{name}: expected Tier.TWO, got {entry.tier}"
            )

    def test_read_only_tools_have_read_only_risk(self):
        from computer_use.core.risk import Risk

        registry = _load_registry()
        for name in EXPECTED_READ_ONLY:
            entry = registry.get(name)
            assert entry is not None
            assert entry.risk == Risk.READ_ONLY, (
                f"{name}: expected READ_ONLY, got {entry.risk}"
            )

    def test_input_tools_have_medium_risk(self):
        from computer_use.core.risk import Risk

        registry = _load_registry()
        for name in EXPECTED_MEDIUM_RISK:
            entry = registry.get(name)
            assert entry is not None
            assert entry.risk == Risk.MEDIUM, (
                f"{name}: expected MEDIUM, got {entry.risk}"
            )


class TestRegistryIntrospection:
    def test_tier_breakdown_reports_thirteen_in_tier_two(self):
        from computer_use.core.tier import Tier

        registry = _load_registry()
        breakdown = registry.tier_breakdown()
        # All existing tools are Tier 2. Could be more if tests added their own.
        assert breakdown.get(Tier.TWO, 0) >= 13

    def test_by_tier_returns_iterable(self):
        from computer_use.core.tier import Tier

        registry = _load_registry()
        tier_two_names = {t.name for t in registry.by_tier(Tier.TWO)}
        assert EXPECTED_TOOLS <= tier_two_names


class TestMcpWireSurfaceUnchanged:
    """The MCP-level tool surface must NOT change with the refactor."""

    def test_fastmcp_still_exposes_thirteen(self):
        from computer_use import mcp_server

        tools = mcp_server.mcp._tool_manager._tools
        assert EXPECTED_TOOLS <= set(tools.keys())
