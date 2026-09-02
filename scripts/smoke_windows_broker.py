#!/usr/bin/env python3
"""Run the committed broker bundle from an isolated Windows directory."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def exchange(file, value: dict[str, object]) -> dict[str, object]:
    file.write((json.dumps(value, separators=(",", ":")) + "\n").encode())
    file.flush()
    line = file.readline()
    if not line:
        raise RuntimeError("broker closed the smoke connection")
    return json.loads(line)


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("the Windows broker smoke must run on Windows")
    repository = Path(__file__).resolve().parents[1]
    packaged = repository / "computer_use" / "browser" / "winbroker"
    manifest_path = packaged / "vadgr-cua-browser-broker-win-x64.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-broker-smoke-") as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        local_app_data = root / "local-app-data"
        bundle.mkdir()
        local_app_data.mkdir()
        with zipfile.ZipFile(packaged / "vadgr-cua-browser-broker-win-x64.zip") as archive:
            archive.extractall(bundle)
        shutil.copyfile(manifest_path, bundle / "bundle-manifest.json")
        environment = dict(os.environ)
        environment["LOCALAPPDATA"] = str(local_app_data)
        process = subprocess.Popen(
            [str(bundle / "vadgr-cua-browser-broker.exe"), "serve"],
            cwd=bundle,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            endpoint_path = local_app_data / "vadgr-cua" / "browser-broker.json"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not endpoint_path.is_file():
                if process.poll() is not None:
                    raise RuntimeError("broker exited before publishing its endpoint")
                time.sleep(0.05)
            endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
            if endpoint.get("bundle_hash") != manifest["archive_sha256"]:
                raise RuntimeError("broker reported a different bundle identity")
            with socket.create_connection(("127.0.0.1", endpoint["port"]), timeout=5) as sock:
                with sock.makefile("rwb") as file:
                    hello = exchange(
                        file,
                        {"token": endpoint["token"], "client_id": None, "secret": None},
                    )
                    if not hello.get("ok") or hello.get("pid") != process.pid:
                        raise RuntimeError("broker handshake identity is incorrect")
                    status = exchange(file, {"id": 1, "op": "status", "params": {}})
                    if not status.get("ok"):
                        raise RuntimeError("broker status request failed")
            listeners = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        f"@(Get-NetTCPConnection -OwningProcess {process.pid} "
                        "-State Listen).LocalAddress -join ','"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            addresses = {item for item in listeners.stdout.strip().split(",") if item}
            if not addresses or addresses != {"127.0.0.1"}:
                raise RuntimeError(f"broker exposed a non-loopback listener: {addresses}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print("Windows broker clean smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
