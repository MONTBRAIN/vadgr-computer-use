# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tier 1 structured tools: read the accessibility tree and act on it by ref.

The MCP wire wrappers live in ``computer_use.mcp_server`` and apply both
``@mcp.tool()`` and ``@tool(...)``, matching the pattern the pixel and system
tools use. The logic here is per-OS-agnostic; the OS-specific backend resolves
behind ``backend.resolve_backend()``.
"""

from computer_use.tools.ui.tools import ui_act, ui_find, ui_tree, ui_wait

__all__ = ["ui_act", "ui_find", "ui_tree", "ui_wait"]
