# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""extension_setup: writing the native-host manifest (no real Chrome)."""

import json

import pytest

from computer_use.setup import extension_setup as S


class TestManifestContent:
    def test_build_manifest_shape(self):
        m = S.build_manifest(host_path="/usr/bin/vadgr-cua-host")
        assert m["name"] == "com.vadgr.cua"
        assert m["type"] == "stdio"
        assert m["path"] == "/usr/bin/vadgr-cua-host"
        assert m["allowed_origins"] == [
            f"chrome-extension://{S.EXTENSION_ID}/"
        ]
        assert "description" in m

    def test_extension_id_is_a_stable_constant(self):
        # 32 lowercase a-p chars (Chrome extension ID alphabet).
        assert isinstance(S.EXTENSION_ID, str)
        assert len(S.EXTENSION_ID) == 32
        assert all(c in "abcdefghijklmnop" for c in S.EXTENSION_ID)


class TestInstall:
    def test_writes_manifest_to_each_target(self, tmp_path):
        chrome = tmp_path / "chrome" / "com.vadgr.cua.json"
        edge = tmp_path / "edge" / "com.vadgr.cua.json"
        written = S.install_manifests(
            host_path="/opt/host",
            paths={"chrome": chrome, "edge": edge},
        )
        assert set(written) == {"chrome", "edge"}
        for p in (chrome, edge):
            data = json.loads(p.read_text())
            assert data["path"] == "/opt/host"
            assert data["allowed_origins"] == [
                f"chrome-extension://{S.EXTENSION_ID}/"
            ]

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "com.vadgr.cua.json"
        S.install_manifests(host_path="/h", paths={"chrome": target})
        assert target.exists()


class TestSelfRegister:
    def test_write_launcher_posix_is_executable(self, tmp_path):
        target = tmp_path / "host.sh"
        path = S.write_launcher(
            python="/venv/bin/python", platform="linux", target=target
        )
        assert path == str(target)
        body = target.read_text()
        assert "computer_use.browser.native_host" in body
        assert "/venv/bin/python" in body
        import os

        assert os.access(target, os.X_OK)

    def test_write_launcher_windows_is_a_bat(self, tmp_path):
        target = tmp_path / "host.bat"
        S.write_launcher(
            python=r"C:\py\python.exe", platform="win32", target=target
        )
        body = target.read_text()
        assert "computer_use.browser.native_host" in body
        assert "python.exe" in body

    def test_register_windows_registry_points_keys_at_manifest(self):
        calls: list[tuple[str, str]] = []
        done = S.register_windows_registry(
            r"C:\m\com.vadgr.cua.json",
            ["chrome", "edge"],
            writer=lambda k, v: calls.append((k, v)),
        )
        assert set(done) == {"chrome", "edge"}
        keys = [k for k, _ in calls]
        assert any(r"Google\Chrome" in k for k in keys)
        assert any(r"Microsoft\Edge" in k for k in keys)
        assert all(v.endswith("com.vadgr.cua.json") for _, v in calls)

    def test_ensure_registered_writes_manifest_with_host_and_id(self, tmp_path):
        chrome = tmp_path / "chrome" / "com.vadgr.cua.json"
        result = S.ensure_registered(
            paths={"chrome": chrome},
            host_path="/opt/vadgr/host.sh",
            platform="linux",
        )
        assert result["browsers"] == ["chrome"]
        assert result["host_path"] == "/opt/vadgr/host.sh"
        data = json.loads(chrome.read_text())
        assert data["path"] == "/opt/vadgr/host.sh"
        assert data["allowed_origins"] == [f"chrome-extension://{S.EXTENSION_ID}/"]

    def test_ensure_registered_writes_windows_registry(self, tmp_path):
        chrome = tmp_path / "com.vadgr.cua.json"
        calls: list[tuple[str, str]] = []
        S.ensure_registered(
            paths={"chrome": chrome},
            host_path=r"C:\vadgr\host.bat",
            platform="win32",
            registry_writer=lambda k, v: calls.append((k, v)),
        )
        assert calls, "Windows registration must write a registry key"
        assert all(v == str(chrome) for _, v in calls)


class TestWSLRegistration:
    """On WSL, cua-in-Linux must register to the *Windows* Chrome it drives:
    write the manifest under /mnt/c and set the registry key via reg.exe."""

    def test_manifest_paths_wsl_targets_windows_under_mnt_c(self):
        paths = S.manifest_paths("wsl", windows_user="alice")
        for browser, p in paths.items():
            assert str(p).startswith("/mnt/c/Users/alice/")
            assert p.name == "com.vadgr.cua.json"
        assert "chrome" in paths and "edge" in paths

    def test_reg_exe_writer_builds_the_right_command(self):
        runs: list[list[str]] = []
        S.reg_exe_writer(
            r"Software\Google\Chrome\NativeMessagingHosts\com.vadgr.cua",
            r"C:\Users\alice\manifest.json",
            runner=lambda argv: runs.append(argv),
        )
        assert len(runs) == 1
        argv = runs[0]
        assert argv[0].endswith("reg.exe")
        assert "ADD" in argv
        # HKCU\<subkey>, default value (/ve), REG_SZ, the manifest path
        assert any("HKCU" in a and "com.vadgr.cua" in a for a in argv)
        assert "/ve" in argv
        assert "REG_SZ" in argv
        assert r"C:\Users\alice\manifest.json" in argv

    def test_ensure_registered_wsl_writes_windows_manifest_and_calls_reg_exe(
        self, tmp_path
    ):
        # Redirect /mnt/c to a tmp dir via an injected path map.
        chrome = tmp_path / "Users" / "alice" / "chrome" / "com.vadgr.cua.json"
        edge = tmp_path / "Users" / "alice" / "edge" / "com.vadgr.cua.json"
        reg_calls: list[tuple[str, str]] = []
        result = S.ensure_registered(
            paths={"chrome": chrome, "edge": edge},
            host_path="C:\\\\Users\\\\alice\\\\relay.exe",
            platform="wsl",
            registry_writer=lambda k, v: reg_calls.append((k, v)),
        )
        # Manifests written to the Windows-side (here, tmp) locations.
        assert chrome.exists() and edge.exists()
        data = json.loads(chrome.read_text())
        assert data["allowed_origins"] == [f"chrome-extension://{S.EXTENSION_ID}/"]
        # reg.exe-style writer was invoked for both browsers, with Win paths.
        assert {k for k, _ in reg_calls}
        chrome_keys = [k for k, _ in reg_calls if r"Google\Chrome" in k]
        edge_keys = [k for k, _ in reg_calls if r"Microsoft\Edge" in k]
        assert chrome_keys and edge_keys
        # the registry value is the Windows-form path of the manifest.
        by_key = dict(reg_calls)
        assert by_key[chrome_keys[0]] == S._mnt_to_windows_path(chrome)
        assert by_key[edge_keys[0]] == S._mnt_to_windows_path(edge)

    def test_ensure_registered_wsl_value_is_windows_form_under_mnt_c(self, tmp_path):
        # A real /mnt/c-style path converts to a C:\ registry value.
        chrome = "/mnt/c/Users/alice/AppData/Local/Google/Chrome/com.vadgr.cua.json"
        # Write into a tmp dir but assert the *value* conversion independently.
        assert S._mnt_to_windows_path(chrome) == (
            r"C:\Users\alice\AppData\Local\Google\Chrome\com.vadgr.cua.json"
        )

    def test_windows_relay_path_points_at_the_exe(self):
        p = S.windows_relay_path(windows_user="alice")
        assert p.endswith("vadgr-cua-host.exe")
        assert p.startswith("C:\\Users\\alice\\")
        assert "vadgr-cua" in p

    def test_ensure_registered_wsl_manifest_path_is_the_relay_exe(self, tmp_path):
        chrome = tmp_path / "com.vadgr.cua.json"
        S.ensure_registered(
            paths={"chrome": chrome},
            platform="wsl",
            windows_user="alice",
            registry_writer=lambda k, v: None,
            relay_installer=lambda windows_user=None: None,
        )
        data = json.loads(chrome.read_text())
        assert data["path"].endswith("vadgr-cua-host.exe")

    def test_ensure_registered_wsl_installs_the_relay_exe(self, tmp_path):
        # The WSL path auto-places the relay shim (no manual copy) — the installer
        # is invoked with the resolved windows_user.
        seen = {}
        S.ensure_registered(
            paths={"chrome": tmp_path / "m.json"},
            platform="wsl",
            windows_user="alice",
            registry_writer=lambda k, v: None,
            relay_installer=lambda windows_user=None: seen.setdefault("user", windows_user),
        )
        assert seen["user"] == "alice"

    def test_ensure_relay_exe_copies_to_dest(self, tmp_path):
        src = tmp_path / "src" / "vadgr-cua-host.exe"
        src.parent.mkdir()
        src.write_bytes(b"RELAYBINARY")
        dest = tmp_path / "win" / "AppData" / "Local" / "vadgr-cua" / "vadgr-cua-host.exe"
        out = S.ensure_relay_exe(src=src, dest=dest)
        assert out == dest
        assert dest.read_bytes() == b"RELAYBINARY"

    def test_ensure_relay_exe_is_idempotent_on_same_size(self, tmp_path):
        src = tmp_path / "src.exe"
        src.write_bytes(b"NEWBYTES")  # 8 bytes
        dest = tmp_path / "dest.exe"
        dest.write_bytes(b"OLDBYTES")  # also 8 bytes -> same size, treated as present
        S.ensure_relay_exe(src=src, dest=dest)
        assert dest.read_bytes() == b"OLDBYTES"  # not overwritten

    def test_ensure_relay_exe_recopies_when_size_differs(self, tmp_path):
        src = tmp_path / "src.exe"
        src.write_bytes(b"A_LONGER_BINARY")
        dest = tmp_path / "dest.exe"
        dest.write_bytes(b"short")
        S.ensure_relay_exe(src=src, dest=dest)
        assert dest.read_bytes() == b"A_LONGER_BINARY"

    def test_non_wsl_linux_unchanged(self, tmp_path):
        chrome = tmp_path / "chrome" / "com.vadgr.cua.json"
        result = S.ensure_registered(
            paths={"chrome": chrome},
            host_path="/opt/host.sh",
            platform="linux",
            registry_writer=lambda k, v: (_ for _ in ()).throw(
                AssertionError("registry must not be touched on linux")
            ),
        )
        assert result["platform"] == "linux"
        assert chrome.exists()


class TestWslAutoDetection:
    def test_ensure_registered_auto_selects_wsl_on_wsl2(self, tmp_path, monkeypatch):
        # Issue #19: sys.platform is "linux" on WSL2, so ensure_registered must
        # resolve the platform via detect_platform() and take the WSL branch
        # WITHOUT an explicit platform= argument.
        from computer_use.platform.detect import Platform

        monkeypatch.setattr(
            "computer_use.platform.detect.detect_platform",
            lambda: Platform.WSL2,
        )
        chrome = tmp_path / "chrome" / "com.vadgr.cua.json"
        reg_calls: list[tuple[str, str]] = []
        result = S.ensure_registered(
            paths={"chrome": chrome},
            host_path="C:\\Users\\alice\\relay.exe",
            registry_writer=lambda k, v: reg_calls.append((k, v)),
            relay_installer=lambda windows_user=None: None,
            # no platform= : must auto-detect WSL2
        )
        assert result["platform"] == "wsl"
        assert chrome.exists()
        assert reg_calls  # WSL branch wrote the Windows registry key
