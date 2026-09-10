"""Receipt-time sidecars preserve the captured CLI stream and its redaction."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/redact_stream.py"


def run_capture(output, stream, timing=None):
    command = [sys.executable, str(SCRIPT), "--output", str(output)]
    if timing is not None:
        command.extend(["--timing-output", str(timing)])
    return subprocess.run(command, input=stream, text=True, capture_output=True, timeout=10)


def test_sidecar_binds_redacted_lines_without_changing_them(tmp_path):
    stream = '\n'.join([
        'not JSON',
        json.dumps({"type": "item.started", "token": "private-fixture"}),
        json.dumps({"type": "item.completed", "result": {"count": 1}}),
    ]) + '\n'
    plain = tmp_path / "plain.jsonl"
    timed = tmp_path / "timed.jsonl"
    sidecar = tmp_path / "timing.jsonl"
    assert run_capture(plain, stream).returncode == 0
    assert run_capture(timed, stream, sidecar).returncode == 0
    assert plain.read_bytes() == timed.read_bytes()
    assert b"private-fixture" not in timed.read_bytes() + sidecar.read_bytes()
    records = timed.read_bytes().splitlines(keepends=True)
    stamps = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert len(stamps) == len(records) == 2
    for index, (record, stamp) in enumerate(zip(records, stamps)):
        assert stamp["record_index"] == index
        assert stamp["record_sha256"] == hashlib.sha256(record).hexdigest()
        assert stamp["received_monotonic_ns"] > 0
        assert stamp["received_utc_ns"] > 0
    assert stamps[1]["received_monotonic_ns"] >= stamps[0]["received_monotonic_ns"]


def test_rejects_same_event_and_timing_path(tmp_path):
    output = tmp_path / "events.jsonl"
    result = run_capture(output, '{}\n', output)
    assert result.returncode != 0
    assert not output.exists()


def test_never_overwrites_existing_timing_file(tmp_path):
    sidecar = tmp_path / "timing.jsonl"
    sidecar.write_text("existing capture")
    output = tmp_path / "events.jsonl"
    result = run_capture(output, '{}\n', sidecar)
    assert result.returncode != 0
    assert sidecar.read_text() == "existing capture"
    assert not output.exists()


def test_never_overwrites_existing_event_file(tmp_path):
    output = tmp_path / "events.jsonl"
    output.write_text("existing capture")
    result = run_capture(output, '{}\n', tmp_path / "timing.jsonl")
    assert result.returncode != 0
    assert output.read_text() == "existing capture"
