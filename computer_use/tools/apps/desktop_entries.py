# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Reading and interpreting the XDG desktop entries (the Linux provider's data).

This is the parsing concern, kept apart from launching and window confirmation:
it discovers ``.desktop`` files, parses one, lists the launchable apps, resolves
a target to its entry, expands an ``Exec`` line into an argv, and derives the
identity tokens the launch matches a window against. It shells out to nothing
and reads no process, so it stays pure and is testable on its own.
"""

from __future__ import annotations

import configparser
import os
import shlex
from pathlib import Path

# Desktop-entry field codes. The file ones are dropped when no file is passed;
# the rest expand to fixed values or are dropped (the deprecated ones always).
_DROP_IF_NO_FILE = ("%f", "%F", "%u", "%U")
_DEPRECATED_CODES = ("%d", "%D", "%n", "%N", "%v", "%m")

# Identities of the Chromium family and the Electron apps built on it, in the
# normalized (lowercase alphanumeric) form the matcher compares. A launched
# Chromium process exposes no accessible tree unless it is told to
# (--force-renderer-accessibility, or the screen-reader signal on the bus), so
# app_open injects the flag for exactly these entries. Matching is exact per
# identity token, never substring: "code" as a substring would claim half the
# desktop.
_CHROMIUM_IDENTITIES = frozenset(
    _id.replace("-", "").replace(".", "")
    for _id in (
        "chromium", "chromium-browser", "chrome", "google-chrome",
        "google-chrome-stable", "google-chrome-beta", "google-chrome-unstable",
        "brave", "brave-browser", "microsoft-edge", "microsoft-edge-stable",
        "microsoft-edge-beta", "microsoft-edge-dev", "vivaldi",
        "vivaldi-stable", "opera", "electron",
        "code", "code-insiders", "codium", "vscodium",
        "slack", "discord", "signal-desktop", "element-desktop", "obsidian",
        "postman", "teams", "teams-for-linux",
    )
)


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


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


def _window_candidates(app_id: str, entry: dict, path: Path) -> set[str]:
    """Normalized tokens an a11y app_name may carry for this desktop entry.

    The a11y bus names an application after its process (``gnome-text-editor``),
    not its desktop id or display name, so the match collects every identity the
    entry declares: the id stem, its last reverse-DNS segment, the display name,
    the ``StartupWMClass``, and the ``Exec`` binary's basename.
    """
    stem = app_id.removesuffix(".desktop")
    raw = {stem, stem.split(".")[-1]}
    for key in ("Name", "StartupWMClass"):
        value = entry.get(key)
        if value:
            raw.add(value)
    exec_line = entry.get("Exec")
    if exec_line:
        try:
            argv0 = shlex.split(exec_line)[0]
        except (ValueError, IndexError):
            argv0 = exec_line.split()[0] if exec_line.split() else ""
        if argv0:
            raw.add(os.path.basename(argv0))
    return {norm for norm in (_normalize(token) for token in raw) if len(norm) >= 3}


def _exec_program(exec_line: str) -> str:
    """The program a desktop Exec line runs, skipping an ``env VAR=x`` prefix."""
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        tokens = exec_line.split()
    for index, token in enumerate(tokens):
        if index == 0 and os.path.basename(token) == "env":
            continue
        if "=" in token and not token.startswith(("/", ".")):
            continue
        return os.path.basename(token)
    return ""


def _is_chromium_entry(app_id: str, entry: dict) -> bool:
    """Whether this desktop entry launches a Chromium or Electron app.

    Decided from the identities the entry itself declares: the Exec program's
    basename, the StartupWMClass, the id stem and its last reverse-DNS segment.
    Each is compared exactly (normalized) against the known Chromium family, so
    a GTK entry never matches by accident.
    """
    stem = app_id.removesuffix(".desktop")
    tokens = {stem, stem.split(".")[-1], stem.split("_")[-1]}
    wm_class = entry.get("StartupWMClass")
    if wm_class:
        tokens.add(wm_class)
    exec_line = entry.get("Exec")
    if exec_line:
        tokens.add(_exec_program(exec_line))
    normalized = {_normalize(token) for token in tokens if token}
    return bool(normalized & _CHROMIUM_IDENTITIES)
