# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Registration faults start with three manifests in a private temporary root."""

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/registration_fault_linux.py"
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux isolated manifests")


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("registration_fault_linux", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture(helper):
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-registration-test-", dir="/tmp") as name:
        root = Path(name)
        originals = [b'{"fixture": "one"}\r\n', b'\x00\xff\n', b'']
        for path, data in zip(helper.manifests(root), originals):
            path.parent.mkdir(parents=True)
            path.write_bytes(data)
        yield root, originals


@pytest.mark.parametrize("ending", ["done", "timeout", "error", "interrupt"])
def test_exact_restore(helper, fixture, monkeypatch, capsys, ending):
    root, originals = fixture
    paths = helper.manifests(root)
    modes = [stat.S_IMODE(p.stat().st_mode) for p in paths]
    backup, ready, done = [root / name for name in ("backup", "ready", "done")]

    def wait(seconds):
        assert not any(p.exists() for p in paths)
        assert json.loads(ready.read_text())["ready"] is True
        assert stat.S_IMODE(backup.stat().st_mode) == 0o700
        for index, data in enumerate(originals):
            saved = backup / f"manifest-{index}.bak"
            assert saved.read_bytes() == data
            assert stat.S_IMODE(saved.stat().st_mode) == 0o600
        if ending == "done":
            done.touch()
        elif ending == "error":
            raise OSError("private path must not enter CLI output")
        elif ending == "interrupt":
            raise KeyboardInterrupt

    monkeypatch.setattr(helper.time, "sleep", wait)
    if ending in ("error", "interrupt", "timeout"):
        error = {"error": OSError, "interrupt": KeyboardInterrupt, "timeout": TimeoutError}[ending]
        with pytest.raises(error):
            helper.fault(root, backup, ready, done, .01)
    else:
        helper.fault(root, backup, ready, done, 1)
    assert [p.read_bytes() for p in paths] == originals
    assert [stat.S_IMODE(p.stat().st_mode) for p in paths] == modes
    output = capsys.readouterr().out
    assert str(root) not in output
    assert json.loads(output.splitlines()[-1])["restored"] is True


@pytest.mark.parametrize("seconds", [0, -1, 181, float("inf"), float("nan"), True])
def test_invalid_bound(helper, fixture, seconds):
    root, originals = fixture
    with pytest.raises(ValueError):
        helper.fault(root, root / "backup", root / "ready", root / "done", seconds)
    assert [p.read_bytes() for p in helper.manifests(root)] == originals


@pytest.mark.parametrize("invalid", ["missing", "symlink", "parent_link", "collision", "same", "outside", "hardlink", "root_name"])
def test_fail_closed(helper, fixture, invalid):
    root, originals = fixture
    backup, ready, done = [root / name for name in ("backup", "ready", "done")]
    paths = helper.manifests(root)
    if invalid == "missing":
        paths[2].unlink()
    elif invalid == "symlink":
        paths[2].unlink()
        paths[2].symlink_to(paths[0])
    elif invalid == "parent_link":
        parent = paths[2].parent
        parent.rename(parent.with_name("saved"))
        parent.symlink_to(parent.with_name("saved"), target_is_directory=True)
    elif invalid == "collision":
        done.touch()
    elif invalid == "same":
        done = ready
    elif invalid == "outside":
        backup = root.parent / "outside"
    elif invalid == "hardlink":
        (root / "link").hardlink_to(paths[0])
    else:
        root = root / "home"
    with pytest.raises(ValueError):
        helper.fault(root, backup, ready, done, 1)
    assert paths[0].read_bytes() == originals[0]
    assert paths[1].read_bytes() == originals[1]
    assert not backup.exists()
    assert not ready.exists()


def test_partial_removal_error_restores(helper, fixture, monkeypatch):
    root, originals = fixture
    paths = helper.manifests(root)
    unlink = Path.unlink

    def fail_second(path, *args, **kwargs):
        if path == paths[1]:
            raise OSError("fixture removal failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_second)
    with pytest.raises(OSError):
        helper.fault(root, root / "backup", root / "ready", root / "done", 1)
    assert [p.read_bytes() for p in paths] == originals
    assert not (root / "ready").exists()


def test_backup_failure_precedes_removal(helper, fixture, monkeypatch):
    root, originals = fixture

    def denied(*args):
        raise OSError("private backup failure")

    monkeypatch.setattr(helper, "write_new", denied)
    with pytest.raises(OSError):
        helper.fault(root, root / "backup", root / "ready", root / "done", 1)
    assert [p.read_bytes() for p in helper.manifests(root)] == originals
    assert not (root / "ready").exists()


def test_cli_timeout_restores_without_private_output(helper, fixture):
    root, originals = fixture
    result = subprocess.run(
        [sys.executable, str(HELPER), "--root", str(root),
         "--backup", str(root / "backup"), "--ready", str(root / "ready"),
         "--done", str(root / "done"), "--seconds", "0.01"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert not result.stderr
    assert str(root) not in result.stdout
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[0]["ready"] is True
    assert rows[1]["restored"] is True
    assert rows[1]["hashes_verified"] is True
    assert rows[2]["failed"] is True
    assert [p.read_bytes() for p in helper.manifests(root)] == originals


def test_cli_error_does_not_print_exception(helper, fixture, monkeypatch, capsys):
    root, _ = fixture

    def denied(*args):
        raise OSError("sensitive fixture path and contents")

    monkeypatch.setattr(helper, "fault", denied)
    assert helper.main(["--root", str(root), "--backup", str(root / "backup"),
                        "--ready", str(root / "ready"), "--done", str(root / "done")]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] is True
