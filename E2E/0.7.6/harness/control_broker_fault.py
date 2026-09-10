# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Request one POSIX B09 relay cut and observe its automatic restoration."""

import argparse
import json
import math
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path


def identity(info):
    return info.st_dev, info.st_ino


def checked_path(root, path, kind):
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(root):
        raise ValueError("path must be inside the isolated root")
    current = root
    for component in path.relative_to(root).parts:
        current /= component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("path must be owned by this user without symlinks")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("path parent must be a directory")
    info = path.lstat()
    if not kind(info.st_mode) or info.st_nlink != 1:
        raise ValueError("expected a single-link FIFO or regular event log")
    return info


def validate_event(row):
    if not isinstance(row, dict):
        raise ValueError("event must be an object")
    fields = {"event", "monotonic", "utc"}
    extras = {"cut": {"seconds", "connection_count"}, "restored": set(),
              "connection_refused": set(), "connection_opened": set(),
              "upstream_unavailable": set()}
    kind = row.get("event")
    if not isinstance(kind, str) or kind not in extras or set(row) != fields | extras[kind]:
        raise ValueError("unexpected relay event shape")
    stamp = row["monotonic"]
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError("invalid event monotonic timestamp")
    if not isinstance(row["utc"], str) or not row["utc"]:
        raise ValueError("invalid event UTC timestamp")
    utc = datetime.fromisoformat(row["utc"])
    if utc.utcoffset() is None or utc.utcoffset().total_seconds() != 0:
        raise ValueError("event timestamp must use UTC")
    if kind == "cut":
        if type(row["seconds"]) not in (int, float) or not math.isfinite(row["seconds"]):
            raise ValueError("invalid cut duration")
        if type(row["connection_count"]) is not int or row["connection_count"] < 0:
            raise ValueError("invalid cut connection count")
    return row


def run(root, control, events, seconds, timeout):
    if os.name != "posix":
        raise ValueError("this control helper requires POSIX FIFOs")
    if type(seconds) is not int or seconds not in (8, 46):
        raise ValueError("seconds must be 8 or 46")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not seconds < timeout <= 60:
        raise ValueError("timeout must exceed seconds and be at most 60")
    root = Path(root)
    if root.parent != Path("/tmp") or not root.name.startswith("vadgr-cua-"):
        raise ValueError("root must be a named /tmp/vadgr-cua-* directory")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("root must be a current-user-owned mode-0700 directory")
    control, events = Path(control), Path(events)
    fifo_info = checked_path(root, control, stat.S_ISFIFO)
    log_info = checked_path(root, events, stat.S_ISREG)
    started = time.monotonic()
    log_fd = os.open(events, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(log_fd)) != identity(log_info):
            raise ValueError("event log replaced during open")
        offset = os.lseek(log_fd, 0, os.SEEK_END)
        initial_offset = offset
        if offset and os.pread(log_fd, 1, offset - 1) != b"\n":
            raise ValueError("event log has an unfinished prior event")
        fifo_fd = os.open(control, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            if identity(os.fstat(fifo_fd)) != identity(fifo_info):
                raise ValueError("control FIFO replaced during open")
            command = (json.dumps({"cut_seconds": seconds}) + "\n").encode()
            if os.write(fifo_fd, command) != len(command):
                raise ValueError("incomplete control write")
        finally:
            os.close(fifo_fd)
        pending, cut, restored = b"", None, None
        while time.monotonic() - started < timeout:
            current = checked_path(root, events, stat.S_ISREG)
            if identity(current) != identity(log_info):
                raise ValueError("event log replaced")
            if current.st_size < offset:
                raise ValueError("event log truncated")
            data = os.read(log_fd, 65536)
            offset += len(data)
            pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                row = validate_event(json.loads(line))
                if row["event"] == "cut":
                    if cut is not None or row["seconds"] != seconds:
                        raise ValueError("unexpected or concurrent cut")
                    cut = row
                    print(json.dumps(row), flush=True)
                elif row["event"] == "restored":
                    if cut is None or restored is not None or row["monotonic"] < cut["monotonic"]:
                        raise ValueError("restoration does not follow the requested cut")
                    restored = row
                    print(json.dumps(row), flush=True)
            if len(pending) > 65536:
                raise ValueError("event line exceeds the size bound")
            if restored is not None and not pending and os.fstat(log_fd).st_size == offset:
                print(json.dumps({"event": "control_complete", "initial_offset": initial_offset,
                                  "elapsed_seconds": time.monotonic() - started,
                                  "restored_minus_cut_seconds": restored["monotonic"] - cut["monotonic"]}), flush=True)
                return
            time.sleep(0.02)
        raise TimeoutError("timed out waiting for a new cut and restoration")
    finally:
        os.close(log_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "control", "events"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--seconds", required=True, type=int, choices=(8, 46))
    parser.add_argument("--timeout", required=True, type=float)
    args = parser.parse_args()
    try:
        run(args.root, args.control, args.events, args.seconds, args.timeout)
    except (OSError, ValueError, TimeoutError):
        print("relay control failed; inspect the isolated relay log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
