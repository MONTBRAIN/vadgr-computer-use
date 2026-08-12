# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""List and launch installed applications, the companion to reading them.

Reading a window is only useful if the model can bring one up first. These are
Tier 0 system tools, not structured reads: listing and launching are OS
operations. ``apps`` scans the XDG desktop entries; ``app_open`` launches one by
id or name. Both are pure-python, no PyGObject: the launch shells out to the
desktop's own launchers (``gio launch``, then ``gtk-launch``) and only falls back
to expanding the ``Exec`` line by hand, so a field code is never handed to a
shell unexpanded.
"""

from __future__ import annotations

import configparser
import os
import shlex
import subprocess
from pathlib import Path

# Desktop-entry field codes. The file ones are dropped when no file is passed;
# the rest expand to fixed values or are dropped (the deprecated ones always).
_DROP_IF_NO_FILE = ("%f", "%F", "%u", "%U")
_DEPRECATED_CODES = ("%d", "%D", "%n", "%N", "%v", "%m")


def _data_dirs() -> list[Path]:
    """The XDG applications directories, in precedence order (home first)."""
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/share:/usr/local/share"
    dirs = [home, *system.split(":")]
    return [Path(d) / "applications" for d in dirs if d]


def _desktop_id(root: Path, path: Path) -> str:
    """The desktop-file-id: the path under applications/, with '/' as '-'."""
    rel = path.relative_to(root)
    return str(rel).replace(os.sep, "-")


def _parse_entry(path: Path) -> dict | None:
    """Parse one .desktop file's [Desktop Entry], or None if it is not an app.

    ``interpolation=None`` keeps ``%`` field codes intact, and ``optionxform=str``
    keeps keys case-sensitive (desktop entries are). Hidden and NoDisplay entries
    are dropped: they are installed but not meant to be launched from a list.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    if entry.get("Type") != "Application":
        return None
    if entry.get("Hidden", "").strip().lower() == "true":
        return None
    if entry.get("NoDisplay", "").strip().lower() == "true":
        return None
    return dict(entry)


def list_apps() -> dict:
    """List installed launchable apps: id, name, and icon where present.

    Keyed by desktop-file-id with first-found winning, so a user override in the
    home directory shadows the system copy, the XDG precedence rule.
    """
    seen: dict[str, dict] = {}
    for root in _data_dirs():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            try:
                app_id = _desktop_id(root, path)
            except ValueError:
                continue
            if app_id in seen:
                continue  # first found wins
            entry = _parse_entry(path)
            if entry is None:
                continue
            name = entry.get("Name") or app_id
            record = {"id": app_id, "name": name}
            icon = entry.get("Icon")
            if icon:
                record["icon"] = icon
            seen[app_id] = record
    return {"apps": sorted(seen.values(), key=lambda a: a["name"].lower())}


def _resolve(target: str) -> tuple[str, Path] | None:
    """Resolve a target (id or name) to its (id, absolute .desktop path)."""
    target_lower = target.lower()
    by_name: tuple[str, Path] | None = None
    for root in _data_dirs():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            try:
                app_id = _desktop_id(root, path)
            except ValueError:
                continue
            if app_id == target:
                if _parse_entry(path) is not None:
                    return (app_id, path)
            if by_name is None:
                entry = _parse_entry(path)
                if entry is not None and (entry.get("Name") or "").lower() == target_lower:
                    by_name = (app_id, path)
    return by_name


def _expand_exec(exec_line: str, name: str, path: Path) -> list[str]:
    """Expand a desktop ``Exec`` line's field codes into an argv (no file args).

    The file codes are dropped (nothing is being opened), ``%i``/``%c``/``%k``
    expand to the icon flag, the name and the path, ``%%`` becomes a literal
    percent, and the deprecated codes are dropped.
    """
    tokens = shlex.split(exec_line)
    argv: list[str] = []
    for token in tokens:
        if token in _DROP_IF_NO_FILE or token in _DEPRECATED_CODES:
            continue
        if token == "%c":
            argv.append(name)
            continue
        if token == "%k":
            argv.append(str(path))
            continue
        if token == "%i":
            continue  # --icon has no value without an Icon key; drop the pair
        token = token.replace("%%", "%")
        argv.append(token)
    return argv


def open_app(target: str) -> dict:
    """Launch an installed app by id or name.

    Tries the desktop's own launchers first (``gio launch`` then ``gtk-launch``),
    which handle field codes, the working directory and startup notification, and
    only expands the ``Exec`` line by hand as a last resort. Returns which method
    launched it so a caller can see the path taken.
    """
    resolved = _resolve(target)
    if resolved is None:
        return {"ok": False, "error": "app_not_found", "target": target}
    app_id, path = resolved

    from shutil import which

    # Launch detached: redirect to DEVNULL (never capture_output) and start a new
    # session. capture_output hands the launched GUI app a stdout/stderr PIPE it
    # inherits, and subprocess.run then blocks reading that pipe until EOF, which
    # only happens when the app EXITS. That was the multi-minute hang the wire e2e
    # caught: the app opened, but the tool never returned. DEVNULL removes the
    # pipe; the timeout is a backstop for a launcher that itself misbehaves.
    def _launch(argv: list[str]):
        try:
            return subprocess.run(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return None

    if which("gio"):
        result = _launch(["gio", "launch", str(path)])
        if result is not None and result.returncode == 0:
            return {"ok": True, "id": app_id, "method": "gio"}
    if which("gtk-launch"):
        result = _launch(["gtk-launch", app_id])
        if result is not None and result.returncode == 0:
            return {"ok": True, "id": app_id, "method": "gtk-launch"}

    entry = _parse_entry(path)
    if entry is None or not entry.get("Exec"):
        return {"ok": False, "error": "no_exec", "id": app_id}
    argv = _expand_exec(entry["Exec"], entry.get("Name") or app_id, path)
    if not argv:
        return {"ok": False, "error": "no_exec", "id": app_id}
    if entry.get("Terminal", "").strip().lower() == "true":
        term = os.environ.get("TERMINAL") or "x-terminal-emulator"
        argv = [term, "-e", *argv]
    try:
        subprocess.Popen(
            argv, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": "launch_failed", "id": app_id, "detail": str(exc)}
    return {"ok": True, "id": app_id, "method": "exec"}
