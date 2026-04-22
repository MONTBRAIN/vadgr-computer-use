# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Acceptance tests for the v0.1.0 public surface.

Codifies what the MCP server, engine, and package expose after the
muscle-memory cache removal. If any of these fail, the release surface
has drifted and the README / docs will lie.
"""

import importlib
import inspect

import pytest


V010_TOOLS = frozenset({
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
})

REMOVED_TOOLS = frozenset({
    "navigate_to",
    "navigate_chain",
    "create_template",
    "execute_template",
    "list_templates",
    "delete_template",
    "find_element",  # dropped in v0.1.0 cleanup: 0/5 success rate in real usage
})

REMOVED_ENGINE_ATTRS = frozenset({
    "_cache",
    "navigate_to",
    "navigate_chain",
    "execute_template",
    "_resolve_cache_context",
    "_cache_lookup",
    "_cache_record",
    "_cache_to_screen",
    # Grounding subsystem, dropped alongside find_element:
    "find_element",
    "find_all_elements",
    "click_element",
    "_get_locator",
    "_locator",
    # Autonomous mode, dropped in v0.1.0 cleanup:
    "run_task",
    "execute_action",
    "_get_provider",
    "_provider",
    "_provider_name",
    "_history",
    "_config",
    "_load_config",
})


REMOVED_MODULES = frozenset({
    "computer_use.core.spatial_cache",
    "computer_use.core.loop",
    "computer_use.providers",
    "computer_use.providers.base",
    "computer_use.providers.anthropic",
    "computer_use.providers.openai",
    "computer_use.providers.registry",
})


def _mcp_tool_names() -> frozenset[str]:
    from computer_use import mcp_server

    tools = getattr(mcp_server.mcp, "_tool_manager", None)
    if tools is None:
        pytest.skip("FastMCP internal layout changed; update this probe")
    return frozenset(tools._tools.keys())


class TestMcpToolSurface:
    def test_exposes_exactly_v010_tools(self):
        assert _mcp_tool_names() == V010_TOOLS

    def test_cache_tools_are_gone(self):
        assert _mcp_tool_names().isdisjoint(REMOVED_TOOLS)


class TestEngineSurface:
    def test_engine_has_no_cache_attrs(self):
        from computer_use.core.engine import ComputerUseEngine

        members = {name for name, _ in inspect.getmembers(ComputerUseEngine)}
        leaked = members & REMOVED_ENGINE_ATTRS
        assert not leaked, f"Cache-era attrs still on engine: {sorted(leaked)}"


class TestRemovedModules:
    @pytest.mark.parametrize("mod", sorted(REMOVED_MODULES))
    def test_module_cannot_be_imported(self, mod):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)
