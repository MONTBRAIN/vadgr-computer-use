# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Each case owns a fresh private root, FIFO and event log; no broker is used."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/control_broker_fault.py"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO setup helper")


@pytest.fixture
def control():
    spec = importlib.util.spec_from_file_location("control_broker_fault", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated():
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-control-test-", dir="/tmp") as name:
        root = Path(name)
        fifo = root / "control"
        os.mkfifo(fifo, 0o600)
        events = root / "events.jsonl"
        events.write_text('{"event":"old"}\n')
        yield root, fifo, events


def event(kind, stamp, **extra):
    return {"event": kind, "monotonic": stamp, "utc": "2026-09-09T12:00:00+00:00", **extra}


def run_fixture(control, isolated, rows, *, partial=False, change=None):
    root, fifo, events = isolated
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    received = []

    def writer():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            data = os.read(reader, 4096)
            if data:
                received.append(json.loads(data))
                break
            time.sleep(0.005)
        if change:
            change(events)
        with events.open("ab", buffering=0) as log:
            for row in rows:
                data = (json.dumps(row) + "\n").encode()
                if partial:
                    for part in (data[:11], data[11:-1], data[-1:]):
                        log.write(part)
                        time.sleep(0.02)
                else:
                    log.write(data)

    worker = threading.Thread(target=writer)
    worker.start()
    try:
        return control.run(root, fifo, events, 8, 9), received
    finally:
        worker.join(timeout=3)
        os.close(reader)


@pytest.mark.parametrize("partial", [False, True])
def test_new_cut_and_restoration(control, isolated, capsys, partial):
    rows = [event("cut", 100, seconds=8, connection_count=1),
            event("connection_refused", 101), event("restored", 108.1)]
    result, received = run_fixture(control, isolated, rows, partial=partial)
    assert result is None
    assert received == [{"cut_seconds": 8}]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[:2] == [rows[0], rows[2]]
    assert output[2]["restored_minus_cut_seconds"] == pytest.approx(8.1)
    assert output[2]["elapsed_seconds"] >= 0


@pytest.mark.parametrize("rows", [
    [event("cut", 100, seconds=46, connection_count=1)],
    [event("restored", 108)],
    [event("cut", 100, seconds=8, connection_count=1)] * 2,
    [event("cut", 100, seconds=True, connection_count=1)],
    [event("cut", 100, seconds=8, connection_count=-1)],
    [{"event": "cut"}], [], [None],
    [event("cut", float("nan"), seconds=8, connection_count=1)],
    [event("stopped", 100)],
    [event("connection_refused", 100, utc="invalid")],
    [event("cut", 100, seconds=8, connection_count=1), event("restored", 99)],
])
def test_mismatched_or_missing_events(control, isolated, rows, monkeypatch):
    real_monotonic = time.monotonic
    start = real_monotonic()
    monkeypatch.setattr(control.time, "monotonic", lambda: start + (real_monotonic() - start) * 100)
    with pytest.raises((ValueError, TimeoutError)):
        run_fixture(control, isolated, rows)


@pytest.mark.parametrize("change", ["replace", "truncate"])
def test_log_changes_fail(control, isolated, change):
    def mutate(path):
        if change == "replace":
            path.rename(path.with_suffix(".old"))
        path.write_text("")
    with pytest.raises(ValueError, match="replaced|truncated"):
        run_fixture(control, isolated, [], change=mutate)


@pytest.mark.parametrize("unsafe", ["root_mode", "missing", "symlink", "hardlink", "regular_control", "outside", "parent_symlink", "owner"])
def test_unsafe_paths(control, isolated, unsafe, monkeypatch):
    root, fifo, events = isolated
    if unsafe == "root_mode":
        root.chmod(0o755)
    elif unsafe == "missing":
        events.unlink()
    elif unsafe == "symlink":
        alias = root / "alias"
        alias.symlink_to(events)
        events = alias
    elif unsafe == "hardlink":
        os.link(events, root / "link")
    elif unsafe == "regular_control":
        fifo.unlink()
        fifo.write_text("")
    elif unsafe == "outside":
        events = root.parent / "outside"
    elif unsafe == "parent_symlink":
        (root / "alias").symlink_to(root, target_is_directory=True)
        events = root / "alias" / events.name
    else:
        monkeypatch.setattr(control.os, "getuid", lambda: os.stat(root).st_uid + 1)
    with pytest.raises((ValueError, OSError)):
        control.run(root, fifo, events, 8, 9)


def test_no_fifo_reader_fails_immediately(control, isolated):
    with pytest.raises(OSError):
        control.run(*isolated, 8, 9)


@pytest.mark.parametrize("seconds,timeout", [(7, 9), (8, 8), (46, 61), (8, float("nan")), (True, 9)])
def test_invalid_bounds(control, isolated, seconds, timeout):
    with pytest.raises(ValueError):
        control.run(*isolated, seconds, timeout)


def test_cli_failure_has_nonzero_status_without_file_contents(isolated):
    root, fifo, events = isolated
    result = subprocess.run(
        [sys.executable, str(HELPER), "--root", str(root), "--control", str(fifo),
         "--events", str(events), "--seconds", "8", "--timeout", "20"],
        capture_output=True, text=True, timeout=3,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "relay control failed; inspect the isolated relay log\n"
