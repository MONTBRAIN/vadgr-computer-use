# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Loopback-only server for the 0.7.6 browser and typing fixture."""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Record no query string or body. Fixture input must never reach logs.
        path = self.path.split("?", 1)[0]
        print(json.dumps({"client": self.client_address[0], "method": self.command, "path": path}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        lambda *values, **kwargs: Handler(*values, directory=str(root), **kwargs),
    )
    address = {
        "host": "127.0.0.1",
        "port": server.server_port,
        "url": f"http://127.0.0.1:{server.server_port}/page.html",
    }
    if args.ready_file:
        args.ready_file.write_text(json.dumps(address), encoding="utf-8")
    print(json.dumps(address), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
