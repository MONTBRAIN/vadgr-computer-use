#!/usr/bin/env python3
"""Prepare and inspect R1 through isolated Chrome DevTools, never the product."""

from __future__ import annotations

import argparse
import importlib
import json
import urllib.request
from pathlib import Path


class DevTools:
    def __init__(self, profile: Path) -> None:
        lines = (profile / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].isdigit():
            raise ValueError("isolated profile has no DevTools port")
        self.base = f"http://127.0.0.1:{lines[0]}"
        with urllib.request.urlopen(f"{self.base}/json/version", timeout=5) as response:
            self.browser_ws = json.load(response)["webSocketDebuggerUrl"]

    @staticmethod
    def call(websocket_url: str, method: str, params: dict | None = None) -> dict:
        connect = importlib.import_module("websockets.sync.client").connect
        request = {"id": 1, "method": method, "params": params or {}}
        with connect(websocket_url, open_timeout=5, close_timeout=2) as websocket:
            websocket.send(json.dumps(request))
            while True:
                response = json.loads(websocket.recv(timeout=5))
                if response.get("id") != 1:
                    continue
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                return response.get("result") or {}

    def targets(self) -> list[dict]:
        with urllib.request.urlopen(f"{self.base}/json/list", timeout=5) as response:
            return json.load(response)

    def create(self, url: str, *, new_window: bool) -> str:
        result = self.call(
            self.browser_ws,
            "Target.createTarget",
            {"url": url, "newWindow": new_window, "background": False},
        )
        return str(result["targetId"])

    def window(self, target_id: str) -> int:
        return int(
            self.call(
                self.browser_ws,
                "Browser.getWindowForTarget",
                {"targetId": target_id},
            )["windowId"]
        )

    def evaluate(self, target_id: str, expression: str):
        target = next(item for item in self.targets() if item.get("id") == target_id)
        result = self.call(
            str(target["webSocketDebuggerUrl"]),
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        return result["result"].get("value")


def prepare_targets(devtools: DevTools, base_url: str) -> dict:
    fixtures = {}
    for name in ("one", "two"):
        target = devtools.create(f"{base_url}?agent={name}", new_window=True)
        window = devtools.window(target)
        decoy = devtools.create(f"about:blank#decoy-{name}", new_window=False)
        if devtools.window(decoy) != window:
            raise RuntimeError("decoy did not open in its fixture window")
        fixtures[name] = {"target_id": target, "window_id": window, "decoy_id": decoy}
    return fixtures


def observe(devtools: DevTools, fixtures: dict) -> dict:
    result = {}
    for name, identity in fixtures.items():
        value = devtools.evaluate(
            identity["target_id"],
            "({agent:document.body.dataset.agent,value:document.querySelector('#arena').value,"
            "visibility:document.visibilityState,focus:document.hasFocus()})",
        )
        decoy = devtools.evaluate(identity["decoy_id"], "document.body.textContent")
        result[name] = {**identity, "page": value, "decoy_empty": decoy == ""}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "observe"))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/browser_fixture.html")
    parser.add_argument("--identity-file", type=Path, required=True)
    args = parser.parse_args()
    profile = args.profile.resolve(strict=True)
    identity = args.identity_file.resolve() if args.identity_file.exists() else args.identity_file
    if profile.parent != identity.parent or not profile.name.startswith("chrome-profile-"):
        raise ValueError("identity file is outside the isolated profile root")
    devtools = DevTools(profile)
    if args.command == "prepare":
        if identity.exists():
            raise ValueError("identity file already exists")
        fixtures = prepare_targets(devtools, args.base_url)
        identity.write_text(json.dumps(fixtures, sort_keys=True), encoding="utf-8")
        print(json.dumps({"event": "prepared", "fixtures": fixtures}, sort_keys=True))
        return 0
    fixtures = json.loads(identity.read_text(encoding="utf-8"))
    print(
        json.dumps({"event": "observed", "fixtures": observe(devtools, fixtures)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
