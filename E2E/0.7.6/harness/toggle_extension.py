# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Toggle only the CUA extension in an isolated Chrome profile for A03/A04."""

import argparse
import json
from pathlib import Path

from lifecycle_control import DevTools, LifecycleSetupError

EXTENSION_ID = "bcbdnpafilijienocokppgmfianhehll"


def toggle(devtools: DevTools, enabled: bool) -> dict:
    target = devtools.create("chrome://extensions/")
    expression = """
new Promise((resolve, reject) => {
  const deadline = performance.now() + 5000;
  const probe = () => {
    const manager = document.querySelector('extensions-manager');
    const list = manager?.shadowRoot?.querySelector('extensions-item-list');
    const item = list?.shadowRoot?.querySelector('extensions-item[id=EXTENSION_ID]');
    const toggle = item?.shadowRoot?.querySelector('#enableToggle');
    if (toggle) {
      if (!!toggle.checked !== ENABLED) toggle.click();
      const verify = () => {
        if (!!toggle.checked === ENABLED) resolve({enabled: !!toggle.checked});
        else if (performance.now() >= deadline) reject(new Error('toggle timed out'));
        else requestAnimationFrame(verify);
      };
      verify();
    } else if (performance.now() >= deadline) reject(new Error('toggle not found'));
    else requestAnimationFrame(probe);
  };
  probe();
})()
""".replace("EXTENSION_ID", json.dumps(EXTENSION_ID)).replace("ENABLED", json.dumps(enabled))
    try:
        result = devtools.evaluate(target, expression)
        if not isinstance(result, dict) or result.get("enabled") is not enabled:
            raise LifecycleSetupError("extension toggle did not match requested state")
    finally:
        browser = devtools.json("/json/version")
        closed = devtools.command(browser, "Target.closeTarget", {"targetId": target["id"]})
        if not closed.get("success"):
            raise LifecycleSetupError("temporary extensions page did not close")
    return {"enabled": enabled, "temporary_extensions_page_closed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port-file", type=Path, required=True)
    parser.add_argument("state", choices=("enable", "disable"))
    args = parser.parse_args()
    print(json.dumps(toggle(DevTools(args.port_file), args.state == "enable")))
