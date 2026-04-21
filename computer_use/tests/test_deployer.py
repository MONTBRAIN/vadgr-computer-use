# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for DaemonDeployer: static-setup concerns for the Windows bridge.

Covers: daemon.py hashing, deploy directory, file copy (idempotent),
stale-file cleanup, Windows-Python discovery, dep verification and
installation, and the orchestrator `ensure()` method.
"""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --- Fixtures ---


@pytest.fixture
def deployer():
    """Fresh DaemonDeployer with default config."""
    from computer_use.bridge.deployer import DaemonDeployer
    return DaemonDeployer()


@pytest.fixture
def tmp_deploy_dir(tmp_path):
    """Temporary path that stands in for the Windows deploy dir."""
    return tmp_path / "deploy"


# --- daemon.py hashing ---


class TestCurrentDaemonHash:
    def test_returns_sha256_hex_of_shipped_daemon_py(self, deployer):
        expected = hashlib.sha256(
            deployer.daemon_source_path().read_bytes()
        ).hexdigest()
        assert deployer.current_daemon_hash() == expected

    def test_hash_is_stable_across_calls(self, deployer):
        assert deployer.current_daemon_hash() == deployer.current_daemon_hash()

    def test_daemon_source_path_points_to_real_file(self, deployer):
        p = deployer.daemon_source_path()
        assert p.is_file()
        assert p.name == "daemon.py"


# --- deploy directory ---


class TestEnsureDeployDir:
    def test_creates_missing_directory(self, tmp_deploy_dir):
        from computer_use.bridge.deployer import DaemonDeployer

        d = DaemonDeployer()
        assert not tmp_deploy_dir.exists()
        d.ensure_deploy_dir(tmp_deploy_dir)
        assert tmp_deploy_dir.is_dir()

    def test_idempotent_on_existing_directory(self, tmp_deploy_dir):
        from computer_use.bridge.deployer import DaemonDeployer

        tmp_deploy_dir.mkdir()
        (tmp_deploy_dir / "sentinel.txt").write_text("keep me")
        DaemonDeployer().ensure_deploy_dir(tmp_deploy_dir)
        assert (tmp_deploy_dir / "sentinel.txt").read_text() == "keep me"


# --- file deployment ---


class TestDeployFiles:
    def test_copies_daemon_py_when_destination_missing(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        written = deployer.deploy_files(tmp_deploy_dir)
        assert (tmp_deploy_dir / "daemon.py").is_file()
        assert "daemon.py" in written

    def test_skips_copy_when_destination_identical(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        # Pre-populate with identical content.
        src = deployer.daemon_source_path().read_bytes()
        (tmp_deploy_dir / "daemon.py").write_bytes(src)
        written = deployer.deploy_files(tmp_deploy_dir)
        assert "daemon.py" not in written  # not re-copied

    def test_overwrites_when_destination_differs(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        (tmp_deploy_dir / "daemon.py").write_text("# stale content")
        written = deployer.deploy_files(tmp_deploy_dir)
        assert "daemon.py" in written
        assert (
            (tmp_deploy_dir / "daemon.py").read_bytes()
            == deployer.daemon_source_path().read_bytes()
        )


# --- stale-file cleanup ---


class TestCleanStale:
    def test_removes_files_not_in_daemon_files_set(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        (tmp_deploy_dir / "daemon.py").write_text("ok")
        (tmp_deploy_dir / "spatial_cache.py").write_text("stale cache-era")
        (tmp_deploy_dir / "old_helper.py").write_text("orphan")
        removed = deployer.clean_stale(tmp_deploy_dir)
        assert set(removed) == {"spatial_cache.py", "old_helper.py"}
        assert (tmp_deploy_dir / "daemon.py").exists()
        assert not (tmp_deploy_dir / "spatial_cache.py").exists()
        assert not (tmp_deploy_dir / "old_helper.py").exists()

    def test_preserves_subdirectories_and_daemon_files(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        (tmp_deploy_dir / "daemon.py").write_text("ok")
        (tmp_deploy_dir / "__pycache__").mkdir()
        removed = deployer.clean_stale(tmp_deploy_dir)
        # __pycache__ is a dir -- we only clean files, not recursively
        assert "__pycache__" not in removed
        assert (tmp_deploy_dir / "daemon.py").exists()

    def test_no_error_on_empty_directory(self, deployer, tmp_deploy_dir):
        tmp_deploy_dir.mkdir()
        assert deployer.clean_stale(tmp_deploy_dir) == []


# --- Windows Python discovery ---


class TestFindWindowsPython:
    def test_returns_path_from_where_python(self, deployer):
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="C:\\Python312\\python.exe\r\n",
            )
            result = deployer.find_windows_python()
            assert result == "C:\\Python312\\python.exe"

    def test_excludes_windowsapps_store_stub(self, deployer):
        """The WindowsApps shim is a stub that opens the Store; skip it."""
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "C:\\Users\\x\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe\n"
                    "C:\\Python312\\python.exe\n"
                ),
            )
            result = deployer.find_windows_python()
            assert "WindowsApps" not in (result or "")

    def test_returns_none_when_nothing_found(self, deployer):
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with patch(
                "computer_use.bridge.deployer.os.path.isfile",
                return_value=False,
            ):
                assert deployer.find_windows_python() is None


# --- dep verification and installation ---


class TestVerifyDeps:
    def test_returns_empty_when_all_deps_importable(self, deployer):
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert deployer.verify_deps("C:\\Python312\\python.exe") == []

    def test_returns_missing_deps(self, deployer):
        # First call succeeds (mss), second fails (Pillow).
        calls = iter(
            [
                MagicMock(returncode=0),  # mss OK
                MagicMock(returncode=1),  # PIL missing
            ]
        )
        with patch(
            "computer_use.bridge.deployer.subprocess.run",
            side_effect=lambda *a, **k: next(calls),
        ):
            missing = deployer.verify_deps("C:\\py\\python.exe")
            assert missing == ["Pillow"]


class TestInstallDeps:
    def test_returns_true_on_pip_success(self, deployer):
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert deployer.install_deps("py", ["mss"]) is True

    def test_returns_false_on_pip_failure(self, deployer):
        with patch(
            "computer_use.bridge.deployer.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="boom")
            assert deployer.install_deps("py", ["mss"]) is False


# --- orchestrator ---


class TestEnsure:
    def test_happy_path_calls_all_steps(self, deployer, tmp_deploy_dir):
        tmp_deploy_dir.mkdir()
        with (
            patch.object(deployer, "ensure_deploy_dir") as mock_dir,
            patch.object(deployer, "deploy_files", return_value=["daemon.py"]),
            patch.object(deployer, "clean_stale", return_value=[]),
            patch.object(deployer, "verify_deps", return_value=[]),
            patch.object(deployer, "install_deps") as mock_install,
        ):
            mock_dir.return_value = tmp_deploy_dir
            assert deployer.ensure("py.exe", tmp_deploy_dir) is True
            mock_install.assert_not_called()  # nothing to install

    def test_installs_missing_deps(self, deployer, tmp_deploy_dir):
        tmp_deploy_dir.mkdir()
        with (
            patch.object(deployer, "ensure_deploy_dir"),
            patch.object(deployer, "deploy_files", return_value=[]),
            patch.object(deployer, "clean_stale", return_value=[]),
            patch.object(deployer, "verify_deps", return_value=["Pillow"]),
            patch.object(
                deployer, "install_deps", return_value=True
            ) as mock_install,
        ):
            deployer.ensure("py.exe", tmp_deploy_dir)
            mock_install.assert_called_once_with("py.exe", ["Pillow"])

    def test_returns_false_when_deps_cannot_be_installed(
        self, deployer, tmp_deploy_dir
    ):
        tmp_deploy_dir.mkdir()
        with (
            patch.object(deployer, "ensure_deploy_dir"),
            patch.object(deployer, "deploy_files", return_value=[]),
            patch.object(deployer, "clean_stale", return_value=[]),
            patch.object(deployer, "verify_deps", return_value=["mss"]),
            patch.object(deployer, "install_deps", return_value=False),
        ):
            assert deployer.ensure("py.exe", tmp_deploy_dir) is False
