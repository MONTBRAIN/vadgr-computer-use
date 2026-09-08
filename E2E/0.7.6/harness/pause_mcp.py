# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare a bounded scheduling pause for one isolated installed POSIX MCP."""

import argparse
import json
import math
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def duration(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 120:
        raise ValueError("pause must be finite and between 0 and 120 seconds")
    return float(value)


def inspect_process(pid):
    # Arguments are inspected privately, never returned in evidence or errors.
    result = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "pid=,ppid=,uid=,lstart=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = result.stdout.strip().split(None, 8)
    if result.returncode or len(parts) != 9:
        raise ValueError("target process is unavailable")
    return (
        int(parts[0]),
        int(parts[1]),
        int(parts[2]),
        " ".join(parts[3:8]),
        tuple(shlex.split(parts[8])),
    )


def validate(root, pid, parent_pid):
    if os.name != "posix":
        raise ValueError("scheduling pause requires POSIX")
    root = root.resolve(strict=True)
    bases = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    if (
        not root.is_dir()
        or not root.name.startswith("vadgr-cua-")
        or not any(root != base and root.is_relative_to(base) for base in bases)
    ):
        raise ValueError("expected a named isolated temporary CUA root")
    if type(pid) is not int or type(parent_pid) is not int or min(pid, parent_pid) <= 1:
        raise ValueError("invalid process identity")
    entry = root / "runtime/bin/vadgr-cua"
    interpreter = root / "runtime/bin/python"
    if not entry.is_file() or not entry.resolve().is_relative_to(root) or not interpreter.is_file():
        raise ValueError("isolated installed entry point is missing")
    identity = inspect_process(pid)
    command = identity[-1]
    if identity[:3] != (pid, parent_pid, os.getuid()) or len(command) != 2:
        raise ValueError("target is not the expected owned MCP child")
    interpreters = {interpreter.resolve()}
    if sys.platform == "darwin":
        # Framework Python's wrapper execs its app executable after startup.
        framework_app = (
            interpreter.resolve().parent.parent / "Resources/Python.app/Contents/MacOS/Python"
        )
        if framework_app.is_file():
            interpreters.add(framework_app.resolve())
    if (
        Path(command[0]).resolve() not in interpreters
        or Path(command[1]).resolve() != entry.resolve()
    ):
        raise ValueError("target is not the isolated installed MCP")
    return identity


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


def pause_and_resume(identity, seconds):
    if inspect_process(identity[0]) != identity:
        raise ValueError("target identity changed before pause")
    try:
        os.kill(identity[0], signal.SIGSTOP)
        emit("paused", pid=identity[0], seconds=seconds)
        time.sleep(seconds)
    finally:
        try:
            if inspect_process(identity[0]) == identity:
                os.kill(identity[0], signal.SIGCONT)
                emit("resumed", pid=identity[0])
            else:
                emit("resume_skipped_identity_changed", pid=identity[0])
        except ProcessLookupError:
            emit("target_exited", pid=identity[0])


def watchdog(identity, seconds):
    # This detached child owns STOP and CONT. Killing the calling helper cannot
    # leave a gap between arming a timer and sending STOP from another process.
    os.setsid()
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def interrupted(signum, frame):
        raise InterruptedError("watchdog interrupted")

    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        pause_and_resume(identity, seconds)
    except (OSError, ValueError):
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--seconds", required=True, type=float)
    args = parser.parse_args()
    try:
        seconds = duration(args.seconds)
        identity = validate(args.root, args.pid, args.parent_pid)
    except (OSError, ValueError):
        emit("refused")
        return 2
    child = os.fork()
    if child == 0:
        os._exit(watchdog(identity, seconds))
    emit("watchdog_started", watchdog_pid=child, target_pid=args.pid)
    _, status = os.waitpid(child, 0)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(main())
