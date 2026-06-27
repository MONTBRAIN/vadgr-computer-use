# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""SessionContext detection: server, compositor, uinput, present libs."""

import pytest

from computer_use.platform.resolver import session as S
from computer_use.platform.resolver.session import SessionContext


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("WAYLAND_DISPLAY", "DISPLAY", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP"):
        monkeypatch.delenv(var, raising=False)
    # Default the probes to "nothing present" so each test opts in.
    monkeypatch.setattr(S, "_uinput_writable", lambda: False)
    monkeypatch.setattr(S, "_present_libs", lambda: frozenset())


class TestServer:
    def test_x11(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.setenv("DISPLAY", ":0")
        assert SessionContext.detect().server == "x11"

    def test_wayland_via_wayland_display(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert SessionContext.detect().server == "wayland"

    def test_wayland_via_session_type(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        assert SessionContext.detect().server == "wayland"

    def test_headless_when_no_display(self):
        assert SessionContext.detect().server == "headless"


class TestCompositor:
    def _wayland(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def test_gnome(self, monkeypatch):
        self._wayland(monkeypatch)
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
        assert SessionContext.detect().compositor == "gnome"

    def test_kde(self, monkeypatch):
        self._wayland(monkeypatch)
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
        assert SessionContext.detect().compositor == "kde"

    def test_wlroots_sway(self, monkeypatch):
        self._wayland(monkeypatch)
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "sway")
        assert SessionContext.detect().compositor == "wlroots"

    def test_unknown(self, monkeypatch):
        self._wayland(monkeypatch)
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "weston")
        assert SessionContext.detect().compositor == "unknown"


class TestProbes:
    def test_uinput_flag(self, monkeypatch):
        monkeypatch.setattr(S, "_uinput_writable", lambda: True)
        assert SessionContext.detect().has_uinput is True

    def test_libs(self, monkeypatch):
        monkeypatch.setattr(S, "_present_libs", lambda: frozenset({"libei", "libpipewire"}))
        ctx = SessionContext.detect()
        assert "libei" in ctx.libs and "libpipewire" in ctx.libs

    def test_frozen(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        ctx = SessionContext.detect()
        with pytest.raises(Exception):
            ctx.server = "x11"  # frozen dataclass
