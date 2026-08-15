# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The MCP wire surface, asserted as a total and read the way a client reads it.

The server moved onto ``mcp.server.mcpserver`` when mcp 2.0.0 removed the
package it was built on before. The move must be invisible to any client, so
the check here is the whole catalog as set equality rather than a subset: a
tool that quietly disappears is exactly what a subset assertion misses.

The names come from ``list_tools()``, the public coroutine both majors expose,
not from a private tool-manager dictionary. Reading the private attribute would
still pass today, which is the argument for moving off it rather than against:
these tests exist to prove what a foreign MCP host sees.
"""

import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The full catalog a client reads from tools/list. Set equality, not a subset.
WIRE_TOOLS = frozenset({
    "browser",
    "browser_eval",
    "click",
    "clipboard",
    "data",
    "double_click",
    "drag",
    "env",
    "fs",
    "get_platform",
    "get_platform_info",
    "get_screen_size",
    "http",
    "key_press",
    "move_mouse",
    "profiles",
    "right_click",
    "screenshot",
    "screenshot_region",
    "scroll",
    "shell",
    "tabs",
    "tempfile",
    "time",
    "type_text",
    "ui_act",
    "ui_find",
    "ui_tree",
    "ui_wait",
    "ui_windows",
    "apps",
    "app_open",
    "windows",
})


def _wire_tool_names() -> frozenset[str]:
    """The tool names a client sees, read the way a client reads them."""
    from computer_use import mcp_server

    return frozenset(t.name for t in asyncio.run(mcp_server.mcp.list_tools()))


class TestWireSurfaceIsTheWholeCatalog:
    def test_exactly_these_tools_are_exposed(self):
        assert _wire_tool_names() == WIRE_TOOLS

    def test_the_catalog_is_thirty_three(self):
        # 0.7.0 adds the four structured-tier tools (ui_tree/find/act/wait), and
        # the 0.7.x expansion adds ui_windows, apps and app_open, to the 26 that
        # 0.6.6 proved stable across the mcp major bump. The 26 stay byte-for-byte;
        # the surface is added to, never altered.
        assert len(WIRE_TOOLS) == 33


class TestRemovedModuleIsNotImported:
    """A source scan, not an import probe.

    An import probe passes on any machine whose environment still holds mcp 1.x.
    Scanning the source fails on the branch that reaches for the removed name
    out of muscle memory, whatever is installed.
    """

    def test_no_module_imports_the_removed_package(self):
        # Assembled rather than written out: the scan reads every .py under the
        # package including this one, so spelling the name here whole would make
        # the test its own only offender. Scanning itself is deliberate, since
        # exempting the scanner is a hole in the thing being scanned.
        removed = "mcp.server." + "fastmcp"
        offenders = [
            str(path.relative_to(ROOT))
            for path in sorted((ROOT / "computer_use").rglob("*.py"))
            if removed in path.read_text(encoding="utf-8")
        ]
        assert not offenders, (
            f"mcp 2.0.0 removed {removed}; these files still name it: "
            + ", ".join(offenders)
        )
