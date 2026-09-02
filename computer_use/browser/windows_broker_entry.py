# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Self-contained Windows entry point for the shared browser broker.

The frozen executable only serves the broker on Windows loopback. Native
Windows clients connect directly; WSL clients use the separately built Go
stdio proxy so the frozen payload never carries a second transport path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _serve() -> int:
    manifest_path = Path(sys.executable).resolve().parent / "bundle-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = str(manifest["archive_sha256"])
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("browser broker bundle manifest is unavailable") from error
    os.environ["VADGR_CUA_BROKER_BUNDLE_HASH"] = bundle_hash
    os.environ["VADGR_CUA_BROKER_STARTED_NS"] = str(time.time_ns())
    from computer_use.browser.broker import main

    return main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vadgr-cua-browser-broker")
    parser.add_argument("mode", nargs="?", choices=("serve",), default="serve")
    parser.parse_args(argv)
    return _serve()


if __name__ == "__main__":
    raise SystemExit(main())
