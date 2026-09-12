#!/usr/bin/env python3
"""Prepare and observe isolated 0.7.7 browser-broker lifecycle states."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def checked_paths(root_value: str, endpoint_value: str) -> tuple[Path, Path]:
    root = Path(root_value).resolve(strict=True)
    if not root.is_dir() or not root.name.startswith("vadgr-cua-077-"):
        raise ValueError("root is not a validated 0.7.7 test root")
    endpoint = Path(endpoint_value)
    parent = endpoint.parent.resolve(strict=True)
    endpoint = parent / endpoint.name
    if root != parent and root not in parent.parents:
        raise ValueError("endpoint is outside the validated test root")
    if endpoint.is_symlink():
        raise ValueError("endpoint cannot be a symbolic link")
    return root, endpoint


def read_endpoint(endpoint: Path) -> dict[str, object]:
    value = json.loads(endpoint.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("endpoint is not an object")
    return value


def safe_identity(endpoint: Path) -> dict[str, object]:
    try:
        value = read_endpoint(endpoint)
    except FileNotFoundError:
        return {"endpoint": "absent"}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"endpoint": "invalid"}
    return {
        "endpoint": "valid",
        "platform": value.get("platform"),
        "host": value.get("host"),
        "port_valid": isinstance(value.get("port"), int) and 1 <= int(value["port"]) <= 65535,
        "token_present": isinstance(value.get("token"), str) and bool(value["token"]),
        "pid": value.get("pid"),
        "process_started_ns": value.get("process_started_ns"),
        "epoch": value.get("epoch"),
        "bundle_hash": value.get("bundle_hash"),
    }


def emit(value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def connect(endpoint: Path) -> int:
    os.environ["VADGR_CUA_BROKER_ENDPOINT"] = str(endpoint)
    from computer_use.browser.broker_client import BrokerClient
    from computer_use.browser.protocol import BrowserError

    client = BrokerClient(connect_timeout=12)
    try:
        status = client.send("status")
        emit(
            {
                "event": "connected",
                "identity": client._broker_identity,
                "status_ok": isinstance(status, dict),
            }
        )
        return 0
    except BrowserError as error:
        emit(
            {
                "event": "browser_error",
                "code": error.code.value,
                "remediation": error.remediation,
            }
        )
        return 2
    finally:
        client._close()


def fault(endpoint: Path, action: str) -> int:
    if action == "remove":
        endpoint.unlink()
    elif action == "corrupt":
        endpoint.write_text("{invalid\n", encoding="utf-8")
    elif action == "mismatch":
        value = read_endpoint(endpoint)
        value["bundle_hash"] = "f" * 64
        endpoint.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    else:
        raise ValueError("unsupported fault")
    emit({"event": "fault_applied", "action": action})
    return 0


def windows_process_path(pid: int) -> Path:
    command = (
        "$ErrorActionPreference='Stop';"
        "$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$args[0]);"
        "if($null -eq $p){exit 3};[Console]::Out.Write($p.ExecutablePath)"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command, str(pid)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("broker process identity is unavailable")
    return Path(result.stdout.strip()).resolve(strict=True)


def stop(root: Path, endpoint: Path) -> int:
    if sys.platform != "win32":
        raise ValueError("stop must run under native Windows Python")
    value = read_endpoint(endpoint)
    pid = value.get("pid")
    if not isinstance(pid, int) or pid < 1:
        raise ValueError("endpoint has no valid broker PID")
    executable = windows_process_path(pid)
    if root != executable.parent and root not in executable.parents:
        raise ValueError("broker executable is outside the validated test root")
    if executable.name.lower() != "vadgr-cua-browser-broker.exe":
        raise ValueError("PID is not the candidate broker executable")
    result = subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("validated broker termination failed")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            emit({"event": "broker_stopped", "pid": pid})
            return 0
        time.sleep(0.05)
    raise RuntimeError("validated broker did not exit")


def proxy(proxy_path: str) -> int:
    executable = Path(proxy_path).resolve(strict=True)
    process = subprocess.run(
        [str(executable), "broker-proxy"],
        input='{"token":null,"client_id":null,"secret":null}\n',
        capture_output=True,
        text=True,
        timeout=10,
    )
    reply = json.loads(process.stdout.splitlines()[0])
    error = reply.get("error") if isinstance(reply, dict) else None
    emit(
        {
            "event": "proxy_result",
            "exit_code": process.returncode,
            "ok": reply.get("ok") if isinstance(reply, dict) else False,
            "code": error.get("code") if isinstance(error, dict) else None,
            "remediation": error.get("remediation") if isinstance(error, dict) else None,
        }
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("observe", "connect", "fault", "stop", "proxy"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--action", choices=("remove", "corrupt", "mismatch"))
    parser.add_argument("--proxy")
    args = parser.parse_args()
    root, endpoint = checked_paths(args.root, args.endpoint)
    if args.command == "observe":
        emit(safe_identity(endpoint))
        return 0
    if args.command == "connect":
        return connect(endpoint)
    if args.command == "fault":
        if args.action is None:
            parser.error("fault requires --action")
        return fault(endpoint, args.action)
    if args.command == "stop":
        return stop(root, endpoint)
    if args.proxy is None:
        parser.error("proxy requires --proxy")
    return proxy(args.proxy)


if __name__ == "__main__":
    raise SystemExit(main())
