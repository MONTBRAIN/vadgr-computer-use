# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Read metadata from one prepared TextEdit window without driving input."""

import argparse
import hashlib
import importlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


class ObserverError(ValueError):
    pass


def validate_wait(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 30:
        raise ObserverError("invalid_wait")
    return float(seconds)


def read_fixture(root, fixture, units):
    try:
        root = root.resolve(strict=True)
        fixture = fixture.resolve(strict=True)
        bases = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
        if (
            not root.is_dir()
            or not root.name.startswith("vadgr-cua-")
            or not any(root != base and root.is_relative_to(base) for base in bases)
            or not fixture.is_file()
            or not fixture.is_relative_to(root)
            or fixture.stat().st_size > 1_000_000
        ):
            raise ObserverError("invalid_fixture")
        value = fixture.read_bytes()
    except OSError:
        raise ObserverError("invalid_fixture") from None
    if not value or not value.isascii():
        raise ObserverError("ascii_fixture_required")
    if units is not None:
        if type(units) is not int or not 0 < units <= len(value):
            raise ObserverError("invalid_units")
        value = value[:units]
    return value


def inspect_process(pid):
    try:
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "pid=,uid=,lstart=,comm="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        fields = result.stdout.strip().split(None, 7)
        if (
            result.returncode
            or len(fields) != 8
            or int(fields[0]) != pid
            or int(fields[1]) != os.getuid()
            or fields[7] != "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit"
        ):
            raise ObserverError("textedit_process_unavailable")
        return tuple(fields)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ObserverError("textedit_process_unavailable") from None


def read_document(window_id):
    if type(window_id) is not int or window_id <= 0:
        raise ObserverError("invalid_identity")
    script = (
        'if application id "com.apple.TextEdit" is not running then error number -600\n'
        'tell application id "com.apple.TextEdit"\n'
        f"return text of document of window id {window_id}\n"
        "end tell"
    )
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        raise ObserverError("document_unavailable") from None
    if result.returncode or not result.stdout.endswith(b"\n"):
        raise ObserverError("document_unavailable")
    # Remove only osascript's output terminator, never the document's newline.
    return result.stdout[:-1]


def modifier_flags(quartz=None):
    try:
        quartz = quartz or importlib.import_module("Quartz")
        flags = quartz.CGEventSourceFlagsState(quartz.kCGEventSourceStateCombinedSessionState)
        return {
            "shift": bool(flags & quartz.kCGEventFlagMaskShift),
            "control": bool(flags & quartz.kCGEventFlagMaskControl),
            "option": bool(flags & quartz.kCGEventFlagMaskAlternate),
            "command": bool(flags & quartz.kCGEventFlagMaskCommand),
        }
    except Exception:
        raise ObserverError("modifier_observation_unavailable") from None


def metadata(actual, expected, pid, window_id, modifiers):
    try:
        count = len(actual.decode("utf-8"))
    except UnicodeDecodeError:
        raise ObserverError("document_encoding_unavailable") from None
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic": time.monotonic(),
        "pid": pid,
        "window_id": window_id,
        "count": count,
        "sha256": hashlib.sha256(actual).hexdigest(),
        "input_length": len(expected),
        "full_match": actual == expected,
        "strict_prefix": 0 < len(actual) < len(expected) and expected.startswith(actual),
        "modifier_flags": modifiers,
        "read_only": True,
    }


def observe(root, pid, window_id, fixture, units, wait_seconds):
    if sys.platform != "darwin":
        raise ObserverError("macos_required")
    if type(pid) is not int or pid <= 1 or type(window_id) is not int or window_id <= 0:
        raise ObserverError("invalid_identity")
    seconds = validate_wait(wait_seconds)
    expected = read_fixture(root, fixture, units)
    identity = inspect_process(pid)
    deadline = time.monotonic() + seconds
    while True:
        actual = read_document(window_id)
        if inspect_process(pid) != identity:
            raise ObserverError("process_identity_changed")
        result = metadata(actual, expected, pid, window_id, modifier_flags())
        if result["count"] or time.monotonic() >= deadline:
            return result
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        if inspect_process(pid) != identity:
            raise ObserverError("process_identity_changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--window-id", type=int, required=True)
    parser.add_argument("--fixture-file", type=Path, required=True)
    parser.add_argument("--units", type=int)
    parser.add_argument("--wait-for-prefix-seconds", type=float, default=0)
    args = parser.parse_args()
    try:
        result = observe(
            args.root,
            args.pid,
            args.window_id,
            args.fixture_file,
            args.units,
            args.wait_for_prefix_seconds,
        )
    except ObserverError as exc:
        print(json.dumps({"error": str(exc), "read_only": True}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
