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


def _copy(text: str) -> dict:
    backend = _pick_backend()
    if backend is None:
        raise RuntimeError(
            "no clipboard backend available; install clip.exe (Windows), "
            "pbcopy (macOS), wl-clipboard (Wayland), or xclip (X11)"
        )
    name, copy_cmd, _ = backend
    proc = subprocess.run(  # noqa: S603
        copy_cmd, input=text, text=True, capture_output=True
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


def clipboard(op: str, text: Optional[str] = None) -> object:
    """Dispatch a clipboard sub-operation.

    Args:
        op: ``copy`` or ``paste``.
        text: Required for ``copy``.

    Raises:
        RuntimeError: When no clipboard backend is on PATH, or the chosen
            backend's subprocess exits non-zero.
    """
    if op == "copy":
        if text is None:
            raise ValueError("clipboard.copy requires text")
        return _copy(text)
    if op == "paste":
        return _paste()
    raise ValueError(f"unknown clipboard op {op!r}; expected copy or paste")
