# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Allocate a unique temporary file path without creating the file.

The agent often wants a path it can hand to a downstream tool that
expects to create the file itself. ``tempfile.mkstemp`` would create the
file; this helper just returns a guaranteed-unique path.
"""

from __future__ import annotations

import os
import tempfile as _stdlib_tempfile
import uuid
from typing import Any

from computer_use.core.ops import OperationGroup

_ops = OperationGroup("tempfile")


@_ops.operation("temp_path")
def _temp_path(prefix: str = "vcu-", suffix: str = "") -> str:
    name = f"{prefix}{uuid.uuid4().hex[:12]}{suffix}"
    return os.path.join(_stdlib_tempfile.gettempdir(), name)


def tempfile(op: str = "temp_path", prefix: str = "vcu-", suffix: str = "") -> Any:
    """Dispatch a tempfile sub-operation.

    Args:
        op: Currently only ``temp_path`` (allocate a unique path).
        prefix: Filename prefix. Defaults to ``vcu-``.
        suffix: Filename suffix (e.g. ``.txt``).

    Returns:
        Absolute path string. The file is NOT created.
    """
    return _ops.run(op, prefix=prefix, suffix=suffix)
