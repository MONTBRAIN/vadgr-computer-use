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

    def test_uses_given_escalation_prefix(self):
        plan = deps.build_plan("apt", missing_names={"wl-clipboard"}, escalate="pkexec")
        assert plan and plan[0].startswith("pkexec apt-get install")


class TestEscalation:
    def test_prefers_pkexec_with_display(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/" + c if c in ("pkexec", "sudo") else None)
        monkeypatch.setenv("DISPLAY", ":0")
        assert deps.detect_escalation() == "pkexec"

    def test_falls_back_to_sudo_without_pkexec(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/sudo" if c == "sudo" else None)
        assert deps.detect_escalation() == "sudo"

    def test_pkexec_needs_a_display(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/" + c if c in ("pkexec", "sudo") else None)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert deps.detect_escalation() == "sudo"

    def test_none_when_neither(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: None)
        assert deps.detect_escalation() is None


class TestPrivilegedSteps:
    def test_apt_steps_are_unprefixed_commands(self):
        steps = deps._privileged_steps("apt", {"wl-clipboard", "uinput-access"})
        assert any(s.startswith("apt-get install -y wl-clipboard") for s in steps)
        assert any("/etc/udev/rules.d" in s for s in steps)
        assert any(s.startswith("usermod -aG input") for s in steps)
        # no escalation baked into the raw steps
        assert all(not s.startswith(("sudo", "pkexec")) for s in steps)
