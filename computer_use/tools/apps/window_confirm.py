# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Confirming a launch by watching the a11y bus for the app's window.

A launcher's exit code only proves dispatch, so the Linux provider proves the
launch by finding a window that belongs to the app. That is a concern of its
own: read the windows through the structured tier, and decide which window is
the launch by the strongest identity available (the owning process and its
ancestors, a name token, a comm that appeared after dispatch, or a new window
whose title vouches for it). The /proc reads live here because the confirmation
is the only thing that needs them.
"""

from __future__ import annotations

import os
import time

from computer_use.tools.apps.desktop_entries import _normalize

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
