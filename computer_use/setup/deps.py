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

import os
import shutil
import subprocess
from pathlib import Path

# package-manager -> (detect binary, install-command prefix tokens)
_MANAGERS = {
    "apt": ("apt-get", ["sudo", "apt-get", "install", "-y"]),
    "dnf": ("dnf", ["sudo", "dnf", "install", "-y"]),
    "pacman": ("pacman", ["sudo", "pacman", "-S", "--noconfirm"]),
    "zypper": ("zypper", ["sudo", "zypper", "install", "-y"]),
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


def build_plan(manager: str | None, missing_names: set[str]) -> list[str]:
    """Return the shell commands that would provision the missing deps."""
    if not missing_names:
        return []
    plan: list[str] = []

    pkgs = [
        _PACKAGES[name][manager]
        for name in sorted(missing_names)
        if name in _PACKAGES and manager in _MANAGERS
    ]
    if pkgs:
        prefix = " ".join(_MANAGERS[manager][1])
        plan.append(f"{prefix} {' '.join(pkgs)}")
    elif "wl-clipboard" in missing_names and manager is None:
        plan.append("# unknown package manager — add 'wl-clipboard' via your distro's tools")

    if "uinput-access" in missing_names:
        plan.append(f"sudo cp {_UDEV_RULE} /etc/udev/rules.d/99-vadgr-uinput.rules")
        plan.append("sudo udevadm control --reload-rules && sudo udevadm trigger")
        plan.append("sudo usermod -aG input \"$USER\"   # then log out and back in")

    return plan


def install_deps(*, assume_yes: bool = False, dry_run: bool = True) -> int:
    """Diagnose, then print the plan (default) or execute it (``assume_yes``)."""
    report = diagnose()
    manager = report["package_manager"]
    names = {item["name"] for item in report["missing"]}
    plan = build_plan(manager, names)

    if not report["missing"]:
        print("All system dependencies are present.")
        return 0

    print(f"Detected package manager: {manager or 'unknown'}")
    print("Missing:")
    for item in report["missing"]:
        print(f"  - {item['name']}: {item['reason']}")
    print("\nPlan:")
    for line in plan:
        print(f"  {line}")

    if dry_run or not assume_yes:
        print("\n(dry run — re-run with --yes to execute)")
        return 0

    for line in plan:
        if line.lstrip().startswith("#"):
            continue
        print(f"\n$ {line}")
        rc = subprocess.run(line, shell=True).returncode
        if rc != 0:
            print(f"command failed (rc={rc}); stopping.")
            return rc
    return 0
