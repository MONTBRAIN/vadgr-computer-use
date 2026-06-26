# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Linux session detection — the one input the backend resolver needs.

Detects the display server (X11 / Wayland / headless), the Wayland compositor
family (GNOME / KDE / wlroots / unknown), whether ``/dev/uinput`` is writable,
and which optional shared libraries are present. This is pure detection: it
holds no policy about which backend to pick (that is the resolver's job).
"""

from __future__ import annotations

import ctypes.util
import os
from dataclasses import dataclass
from typing import Literal

Server = Literal["x11", "wayland", "headless"]
Compositor = Literal["gnome", "kde", "wlroots", "unknown"]

# Shared libs the standards-based backends can use via ctypes. Detected by name
# so a backend can declare "I need libei" without importing anything heavy.
_OPTIONAL_LIBS = ("libei", "libpipewire-0.3", "xkbcommon")
# Reported under stable short names regardless of soname.
_LIB_ALIASES = {"libpipewire-0.3": "libpipewire", "xkbcommon": "libxkbcommon"}

_WLROOTS_DESKTOPS = ("sway", "hyprland", "wlroots", "river", "labwc", "wayfire")


def _is_wayland() -> bool:
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _is_x11() -> bool:
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        return True
    return bool(os.environ.get("DISPLAY")) and not _is_wayland()


def _detect_server() -> Server:
    if _is_wayland():
        return "wayland"
    if _is_x11():
        return "x11"
    return "headless"


def _detect_compositor() -> Compositor:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop:
        return "gnome"
    if "kde" in desktop or "plasma" in desktop:
        return "kde"
    if any(name in desktop for name in _WLROOTS_DESKTOPS):
        return "wlroots"
    return "unknown"


def _uinput_writable() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def _present_libs() -> frozenset[str]:
    found = set()
    for name in _OPTIONAL_LIBS:
        if ctypes.util.find_library(name):
            found.add(_LIB_ALIASES.get(name, name))
    return frozenset(found)


@dataclass(frozen=True)
class SessionContext:
    """A snapshot of the desktop session the resolver picks a backend for."""

    server: Server
    compositor: Compositor
    has_uinput: bool
    libs: frozenset[str]

    @classmethod
    def detect(cls) -> "SessionContext":
        return cls(
            server=_detect_server(),
            compositor=_detect_compositor() if _is_wayland() else "unknown",
            has_uinput=_uinput_writable(),
            libs=_present_libs(),
        )
