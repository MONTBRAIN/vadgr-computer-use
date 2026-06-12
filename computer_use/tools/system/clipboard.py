# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Clipboard read / write.

Each backend is a (copy_argv, paste_argv) pair that uses stdin/stdout to
move text. The first available pair wins:

1. ``clip.exe`` + ``powershell.exe Get-Clipboard`` — Windows + WSL2.
2. ``pbcopy`` + ``pbpaste`` — macOS.
3. ``wl-copy`` + ``wl-paste`` — Wayland.
4. ``xclip -selection clipboard`` — X11.

If none are on PATH, the call raises a RuntimeError explaining what to
install. Tests skip gracefully on hosts without any backend.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional

from computer_use.core.ops import OperationGroup

_ops = OperationGroup("clipboard")

_BACKENDS = [
    # (name, copy_cmd, paste_cmd)
    ("clip.exe", ["clip.exe"], ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"]),
    ("pbcopy", ["pbcopy"], ["pbpaste"]),
    ("wl-copy", ["wl-copy"], ["wl-paste", "--no-newline"]),
    ("xclip", ["xclip", "-selection", "clipboard", "-in"], ["xclip", "-selection", "clipboard", "-out"]),
]


def _pick_backend() -> Optional[tuple[str, list[str], list[str]]]:
    """Return the first backend whose copy binary is on PATH, or None."""
    # On macOS prefer pbcopy/pbpaste; otherwise fall back to the canonical order.
    order = list(_BACKENDS)
    if sys.platform == "darwin":
        order.sort(key=lambda b: 0 if b[0] == "pbcopy" else 1)
    for name, copy_cmd, paste_cmd in order:
        if shutil.which(copy_cmd[0]) and shutil.which(paste_cmd[0]):
            return name, copy_cmd, paste_cmd
    return None


# wl-copy has no central clipboard store to write to and exit: the source
# process must stay alive to serve the data, so wl-copy forks a background
# daemon. That daemon inherits the parent's std fds, so capturing them keeps
# the read end open and ``subprocess.run`` blocks forever. We special-case it
# below; the defensive timeout also guards the (rare) sync-write window.
_COPY_TIMEOUT = 5.0


def _copy_detached(copy_cmd: list[str], text: str) -> None:
    """Feed *text* to a copy backend that detaches a daemon (e.g. wl-copy).

    The daemon must keep the *data* alive but must not hold our pipes open, so
    stdout/stderr go to ``/dev/null``. We write the text to stdin, close it
    (EOF lets the foreground process hand off to its daemon), then wait only on
    the foreground process with a bounded timeout — never on the daemon.
    """
    proc = subprocess.Popen(  # noqa: S603
        copy_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        proc.stdin.write(text)
        proc.stdin.close()
        proc.wait(timeout=_COPY_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise


def _copy(text: str) -> dict:
    backend = _pick_backend()
    if backend is None:
        raise RuntimeError(
            "no clipboard backend available; install clip.exe (Windows), "
            "pbcopy (macOS), wl-clipboard (Wayland), or xclip (X11)"
        )
    name, copy_cmd, _ = backend
    if name == "wl-copy":
        _copy_detached(copy_cmd, text)
        return {"backend": name, "bytes": len(text)}
    proc = subprocess.run(  # noqa: S603
        copy_cmd, input=text, text=True, capture_output=True, timeout=_COPY_TIMEOUT
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"clipboard copy via {name} failed: {proc.stderr.strip() or 'no error output'}"
        )
    return {"backend": name, "bytes": len(text)}


def _paste() -> str:
    backend = _pick_backend()
    if backend is None:
        raise RuntimeError(
            "no clipboard backend available; install clip.exe (Windows), "
            "pbcopy (macOS), wl-clipboard (Wayland), or xclip (X11)"
        )
    name, _, paste_cmd = backend
    proc = subprocess.run(  # noqa: S603
        paste_cmd, text=True, capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"clipboard paste via {name} failed: {proc.stderr.strip() or 'no error output'}"
        )
    return proc.stdout


@_ops.operation("copy")
def _op_copy(text: Optional[str] = None) -> dict:
    if text is None:
        raise ValueError("clipboard.copy requires text")
    return _copy(text)


@_ops.operation("paste")
def _op_paste() -> str:
    return _paste()


def clipboard(op: str, text: Optional[str] = None) -> object:
    """Dispatch a clipboard sub-operation.

    Args:
        op: ``copy`` or ``paste``.
        text: Required for ``copy``.

    Raises:
        RuntimeError: When no clipboard backend is on PATH, or the chosen
            backend's subprocess exits non-zero.
    """
    return _ops.run(op, text=text)
