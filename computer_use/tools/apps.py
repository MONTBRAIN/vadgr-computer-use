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
desktop's own launchers (``gio launch``, ``gtk-launch``) and only falls back
to expanding the ``Exec`` line by hand, so a field code is never handed to a
shell unexpanded.

``app_open`` never trusts a launcher's exit code: for a ``DBusActivatable``
app, ``gio launch`` exits 0 once it queues the D-Bus ``Activate`` call, and the
daemon drops that queued call when the sender is gone before the activated
service registers its name, so the app starts, idles, and exits with no window.
The tool confirms the launch by watching the a11y bus for the app's window and
only reports ok when one is there.
"""

from __future__ import annotations

import configparser
import os
import shlex
import subprocess
import time
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


# How often the window confirmation re-reads the a11y bus while it waits.
_POLL_SECONDS = 0.25


def _structured_backend():
    """The structured (a11y) backend, or None where it cannot resolve.

    A seam: the confirmation step reads windows through the structured tier
    rather than shelling out, and tests substitute a fake here.
    """
    try:
        from computer_use.tools.ui.backend import resolve_backend
    except ImportError:
        return None
    return resolve_backend()


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _window_candidates(app_id: str, entry: dict, path: Path) -> set[str]:
    """Normalized tokens an a11y app_name may carry for this desktop entry.

    The a11y bus names an application after its process (``gnome-text-editor``),
    not its desktop id or display name, so the match collects every identity the
    entry declares: the id stem, its last reverse-DNS segment, the display name,
    the ``StartupWMClass``, and the ``Exec`` binary's basename.
    """
    stem = app_id[: -len(".desktop")] if app_id.endswith(".desktop") else app_id
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


def _matching_window(windows: list[dict], candidates: set[str]) -> dict | None:
    for window in windows:
        app_name = _normalize(window.get("app_name") or "")
        if len(app_name) < 3:
            continue
        if any(app_name in cand or cand in app_name for cand in candidates):
            return window
    return None


def _snap_windows(backend) -> list[dict] | None:
    """One windows() read, or None where the bus cannot answer."""
    if backend is None:
        return None
    try:
        return backend.windows().get("windows", [])
    except Exception:
        return None


def _poll_for_window(backend, candidates: set[str], timeout_ms: int) -> dict | None:
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
    while True:
        windows = _snap_windows(backend)
        match = _matching_window(windows or [], candidates)
        if match is not None:
            return match
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(_POLL_SECONDS, remaining))


def open_app(target: str, timeout_ms: int = 5000) -> dict:
    """Launch an installed app by id or name, and confirm a window appeared.

    Dispatches through the desktop's own launchers and then watches the a11y
    bus for a window belonging to the app, because a launcher's exit code only
    proves dispatch. ``ok`` therefore means a matching window is open; a launch
    that dispatched but mapped nothing within ``timeout_ms`` is the named error
    ``no_window``, and each dispatched method escalates to the next before the
    tool gives up.

    "Opened" is a matching window present after the dispatch, not a new one: a
    single-instance app presents its existing window on activation, and that
    result carries ``already_open``. Where the a11y bus cannot answer at all,
    the tool returns the dispatch result with ``confirmed: false`` rather than
    guessing either way.

    A ``DBusActivatable`` entry tries ``gtk-launch`` before ``gio launch``:
    gio queues the D-Bus ``Activate`` call and exits without waiting for the
    reply, and the daemon drops the queued call when the sender is gone before
    the activated service registers, so the service starts, idles, and exits
    with no window. gtk-launch waits the activation out.
    """
    resolved = _resolve(target)
    if resolved is None:
        return {"ok": False, "error": "app_not_found", "target": target}
    app_id, path = resolved
    entry = _parse_entry(path) or {}
    candidates = _window_candidates(app_id, entry, path)
    timeout_ms = max(0, min(timeout_ms, 60_000))

    backend = _structured_backend()
    baseline = _snap_windows(backend)
    already_open = (
        _matching_window(baseline, candidates) if baseline is not None else None
    )

    from shutil import which

    # Launch detached: redirect to DEVNULL (never capture_output) and start a new
    # session. capture_output hands the launched GUI app a stdout/stderr PIPE it
    # inherits, and subprocess.run then blocks reading that pipe until EOF, which
    # only happens when the app EXITS. That was the multi-minute hang the wire e2e
    # caught: the app opened, but the tool never returned. DEVNULL removes the
    # pipe; the timeout is a backstop for a launcher that itself misbehaves.
    def _launch(argv: list[str]) -> bool:
        try:
            result = subprocess.run(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return False
        return result.returncode == 0

    def _launch_exec() -> tuple[bool, dict | None]:
        if not entry.get("Exec"):
            return False, None
        argv = _expand_exec(entry["Exec"], entry.get("Name") or app_id, path)
        if not argv:
            return False, None
        if entry.get("Terminal", "").strip().lower() == "true":
            term = os.environ.get("TERMINAL") or "x-terminal-emulator"
            argv = [term, "-e", *argv]
        try:
            subprocess.Popen(
                argv, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            return False, {"ok": False, "error": "launch_failed", "id": app_id,
                           "detail": str(exc)}
        return True, None

    dbus_activatable = entry.get("DBusActivatable", "").strip().lower() == "true"
    ladder = ["gtk-launch", "gio"] if dbus_activatable else ["gio", "gtk-launch"]
    ladder.append("exec")

    dispatched: list[str] = []
    exec_error: dict | None = None
    for method in ladder:
        if method == "gio":
            if not which("gio") or not _launch(["gio", "launch", str(path)]):
                continue
        elif method == "gtk-launch":
            if not which("gtk-launch") or not _launch(["gtk-launch", app_id]):
                continue
        else:
            ok, exec_error = _launch_exec()
            if not ok:
                continue
        dispatched.append(method)
        if baseline is None:
            # No a11y bus to confirm against: report the dispatch honestly
            # rather than claiming the app is up.
            return {"ok": True, "id": app_id, "method": method,
                    "window": None, "confirmed": False}
        window = _poll_for_window(backend, candidates, timeout_ms)
        if window is not None:
            result = {
                "ok": True, "id": app_id, "method": method,
                "window": {"app_name": window.get("app_name"),
                           "title": window.get("title"),
                           "ref": window.get("ref")},
            }
            if already_open is not None:
                result["already_open"] = True
            return result

    if dispatched:
        return {"ok": False, "error": "no_window", "id": app_id,
                "methods": dispatched, "timeout_ms": timeout_ms}
    if exec_error is not None:
        return exec_error
    return {"ok": False, "error": "no_exec", "id": app_id}
