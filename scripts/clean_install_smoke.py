#!/usr/bin/env python3
"""Clean-install smoke test: a first-time install starts and serves.

Run this AFTER installing the built wheel into a from-nothing environment (a
fresh container or venv that carries only the wheel and its declared
dependencies). It proves what the ``0.6.6`` patch existed to guarantee: a fresh
install can START ``vadgr-cua`` and it serves its whole tool surface. A fresh
install of ``0.6.5`` could not start at all, because a dependency floor let a
breaking major through, and nothing checked a clean install before publish.

The test imports the INSTALLED package, never the source tree, so run it from a
directory that is not the repo root. It is deliberately dependency-light: it
uses only the standard library plus the package under test, so it runs inside a
minimal container with nothing else added.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time

EXPECTED_TOOLS = 33
# A sample across the tiers, so a surface that lost a whole tier fails loudly
# rather than only failing the count.
KEY_TOOLS = (
    "ui_find",     # structured tier
    "ui_act",
    "app_open",
    "screenshot",  # pixel tier
    "browser",     # browser tier
    "shell",       # system tier
)


def check_surface() -> None:
    """The installed entry module imports and serves the whole tool surface."""
    from computer_use import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = sorted(t.name for t in tools)
    missing = [t for t in KEY_TOOLS if t not in names]
    if missing:
        raise SystemExit(f"FAIL: key tools missing from the served surface: {missing}")
    if len(names) != EXPECTED_TOOLS:
        raise SystemExit(
            f"FAIL: expected {EXPECTED_TOOLS} tools, the install serves {len(names)}"
        )
    print(f"OK: the installed package imports and serves {len(names)} tools")


def check_startup() -> None:
    """The ``vadgr-cua`` console script starts the stdio server without crashing.

    This is the exact 0.6.6 failure mode: the entry point could not start. Where
    the console script is on PATH (a real wheel install), start it and confirm it
    stays up. Where it is not (an isolated site directory whose scripts are not
    on PATH), the in-process surface check above already proved the import, so
    skip rather than shell out to the wrong interpreter.
    """
    exe = shutil.which("vadgr-cua")
    if not exe:
        print("SKIP: vadgr-cua not on PATH; the surface check already proved the import")
        return
    proc = subprocess.Popen(
        [exe],
        stdin=subprocess.PIPE,       # keep stdin open so the stdio server waits
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    time.sleep(2.5)
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace")[-2000:] if proc.stderr else ""
        raise SystemExit("FAIL: vadgr-cua exited on startup:\n" + err)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("OK: vadgr-cua starts the stdio server and stays up")


def main() -> int:
    check_surface()
    check_startup()
    print("clean-install smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
