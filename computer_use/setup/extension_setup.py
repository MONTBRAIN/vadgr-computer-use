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


def register_windows_registry(manifest_path, browsers, *, writer=None) -> list[str]:
    """Point each browser's HKCU native-host key at ``manifest_path``.

    ``writer(subkey, value)`` is injected in tests; defaults to a winreg write.
    """
    write = writer or _winreg_writer
    done: list[str] = []
    for browser in browsers:
        subkey = _WIN_REGISTRY_KEYS.get(browser)
        if subkey is None:
            continue
        write(subkey, str(manifest_path))
        done.append(browser)
    return done


def ensure_registered(
    *,
    paths: dict | None = None,
    host_path: str | None = None,
    platform: str | None = None,
    registry_writer=None,
) -> dict:
    """Self-register the native host so Chrome can reach cua — no manual step.

    Writes the launcher, the per-OS manifest, and (on Windows) the registry
    keys. Idempotent: safe to call on every startup. Returns what was written.
    """
    plat = platform or sys.platform
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
