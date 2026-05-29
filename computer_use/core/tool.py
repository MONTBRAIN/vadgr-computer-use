# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tool dataclass: a single registered tool with its metadata.

The `@tool` decorator attaches metadata (name, tier, risk, schema) and
registers the function with the global ToolRegistry at import time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from computer_use.core.risk import Risk
from computer_use.core.tier import Tier


@dataclass(frozen=True)
class Tool:
    """A single tool entry. Immutable after registration."""

    name: str
    tier: Tier
    risk: Risk
    func: Callable
    doc: str = ""
