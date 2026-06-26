# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Dependency provisioning: package-manager detection + the install plan."""

from unittest.mock import patch

from computer_use.setup import deps


class TestDetectPackageManager:
    def test_prefers_apt(self):
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/" + c if c == "apt-get" else None):
            assert deps.detect_package_manager() == "apt"

    def test_dnf(self):
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/dnf" if c == "dnf" else None):
            assert deps.detect_package_manager() == "dnf"

    def test_pacman(self):
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/pacman" if c == "pacman" else None):
            assert deps.detect_package_manager() == "pacman"

    def test_none_when_unknown(self):
        with patch("shutil.which", return_value=None):
            assert deps.detect_package_manager() is None


class TestDiagnose:
    def test_flags_missing_clipboard(self):
        with patch("shutil.which", return_value=None), \
             patch("os.access", return_value=False):
            report = deps.diagnose()
        names = {item["name"] for item in report["missing"]}
        assert "wl-clipboard" in names
        assert "uinput-access" in names

    def test_clipboard_present_not_missing(self):
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/wl-copy" if c == "wl-copy" else None), \
             patch("os.access", return_value=True):
            report = deps.diagnose()
        names = {item["name"] for item in report["missing"]}
        assert "wl-clipboard" not in names
        assert "uinput-access" not in names


class TestInstallPlan:
    def test_apt_plan_includes_clipboard_install_and_udev(self):
        plan = deps.build_plan("apt", missing_names={"wl-clipboard", "uinput-access"})
        joined = "\n".join(plan)
        assert "apt-get install" in joined and "wl-clipboard" in joined
        assert "udev" in joined or "uinput" in joined
        assert "usermod -aG input" in joined

    def test_pacman_plan_uses_pacman(self):
        plan = deps.build_plan("pacman", missing_names={"wl-clipboard"})
        assert any("pacman -S" in line for line in plan)

    def test_empty_plan_when_nothing_missing(self):
        assert deps.build_plan("apt", missing_names=set()) == []

    def test_unknown_manager_has_no_install_lines(self):
        plan = deps.build_plan(None, missing_names={"wl-clipboard"})
        assert all("install" not in line.lower() for line in plan)
