"""Capture read-only artifact and cleanup facts; never award a live verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import winreg

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--owned-pid", required=True, type=int, action="append")
    parser.add_argument("--fixture-port", required=True, type=int)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    marker = json.loads((root / ".cua-079-root.json").read_text())
    if marker != {"schema": 1, "root": str(root)}:
        raise ValueError("root marker differs")
    files = [*root.glob("candidate/output/*"), *root.glob("predecessors/*.whl"), root / "chrome.zip"]
    rows = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": digest(p)} for p in files]
    registry = []
    for browser, vendor in (("chrome", "Google\\Chrome"), ("edge", "Microsoft\\Edge")):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\" + vendor + "\\NativeMessagingHosts\\com.vadgr.cua") as key:
            value = Path(winreg.QueryValueEx(key, "")[0])
            registry.append({"browser": browser, "manifest_sha256": digest(value), "points_to_test_root": root in value.parents})
    if any(pid <= 0 for pid in args.owned_pid) or not 1 <= args.fixture_port <= 65535:
        raise ValueError("invalid owned identity or port")
    pid_values = ",".join(str(pid) for pid in args.owned_pid)
    command = (
        "$p = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in " + pid_values + " }); "
        "[PSCustomObject]@{owned_remaining=$p.Count; fixture_http_listeners=@(Get-NetTCPConnection -LocalPort "
        + str(args.fixture_port) + " -State Listen -ErrorAction SilentlyContinue).Count} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = {"schema": 1, "kind": "read-only setup and cleanup observation, not live qualification", "captured_utc": datetime.now(timezone.utc).isoformat(), "files": rows, "registry": registry, "cleanup": json.loads(result.stdout)}
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("Read-only boundary receipt captured; no live verdict awarded")


if __name__ == "__main__":
    main()
