# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Filesystem operations: read, write, list, stat, delete.

A single dispatch function ``fs(op=...)`` keeps the wire surface compact
(one MCP tool) while internal helpers stay individually testable.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from computer_use.core.ops import OperationGroup

_ops = OperationGroup("fs")


@_ops.operation("read")
def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


@_ops.operation("write")
def _write(path: str, content: str = "") -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "written": len(content)}


@_ops.operation("list")
def _list(path: str) -> list[str]:
    return sorted(e.name for e in Path(path).iterdir())


@_ops.operation("stat")
def _stat(path: str) -> dict[str, Any]:
    p = Path(path)
    st = p.stat()
    if p.is_file():
        kind = "file"
    elif p.is_dir():
        kind = "dir"
    else:
        kind = "other"
    return {"path": str(p), "size": st.st_size, "kind": kind, "mtime": st.st_mtime}


@_ops.operation("delete")
def _delete(path: str, recursive: bool = False) -> dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        if not recursive:
            raise IsADirectoryError(
                f"{path} is a directory; pass recursive=True to remove it"
            )
        shutil.rmtree(p)
    else:
        os.remove(p)
    return {"path": str(p), "deleted": True}


def fs(
    op: str,
    path: str,
    content: str = "",
    recursive: bool = False,
) -> Any:
    """Dispatch a filesystem sub-operation.

    Args:
        op: One of ``read``, ``write``, ``list``, ``stat``, ``delete``.
        path: Filesystem path.
        content: Required when ``op="write"``.
        recursive: Required when deleting a directory.
    """
    return _ops.run(op, path=path, content=content, recursive=recursive)
