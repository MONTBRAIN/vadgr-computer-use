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


def _proc_pids() -> set[int]:
    """The live pids, from /proc. Empty where there is no /proc (non-Linux)."""
    try:
        return {int(p) for p in os.listdir("/proc") if p.isdigit()}
    except OSError:
        return set()


def _proc_comm(pid: int) -> str:
    """The process command name from /proc, or empty. Best effort by design."""
    if pid <= 0:
        return ""
    try:
        with open(f"/proc/{pid}/comm") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _lineage(pid: int) -> set[int]:
    """The pid and its ancestors, so a launched wrapper's child still matches."""
    out: set[int] = set()
    for _ in range(64):
        if pid <= 1 or pid in out:
            break
        out.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as handle:
                stat = handle.read()
            # Field 4 (ppid) sits after the parenthesised comm, which may
            # itself contain spaces, so split after the closing parenthesis.
            pid = int(stat.rpartition(")")[2].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return out


def _launched_comms(baseline_pids: set[int], baseline_comms: set[str]) -> set[str]:
    """Normalized comms of processes that appeared after the dispatch.

    Only a comm no pre-dispatch process carried counts: a new worker of an app
    that was already running (a browser renderer) must not turn that app's
    window into a match.
    """
    comms: set[str] = set()
    for pid in _proc_pids() - baseline_pids:
        comm = _normalize(_proc_comm(pid))
        if len(comm) >= 3 and comm not in baseline_comms:
            comms.add(comm)
    return comms


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


def _window_key(window: dict) -> tuple:
    """A window's identity for the new-since-dispatch comparison."""
    return (window.get("app_name") or "", window.get("title") or "")


def _matching_window(
    windows: list[dict],
    candidates: set[str],
    launched_pids: set[int] | frozenset[int] = frozenset(),
    baseline_keys: frozenset[tuple] | None = None,
) -> dict | None:
    # Three passes, strongest identity first, so a weak match never shadows a
    # strong one later in the list.
    for window in windows:
        # Process identity: a window owned by the launched process (or a
        # descendant of it) is the launch, whatever the toolkit named it. The
        # a11y app name is derived from the process, not the desktop entry, and
        # LibreOffice's 'soffice' matches no token of libreoffice_writer.desktop.
        pid = window.get("pid") or 0
        if pid and launched_pids and launched_pids & _lineage(pid):
            return window
    for window in windows:
        app_name = _normalize(window.get("app_name") or "")
        if len(app_name) < 3:
            continue
        if any(app_name in cand or cand in app_name for cand in candidates):
            return window
    if baseline_keys is None:
        return None
    for window in windows:
        # Last resort: a window that did not exist before the dispatch AND
        # whose title carries one of the entry's own tokens. Newness is the
        # only signal a single-instance snap leaves - the new Writer window
        # opens inside the already-running soffice process (no pid lineage, no
        # matching app name, no new comm) - but newness alone would claim any
        # unrelated window that happened to appear mid-poll, so the title must
        # vouch for the identity: 'Untitled 2 - LibreOffice Writer' carries
        # the entry's Name where the app name 'soffice' never does.
        if _window_key(window) in baseline_keys:
            continue
        title = _normalize(window.get("title") or "")
        if len(title) >= 3 and any(cand in title for cand in candidates):
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


def _poll_for_window(
    backend,
    candidates: set[str],
    timeout_ms: float,
    launched_pids: set[int] | frozenset[int] = frozenset(),
    baseline_pids: set[int] | frozenset[int] = frozenset(),
    baseline_comms: set[str] | frozenset[str] = frozenset(),
    baseline_keys: frozenset[tuple] | None = None,
) -> dict | None:
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
    while True:
        windows = _snap_windows(backend)
        # gio and gtk-launch hand the spawn to the session, so there is no
        # child pid to match; the processes that appeared since dispatch stand
        # in, contributing their comms as name candidates each poll.
        polled = candidates | _launched_comms(set(baseline_pids), set(baseline_comms))
        match = _matching_window(windows or [], polled, launched_pids, baseline_keys)
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

    A window matches by name token or by process identity. The a11y app name is
    derived from the process, not the desktop entry, so a name that matches no
    entry token (LibreOffice's windows belong to ``soffice``) is still confirmed
    when the window's owning pid is the launched process (or a descendant), or
    when a process that appeared after dispatch carries a comm the window's
    name matches.

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
    # The windows open before the dispatch, by identity. A window absent from
    # this set is new since dispatch, which is the last-resort confirmation for
    # a single-instance snap whose new window opens inside a pre-existing
    # process (LibreOffice: no pid lineage, no matching token, no new comm).
    baseline_keys = (
        frozenset(_window_key(w) for w in baseline)
        if baseline is not None else None
    )

    # The processes alive before the dispatch, so the confirmation can also
    # recognise the launch by identity: the window of a process that appeared
    # after dispatch (matched by pid, or by its comm as a name candidate) is
    # the launch even when the toolkit's a11y app name ('soffice') matches no
    # token derived from the desktop entry.
    baseline_pids = _proc_pids()
    baseline_comms = {_normalize(_proc_comm(p)) for p in baseline_pids}
    launched_pids: set[int] = set()

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

    # A Chromium or Electron app exposes no accessible tree unless launched
    # with the accessibility flag, and gio and gtk-launch run the Exec line as
    # written, so a detected Chromium entry dispatches the expanded Exec first
    # with the flag appended and the enabling environment set. The launchers
    # stay on its ladder as fallbacks: a launch without the flag still beats no
    # launch, and the tree can be enabled later over the bus.
    chromium = _is_chromium_entry(app_id, entry)

    def _launch_exec() -> tuple[bool, dict | None]:
        if not entry.get("Exec"):
            return False, None
        argv = _expand_exec(entry["Exec"], entry.get("Name") or app_id, path)
        if not argv:
            return False, None
        if entry.get("Terminal", "").strip().lower() == "true":
            term = os.environ.get("TERMINAL") or "x-terminal-emulator"
            argv = [term, "-e", *argv]
        env = None
        if chromium:
            from computer_use.tools.ui.atspi import (
                accessibility_launch_env,
                chromium_accessibility_flags,
            )

            argv = [*argv, *chromium_accessibility_flags()]
            env = accessibility_launch_env()
        try:
            proc = subprocess.Popen(
                argv, start_new_session=True, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            return False, {"ok": False, "error": "launch_failed", "id": app_id,
                           "detail": str(exc)}
        launched_pids.add(proc.pid)
        return True, None

    dbus_activatable = entry.get("DBusActivatable", "").strip().lower() == "true"
    ladder = ["gtk-launch", "gio"] if dbus_activatable else ["gio", "gtk-launch"]
    if chromium:
        ladder.insert(0, "exec")
    else:
        ladder.append("exec")

    dispatched: list[str] = []
    exec_error: dict | None = None
    # One budget for the whole ladder, split over the methods not yet tried.
    # Each dispatched method used to poll the full timeout, so three dispatches
    # stretched a five-second budget into the observed ~18s; now the last
    # method inherits whatever its predecessors did not spend, and the total
    # stays the caller's timeout.
    deadline = time.monotonic() + timeout_ms / 1000.0
    for index, method in enumerate(ladder):
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
        remaining_ms = max((deadline - time.monotonic()) * 1000.0, 0.0)
        share_ms = remaining_ms / (len(ladder) - index)
        window = _poll_for_window(
            backend, candidates, share_ms,
            launched_pids, baseline_pids, baseline_comms, baseline_keys,
        )
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
