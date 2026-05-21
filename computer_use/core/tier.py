# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tool tiers per ARCHITECTURE.md §5.1.

| Tier | Examples | Cost |
| ZERO | System: fs.read, shell.run, http.fetch, ... | tens of tokens |
| HALF | CLI wrappers: git.status, search.find | tens-to-hundreds |
| ONE  | Browser DOM / Structured (AT-SPI / UIA / AX) | hundreds |
| TWO  | Pixel fallback: screenshot + vision | thousands |
"""

from __future__ import annotations

from enum import Enum


class Tier(Enum):
    """Cost tier of a tool. Lower is cheaper / faster / preferred."""

    ZERO = 0
    HALF = 0.5
    ONE = 1
    TWO = 2

    def __str__(self) -> str:
        # Stable string representation for JSON keys (doctor uses this).
        v = self.value
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
