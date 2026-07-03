# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Translate ``upload`` file paths to the browser process's OS (the WSL boundary).

``upload`` is the one op whose params carry an OS path, so the translation lives
cua-side and the wire stays OS-agnostic. ``DOM.setFileInputFiles`` resolves each
path in Chrome's own process, so:

- **Native Chrome (Linux / macOS / Windows)** shares cua's filesystem — paths
  pass through unchanged.
- **WSL** drives *Windows* Chrome over the bridge, so a cua-side WSL path is
  unreadable to it. cua rewrites each entry:
  * ``/mnt/<drive>/...`` -> ``<DRIVE>:\\...`` (the file already lives on a Windows
    volume Windows Chrome can read directly), reusing the same ``/mnt/c`` interop
    foothold as host-manifest registration;
  * a path under the WSL rootfs -> a ``\\\\wsl.localhost\\<distro>\\...`` UNC that
    Windows Chrome can open over the 9P share.
"""

from __future__ import annotations

import os
import sys


def _detect_distro() -> str:
    """The WSL distro name (for the ``\\wsl.localhost`` UNC). Best-effort."""
    return os.environ.get("WSL_DISTRO_NAME", "") or "Ubuntu"


def _mnt_to_windows(path: str) -> str:
    """``/mnt/c/Users/..`` -> ``C:\\Users\\..`` (WSL view -> Windows form)."""
    drive = path[5].upper()
    rest = path[6:].replace("/", "\\")
    return f"{drive}:{rest}"


def _rootfs_to_unc(path: str, distro: str) -> str:
    """``/home/u/cv.pdf`` -> ``\\\\wsl.localhost\\<distro>\\home\\u\\cv.pdf``."""
    rest = path.lstrip("/").replace("/", "\\")
    return f"\\\\wsl.localhost\\{distro}\\{rest}"


def translate_upload_path(
    path: str, *, platform: str | None = None, distro: str | None = None
) -> str:
    """Rewrite one ``upload`` path to the browser process's OS.

    ``platform`` defaults to ``sys.platform`` (``"wsl"`` is passed explicitly by
    the bridge on WSL, which ``sys.platform`` reports as ``"linux"``). Native
    platforms return the path unchanged.
    """
    plat = platform or sys.platform
    if plat != "wsl":
        return path
    if path.startswith("/mnt/") and len(path) > 6 and path[6] == "/":
        return _mnt_to_windows(path)
    if path.startswith("/"):
        return _rootfs_to_unc(path, distro or _detect_distro())
    return path  # relative / already-Windows path — leave it alone


def translate_upload_paths(
    files: list[str], *, platform: str | None = None, distro: str | None = None
) -> list[str]:
    """Translate each path in ``files`` (see :func:`translate_upload_path`)."""
    return [
        translate_upload_path(f, platform=platform, distro=distro) for f in files
    ]
