# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Subprocess + PATH lookup helpers.

``shell.run`` is classified HIGH because it can mutate anything; the
agent loop should treat it accordingly.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Optional, Union

from computer_use.core.ops import OperationGroup

# Cap to prevent a runaway subprocess from hanging the MCP session.
_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 600

_ops = OperationGroup("shell")


def _run(
    command: Union[str, list[str]],
    shell: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    if timeout > _MAX_TIMEOUT:
        timeout = _MAX_TIMEOUT
    if isinstance(command, str) and not shell:
        # The agent passed a string but didn't ask for shell parsing; treat as
        # a single argv element to avoid the unsafe shell=True surprise.
        command = [command]
    proc = subprocess.run(  # noqa: S603 — HIGH-risk tool by design
        command,
        shell=shell,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _which(command: str) -> Optional[str]:
    return shutil.which(command)


@_ops.operation("run")
def _op_run(
    command: Union[str, list[str], None] = None,
    shell_mode: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    if command is None:
        raise ValueError("shell.run requires a command")
    return _run(command, shell=shell_mode, timeout=timeout, cwd=cwd)


@_ops.operation("which")
def _op_which(command: Union[str, list[str], None] = None) -> Optional[str]:
    if not isinstance(command, str):
        raise ValueError("shell.which requires a string command name")
    return _which(command)


def shell(
    op: str,
    command: Union[str, list[str], None] = None,
    shell_mode: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Optional[str] = None,
) -> Any:
    """Dispatch a shell sub-operation.

    Args:
        op: ``run`` or ``which``.
        command: argv list (preferred) or string. For ``which``, just a name.
        shell_mode: Pass True to invoke the user's shell to interpret the
            command string. Default False (safer).
        timeout: Seconds before the subprocess is killed. Capped at 600.
        cwd: Working directory for the subprocess.
    """
    return _ops.run(
        op, command=command, shell_mode=shell_mode, timeout=timeout, cwd=cwd
    )
