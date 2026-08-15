# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The Linux apps provider: list from the XDG entries, launch and confirm.

This is one provider behind the AppsBackend seam. It owns the launch
orchestration - the launcher ladder, the detached spawn, the Chromium
accessibility injection, and the single timeout budget split across the ladder -
and delegates the two other concerns: reading the desktop entries
(``desktop_entries``) and proving a window appeared (``window_confirm``).

``app_open`` never trusts a launcher's exit code: for a ``DBusActivatable``
app, ``gio launch`` exits 0 once it queues the D-Bus ``Activate`` call, and the
daemon drops that queued call when the sender is gone before the activated
service registers its name, so the app starts, idles, and exits with no window.
The provider confirms the launch by watching the a11y bus for the app's window
and only reports ok when one is there.
"""

from __future__ import annotations

import os
import subprocess
import time

from computer_use.tools.apps import desktop_entries, window_confirm


class LinuxAppsBackend:
    """List and launch apps through the XDG desktop entries and the a11y bus."""

    def list_apps(self) -> dict:
        return desktop_entries.list_apps()

    def open_app(self, target: str, timeout_ms: int = 5000) -> dict:
        """Launch an installed app by id or name, and confirm a window appeared.

        Dispatches through the desktop's own launchers and then watches the a11y
        bus for a window belonging to the app, because a launcher's exit code
        only proves dispatch. ``ok`` therefore means a matching window is open; a
        launch that dispatched but mapped nothing within ``timeout_ms`` is the
        named error ``no_window``, and each dispatched method escalates to the
        next before the tool gives up.

        "Opened" is a matching window present after the dispatch, not a new one:
        a single-instance app presents its existing window on activation, and
        that result carries ``already_open``. Where the a11y bus cannot answer at
        all, the tool returns the dispatch result with ``confirmed: false``
        rather than guessing either way.

        A window matches by name token or by process identity. The a11y app name
        is derived from the process, not the desktop entry, so a name that
        matches no entry token (LibreOffice's windows belong to ``soffice``) is
        still confirmed when the window's owning pid is the launched process (or
        a descendant), or when a process that appeared after dispatch carries a
        comm the window's name matches.

        A ``DBusActivatable`` entry tries ``gtk-launch`` before ``gio launch``:
        gio queues the D-Bus ``Activate`` call and exits without waiting for the
        reply, and the daemon drops the queued call when the sender is gone
        before the activated service registers, so the service starts, idles, and
        exits with no window. gtk-launch waits the activation out.
        """
        resolved = desktop_entries._resolve(target)
        if resolved is None:
            return {"ok": False, "error": "app_not_found", "target": target}
        app_id, path = resolved
        entry = desktop_entries._parse_entry(path) or {}
        candidates = desktop_entries._window_candidates(app_id, entry, path)
        timeout_ms = max(0, min(timeout_ms, 60_000))

        backend = window_confirm._structured_backend()
        baseline = window_confirm._snap_windows(backend)
        already_open = (
            window_confirm._matching_window(baseline, candidates)
            if baseline is not None else None
        )
        # The windows open before the dispatch, by identity. A window absent from
        # this set is new since dispatch, which is the last-resort confirmation
        # for a single-instance snap whose new window opens inside a pre-existing
        # process (LibreOffice: no pid lineage, no matching token, no new comm).
        baseline_keys = (
            frozenset(window_confirm._window_key(w) for w in baseline)
            if baseline is not None else None
        )

        # The processes alive before the dispatch, so the confirmation can also
        # recognise the launch by identity: the window of a process that appeared
        # after dispatch (matched by pid, or by its comm as a name candidate) is
        # the launch even when the toolkit's a11y app name ('soffice') matches no
        # token derived from the desktop entry.
        baseline_pids = window_confirm._proc_pids()
        baseline_comms = {
            desktop_entries._normalize(window_confirm._proc_comm(p))
            for p in baseline_pids
        }
        launched_pids: set[int] = set()

        from shutil import which

        # Launch detached: redirect to DEVNULL (never capture_output) and start a
        # new session. capture_output hands the launched GUI app a stdout/stderr
        # PIPE it inherits, and subprocess.run then blocks reading that pipe until
        # EOF, which only happens when the app EXITS. That was the multi-minute
        # hang the wire e2e caught: the app opened, but the tool never returned.
        # DEVNULL removes the pipe; the timeout is a backstop for a launcher that
        # itself misbehaves.
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
        # with the accessibility flag, and gio and gtk-launch run the Exec line
        # as written, so a detected Chromium entry dispatches the expanded Exec
        # first with the flag appended and the enabling environment set. The
        # launchers stay on its ladder as fallbacks: a launch without the flag
        # still beats no launch, and the tree can be enabled later over the bus.
        chromium = desktop_entries._is_chromium_entry(app_id, entry)

        def _launch_exec() -> tuple[bool, dict | None]:
            if not entry.get("Exec"):
                return False, None
            argv = desktop_entries._expand_exec(
                entry["Exec"], entry.get("Name") or app_id, path
            )
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
        # Each dispatched method used to poll the full timeout, so three
        # dispatches stretched a five-second budget into the observed ~18s; now
        # the last method inherits whatever its predecessors did not spend, and
        # the total stays the caller's timeout.
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
            window = window_confirm._poll_for_window(
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
