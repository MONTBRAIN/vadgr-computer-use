# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""First-run: install the native-host manifest so Chrome can spawn the host.

Chrome only spawns ``native_host.py`` if a host manifest is registered. The
manifest is ``com.vadgr.cua.json`` — ``{name, description, path, type:"stdio",
allowed_origins:["chrome-extension://<EXTENSION_ID>/"]}``. Two things bite if
wrong: the per-OS location, and ``allowed_origins`` must match the extension's
ID exactly (a mismatch = native messaging silently never connects).

The extension ID is fixed by the ``key`` pinned in ``extension/manifest.json``
so an unpacked dev build keeps a stable ID across loads. ``EXTENSION_ID`` here
is the SHA256-derived ID of that pinned key — keep the two in sync (one source
of truth for the test harness).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from computer_use.browser.bridge import manifest_paths

# The stable unpacked-dev extension ID, derived from the public key pinned in
# extension/manifest.json. If the manifest key changes, regenerate this.
EXTENSION_ID = "bcbdnpafilijienocokppgmfianhehll"

HOST_NAME = "com.vadgr.cua"


def build_manifest(host_path: str) -> dict:
    """Build the native-host manifest contents."""
    return {
        "name": HOST_NAME,
        "description": "vadgr-computer-use browser tier native messaging host",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }


def install_manifests(
    host_path: str,
    paths: dict[str, Path] | None = None,
) -> list[str]:
    """Write the manifest to each per-OS target. Returns the browsers written."""
    targets = paths if paths is not None else manifest_paths()
    manifest = build_manifest(host_path)
    written: list[str] = []
    for browser, dest in targets.items():
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        written.append(browser)
    return written


def load_steps() -> str:
    """Human-facing instructions for sideloading the unpacked extension."""
    return (
        "Browser tier setup:\n"
        "  1. Open chrome://extensions (or edge://extensions).\n"
        "  2. Enable Developer mode.\n"
        "  3. Click 'Load unpacked' and select the built `extension/` dir.\n"
        f"  4. Confirm the extension ID is {EXTENSION_ID}.\n"
        "  5. The native-host manifest has been installed; restart the browser\n"
        "     if it was already running, then run `browser(op='status')`."
    )


# --- self-registration: cua writes its own host wiring (no manual setup) ------

# HKCU registry subkeys Chrome/Edge read native hosts from (Windows only). The
# manifest *file* alone isn't enough on Windows — the key must point at it.
_WIN_REGISTRY_KEYS = {
    "chrome": r"Software\Google\Chrome\NativeMessagingHosts\com.vadgr.cua",
    "edge": r"Software\Microsoft\Edge\NativeMessagingHosts\com.vadgr.cua",
}


def windows_relay_path(windows_user: str | None = None) -> str:
    """The Windows-form path of the relay shim Chrome spawns on Windows (WSL).

    On WSL the manifest ``path`` cannot point at a Linux launcher — Chrome runs
    on Windows. It points at ``vadgr-cua-host.exe``, a tiny stdio<->TCP
    forwarder placed under the Windows user's ``AppData\\Local\\vadgr-cua``
    (see ``computer_use/browser/winhost/``). Returns the ``C:\\...`` form
    written into the manifest + the registry.
    """
    from computer_use.browser.bridge import windows_user_home_mnt

    mnt = windows_user_home_mnt(windows_user) / "AppData" / "Local" / "vadgr-cua"
    return _mnt_to_windows_path(mnt / "vadgr-cua-host.exe")


def bundled_relay_exe() -> Path:
    """Path to the packaged Windows relay shim (shipped as package data next to
    ``computer_use/browser/winhost/__init__.py``)."""
    from computer_use.browser import winhost

    return Path(winhost.__file__).resolve().parent / "vadgr-cua-host.exe"


def relay_exe_dest(windows_user: str | None = None) -> Path:
    """The ``/mnt/c`` destination the relay shim must live at for Windows Chrome
    to spawn it — the WSL view of
    ``%LOCALAPPDATA%\\vadgr-cua\\vadgr-cua-host.exe``."""
    from computer_use.browser.bridge import windows_user_home_mnt

    return (
        windows_user_home_mnt(windows_user)
        / "AppData" / "Local" / "vadgr-cua" / "vadgr-cua-host.exe"
    )


def ensure_relay_exe(
    windows_user: str | None = None,
    *,
    src: Path | None = None,
    dest: Path | None = None,
) -> Path:
    """Copy the packaged relay shim to the Windows-readable location the manifest
    points at, so the WSL bridge needs **no manual file placement**. Idempotent:
    copies only when the destination is missing or differs in size. Returns the
    destination path.
    """
    src = Path(src) if src is not None else bundled_relay_exe()
    dest = Path(dest) if dest is not None else relay_exe_dest(windows_user)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return dest


def host_launcher_path(platform: str | None = None) -> Path:
    """Stable path for the generated launcher Chrome executes as the host."""
    plat = platform or sys.platform
    base = Path.home() / ".vadgr-cua"
    return base / ("host.bat" if plat.startswith("win") else "host.sh")


def write_launcher(
    python: str | None = None,
    platform: str | None = None,
    target: Path | None = None,
) -> str:
    """Write the launcher that runs the native-messaging host, return its path.

    Chrome's manifest ``path`` must be an executable, so we generate a tiny
    wrapper that invokes the current interpreter on ``native_host``.
    """
    plat = platform or sys.platform
    py = python or sys.executable
    dest = Path(target) if target is not None else host_launcher_path(plat)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if plat.startswith("win"):
        dest.write_text(
            f'@echo off\r\n"{py}" -m computer_use.browser.native_host %*\r\n',
            encoding="utf-8",
        )
    else:
        dest.write_text(
            f'#!/bin/sh\nexec "{py}" -m computer_use.browser.native_host "$@"\n',
            encoding="utf-8",
        )
        dest.chmod(0o755)
    return str(dest)


def _winreg_writer(subkey: str, value: str) -> None:  # pragma: no cover - Windows only
    import winreg

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey)
    try:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


# Resolve reg.exe via the WSL interop path; falls back to PATH.
_REG_EXE = "/mnt/c/Windows/System32/reg.exe"


def reg_exe_writer(subkey: str, value: str, *, runner=None) -> None:
    """Set ``HKCU\\<subkey>`` default value via Windows ``reg.exe`` from WSL.

    This is the WSL analogue of ``_winreg_writer`` — cua-in-Linux cannot use
    ``winreg``, so it shells out to the Windows ``reg.exe`` over interop. The
    ``runner(argv)`` seam is injected in tests; it defaults to ``subprocess``.
    """
    import os

    reg = _REG_EXE if os.path.exists(_REG_EXE) else "reg.exe"
    argv = [
        reg, "ADD", f"HKCU\\{subkey}",
        "/ve", "/t", "REG_SZ", "/d", value, "/f",
    ]
    if runner is None:  # pragma: no cover - real interop
        import subprocess

        subprocess.run(
            argv, check=False, capture_output=True, timeout=10,
            # Never inherit fd 0: this reg.exe runs at startup on WSL (the #19
            # auto-registration path), and a child holding fd 0 (the stdio MCP
            # JSON-RPC pipe) stalls `initialize` — same class as #18.
            stdin=subprocess.DEVNULL,
        )
    else:
        runner(argv)


def register_windows_registry(
    manifest_path, browsers, *, writer=None, value=None
) -> list[str]:
    """Point each browser's HKCU native-host key at the manifest.

    ``writer(subkey, value)`` is injected in tests; defaults to a winreg write.
    ``value`` overrides the registry value (the WSL path uses the Windows-form
    ``C:\\...`` path, not the ``/mnt/c`` view).
    """
    write = writer or _winreg_writer
    val = value if value is not None else str(manifest_path)
    done: list[str] = []
    for browser in browsers:
        subkey = _WIN_REGISTRY_KEYS.get(browser)
        if subkey is None:
            continue
        write(subkey, val)
        done.append(browser)
    return done


def _mnt_to_windows_path(p) -> str:
    """``/mnt/c/Users/..`` -> ``C:\\Users\\..`` (WSL view -> Windows form)."""
    from computer_use.platform.wsl2 import wsl_to_win_path

    return wsl_to_win_path(str(p))


def _resolve_platform(platform: str | None) -> str:
    """Effective platform string; WSL2 maps to the ``wsl`` branch.

    ``sys.platform`` is ``linux`` on WSL2, so a raw ``sys.platform`` never selects
    the WSL branch, and the Windows relay + registry (which the Windows Chrome
    actually driven on WSL reads) are never set up (issue #19). Resolve via the
    canonical detector instead.
    """
    if platform is not None:
        return platform
    from computer_use.platform.detect import Platform, detect_platform

    return "wsl" if detect_platform() is Platform.WSL2 else sys.platform


def ensure_registered(
    *,
    paths: dict | None = None,
    host_path: str | None = None,
    platform: str | None = None,
    registry_writer=None,
    relay_installer=None,
    windows_user: str | None = None,
) -> dict:
    """Self-register the native host so Chrome can reach cua — no manual step.

    Writes the launcher, the per-OS manifest, and the registry keys (Windows
    and WSL). On WSL cua-in-Linux targets the *Windows* Chrome it actually
    drives: the manifest is written under ``/mnt/c`` and the registry key is set
    via ``reg.exe`` interop. Idempotent: safe to call on every startup.
    """
    plat = _resolve_platform(platform)
    if plat == "wsl":
        targets = paths if paths is not None else manifest_paths(
            "wsl", windows_user=windows_user
        )
        # On WSL the manifest `path` must point at the Windows relay shim
        # (a .exe Chrome spawns on Windows); the launcher script is irrelevant.
        host = host_path or windows_relay_path(windows_user=windows_user)
        # Place the packaged relay shim where the manifest points — no manual copy.
        if host_path is None:
            (relay_installer or ensure_relay_exe)(windows_user=windows_user)
        written = install_manifests(host, targets)
        reg = registry_writer or reg_exe_writer
        for browser, dest in targets.items():
            win_value = _mnt_to_windows_path(dest)
            register_windows_registry(
                dest, [browser], writer=reg, value=win_value
            )
        return {"host_path": host, "browsers": written, "platform": plat}

    targets = paths if paths is not None else manifest_paths(plat)
    host = host_path or write_launcher(platform=plat)
    written = install_manifests(host, targets)
    if plat.startswith("win"):
        for browser, dest in targets.items():
            register_windows_registry(dest, [browser], writer=registry_writer)
    return {"host_path": host, "browsers": written, "platform": plat}


if __name__ == "__main__":  # `python -m computer_use.setup.extension_setup`
    result = ensure_registered()
    print(f"native host registered for: {', '.join(result['browsers'])}")
    print(f"host launcher: {result['host_path']}\n")
    print(load_steps())
