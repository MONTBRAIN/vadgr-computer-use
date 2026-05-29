# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Risk levels for tools.

A tool's risk drives policy (logging detail, confirmation gates, denylists).
The enum is intentionally small; we add levels only when policy actually
differs.
"""

from __future__ import annotations

from enum import Enum


class Risk(Enum):
    """Risk level of a tool call.

    - READ_ONLY: reads only; cannot mutate user state.
    - LOW: mutates ephemeral / non-critical state.
    - MEDIUM: mutates user state (mouse / keyboard / files within scope).
    - HIGH: mutates outside the agent's scope (network sends, deletions).
    """

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
