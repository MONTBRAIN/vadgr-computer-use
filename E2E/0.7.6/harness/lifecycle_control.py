# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare and verify exact Chrome lifecycle states for C07.

This helper talks only to an isolated Chrome-for-Testing DevTools endpoint. It
never activates a page target. Product operations remain MCP calls made by the
E2E driver after this helper has established and independently verified state.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect


class LifecycleSetupError(RuntimeError):
    """The isolated Chrome fixture could not establish the requested state."""


class DevTools:
    def __init__(self, port_file: Path) -> None:
        lines = port_file.read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].isdigit():
            raise LifecycleSetupError("DevToolsActivePort has no valid port")
        self.base = f"http://127.0.0.1:{lines[0]}"

    def json(self, path: str, *, method: str = "GET") -> Any:
        request = urllib.request.Request(f"{self.base}{path}", method=method)
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return json.load(response)

    def targets(self) -> list[dict[str, Any]]:
        return self.json("/json/list")

    def create(self, url: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(url, safe="")
        return self.json(f"/json/new?{encoded}", method="PUT")

    @staticmethod
    def command(target: dict[str, Any], method: str, params: dict[str, Any]) -> Any:
        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str):
            raise LifecycleSetupError("target has no DevTools websocket")
        request = {"id": 1, "method": method, "params": params}
        with connect(websocket_url, open_timeout=5, close_timeout=2) as websocket:
            websocket.send(json.dumps(request))
            while True:
                response = json.loads(websocket.recv(timeout=5))
                if response.get("id") != 1:
                    continue
                if "error" in response:
                    raise LifecycleSetupError(str(response["error"]))
                return response.get("result")

    def evaluate(self, target: dict[str, Any], expression: str) -> Any:
        result = self.command(
            target,
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if not isinstance(result, dict):
            raise LifecycleSetupError("Runtime.evaluate returned no result")
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise LifecycleSetupError(details.get("text", "evaluation failed"))
        remote = result.get("result")
        if not isinstance(remote, dict):
            raise LifecycleSetupError("Runtime.evaluate returned no value")
        if remote.get("subtype") == "error":
            raise LifecycleSetupError(remote.get("description", "evaluation failed"))
        return remote.get("value")


def exact_target(devtools: DevTools, url: str) -> dict[str, Any]:
    matches = [
        target
        for target in devtools.targets()
        if target.get("type") == "page" and target.get("url") == url
    ]
    if len(matches) != 1:
        raise LifecycleSetupError(
            f"expected one exact page target for {url!r}, found {len(matches)}"
        )
    return matches[0]


def wait_for_target(
    devtools: DevTools,
    url: str,
    *,
    title: str | None = None,
    timeout: float = 5,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [
            target
            for target in devtools.targets()
            if target.get("type") == "page"
            and target.get("url") == url
            and (title is None or target.get("title") == title)
        ]
        if matches:
            return matches[-1]
        time.sleep(0.1)
    raise LifecycleSetupError(f"timed out waiting for {url!r}")


def prepare_internal_pages(devtools: DevTools) -> dict[str, Any]:
    chrome_urls = next(
        (
            target
            for target in devtools.targets()
            if target.get("type") == "page"
            and target.get("url") == "chrome://chrome-urls/"
        ),
        None,
    )
    if chrome_urls is None:
        devtools.create("chrome://chrome-urls/")
        chrome_urls = wait_for_target(devtools, "chrome://chrome-urls/")

    expression = """
(() => {
  const root = document.querySelector('chrome-urls-app')?.shadowRoot;
  const description = root?.querySelector('#debug-pages-description')
    ?.textContent?.trim() ?? '';
  if (description.includes('enabled')) return {enabled: true, changed: false};
  const button = root?.querySelector('cr-button');
  if (!button || button.textContent.trim() !== 'Enable internal debugging pages') {
    throw new Error('internal debugging page enable control is unavailable');
  }
  button.click();
  return {enabled: true, changed: true};
})()
"""
    outcome = devtools.evaluate(chrome_urls, expression)

    discards = next(
        (
            target
            for target in devtools.targets()
            if target.get("type") == "page"
            and target.get("url") == "chrome://discards/"
            and target.get("title") == "Discards"
        ),
        None,
    )
    if discards is None:
        devtools.create("chrome://discards/")
        discards = wait_for_target(
            devtools, "chrome://discards/", title="Discards", timeout=10
        )
    return {"debug_pages": outcome, "discards_target_id": discards.get("id")}


def discards_target(devtools: DevTools) -> dict[str, Any]:
    matches = [
        target
        for target in devtools.targets()
        if target.get("type") == "page"
        and target.get("url") == "chrome://discards/"
        and target.get("title") == "Discards"
    ]
    if len(matches) != 1:
        raise LifecycleSetupError(
            f"expected one enabled chrome://discards target, found {len(matches)}"
        )
    return matches[0]


def row_expression(url: str, body: str) -> str:
    return f"""
(() => {{
  const root = document.querySelector('discards-main')?.shadowRoot
    ?.querySelector('discards-tab')?.shadowRoot;
  if (!root) throw new Error('discards table is unavailable');
  const row = [...root.querySelectorAll('tbody tr')].find(
    item => item.querySelector('.tab-url-cell')?.textContent?.trim() === {json.dumps(url)}
  );
  if (!row) throw new Error('exact lifecycle target row is unavailable');
  {body}
}})()
"""


def lifecycle_row(devtools: DevTools, url: str) -> dict[str, Any]:
    value = devtools.evaluate(
        discards_target(devtools),
        row_expression(
            url,
            """
return {
  lifecycle: row.children[6]?.textContent?.trim() ?? '',
  active: row.children[4]?.textContent?.trim() === 'visible',
  url: row.querySelector('.tab-url-cell')?.textContent?.trim() ?? '',
};
""",
        ),
    )
    if not isinstance(value, dict):
        raise LifecycleSetupError("lifecycle row returned no structured state")
    return value


def wait_for_lifecycle(
    devtools: DevTools, url: str, expected: str, timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = lifecycle_row(devtools, url)
        if expected in str(last.get("lifecycle", "")).lower():
            return last
        time.sleep(0.2)
    raise LifecycleSetupError(
        f"target never reached {expected!r}; last state was {last!r}"
    )


def freeze(devtools: DevTools, url: str, timeout: float) -> dict[str, Any]:
    protocol = devtools.json("/json/protocol")
    supported = any(
        command.get("name") == "setWebLifecycleState"
        for domain in protocol.get("domains", [])
        if domain.get("domain") == "Page"
        for command in domain.get("commands", [])
    )
    if not supported:
        raise LifecycleSetupError("Page.setWebLifecycleState is unavailable")
    target = exact_target(devtools, url)
    devtools.command(target, "Page.setWebLifecycleState", {"state": "frozen"})
    return wait_for_lifecycle(devtools, url, "frozen", timeout)


def discard(devtools: DevTools, url: str, timeout: float) -> dict[str, Any]:
    result = devtools.evaluate(
        discards_target(devtools),
        row_expression(
            url,
            """
const action = [...row.querySelectorAll('.actions-cell [is="action-link"]')]
  .find(item => item.textContent.trim() === '[Urgent Discard]');
if (!action || action.hasAttribute('disabled')) {
  throw new Error('exact target is not urgently discardable');
}
action.click();
return {requested: true};
""",
        ),
    )
    if not isinstance(result, dict) or result.get("requested") is not True:
        raise LifecycleSetupError("urgent discard was not requested")
    return wait_for_lifecycle(devtools, url, "discarded", timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    for command in ("freeze", "discard", "state"):
        child = subparsers.add_parser(command)
        child.add_argument("--url", required=True)
    args = parser.parse_args()

    devtools = DevTools(args.port_file)
    if args.command == "prepare":
        result = prepare_internal_pages(devtools)
    elif args.command == "freeze":
        result = freeze(devtools, args.url, args.timeout)
    elif args.command == "discard":
        result = discard(devtools, args.url, args.timeout)
    else:
        result = lifecycle_row(devtools, args.url)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
