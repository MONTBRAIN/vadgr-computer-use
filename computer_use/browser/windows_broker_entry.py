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
    from computer_use.browser.windows_process import current_process_creation_filetime

    os.environ["VADGR_CUA_BROKER_CREATED_FILETIME"] = current_process_creation_filetime()
    from computer_use.browser.broker import main

    return main()


def _upgrade_handoff() -> int:
    from computer_use.browser.broker import broker_lock_path
    from computer_use.browser.windows_process import (
        UpgradeHandoffError,
        perform_upgrade_handoff,
    )

    bundle = Path(sys.executable).resolve().parent
    packaged = Path(getattr(sys, "_MEIPASS", bundle))
    try:
        result = perform_upgrade_handoff(
            lock_path=broker_lock_path(),
            candidate_bundle=bundle,
            catalog_path=packaged / "predecessor-catalog.json",
        )
    except UpgradeHandoffError as error:
        result = {
            "state": "refused",
            "code": error.code,
            "message": str(error),
            "remediation": error.remediation,
        }
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vadgr-cua-browser-broker")
    parser.add_argument("mode", nargs="?", choices=("serve", "upgrade-handoff"), default="serve")
    options = parser.parse_args(argv)
    return _upgrade_handoff() if options.mode == "upgrade-handoff" else _serve()


if __name__ == "__main__":
    raise SystemExit(main())
