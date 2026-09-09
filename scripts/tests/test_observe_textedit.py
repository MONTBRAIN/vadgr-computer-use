"""The TextEdit observer reads only an exact owned document and emits metadata."""

import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "E2E/0.7.6/harness/observe_textedit.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("observe_textedit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root():
    with tempfile.TemporaryDirectory(prefix="vadgr-cua-observe-test-") as directory:
        yield Path(directory).resolve()


def test_non_macos_refuses_before_app_access(helper, monkeypatch, root):
    monkeypatch.setattr(helper.sys, "platform", "win32")
    probe = Mock()
    monkeypatch.setattr(helper, "inspect_process", probe)
    with pytest.raises(helper.ObserverError, match="macos_required"):
        helper.observe(root, 12, 34, root / "fixture", None, 0)
    probe.assert_not_called()


@pytest.mark.parametrize("value", [-1, 31, float("nan"), float("inf"), True])
def test_invalid_wait(helper, value):
    with pytest.raises(helper.ObserverError, match="invalid_wait"):
        helper.validate_wait(value)


def test_fixture_bounds_and_ascii(helper, root):
    source = root / "fixture.txt"
    source.write_bytes(b"abc\ndef\n")
    assert helper.read_fixture(root, source, 4) == b"abc\n"
    for units in [0, 100, True]:
        with pytest.raises(helper.ObserverError, match="invalid_units"):
            helper.read_fixture(root, source, units)
    with pytest.raises(helper.ObserverError, match="invalid_fixture"):
        helper.read_fixture(root / "nested", source, None)
    source.write_bytes(b"\xc3\xa9")
    with pytest.raises(helper.ObserverError, match="ascii_fixture_required"):
        helper.read_fixture(root, source, None)


def test_escaping_fixture_symlink_refused(helper, root):
    with tempfile.TemporaryDirectory() as other:
        outside = Path(other) / "outside"
        outside.write_bytes(b"fixture")
        link = root / "escape"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks unavailable")
        with pytest.raises(helper.ObserverError, match="invalid_fixture"):
            helper.read_fixture(root, link, None)


def test_exact_window_query_keeps_trailing_newline(helper, monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=b"abc\n\n"))
    monkeypatch.setattr(helper.subprocess, "run", run)
    assert helper.read_document(34) == b"abc\n"
    script = run.call_args.args[0][-1]
    assert "text of document of window id 34" in script
    assert "front document" not in script
    assert "activate" not in script
    run.return_value = SimpleNamespace(returncode=1, stdout=b"owner data")
    with pytest.raises(helper.ObserverError, match="document_unavailable"):
        helper.read_document(34)


def test_metadata_prefix_hash_and_modifiers(helper):
    quartz = SimpleNamespace(
        kCGEventSourceStateCombinedSessionState=0,
        kCGEventFlagMaskShift=2,
        kCGEventFlagMaskControl=4,
        kCGEventFlagMaskAlternate=8,
        kCGEventFlagMaskCommand=16,
        CGEventSourceFlagsState=lambda state: 10,
    )
    assert helper.modifier_flags(quartz) == {
        "shift": True,
        "control": False,
        "option": True,
        "command": False,
    }
    result = helper.metadata(b"abc", b"abcdef", 12, 34, {})
    assert result["count"] == 3
    assert result["sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert result["strict_prefix"] is True and result["full_match"] is False
    assert helper.metadata(b"abcdef", b"abcdef", 12, 34, {})["full_match"] is True
    assert helper.metadata(b"wrong", b"abcdef", 12, 34, {})["strict_prefix"] is False
    assert helper.metadata(b"", b"abcdef", 12, 34, {})["strict_prefix"] is False
    assert b"abc" not in str(result).encode()


def test_identity_change_refused_without_metadata(helper, monkeypatch, root):
    monkeypatch.setattr(helper.sys, "platform", "darwin")
    source = root / "fixture"
    source.write_bytes(b"abcdef")
    monkeypatch.setattr(helper, "inspect_process", Mock(side_effect=["start", "changed"]))
    monkeypatch.setattr(helper, "read_document", lambda window: b"abc")
    modifiers = Mock(return_value={})
    monkeypatch.setattr(helper, "modifier_flags", modifiers)
    with pytest.raises(helper.ObserverError, match="process_identity_changed"):
        helper.observe(root, 12, 34, source, None, 0)
    modifiers.assert_not_called()


def test_wait_observes_nonzero_prefix_without_signals(helper, monkeypatch, root):
    monkeypatch.setattr(helper.sys, "platform", "darwin")
    source = root / "fixture"
    source.write_bytes(b"abcdef")
    monkeypatch.setattr(helper, "inspect_process", lambda pid: "start")
    monkeypatch.setattr(helper, "read_document", Mock(side_effect=[b"", b"abc"]))
    monkeypatch.setattr(helper, "modifier_flags", dict)
    monkeypatch.setattr(helper.time, "sleep", lambda seconds: None)
    result = helper.observe(root, 12, 34, source, None, 1)
    assert result["strict_prefix"] is True
    assert result["read_only"] is True


def test_process_identity_requires_exact_owner_and_executable(helper, monkeypatch):
    monkeypatch.setattr(helper.os, "getuid", lambda: 42, raising=False)
    line = "12 42 Wed Sep 9 00:00:00 2026 /System/Applications/TextEdit.app/Contents/MacOS/TextEdit"
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=line))
    monkeypatch.setattr(helper.subprocess, "run", run)
    assert helper.inspect_process(12)[2:7] == ("Wed", "Sep", "9", "00:00:00", "2026")
    for invalid in [line.replace("12 42", "12 43"), line.replace("/System/", "/unrelated/")]:
        run.return_value = SimpleNamespace(returncode=0, stdout=invalid)
        with pytest.raises(helper.ObserverError, match="textedit_process_unavailable"):
            helper.inspect_process(12)


def test_empty_document_wait_expires_with_observation_not_verdict(helper, monkeypatch, root):
    monkeypatch.setattr(helper.sys, "platform", "darwin")
    source = root / "fixture"
    source.write_bytes(b"abcdef")
    monkeypatch.setattr(helper, "inspect_process", lambda pid: "start")
    monkeypatch.setattr(helper, "read_document", lambda window: b"")
    monkeypatch.setattr(helper, "modifier_flags", dict)
    clock = iter(range(100))
    monkeypatch.setattr(helper.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(helper.time, "sleep", lambda seconds: None)
    result = helper.observe(root, 12, 34, source, None, 1)
    assert result["count"] == 0 and result["strict_prefix"] is False
    assert "verdict" not in result
