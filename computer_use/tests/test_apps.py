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


class TestOpenApp:
    def test_unknown_target_is_named_error(self, tmp_path, monkeypatch):
        _dirs(monkeypatch, tmp_path / "home", tmp_path / "system")
        result = apps.open_app("does-not-exist")
        assert result["ok"] is False
        assert result["error"] == "app_not_found"

    def test_resolves_by_name_and_launches_via_gio(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _write(home / "applications" / "calc.desktop", _entry("Calculator"))
        _dirs(monkeypatch, home, tmp_path / "system")

        calls = {}

        def fake_which(tool):
            return "/usr/bin/gio" if tool == "gio" else None

        class _Result:
            returncode = 0

        def fake_run(argv, **kwargs):
            calls["argv"] = argv
            return _Result()

        monkeypatch.setattr(apps, "subprocess",
                            type("S", (), {"run": staticmethod(fake_run)}))
        monkeypatch.setattr("shutil.which", fake_which)
        result = apps.open_app("Calculator")
        assert result["ok"] is True
        assert result["method"] == "gio"
        assert result["id"] == "calc.desktop"
        assert calls["argv"][:2] == ["gio", "launch"]
