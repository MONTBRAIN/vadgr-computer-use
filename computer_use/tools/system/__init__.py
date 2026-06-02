# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tier 0 system tools.

Each module exposes one public function named after the module that
dispatches sub-operations via the ``op`` argument. The MCP wire wrappers
live in ``computer_use.mcp_server`` and apply both ``@mcp.tool()`` and
``@tool(...)`` to the entry point so the registry stays accurate.
"""
