"""Select the subscription CLI for a CUA E2E group from Codex weekly usage."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

WEEK_MINUTES = 7 * 24 * 60
CODEX_MINIMUM_REMAINING = 75


def _codex_command(executable: str) -> list[str]:
    args = [executable, "app-server", "--listen", "stdio://"]
    if os.name == "nt" and os.path.splitext(executable)[1].lower() in {".bat", ".cmd"}:
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        return [command_processor, "/d", "/s", "/c", subprocess.list2cmdline(args)]
    return args


def _read_rate_limits(executable: str, timeout: float) -> dict[str, Any]:
    requests = [
        {
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "vadgr-cua-e2e-usage-probe", "version": "1.0.0"}},
        },
        {"method": "initialized"},
        {
            "id": 2,
            "method": "account/rateLimits/read",
            "params": {"excludeResetCreditDetails": True},
        },
    ]
    process = subprocess.Popen(
        _codex_command(executable),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Codex app-server pipes were unavailable")
    responses: queue.Queue[dict[str, Any]] = queue.Queue()

    def read_responses() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(response, dict):
                responses.put(response)

    reader = threading.Thread(target=read_responses, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout

    def wait_for(request_id: int) -> dict[str, Any]:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(_codex_command(executable), timeout)
            try:
                response = responses.get(timeout=remaining)
            except queue.Empty as error:
                raise subprocess.TimeoutExpired(_codex_command(executable), timeout) from error
            if response.get("id") == request_id:
                return response

    try:
        process.stdin.write(json.dumps(requests[0], separators=(",", ":")) + "\n")
        process.stdin.flush()
        initialized = wait_for(1)
        if initialized.get("error") is not None:
            raise RuntimeError("Codex initialization returned an error")
        for request in requests[1:]:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        process.stdin.flush()
        response = wait_for(2)
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if response.get("error") is not None:
        raise RuntimeError("Codex rate-limit request returned an error")
    result = response.get("result")
    if isinstance(result, dict):
        return result
    raise RuntimeError("Codex rate-limit response was unavailable")


def _weekly_window(result: dict[str, Any]) -> dict[str, Any]:
    snapshot = result.get("rateLimits")
    if not isinstance(snapshot, dict):
        by_id = result.get("rateLimitsByLimitId")
        snapshot = by_id.get("codex") if isinstance(by_id, dict) else None
    if not isinstance(snapshot, dict):
        raise ValueError("ordinary Codex rate limit was unavailable")

    windows = []
    for key in ("primary", "secondary"):
        window = snapshot.get(key)
        if isinstance(window, dict) and window.get("windowDurationMins") == WEEK_MINUTES:
            windows.append(window)
    if not windows:
        raise ValueError("ordinary Codex weekly window was unavailable")

    def remaining(window: dict[str, Any]) -> int:
        used = window.get("usedPercent")
        if not isinstance(used, int) or isinstance(used, bool) or not 0 <= used <= 100:
            raise ValueError("ordinary Codex weekly usage was invalid")
        return 100 - used

    return min(windows, key=remaining)


def _reset_time(epoch: Any) -> str | None:
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        return None
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def select_driver(result: dict[str, Any]) -> dict[str, Any]:
    window = _weekly_window(result)
    remaining = 100 - window["usedPercent"]
    use_codex = remaining >= CODEX_MINIMUM_REMAINING
    return {
        "probe_status": "ok",
        "selected_driver": "codex" if use_codex else "claude",
        "codex_model": "gpt-5.6-luna" if use_codex else None,
        "claude_model": None if use_codex else "claude-sonnet-5",
        "codex_weekly_remaining_percent": remaining,
        "codex_weekly_reset_at": _reset_time(window.get("resetsAt")),
        "threshold_percent": CODEX_MINIMUM_REMAINING,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", help="Codex executable; defaults to PATH lookup")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    executable = args.codex or shutil.which("codex")
    if not executable:
        print(
            json.dumps(
                {
                    "probe_status": "failed",
                    "selected_driver": "claude",
                    "claude_model": "claude-sonnet-5",
                    "reason": "codex_cli_unavailable",
                }
            )
        )
        return 2
    try:
        selection = select_driver(_read_rate_limits(executable, args.timeout))
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        selection = {
            "probe_status": "failed",
            "selected_driver": "claude",
            "claude_model": "claude-sonnet-5",
            "reason": "weekly_usage_unavailable",
        }
        print(json.dumps(selection, sort_keys=True))
        return 2
    print(json.dumps(selection, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
