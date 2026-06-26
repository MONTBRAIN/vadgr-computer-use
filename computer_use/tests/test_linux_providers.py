# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""describe_backends: the session-aware capture/input resolution shown by doctor."""

from unittest.mock import patch

from computer_use.platform.linux_providers import describe_backends
from computer_use.platform.session import SessionContext


def _ctx(server="wayland", compositor="gnome", has_uinput=False, libs=frozenset()):
    return SessionContext(server=server, compositor=compositor, has_uinput=has_uinput, libs=libs)


class TestDescribe:
    def test_x11_selects_mss_and_xtest(self):
        d = describe_backends(_ctx(server="x11", compositor="unknown"))
        assert d["capture"]["selected"] == "mss"
        assert d["input"]["selected"] == "xtest"

    def test_gnome_wayland_with_portal_selects_portal_and_mutter(self):
        with patch("computer_use.platform.linux_providers.portal_available", return_value=True), \
             patch("computer_use.platform.linux_providers._mutter_available", return_value=True), \
             patch("shutil.which", return_value=None):
            d = describe_backends(_ctx(server="wayland", compositor="gnome"))
        assert d["capture"]["selected"] == "portal"
        assert d["input"]["selected"] == "mutter-remotedesktop"

    def test_gnome_with_gnome_screenshot_prefers_it_over_portal(self):
        """Backward-compat: 24.04 keeps gnome-screenshot ahead of the portal."""
        with patch("computer_use.platform.linux_providers.portal_available", return_value=True), \
             patch("shutil.which", side_effect=lambda c: "/u/" + c if c == "gnome-screenshot" else None):
            d = describe_backends(_ctx(server="wayland", compositor="gnome"))
        assert d["capture"]["selected"] == "gnome-screenshot"

    def test_wlroots_uinput_when_writable(self):
        with patch("computer_use.platform.linux_providers.portal_available", return_value=False), \
             patch("computer_use.platform.linux_providers._mutter_available", return_value=False), \
             patch("shutil.which", side_effect=lambda c: "/u/grim" if c == "grim" else None):
            d = describe_backends(_ctx(server="wayland", compositor="wlroots", has_uinput=True))
        assert d["capture"]["selected"] == "grim"
        assert d["input"]["selected"] == "uinput"

    def test_reports_session_fields(self):
        d = describe_backends(_ctx(server="wayland", compositor="kde", libs=frozenset({"libei"})))
        assert d["server"] == "wayland" and d["compositor"] == "kde"
        assert "libei" in d["libs"]

    def test_candidates_carry_applicable_flags(self):
        d = describe_backends(_ctx(server="x11", compositor="unknown"))
        names = {c["name"]: c["applicable"] for c in d["capture"]["candidates"]}
        assert names["mss"] is True and names["grim"] is False
