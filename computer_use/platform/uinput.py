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

"""Pure-python uinput — a kernel virtual input device with no compiler needed.

The python-evdev package is sdist-only (needs a C toolchain); it is used here for
nothing but constants and ioctl numbers we can compute ourselves. This module
writes ``struct input_event`` records straight to ``/dev/uinput`` via ``fcntl``,
so the default Wayland input fallback installs from a pure wheel. It still needs
``/dev/uinput`` to be writable — the installer ships a udev rule for that.

The event encoding and emission are unit-tested with an injected fd; the real
device-create (ioctl setup) is permission-gated and covered by the e2e runbook.
"""

from __future__ import annotations

import fcntl
import os
import struct

# --- event types / codes (linux/input-event-codes.h) ---
EV_SYN, EV_KEY, EV_REL, EV_ABS = 0x00, 0x01, 0x02, 0x03
SYN_REPORT = 0
REL_WHEEL = 0x08
ABS_X, ABS_Y = 0x00, 0x01
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112

ABS_MAX = 32767

# input_event: timeval(16 on 64-bit) + __u16 type + __u16 code + __s32 value
_EVENT_FMT = "llHHi"


def pack_event(etype: int, code: int, value: int) -> bytes:
    """Pack one ``struct input_event`` (timestamp left zero; the kernel stamps it)."""
    return struct.pack(_EVENT_FMT, 0, 0, etype, code, value)


# --- ioctl numbers (_IOW/_IO over the 'U' base) ---
def _ioc(direction: int, type_ch: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(type_ch) << 8) | nr


_IOC_WRITE = 1
UI_DEV_CREATE = _ioc(0, "U", 1, 0)
UI_DEV_DESTROY = _ioc(0, "U", 2, 0)
UI_DEV_SETUP = _ioc(_IOC_WRITE, "U", 3, 92)      # sizeof(struct uinput_setup)
UI_ABS_SETUP = _ioc(_IOC_WRITE, "U", 4, 28)      # sizeof(struct uinput_abs_setup)
UI_SET_EVBIT = _ioc(_IOC_WRITE, "U", 100, 4)
UI_SET_KEYBIT = _ioc(_IOC_WRITE, "U", 101, 4)
UI_SET_RELBIT = _ioc(_IOC_WRITE, "U", 102, 4)
UI_SET_ABSBIT = _ioc(_IOC_WRITE, "U", 103, 4)

# Every key/button this virtual device may emit. Covers the main keyboard
# (evdev codes 1-88) plus the three mouse buttons.
_ALL_KEYS = list(range(1, 89)) + [BTN_LEFT, BTN_RIGHT, BTN_MIDDLE]


class UinputDevice:
    """A virtual absolute-pointer + keyboard device on ``/dev/uinput``.

    Pass ``fd`` to unit-test the encoding without touching the kernel. With no
    ``fd`` it opens and registers a real device (needs ``/dev/uinput`` write
    access) and raises ``OSError`` if it cannot.
    """

    def __init__(self, fd=None, *, screen_w: int = 1366, screen_h: int = 768):
        self._screen_w = max(1, screen_w)
        self._screen_h = max(1, screen_h)
        self._owns_fd = fd is None
        self._fd = fd if fd is not None else self._open_real_device()

    # --- emission (unit-tested) ---
    def emit(self, etype: int, code: int, value: int) -> None:
        self._fd.write(pack_event(etype, code, value))

    def syn(self) -> None:
        self.emit(EV_SYN, SYN_REPORT, 0)

    def move_abs(self, x: int, y: int) -> None:
        ax = int(max(0, min(x, self._screen_w)) * ABS_MAX / self._screen_w)
        ay = int(max(0, min(y, self._screen_h)) * ABS_MAX / self._screen_h)
        self.emit(EV_ABS, ABS_X, ax)
        self.emit(EV_ABS, ABS_Y, ay)
        self.syn()

    def button(self, code: int, pressed: bool) -> None:
        self.emit(EV_KEY, code, 1 if pressed else 0)
        self.syn()

    def key(self, code: int, pressed: bool) -> None:
        self.emit(EV_KEY, code, 1 if pressed else 0)
        self.syn()

    def wheel(self, steps: int) -> None:
        self.emit(EV_REL, REL_WHEEL, steps)
        self.syn()

    def close(self) -> None:
        if not self._owns_fd or self._fd is None:
            return
        try:
            fcntl.ioctl(self._fd, UI_DEV_DESTROY)
        except OSError:
            pass
        raw = self._fd.fileno() if hasattr(self._fd, "fileno") else self._fd
        try:
            os.close(raw)
        except (OSError, TypeError):
            pass
        self._fd = None

    # --- real device registration (permission-gated; e2e-covered) ---
    def _open_real_device(self) -> int:
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            for evbit in (EV_KEY, EV_ABS, EV_REL, EV_SYN):
                fcntl.ioctl(fd, UI_SET_EVBIT, evbit)
            for code in _ALL_KEYS:
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            fcntl.ioctl(fd, UI_SET_RELBIT, REL_WHEEL)
            for axis in (ABS_X, ABS_Y):
                fcntl.ioctl(fd, UI_SET_ABSBIT, axis)
                # struct uinput_abs_setup { __u16 code; struct input_absinfo info; }
                absinfo = struct.pack("iiiiii", 0, 0, ABS_MAX, 0, 0, 0)
                fcntl.ioctl(fd, UI_ABS_SETUP, struct.pack("H2x", axis) + absinfo)
            # struct uinput_setup { input_id id; char name[80]; __u32 ff_effects_max; }
            setup = struct.pack("HHHH", 0x03, 0x1234, 0x5678, 1)  # USB, vendor, product, ver
            setup += b"vadgr-cua virtual input".ljust(80, b"\x00")
            setup += struct.pack("I", 0)
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        return _RawFdWriter(fd)  # type: ignore[return-value]


class _RawFdWriter:
    """Adapts an int fd to the ``.write(bytes)`` seam ``UinputDevice`` emits through."""

    def __init__(self, fd: int):
        self._fd = fd

    def write(self, data: bytes) -> int:
        return os.write(self._fd, data)

    def fileno(self) -> int:
        return self._fd
