"""Registry fault tests use only unique temporary HKCU test keys."""

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/registration_fault_windows.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("registration_fault_windows", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry_key():
    if sys.platform != "win32":
        pytest.skip("native Windows temporary registry fixture")
    import winreg

    subkey = "Software\\vadgr-cua-test-" + uuid.uuid4().hex
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
        winreg.SetValueEx(key, "preserve", 0, winreg.REG_SZ, "fixture sibling")
        yield winreg, subkey, key
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)


@pytest.mark.parametrize("kind,value", [
    (1, "fixture plain"), (2, "%FIXTURE_ENV%\\unexpanded"),
    (3, b"\x00\xff\x01"), (4, 4294967295), (7, ["one", "two"]),
    (11, 9223372036854775809), (0, b"\x01\x02"),
])
def test_exact_default_type_value_acl_and_other_values_survive(
    helper, registry_key, tmp_path, monkeypatch, kind, value,
):
    winreg, subkey, key = registry_key
    winreg.SetValueEx(key, "", 0, kind, value)
    original_acl = helper.acl_bytes(key)
    snapshot, ready, done = [tmp_path / name for name in ("snapshot", "ready", "done")]

    def during_fault(seconds):
        with pytest.raises(FileNotFoundError):
            winreg.QueryValueEx(key, "")
        assert snapshot.is_file()
        assert ready.is_file()
        assert helper.acl_bytes(key) == original_acl
        assert winreg.QueryValueEx(key, "preserve") == ("fixture sibling", winreg.REG_SZ)
        done.write_text("done")

    monkeypatch.setattr(helper.time, "sleep", during_fault)
    helper.fault(tmp_path, snapshot, ready, done, 1, subkeys=(subkey,))
    assert winreg.QueryValueEx(key, "") == (value, kind)
    assert helper.acl_bytes(key) == original_acl
    assert json.loads(snapshot.read_text())[0]["default"]["kind"] == kind


def test_absent_default_and_key_remain_absent(helper, registry_key, tmp_path, monkeypatch):
    winreg, subkey, key = registry_key
    missing = subkey + "\\missing"
    snapshot, ready, done = [tmp_path / name for name in ("snapshot", "ready", "done")]
    monkeypatch.setattr(helper.time, "sleep", lambda seconds: done.write_text("done"))
    helper.fault(tmp_path, snapshot, ready, done, 1, subkeys=(subkey, missing))
    with pytest.raises(FileNotFoundError):
        winreg.QueryValueEx(key, "")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, missing)
    assert json.loads(snapshot.read_text())[1]["exists"] is False


def test_timeout_restores_before_raising(helper, registry_key, tmp_path):
    winreg, subkey, key = registry_key
    winreg.SetValueEx(key, "", 0, winreg.REG_EXPAND_SZ, "%FIXTURE_ENV%")
    snapshot, ready, done = [tmp_path / name for name in ("snapshot", "ready", "done")]
    with pytest.raises(TimeoutError):
        helper.fault(tmp_path, snapshot, ready, done, .01, subkeys=(subkey,))
    assert winreg.QueryValueEx(key, "") == ("%FIXTURE_ENV%", winreg.REG_EXPAND_SZ)


def test_snapshot_security_failure_precedes_registry_mutation(
    helper, registry_key, tmp_path, monkeypatch,
):
    winreg, subkey, key = registry_key
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "fixture default")

    def denied(path):
        assert winreg.QueryValueEx(key, "") == ("fixture default", winreg.REG_SZ)
        raise PermissionError("fixture DACL failure")

    monkeypatch.setattr(helper, "private_file", denied)
    with pytest.raises(PermissionError):
        helper.fault(tmp_path, tmp_path / "snapshot", tmp_path / "ready", tmp_path / "done",
                     1, subkeys=(subkey,))
    assert winreg.QueryValueEx(key, "") == ("fixture default", winreg.REG_SZ)
    assert not (tmp_path / "ready").exists()


@pytest.mark.parametrize("seconds", [0, -1, 181, float("inf"), float("nan"), True])
def test_unbounded_fault_refused(helper, monkeypatch, tmp_path, seconds):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    with pytest.raises(ValueError, match="between 0 and 180"):
        helper.validate(tmp_path, tmp_path / "snapshot", tmp_path / "ready",
                        tmp_path / "done", seconds)


def test_non_windows_refused_before_registry_access(helper, monkeypatch, tmp_path):
    monkeypatch.setattr(helper.sys, "platform", "linux")
    with pytest.raises(ValueError, match="native Windows"):
        helper.validate(tmp_path, tmp_path / "snapshot", tmp_path / "ready", tmp_path / "done", 1)


def test_fault_signals_must_be_fresh_distinct_and_contained(helper, monkeypatch, tmp_path):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    root = tmp_path / "vadgr-cua-registration"
    root.mkdir()
    snapshot, ready, done = [root / name for name in ("snapshot", "ready", "done")]
    assert helper.validate(root, snapshot, ready, done, 180)[0] == root.resolve()
    with pytest.raises(ValueError):
        helper.validate(root, tmp_path / "outside", ready, done, 180)
    with pytest.raises(ValueError):
        helper.validate(root, snapshot, ready, ready, 180)
    done.touch()
    with pytest.raises(ValueError):
        helper.validate(root, snapshot, ready, done, 180)


def test_interrupted_wait_restores_the_default(helper, registry_key, tmp_path, monkeypatch):
    winreg, subkey, key = registry_key
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "fixture default")

    def interrupted(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(helper.time, "sleep", interrupted)
    with pytest.raises(KeyboardInterrupt):
        helper.fault(tmp_path, tmp_path / "snapshot", tmp_path / "ready", tmp_path / "done",
                     1, subkeys=(subkey,))
    assert winreg.QueryValueEx(key, "") == ("fixture default", winreg.REG_SZ)
