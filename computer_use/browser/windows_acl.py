# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Windows owner-and-SYSTEM ACL helper for broker secrets and locks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def protect_owner_and_system(path: Path) -> None:
    if sys.platform != "win32":
        return
    username = os.environ.get("USERNAME")
    domain = os.environ.get("USERDOMAIN")
    if not username:
        raise OSError("cannot resolve the Windows owner for broker ACLs")
    owner = f"{domain}\\{username}" if domain else username
    result = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{owner}:F",
            "*S-1-5-18:F",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    if result.returncode != 0:
        raise OSError(f"failed to protect Windows broker file {path.name}")
