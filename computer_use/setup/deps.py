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

"""System-dependency provisioning — the bits ``pip`` cannot install.

The desktop tier's common GNOME/KDE/X11 paths are pure-python (jeepney, Pillow,
python-xlib) and need no system packages. What's left is genuine OS-package
residue — ``wl-clipboard`` for the clipboard, and write access to ``/dev/uinput``
for the uinput fallback. ``pip`` cannot install those (and must not shell out to
a package manager during install), so this module diagnoses what's missing and
emits an explicit, distro-aware plan, à la ``playwright install-deps``: printed
by default, executed only with ``--yes``.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from pathlib import Path

# package-manager -> (detect binary, install-command tokens WITHOUT escalation).
# The privilege escalation (pkexec / sudo) is chosen separately and prepended at
# run time, so the whole plan runs under a single auth prompt.
_MANAGERS = {
    "apt": ("apt-get", ["apt-get", "install", "-y"]),
    "dnf": ("dnf", ["dnf", "install", "-y"]),
    "pacman": ("pacman", ["pacman", "-S", "--noconfirm"]),
    "zypper": ("zypper", ["zypper", "install", "-y"]),
}

# logical dep -> package name per manager (same name on all four here).
_PACKAGES = {
    "wl-clipboard": {m: "wl-clipboard" for m in _MANAGERS},
}

_UDEV_RULE = Path(__file__).resolve().parent / "udev" / "99-vadgr-uinput.rules"


def detect_package_manager() -> str | None:
    for name, (binary, _cmd) in _MANAGERS.items():
        if shutil.which(binary):
            return name
    return None


def _clipboard_present() -> bool:
    return any(shutil.which(t) for t in ("wl-copy", "wl-paste", "xclip", "xsel"))


def diagnose() -> dict:
    """Report which system-level deps are missing, each with a reason + fix."""
    missing = []
    if not _clipboard_present():
        missing.append({
            "name": "wl-clipboard",
            "reason": "no clipboard backend (wl-copy/xclip) on PATH",
            "fix": "install wl-clipboard",
        })
    if not os.access("/dev/uinput", os.W_OK):
        missing.append({
            "name": "uinput-access",
            "reason": "/dev/uinput is not writable (uinput input fallback unavailable)",
            "fix": "install the udev rule and join the 'input' group",
        })
    return {"package_manager": detect_package_manager(), "missing": missing}


def detect_escalation() -> str | None:
    """Pick how to gain root: ``pkexec`` (graphical polkit auth) when there is a
    display, else ``sudo``. Returns None if neither is available.

    pkexec pops a desktop password dialog (one click, no terminal), so the whole
    plan runs under a single GUI prompt — the macOS-style "authenticate once".
    """
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if has_display and shutil.which("pkexec"):
        return "pkexec"
    if shutil.which("sudo"):
        return "sudo"
    if shutil.which("pkexec"):
        return "pkexec"
    return None


def _privileged_steps(manager: str | None, missing_names: set[str]) -> list[str]:
    """The raw root commands (no escalation prefix) to provision the missing deps."""
    steps: list[str] = []
    pkgs = [
        _PACKAGES[name][manager]
        for name in sorted(missing_names)
        if name in _PACKAGES and manager in _MANAGERS
    ]
    if pkgs:
        steps.append(" ".join(_MANAGERS[manager][1] + pkgs))
    if "uinput-access" in missing_names:
        steps.append(f"cp {_UDEV_RULE} /etc/udev/rules.d/99-vadgr-uinput.rules")
        steps.append("udevadm control --reload-rules && udevadm trigger")
        steps.append(f"usermod -aG input {getpass.getuser()}")
    return steps


def build_plan(
    manager: str | None, missing_names: set[str], *, escalate: str = "sudo"
) -> list[str]:
    """Human-readable plan: the privileged steps, each shown under ``escalate``."""
    if not missing_names:
        return []
    steps = _privileged_steps(manager, missing_names)
    plan = [f"{escalate} {step}" for step in steps]
    if not steps and "wl-clipboard" in missing_names and manager is None:
        plan.append("# unknown package manager — add 'wl-clipboard' via your distro's tools")
    return plan


def install_deps(*, assume_yes: bool = False, dry_run: bool = True) -> int:
    """Diagnose, then print the plan (default) or run it under one auth prompt."""
    report = diagnose()
    if not report["missing"]:
        print("All system dependencies are present.")
        return 0

    manager = report["package_manager"]
    names = {item["name"] for item in report["missing"]}
    escalate = detect_escalation()
    plan = build_plan(manager, names, escalate=escalate or "sudo")

    print(f"Detected package manager: {manager or 'unknown'}")
    print(f"Privilege escalation: {escalate or 'none (run as root)'}")
    print("Missing:")
    for item in report["missing"]:
        print(f"  - {item['name']}: {item['reason']}")
    print("\nPlan:")
    for line in plan:
        print(f"  {line}")

    if dry_run or not assume_yes:
        print("\n(dry run — re-run with --yes to execute)")
        return 0

    steps = _privileged_steps(manager, names)
    if not steps:
        print("\nNothing runnable (unknown package manager) — install the package manually.")
        return 1
    if escalate is None:
        print("\nNo pkexec or sudo available — run the plan as root.")
        return 1

    # One escalated invocation -> a single GUI/sudo auth prompt for the whole plan.
    joined = " && ".join(steps)
    print(f"\n$ {escalate} sh -c {joined!r}")
    rc = subprocess.run([escalate, "sh", "-c", joined]).returncode
    if rc != 0:
        print(f"provisioning failed (rc={rc})")
    return rc
