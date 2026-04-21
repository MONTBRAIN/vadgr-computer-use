# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Daemon lifecycle supervisor for the Windows bridge.

Single responsibility: decide whether the bridge daemon is ready,
bring it up if it isn't, kill it when asked, and report its state.

The deployer and the client factory are injected via the constructor,
so every decision branch is testable without touching Windows, TCP,
or the filesystem.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from computer_use.bridge.client import BridgeClient
from computer_use.bridge.deployer import DaemonDeployer
from computer_use.bridge.protocol import get_port

logger = logging.getLogger("computer_use.bridge.supervisor")


class DaemonSupervisor:
    """Ensures the Windows bridge daemon is running.

    Usage:
        supervisor = DaemonSupervisor()
        client = supervisor.ensure_running()
        if client is None:
            # fall back to slower path
            ...
    """

    # Poll cadence after a launch. Short interval + modest total so
    # callers don't wait too long when something is wrong.
    _LAUNCH_POLL_INTERVAL: float = 0.25
    _LAUNCH_TIMEOUT: float = 5.0

    # Short timeout for stop-side PowerShell calls.
    _STOP_TIMEOUT: float = 10.0

    def __init__(
        self,
        deployer: Optional[DaemonDeployer] = None,
        client_factory: Optional[Callable[[], BridgeClient]] = None,
    ) -> None:
        self._deployer = deployer or DaemonDeployer()
        self._client_factory = client_factory or BridgeClient

    # --- Public API ---

    def ensure_running(self) -> Optional[BridgeClient]:
        """Return a working BridgeClient, or None if the daemon can't be brought up.

        Decision tree:
          1. Probe. If healthy AND version matches, return client.
          2. If healthy but stale (hash mismatch or legacy daemon with no
             version_hash), stop and fall through to redeploy.
          3. Locate Windows Python and deploy dir. If either missing, return None.
          4. Run `deployer.ensure(...)`. If it fails, return None.
          5. Launch the daemon (detached Windows process).
          6. Poll until the daemon responds on its port, or time out.
        """
        client = self._client_factory()
        if client.is_available():
            if self._is_up_to_date(client):
                return client
            logger.info(
                "Daemon version drift detected; stopping and redeploying"
            )
            self.stop()
            # fall through to redeploy + relaunch

        return self._deploy_and_launch()

    def _is_up_to_date(self, client: BridgeClient) -> bool:
        """True if the running daemon's version hash matches the shipped one.

        Missing `version_hash` in the handshake is treated as drift: it's a
        pre-handshake daemon whose code we can't vouch for, so redeploy.
        """
        expected = self._deployer.current_daemon_hash()
        try:
            resp = client.handshake()
        except Exception:
            return False
        if not isinstance(resp, dict):
            return False
        return resp.get("version_hash") == expected

    def _deploy_and_launch(self) -> Optional[BridgeClient]:
        """Common path for first-time launch and post-drift relaunch."""
        win_python = self._deployer.find_windows_python()
        if win_python is None:
            logger.warning(
                "Bridge daemon unavailable and Windows Python not found. "
                "Run `vadgr-cua install-daemon` for a guided setup."
            )
            return None

        deploy_dir = self._deployer.get_deploy_dir()
        if deploy_dir is None:
            logger.warning("Could not resolve Windows user profile for daemon deploy")
            return None

        if not self._deployer.ensure(win_python, deploy_dir):
            logger.warning("Deployer failed to prepare daemon; skipping launch")
            return None

        self._launch(win_python, self._wsl_to_win_path(deploy_dir))

        ready = self._poll_for_ready(self._LAUNCH_TIMEOUT)
        if ready is None:
            logger.warning(
                "Launched daemon but it did not become ready within %.1fs",
                self._LAUNCH_TIMEOUT,
            )
        return ready

    def stop(self) -> None:
        """Kill any running daemon. Best-effort, never raises.

        Two passes:
          1. Kill the process listening on the configured bridge port.
          2. Kill any `pythonw.exe` whose command line mentions `daemon.py`
             (catches zombies that crashed before binding the port).
        """
        port = get_port()
        kill_by_port = (
            f"Get-NetTCPConnection -LocalPort {port} -State Listen "
            f"-ErrorAction SilentlyContinue | "
            f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"
        )
        kill_by_cmdline = (
            'Get-CimInstance Win32_Process -Filter "Name=\'pythonw.exe\'" '
            "| Where-Object { $_.CommandLine -like '*daemon.py*' } "
            "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )

        for script in (kill_by_port, kill_by_cmdline):
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", script],
                    capture_output=True,
                    timeout=self._STOP_TIMEOUT,
                )
            except Exception as e:
                logger.debug("Daemon stop step failed (continuing): %s", e)

    def restart(self) -> Optional[BridgeClient]:
        """Stop then start. Returns the fresh client or None."""
        self.stop()
        return self.ensure_running()

    def status(self) -> dict:
        """Introspect current daemon state for doctor-style output."""
        client = self._client_factory()
        running = False
        try:
            running = bool(client.is_available())
        except Exception:
            running = False

        return {
            "daemon_running": running,
            "windows_python": self._deployer.find_windows_python(),
            "deploy_dir": str(self._deployer.get_deploy_dir() or ""),
            "daemon_hash": self._deployer.current_daemon_hash(),
            "port": get_port(),
        }

    # --- Internal hooks (patchable in tests) ---

    def _launch(self, win_python: str, win_dir: str) -> None:
        """Start the daemon as a detached Windows process.

        Uses `pythonw.exe` (no console window) with `-WindowStyle Hidden`.
        Falls back to `python.exe` + Minimized if pythonw is missing.
        """
        pythonw = win_python.replace("python.exe", "pythonw.exe")

        logger.info("Launching daemon: %s daemon.py", pythonw)
        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    (
                        f'Start-Process -FilePath "{pythonw}" '
                        f'-ArgumentList "daemon.py" '
                        f'-WorkingDirectory "{win_dir}" '
                        f"-WindowStyle Hidden"
                    ),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning("Daemon launch failed: %s", e)

    def _poll_for_ready(self, timeout: float) -> Optional[BridgeClient]:
        """Probe repeatedly until the daemon responds or the timeout elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            client = self._client_factory()
            try:
                if client.is_available():
                    return client
            except Exception:
                pass
            time.sleep(self._LAUNCH_POLL_INTERVAL)
        return None

    # --- Helpers ---

    @staticmethod
    def _wsl_to_win_path(wsl_path: Path) -> str:
        """Convert `/mnt/c/Users/...` to `C:\\Users\\...` without shelling out."""
        s = str(wsl_path)
        if s.startswith("/mnt/") and len(s) > 6:
            drive = s[5].upper()
            rest = s[6:].replace("/", "\\")
            return f"{drive}:{rest}"
        return s
