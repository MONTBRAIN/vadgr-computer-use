# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare an opaque loopback transport fault for one isolated B09 client.

Standard input accepts {"cut_seconds": 8} or {"stop": true}. EOF stops the
relay. Standard output contains timing and connection metadata, never bytes.
"""

import argparse
import json
import math
import os
import queue
import select
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def isolated_path(root: Path, path: Path) -> Path:
    root = root.resolve(strict=True)
    temporary_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    if not root.is_dir() or not root.name.startswith("vadgr-cua-"):
        raise ValueError("expected a named isolated CUA directory")
    if not any(root.is_relative_to(base) and root != base for base in temporary_roots):
        raise ValueError("isolated root must be below the system temporary directory")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("endpoint path must be inside the isolated root")
    return resolved


def read_endpoint(root: Path, path: Path) -> dict:
    endpoint = json.loads(isolated_path(root, path).read_text(encoding="utf-8"))
    port = endpoint.get("port")
    if endpoint.get("host") != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("endpoint must name a valid IPv4 loopback port")
    return endpoint


def write_alias(root: Path, source: Path, alias: Path, endpoint: dict, port: int) -> Path:
    if sys.platform == "win32":
        raise ValueError("relay alias requires an owner-only Windows ACL implementation")
    destination = isolated_path(root, alias)
    if destination == isolated_path(root, source):
        raise ValueError("alias must not replace the original endpoint")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("relay port is invalid")
    payload = dict(endpoint, port=port)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream)
    return destination


def duration(command: dict) -> float:
    value = command.get("cut_seconds")
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 120:
        raise ValueError("cut_seconds must be finite and between 0 and 120")
    return float(value)


class Relay:
    def __init__(self, port: int, emit):
        self.upstream = ("127.0.0.1", port)
        self.emit = emit
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.connections = set()
        self.lock = threading.Lock()
        self.until = 0.0
        self.stopped = False

    def close_connections(self):
        with self.lock:
            connections = tuple(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        return len(connections) // 2

    def cut(self, seconds):
        seconds = duration({"cut_seconds": seconds})
        self.until = time.monotonic() + seconds
        count = self.close_connections()
        self.emit("cut", seconds=seconds, connection_count=count)

    def forward(self, downstream, upstream):
        try:
            while not self.stopped:
                ready, _, _ = select.select([downstream, upstream], [], [], 0.1)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is downstream else downstream
                    target.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                self.connections.discard(downstream)
                self.connections.discard(upstream)
            downstream.close()
            upstream.close()

    def tick(self):
        if self.until and time.monotonic() >= self.until:
            self.until = 0.0
            self.emit("restored")
        try:
            downstream, _ = self.listener.accept()
        except TimeoutError:
            return
        if self.until:
            downstream.close()
            self.emit("connection_refused")
            return
        try:
            upstream = socket.create_connection(self.upstream, timeout=2)
        except OSError:
            downstream.close()
            self.emit("upstream_unavailable")
            return
        downstream.settimeout(2)
        with self.lock:
            self.connections.update((downstream, upstream))
        threading.Thread(target=self.forward, args=(downstream, upstream), daemon=True).start()
        self.emit("connection_opened")

    def close(self):
        self.stopped = True
        self.listener.close()
        self.close_connections()


def emit(event, **metadata):
    print(
        json.dumps(
            {
                "event": event,
                "monotonic": time.monotonic(),
                "utc": datetime.now(timezone.utc).isoformat(),
                **metadata,
            }
        ),
        flush=True,
    )


def main():
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--endpoint", required=True, type=Path)
    parser.add_argument("--alias", required=True, type=Path)
    args = parser.parse_args()
    endpoint = read_endpoint(args.root, args.endpoint)
    relay = Relay(endpoint["port"], emit)
    alias = None
    commands = queue.Queue()

    def read_commands():
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("command must be an object")
                commands.put(command)
            except ValueError:
                emit("invalid_command")
        commands.put({"stop": True})

    try:
        alias = write_alias(args.root, args.endpoint, args.alias, endpoint, relay.port)
        alias_identity = alias.stat().st_ino
        emit("ready", relay_port=relay.port, upstream_port=endpoint["port"])
        threading.Thread(target=read_commands, daemon=True).start()
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None
            if command is not None:
                if command.get("stop") is True:
                    break
                try:
                    relay.cut(duration(command))
                except ValueError:
                    emit("invalid_command")
            relay.tick()
    finally:
        relay.close()
        if alias is not None and alias.exists() and alias.stat().st_ino == alias_identity:
            alias.unlink()
        emit("stopped")


if __name__ == "__main__":
    main()
