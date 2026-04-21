# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Static-setup concerns for the Windows bridge daemon.

Single responsibility: get the daemon code onto the Windows filesystem
and its Python deps installed on the Windows-side interpreter.

Does NOT know about: daemon lifecycle (probe/start/stop), TCP, RPC.
Those live in `supervisor.py` and `client.py`.
"""

from __future__ import annotations

import filecmp
import glob
import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("computer_use.bridge.deployer")


class DaemonDeployer:
    """Deploys daemon.py to the Windows side and ensures its deps are present.

    Stateless between calls. All paths passed in are WSL-mounted
    filesystem paths (e.g. `/mnt/c/Users/<name>/vadgr`).
    """

    DEPLOY_DIR_NAME: str = "vadgr"

    # Files the daemon needs at runtime. Anything else in the deploy dir
    # is treated as stale (see `clean_stale`).
    DAEMON_FILES: tuple[str, ...] = ("daemon.py",)

    # Windows Python packages the daemon imports at runtime.
    # Key = pip name, value = importable module name.
    DAEMON_DEPS: dict[str, str] = {
        "mss": "mss",
        "Pillow": "PIL",
    }

    _SUBPROCESS_TIMEOUT_SHORT = 5.0
    _SUBPROCESS_TIMEOUT_PIP = 120.0

    def __init__(self, deploy_dir_name: Optional[str] = None) -> None:
        self._dir_name = deploy_dir_name or self.DEPLOY_DIR_NAME

    # --- Inspection ---

    def daemon_source_path(self) -> Path:
        """Return the path to the daemon.py shipped with this package."""
        return Path(__file__).resolve().parent / "daemon.py"

    def current_daemon_hash(self) -> str:
        """Return SHA-256 hex of the shipped daemon.py.

        Used for version-drift detection: supervisor compares this with
        the hash reported by a running daemon's handshake.
        """
        return hashlib.sha256(self.daemon_source_path().read_bytes()).hexdigest()

    # --- Windows Python discovery ---

    def find_windows_python(self) -> Optional[str]:
        """Find a usable Windows python.exe.

        Resolution order:
          1. `where python` via cmd.exe (respects the user's PATH).
             Skips the Microsoft Store WindowsApps shim.
          2. Common per-user install paths: `%USERPROFILE%\\AppData\\Local\\Programs\\Python\\PythonNNN\\python.exe`.
          3. System-wide paths: `C:\\PythonNNN\\python.exe`.

        Returns the Windows-native path (e.g. `C:\\Python312\\python.exe`) or None.
        """
        # 1. `where python` via cmd.exe
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "where python"],
                capture_output=True,
                text=True,
                timeout=self._SUBPROCESS_TIMEOUT_SHORT,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    path = line.strip()
                    if path and "WindowsApps" not in path:
                        return path
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("`where python` failed: %s", e)

        # 2. / 3. Check common install paths via WSL mount.
        wsl_candidates: list[str] = []
        profile_wsl = self._get_windows_userprofile_wsl()
        if profile_wsl:
            wsl_candidates += [
                f"{profile_wsl}/AppData/Local/Programs/Python/Python{v}/python.exe"
                for v in ("313", "312", "311", "310")
            ]
        wsl_candidates += [
            "/mnt/c/Python313/python.exe",
            "/mnt/c/Python312/python.exe",
            "/mnt/c/Python311/python.exe",
            "/mnt/c/Python310/python.exe",
        ]

        for wsl_path in wsl_candidates:
            if os.path.isfile(wsl_path):
                return self._wsl_to_win_path(wsl_path)

        return None

    # --- Deploy directory ---

    def get_deploy_dir(self) -> Optional[Path]:
        """Return the WSL-mounted path to the Windows deploy directory.

        Does not create it. Returns None if the Windows user profile
        cannot be resolved.
        """
        profile_wsl = self._get_windows_userprofile_wsl()
        if profile_wsl is None:
            return None
        return Path(profile_wsl) / self._dir_name

    def ensure_deploy_dir(self, path: Path) -> Path:
        """Create the deploy directory if missing. Return the path."""
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --- File management ---

    def deploy_files(self, deploy_dir: Path) -> list[str]:
        """Copy DAEMON_FILES into deploy_dir, skipping unchanged files.

        Returns the names of files actually written (a no-op re-copy
        returns an empty list).
        """
        source_dir = self.daemon_source_path().parent
        written: list[str] = []
        for fname in self.DAEMON_FILES:
            src = source_dir / fname
            if not src.is_file():
                logger.warning("Skipping missing source: %s", src)
                continue
            dst = deploy_dir / fname
            if dst.exists() and filecmp.cmp(src, dst, shallow=False):
                continue
            shutil.copy2(src, dst)
            written.append(fname)
            logger.debug("Deployed %s -> %s", fname, dst)
        return written

    def clean_stale(self, deploy_dir: Path) -> list[str]:
        """Remove files in deploy_dir that are not in DAEMON_FILES.

        Only removes regular files (not directories). Returns the names
        of removed entries.
        """
        keep = set(self.DAEMON_FILES)
        removed: list[str] = []
        if not deploy_dir.exists():
            return removed
        for entry in deploy_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.name in keep:
                continue
            try:
                entry.unlink()
                removed.append(entry.name)
                logger.info("Removed stale file from deploy dir: %s", entry.name)
            except OSError as e:
                logger.warning("Could not remove stale %s: %s", entry, e)
        return removed

    # --- Dependency management ---

    def verify_deps(self, win_python: str) -> list[str]:
        """Return the pip names of deps missing on the Windows Python."""
        missing: list[str] = []
        for pkg, module in self.DAEMON_DEPS.items():
            if not self._check_import(win_python, module):
                missing.append(pkg)
        return missing

    def install_deps(self, win_python: str, deps: list[str]) -> bool:
        """pip-install the given packages on the Windows Python.

        Returns True if pip returned 0. Does NOT re-verify the imports
        here; call `verify_deps` afterwards if you need the postcondition.
        """
        if not deps:
            return True
        logger.info("Installing daemon deps on Windows Python: %s", ", ".join(deps))
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f'& "{win_python}" -m pip install {" ".join(deps)}',
                ],
                capture_output=True,
                text=True,
                timeout=self._SUBPROCESS_TIMEOUT_PIP,
            )
            if result.returncode != 0:
                logger.warning(
                    "pip install failed (exit %d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
            return True
        except Exception as e:
            logger.warning("pip install error: %s", e)
            return False

    # --- Orchestrator ---

    def ensure(self, win_python: str, deploy_dir: Path) -> bool:
        """Run the full deploy cycle.

        Steps:
          1. Ensure deploy_dir exists.
          2. Remove stale files (not in DAEMON_FILES).
          3. Copy/refresh DAEMON_FILES.
          4. Verify deps; install missing ones.

        Returns True if every step succeeded. Logs and returns False
        on the first failure that can't be recovered.
        """
        self.ensure_deploy_dir(deploy_dir)
        self.clean_stale(deploy_dir)
        self.deploy_files(deploy_dir)

        missing = self.verify_deps(win_python)
        if missing:
            if not self.install_deps(win_python, missing):
                return False
        return True

    # --- Internal helpers ---

    def _check_import(self, win_python: str, module: str) -> bool:
        """Return True if `module` is importable on the Windows Python."""
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f'& "{win_python}" -c "import {module}"',
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_windows_userprofile_wsl(self) -> Optional[str]:
        """Return `$env:USERPROFILE` as a WSL-mounted path, or None."""
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "echo %USERPROFILE%"],
                capture_output=True,
                text=True,
                timeout=self._SUBPROCESS_TIMEOUT_SHORT,
            )
            if result.returncode != 0:
                return None
            profile = result.stdout.strip()
            if not profile or ":" not in profile:
                return None
            drive = profile[0].lower()
            rest = profile[2:].replace("\\", "/")
            return f"/mnt/{drive}{rest}"
        except Exception:
            return None

    @staticmethod
    def _wsl_to_win_path(wsl_path: str) -> str:
        """Convert `/mnt/c/...` to `C:\\...` without shelling out."""
        if wsl_path.startswith("/mnt/") and len(wsl_path) > 6:
            drive = wsl_path[5].upper()
            rest = wsl_path[6:].replace("/", "\\")
            return f"{drive}:{rest}"
        return wsl_path
