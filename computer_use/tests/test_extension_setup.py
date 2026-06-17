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
