# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Stop one isolated extension worker; never issue a product operation."""

import argparse
import importlib
import json
import time
from pathlib import Path

from lifecycle_control import DevTools, LifecycleSetupError, exact_target


def stop_worker(devtools: DevTools, page_url: str, extension_id: str) -> dict:
    target = exact_target(devtools, page_url)
    connect = importlib.import_module("websockets.sync.client").connect
    prefix = f"chrome-extension://{extension_id}/"
    version_id = None
    acknowledged = False
    stopped = False
    deadline = time.monotonic() + 15
    with connect(target["webSocketDebuggerUrl"], open_timeout=5, close_timeout=2) as ws:
        ws.send(json.dumps({"id": 1, "method": "ServiceWorker.enable"}))
        while not (acknowledged and stopped):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LifecycleSetupError("named worker did not stop within 15 seconds")
            message = json.loads(ws.recv(timeout=remaining))
            if "error" in message:
                raise LifecycleSetupError(str(message["error"]))
            if message.get("id") == 2:
                acknowledged = True
            if message.get("method") != "ServiceWorker.workerVersionUpdated":
                continue
            for version in message.get("params", {}).get("versions", []):
                if not version.get("scriptURL", "").startswith(prefix):
                    continue
                if version_id is None and version.get("runningStatus") == "running":
                    version_id = version["versionId"]
                    ws.send(json.dumps({
                        "id": 2,
                        "method": "ServiceWorker.stopWorker",
                        "params": {"versionId": version_id},
                    }))
                elif version.get("versionId") == version_id:
                    stopped = version.get("runningStatus") == "stopped"
    return {
        "extension_id": extension_id,
        "stop_acknowledged": acknowledged,
        "runningStatus": "stopped",
        "devtools_disconnected": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port-file", type=Path, required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--extension-id", required=True)
    args = parser.parse_args()
    print(json.dumps(stop_worker(DevTools(args.port_file), args.page_url, args.extension_id)))
