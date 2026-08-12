# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The apps list and launch tools, against synthetic XDG desktop entries.

The parsing rules are the contract: Type=Application only, Hidden and NoDisplay
dropped, keyed by desktop-file-id with first-found winning, and the Exec field
codes expanded without handing a raw code to the shell. Launch itself shells out,
so it is exercised with the launcher stubbed rather than really starting apps.
"""

from __future__ import annotations

from pathlib import Path

from computer_use.tools import apps


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _entry(name, exec_line="/usr/bin/true", extra=""):
    return f"[Desktop Entry]\nType=Application\nName={name}\nExec={exec_line}\n{extra}"


def _dirs(monkeypatch, home, system):
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))


class TestListApps:
    def test_lists_application_entries(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _write(home / "applications" / "calc.desktop", _entry("Calculator"))
        _dirs(monkeypatch, home, tmp_path / "system")
        result = apps.list_apps()
        names = {a["name"] for a in result["apps"]}
        ids = {a["id"] for a in result["apps"]}
        assert "Calculator" in names
        assert "calc.desktop" in ids

    def test_drops_hidden_and_nodisplay_and_non_application(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _write(home / "applications" / "hidden.desktop",
               _entry("Hidden One", extra="Hidden=true\n"))
        _write(home / "applications" / "nodisplay.desktop",
               _entry("No Display", extra="NoDisplay=true\n"))
        _write(home / "applications" / "link.desktop",
               "[Desktop Entry]\nType=Link\nName=A Link\nURL=http://x\n")
        _write(home / "applications" / "real.desktop", _entry("Real App"))
        _dirs(monkeypatch, home, tmp_path / "system")
        names = {a["name"] for a in apps.list_apps()["apps"]}
        assert names == {"Real App"}

    def test_first_found_wins_home_over_system(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        system = tmp_path / "system"
        _write(home / "applications" / "calc.desktop", _entry("Home Calculator"))
        _write(system / "applications" / "calc.desktop", _entry("System Calculator"))
        _dirs(monkeypatch, home, system)
        result = {a["id"]: a["name"] for a in apps.list_apps()["apps"]}
        assert result["calc.desktop"] == "Home Calculator"

    def test_nested_dir_becomes_dashed_id(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _write(home / "applications" / "org" / "gnome" / "Calc.desktop",
               _entry("Nested"))
        _dirs(monkeypatch, home, tmp_path / "system")
        ids = {a["id"] for a in apps.list_apps()["apps"]}
        assert "org-gnome-Calc.desktop" in ids


class TestExpandExec:
    def test_drops_file_codes_and_expands_specials(self):
        argv = apps._expand_exec("myapp %F --flag %c %k %%literal",
                                 name="My App", path=Path("/x/my.desktop"))
        assert "%F" not in argv
        assert "My App" in argv  # %c -> Name
        assert "/x/my.desktop" in argv  # %k -> path
        assert "%literal" in argv  # %% -> %
        assert "myapp" in argv and "--flag" in argv

    def test_drops_deprecated_codes(self):
        argv = apps._expand_exec("myapp %d %D %n", name="n", path=Path("/x"))
        assert argv == ["myapp"]


_DEVNULL = object()

_CALC_WINDOW = {
    "app_name": "gnome-calculator",
    "title": "Calculator",
    "active": True,
    "ref": "atspi:9",
}


class _FakeBackend:
    """windows() plays a script of window lists; the last list repeats."""

    def __init__(self, script):
        self.script = script
        self.calls = 0

    def windows(self):
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return {"windows": list(self.script[index])}


def _install_launch_fakes(monkeypatch, *, have=("gio", "gtk-launch"), rcs=None):
    """Stub which() and subprocess so no real app launches. Returns the calls.

    ``rcs`` maps a launcher basename to the exit code its dispatch returns
    (default 0 for all).
    """
    calls = []
    rcs = rcs or {}

    def fake_which(tool):
        return f"/usr/bin/{tool}" if tool in have else None

    def fake_run(argv, **kwargs):
        calls.append({"argv": argv, "kwargs": kwargs, "via": "run"})
        rc = rcs.get(argv[0], 0)
        return type("R", (), {"returncode": rc})()

    def fake_popen(argv, **kwargs):
        calls.append({"argv": argv, "kwargs": kwargs, "via": "popen"})
        return type("P", (), {"pid": 4242})()

    monkeypatch.setattr(
        apps,
        "subprocess",
        type(
            "S",
            (),
            {
                "run": staticmethod(fake_run),
                "Popen": staticmethod(fake_popen),
                "DEVNULL": _DEVNULL,
                "TimeoutExpired": type("TimeoutExpired", (Exception,), {}),
            },
        ),
    )
    monkeypatch.setattr("shutil.which", fake_which)
    return calls


class TestOpenApp:
    def test_unknown_target_is_named_error(self, tmp_path, monkeypatch):
        _dirs(monkeypatch, tmp_path / "home", tmp_path / "system")
        result = apps.open_app("does-not-exist")
        assert result["ok"] is False
        assert result["error"] == "app_not_found"

    def test_resolves_by_name_and_launches_via_gio_detached(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _write(home / "applications" / "calc.desktop",
               _entry("Calculator", exec_line="gnome-calculator"))
        _dirs(monkeypatch, home, tmp_path / "system")
        calls = _install_launch_fakes(monkeypatch, have=("gio",))
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [_CALC_WINDOW]]),
        )
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["method"] == "gio"
        assert result["id"] == "calc.desktop"
        assert calls[0]["argv"][:2] == ["gio", "launch"]
        # The launch MUST be detached: a launched GUI app that inherits a
        # stdout/stderr PIPE makes subprocess.run block until the app EXITS - the
        # multi-minute hang the wire e2e caught. So no capture_output; DEVNULL, a
        # new session, and a timeout backstop instead.
        kw = calls[0]["kwargs"]
        assert not kw.get("capture_output")
        assert kw.get("stdout") is _DEVNULL and kw.get("stderr") is _DEVNULL
        assert kw.get("start_new_session") is True
        assert "timeout" in kw


class TestOpenAppConfirmsWindow:
    """ok means a window was seen on the a11y bus, never a launcher exit code.

    The wire e2e caught app_open returning ok for Text Editor with no window
    ever appearing: gio launch exits 0 once it queues the D-Bus Activate call,
    so its exit code proves dispatch, not a launch.
    """

    def _calc(self, tmp_path, monkeypatch, extra=""):
        home = tmp_path / "home"
        _write(home / "applications" / "calc.desktop",
               _entry("Calculator", exec_line="gnome-calculator", extra=extra))
        _dirs(monkeypatch, home, tmp_path / "system")

    def test_ok_carries_the_confirmed_window(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [], [_CALC_WINDOW]]),
        )
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["window"]["ref"] == "atspi:9"
        assert result["window"]["app_name"] == "gnome-calculator"

    def test_no_window_within_timeout_is_a_named_error(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(apps, "_structured_backend", lambda: _FakeBackend([[]]))
        result = apps.open_app("Calculator", timeout_ms=50)
        assert result["ok"] is False
        assert result["error"] == "no_window"
        assert result["id"] == "calc.desktop"
        # Every method dispatched before giving up, so the caller sees the path.
        assert "gio" in result["methods"] and "exec" in result["methods"]

    def test_dbus_activatable_prefers_gtk_launch(self, tmp_path, monkeypatch):
        # gio launch queues the D-Bus Activate call and exits 0 without waiting
        # for the reply; the daemon drops the queued call when the sender is
        # gone before the service registers, so the app starts, idles and exits
        # with no window. gtk-launch waits out the activation, so a
        # DBusActivatable entry tries it first.
        self._calc(tmp_path, monkeypatch, extra="DBusActivatable=true\n")
        calls = _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [_CALC_WINDOW]]),
        )
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["method"] == "gtk-launch"
        assert calls[0]["argv"][0] == "gtk-launch"

    def test_escalates_to_the_next_launcher_when_no_window(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        calls = _install_launch_fakes(monkeypatch)

        class _WindowAfterGtkLaunch:
            # gio dispatches fine but maps nothing (the Text Editor defect);
            # the window exists only once gtk-launch has been dispatched.
            def windows(self):
                dispatched = [c["argv"][0] for c in calls if c["via"] == "run"]
                wins = [_CALC_WINDOW] if "gtk-launch" in dispatched else []
                return {"windows": wins}

        monkeypatch.setattr(
            apps, "_structured_backend", lambda: _WindowAfterGtkLaunch()
        )
        result = apps.open_app("Calculator", timeout_ms=1)
        assert result["ok"] is True
        assert result["method"] == "gtk-launch"
        assert [c["argv"][0] for c in calls] == ["gio", "gtk-launch"]

    def test_already_open_window_is_reported(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        calls = _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[_CALC_WINDOW]]),
        )
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["already_open"] is True
        assert result["window"]["ref"] == "atspi:9"
        # The launch is still dispatched: a single-instance app presents its
        # existing window on activation.
        assert len(calls) == 1

    def test_unconfirmed_when_the_backend_is_unavailable(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(apps, "_structured_backend", lambda: None)
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["confirmed"] is False
        assert result["window"] is None

    def test_confirms_by_pid_when_app_name_matches_no_token(self, tmp_path, monkeypatch):
        # LibreOffice: the a11y app name is 'soffice', which matches nothing
        # derived from libreoffice_writer.desktop (id stem, Name, Exec
        # basename). The launched process's pid owns the window, and that
        # identity must confirm the launch instead of a full-timeout poll.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=())  # exec path: Popen pid 4242
        soffice_win = {"app_name": "soffice", "title": "Untitled 1",
                       "active": True, "ref": "atspi:3", "pid": 4242}
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [soffice_win]]),
        )
        monkeypatch.setattr(apps, "_proc_pids", lambda: {1, 2}, raising=False)
        monkeypatch.setattr(apps, "_proc_comm", lambda pid: "", raising=False)
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=3000)
        assert result["ok"] is True
        assert result["method"] == "exec"
        assert result["window"]["app_name"] == "soffice"

    def test_new_process_comm_becomes_a_window_candidate(self, tmp_path, monkeypatch):
        # gio spawns the app via the session, so there is no child pid to
        # match, and the window's own pid may be unreadable. A process that
        # appeared after dispatch contributes its comm ('soffice.bin') as a
        # name candidate, which is what the window's 'soffice' matches.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=("gio",))
        soffice_win = {"app_name": "soffice", "title": "Untitled 1",
                       "active": True, "ref": "atspi:3", "pid": 0}
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [soffice_win]]),
        )
        pid_reads = {"count": 0}

        def fake_pids():
            pid_reads["count"] += 1
            # The baseline snapshot, then soffice.bin appears after dispatch.
            return {100} if pid_reads["count"] == 1 else {100, 555}

        monkeypatch.setattr(apps, "_proc_pids", fake_pids, raising=False)
        monkeypatch.setattr(
            apps, "_proc_comm",
            lambda pid: {555: "soffice.bin"}.get(pid, ""), raising=False,
        )
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=3000)
        assert result["ok"] is True
        assert result["method"] == "gio"
        assert result["window"]["app_name"] == "soffice"

    def test_a_preexisting_comm_is_not_a_candidate(self, tmp_path, monkeypatch):
        # A new worker of an app that was already running (a browser renderer)
        # must not turn that app's window into a match: only a comm that no
        # pre-dispatch process carried counts as launched.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=("gio",))
        chrome_win = {"app_name": "chrome", "title": "Tab", "active": True,
                      "ref": "atspi:8", "pid": 0}
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [chrome_win]]),
        )
        pid_reads = {"count": 0}

        def fake_pids():
            pid_reads["count"] += 1
            return {100} if pid_reads["count"] == 1 else {100, 555}

        monkeypatch.setattr(apps, "_proc_pids", fake_pids, raising=False)
        # 100 (pre-existing) and 555 (new) are both 'chrome': a renderer.
        monkeypatch.setattr(
            apps, "_proc_comm", lambda pid: "chrome", raising=False,
        )
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=50)
        assert result["ok"] is False
        assert result["error"] == "no_window"

    def test_a_new_window_since_dispatch_confirms_a_single_instance_snap(
        self, tmp_path, monkeypatch
    ):
        # LibreOffice snap with soffice already running: the new Writer window
        # opens inside the existing process, so there is no launched pid to
        # match, 'soffice' matches no desktop-entry token, and 'soffice.bin'
        # already sat in the pre-dispatch comms so it is not a new comm either.
        # The signal left is the window itself: it was not in the pre-dispatch
        # snapshot (observed live: the new frame appeared in the windows() diff
        # 13.6s after gio launch) and its title carries the entry's Name, and
        # together those must confirm.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=("gio",))
        old_win = {"app_name": "soffice",
                   "title": "Untitled 1 - LibreOffice Writer",
                   "active": False, "ref": "atspi:3", "pid": 900}
        new_win = {"app_name": "soffice",
                   "title": "Untitled 2 - LibreOffice Writer",
                   "active": True, "ref": "atspi:9", "pid": 900}
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[old_win], [old_win], [old_win, new_win]]),
        )
        monkeypatch.setattr(apps, "_proc_pids", lambda: {100, 900}, raising=False)
        monkeypatch.setattr(
            apps, "_proc_comm", lambda pid: "soffice.bin", raising=False,
        )
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=3000)
        assert result["ok"] is True
        assert result["window"]["title"] == "Untitled 2 - LibreOffice Writer"

    def test_a_new_window_with_an_unrelated_title_never_matches(
        self, tmp_path, monkeypatch
    ):
        # Newness alone is not identity: a window that appears mid-poll but
        # carries none of the entry's tokens in its title (another app's
        # notification, a stray dialog) must not confirm the launch.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=("gio",))
        stray = {"app_name": "zulip", "title": "New message",
                 "active": True, "ref": "atspi:7", "pid": 700}
        monkeypatch.setattr(
            apps, "_structured_backend", lambda: _FakeBackend([[], [stray]]),
        )
        monkeypatch.setattr(apps, "_proc_pids", lambda: {100, 700}, raising=False)
        monkeypatch.setattr(
            apps, "_proc_comm", lambda pid: "zulip", raising=False,
        )
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=50)
        assert result["ok"] is False
        assert result["error"] == "no_window"

    def test_a_window_present_before_dispatch_never_matches_as_new(
        self, tmp_path, monkeypatch
    ):
        # The new-window rule must not turn an unrelated pre-existing window
        # into a false confirmation when nothing new ever appears.
        home = tmp_path / "home"
        _write(home / "applications" / "libreoffice_writer.desktop",
               _entry("LibreOffice Writer", exec_line="libreoffice --writer %U"))
        _dirs(monkeypatch, home, tmp_path / "system")
        _install_launch_fakes(monkeypatch, have=("gio",))
        old_win = {"app_name": "soffice", "title": "Untitled 1",
                   "active": True, "ref": "atspi:3", "pid": 900}
        monkeypatch.setattr(
            apps, "_structured_backend", lambda: _FakeBackend([[old_win]]),
        )
        monkeypatch.setattr(apps, "_proc_pids", lambda: {100, 900}, raising=False)
        monkeypatch.setattr(
            apps, "_proc_comm", lambda pid: "soffice.bin", raising=False,
        )
        result = apps.open_app("libreoffice_writer.desktop", timeout_ms=50)
        assert result["ok"] is False
        assert result["error"] == "no_window"

    def test_the_timeout_bounds_the_whole_ladder_not_each_method(
        self, tmp_path, monkeypatch
    ):
        # Three dispatched methods each polling the full timeout stretched a
        # five-second budget into the observed ~18s. The budget is one total,
        # split across the methods not yet tried, and every method still gets
        # its dispatch.
        import time as _time

        self._calc(tmp_path, monkeypatch)
        _install_launch_fakes(monkeypatch)
        monkeypatch.setattr(apps, "_structured_backend", lambda: _FakeBackend([[]]))
        start = _time.monotonic()
        result = apps.open_app("Calculator", timeout_ms=300)
        elapsed = _time.monotonic() - start
        assert result["ok"] is False
        assert result["error"] == "no_window"
        assert "gio" in result["methods"] and "exec" in result["methods"]
        assert elapsed < 0.75, f"ladder took {elapsed:.2f}s for a 0.3s budget"

    def test_exec_fallback_still_confirms(self, tmp_path, monkeypatch):
        self._calc(tmp_path, monkeypatch)
        calls = _install_launch_fakes(monkeypatch, have=())
        monkeypatch.setattr(
            apps, "_structured_backend",
            lambda: _FakeBackend([[], [_CALC_WINDOW]]),
        )
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["method"] == "exec"
        assert result["window"]["ref"] == "atspi:9"
        assert calls[0]["via"] == "popen"
        kw = calls[0]["kwargs"]
        assert kw.get("stdout") is _DEVNULL and kw.get("stderr") is _DEVNULL
        assert kw.get("start_new_session") is True
