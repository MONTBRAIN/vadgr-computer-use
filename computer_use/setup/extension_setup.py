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
