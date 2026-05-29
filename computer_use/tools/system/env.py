# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Process-scoped environment variables.

``env.set`` does NOT persist to the user's shell init — it only updates
the running MCP server's ``os.environ``. Documented in the docstring so
the agent doesn't mistake it for a persistent setter.
"""

from __future__ import annotations

import os
from typing import Any, Optional


def env(op: str, name: str, value: Optional[str] = None) -> Any:
    """Dispatch an environment-variable sub-operation.

    Args:
        op: ``get`` or ``set``.
        name: Variable name.
        value: Required for ``set``. Applied to ``os.environ[name]``;
            does NOT persist beyond the current process.

    Returns:
        The string value for ``get`` (or ``None`` if unset).
        ``{"name": ..., "value": ...}`` for ``set``.
    """
    if op == "get":
        return os.environ.get(name)
    if op == "set":
        if value is None:
            raise ValueError("env.set requires value")
        os.environ[name] = value
        return {"name": name, "value": value}
    raise ValueError(f"unknown env op {op!r}; expected get or set")
