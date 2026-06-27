# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Pure-python uinput: input_event packing + event emission against a fake fd."""

import struct

from computer_use.platform.backends import uinput as U


class FakeFd:
    """Captures bytes written to a uinput fd (no real /dev/uinput needed)."""

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)


class TestPackEvent:
    def test_size_is_24_bytes(self):
        # struct input_event on 64-bit: timeval(16) + type(2) + code(2) + value(4)
        assert len(U.pack_event(U.EV_KEY, 30, 1)) == 24

    def test_roundtrip_fields(self):
        data = U.pack_event(U.EV_KEY, 272, 1)
        _sec, _usec, etype, code, value = struct.unpack("llHHi", data)
        assert (etype, code, value) == (U.EV_KEY, 272, 1)


class TestDeviceEmit:
    def test_emit_writes_packed_event(self):
        fd = FakeFd()
        dev = U.UinputDevice(fd=fd, screen_w=1366, screen_h=768)
        dev.emit(U.EV_KEY, U.BTN_LEFT, 1)
        assert fd.writes[-1] == U.pack_event(U.EV_KEY, U.BTN_LEFT, 1)

    def test_syn_emits_report(self):
        fd = FakeFd()
        dev = U.UinputDevice(fd=fd, screen_w=1366, screen_h=768)
        dev.syn()
        assert fd.writes[-1] == U.pack_event(U.EV_SYN, U.SYN_REPORT, 0)

    def test_move_abs_scales_to_device_range(self):
        fd = FakeFd()
        dev = U.UinputDevice(fd=fd, screen_w=1000, screen_h=1000)
        dev.move_abs(500, 250)  # midpoint x, quarter y -> scaled into 0..32767
        # two ABS writes + a SYN
        sec = [struct.unpack("llHHi", w) for w in fd.writes]
        xs = [v for (_s, _u, t, c, v) in sec if t == U.EV_ABS and c == U.ABS_X]
        ys = [v for (_s, _u, t, c, v) in sec if t == U.EV_ABS and c == U.ABS_Y]
        assert xs and ys
        assert abs(xs[-1] - 32767 // 2) <= 2
        assert abs(ys[-1] - 32767 // 4) <= 2


class TestButtonAndKeyMaps:
    def test_button_codes(self):
        assert U.BTN_LEFT == 0x110 and U.BTN_RIGHT == 0x111 and U.BTN_MIDDLE == 0x112
