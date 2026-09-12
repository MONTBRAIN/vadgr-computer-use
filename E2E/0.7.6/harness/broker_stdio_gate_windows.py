# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Wait for relay setup, then pass inherited stdio directly to installed MCP."""

import json
import os
import pathlib
import subprocess
import sys
import time


def main():
    gate, runtime = map(pathlib.Path, sys.argv[1:])
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        try:
            value = json.loads(gate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        if value.get("abort"):
            return 2
        if value.get("ready") is True:
            alias = pathlib.Path(value["alias"])
            if not alias.is_file() or not runtime.is_file():
                return 2
            environment = dict(os.environ, VADGR_CUA_BROKER_ENDPOINT=str(alias))
            # No protocol reads, writes or substitutions. The installed program
            # receives exactly the CLI's original streams and supplies all replies.
            child = subprocess.Popen(
                [str(runtime)], stdin=sys.stdin.buffer, stdout=sys.stdout.buffer,
                stderr=sys.stderr.buffer, env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return child.wait()
        time.sleep(.1)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(2)
