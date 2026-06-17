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
