# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Request a Windows relay cut and return only after its actual restoration."""

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path


def coordinator():
    spec = importlib.util.spec_from_file_location(
        "windows_b09_coordinator", Path(__file__).with_name("coordinate_broker_fault_windows.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_state(path):
    if path.is_symlink() or path.stat().st_nlink != 1:
        raise ValueError("state must be a regular single-link file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("state must be an object")
    return value


def restoration(state, sequence, seconds, started):
    if type(state.get("sequence")) is not int or state["sequence"] not in (sequence - 1, sequence):
        raise ValueError("unexpected relay sequence")
    if state.get("event") in ("stopped", "relay_eof"):
        raise ValueError("relay stopped before restoration")
    if state["sequence"] != sequence or "restored" not in state:
        return None
    cut, restored = state.get("cut"), state["restored"]
    if not isinstance(cut, dict) or not isinstance(restored, dict):
        raise ValueError("missing actual relay events")
    for event, expected in ((cut, "cut"), (restored, "restored")):
        if event.get("event") != expected:
            raise ValueError("unexpected relay event")
        stamp = event.get("monotonic")
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < started:
            raise ValueError("stale or invalid relay timestamp")
    if (type(cut.get("seconds")) not in (int, float) or cut["seconds"] != seconds
            or type(cut.get("connection_count")) is not int or cut["connection_count"] < 1
            or restored["monotonic"] < cut["monotonic"]):
        raise ValueError("cut does not match the requested connected fault")
    # Output is rebuilt from numeric metadata, never copied from a control file.
    return {"event": "control_complete", "sequence": sequence, "seconds": seconds,
            "cut_monotonic": cut["monotonic"], "restored_monotonic": restored["monotonic"],
            "connection_count": cut["connection_count"],
            "restored_minus_cut_seconds": restored["monotonic"] - cut["monotonic"]}


def run(root, sequence, seconds, timeout=58):
    if sys.platform != "win32":
        raise ValueError("native Windows required")
    if (type(sequence) is not int or type(seconds) is not int
            or {1: 8, 2: 46}.get(sequence) != seconds):
        raise ValueError("use sequence 1 with 8 seconds or sequence 2 with 46 seconds")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not seconds < timeout <= 60):
        raise ValueError("timeout must exceed the duration and be at most 60 seconds")
    helper = coordinator()
    root = helper.checked_root(root)
    state_path = root / "b09-state.json"
    state = read_state(state_path)
    if (type(state.get("sequence")) is not int or state["sequence"] != sequence - 1
            or state.get("event") not in ("ready", "restored")
            or type(state.get("connections_opened")) is not int or state["connections_opened"] < 1):
        raise ValueError("relay is not ready for this sequence")
    request_path = root / "b09-request.json"
    if request_path.exists() and (request_path.is_symlink() or request_path.stat().st_nlink != 1):
        raise ValueError("request must be a single-link file")
    # Exclusive retained markers prevent duplicate controllers for one sequence.
    with (root / f"b09-control-{sequence}.lock").open("x", encoding="utf-8") as marker:
        json.dump({"pid": os.getpid(), "sequence": sequence}, marker)
    started = time.monotonic()
    helper.write_json(request_path, {"sequence": sequence, "cut_seconds": seconds})
    while time.monotonic() - started < timeout:
        state = read_state(state_path)
        completed = restoration(state, sequence, seconds, started)
        if completed is not None:
            completed["elapsed_seconds"] = time.monotonic() - started
            print(json.dumps(completed), flush=True)
            return completed
        if (root / "b09-result.json").exists():
            raise ValueError("coordinator ended before restoration")
        time.sleep(0.02)
    raise TimeoutError("relay restoration was not observed within the bound")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sequence", required=True, type=int, choices=(1, 2))
    parser.add_argument("--seconds", required=True, type=int, choices=(8, 46))
    parser.add_argument("--timeout", type=float, default=58)
    args = parser.parse_args()
    try:
        run(args.root, args.sequence, args.seconds, args.timeout)
    except (OSError, ValueError, TimeoutError):
        print("relay control failed; inspect the isolated relay log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
