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

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from typing import Any

from computer_use.core.ops import OperationGroup

# Cap to prevent a runaway subprocess from hanging the MCP session.
_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 600

_ops = OperationGroup("shell")


def _run(
    command: str | list[str],
    shell: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> dict[str, Any]:
    timeout = min(timeout, _MAX_TIMEOUT)
    if isinstance(command, str) and not shell:
        # The agent passed a string but didn't ask for shell parsing; treat as
        # a single argv element to avoid the unsafe shell=True surprise.
        command = [command]
    proc = subprocess.run(
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


def _which(command: str) -> str | None:
    return shutil.which(command)


async def _terminate_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        await asyncio.to_thread(
            subprocess.run,
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        await asyncio.wait_for(proc.wait(), timeout=1)
    except asyncio.TimeoutError:
        if sys.platform == "win32":
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        await proc.wait()


async def _run_async(
    command: str | list[str],
    shell: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> dict[str, Any]:
    timeout = min(timeout, _MAX_TIMEOUT)
    if isinstance(command, str) and not shell:
        command = [command]
    if shell:
        if not isinstance(command, str):
            raise ValueError("shell_mode requires a string command")
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            start_new_session=sys.platform != "win32",
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            start_new_session=sys.platform != "win32",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0),
        )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.CancelledError:
        await _terminate_tree(proc)
        raise
    except asyncio.TimeoutError as error:
        await _terminate_tree(proc)
        raise subprocess.TimeoutExpired(command, timeout) from error
    return {
        "returncode": proc.returncode,
        # Never strict. The synchronous path decoded with the locale codepage,
        # so a command emitting cp1252 on Windows or any non-UTF-8 byte used to
        # return its output. A strict decode here would raise instead, turning
        # ordinary output into a failed tool call. Replacement keeps the result
        # readable and keeps the failure mode out of the agent's way.
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
    }


@_ops.operation("run")
def _op_run(
    command: str | list[str] | None = None,
    shell_mode: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> dict[str, Any]:
    if command is None:
        raise ValueError("shell.run requires a command")
    return _run(command, shell=shell_mode, timeout=timeout, cwd=cwd)


@_ops.operation("which")
def _op_which(command: str | list[str] | None = None) -> str | None:
    if not isinstance(command, str):
        raise ValueError("shell.which requires a string command name")
    return _which(command)


def shell(
    op: str,
    command: str | list[str] | None = None,
    shell_mode: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: str | None = None,
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


async def shell_async(
    op: str,
    command: str | list[str] | None = None,
    shell_mode: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: str | None = None,
) -> Any:
    if op == "which":
        return _op_which(command=command)
    if op != "run":
        return shell(op=op, command=command, shell_mode=shell_mode, timeout=timeout, cwd=cwd)
    if command is None:
        raise ValueError("shell.run requires a command")
    return await _run_async(command, shell=shell_mode, timeout=timeout, cwd=cwd)
