"""Native ACL tests use only fresh temporary directories and synthetic payloads."""

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from computer_use.browser import private_file, windows_acl

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL APIs")


def verify(path):
    with windows_acl._security() as (kernel, api, _descriptor, owner):
        observed = ctypes.c_void_p()
        try:
            assert api.GetNamedSecurityInfoW(str(path), 1, 5, None, None, None, None,
                                             ctypes.byref(observed)) == 0
            windows_acl._verify(api, kernel, observed, owner)
        finally:
            if observed:
                kernel.LocalFree(observed)


@pytest.mark.parametrize("filename", ["browser-broker.json", "browser.port"])
def test_native_private_acl_before_first_byte_and_after_replace(tmp_path, monkeypatch, filename):
    endpoint = tmp_path / "state" / filename
    environment = dict(os.environ)
    original = json.dump
    writes = []

    def inspect(value, stream, *args, **kwargs):
        verify(endpoint.parent)
        temporary = next(endpoint.parent.glob(".*.tmp"))
        assert temporary.stat().st_size == 0
        verify(temporary)
        writes.append(True)
        return original(value, stream, *args, **kwargs)

    monkeypatch.setattr(json, "dump", inspect)
    for generation in (1, 2):
        private_file.write_private(endpoint, {"generation": generation})
        verify(endpoint)
        assert json.loads(endpoint.read_text()) == {"generation": generation}
    assert writes == [True, True]
    assert dict(os.environ) == environment


def test_native_acl_failure_retains_original_without_temporary(tmp_path, monkeypatch):
    endpoint = tmp_path / "state" / "browser-broker.json"
    private_file.write_private(endpoint, {"generation": 1})
    original = windows_acl.protect_owner_and_system

    def refuse(path):
        if path.suffix == ".tmp":
            assert path.stat().st_size == 0
            raise PermissionError("fixture ACL refusal")
        return original(path)

    monkeypatch.setattr(windows_acl, "protect_owner_and_system", refuse)
    with pytest.raises(PermissionError):
        private_file.write_private(endpoint, {"generation": 2})
    assert json.loads(endpoint.read_text()) == {"generation": 1}
    assert list(endpoint.parent.iterdir()) == [endpoint]
    verify(endpoint)


def test_native_linked_lock_is_refused_without_target_mutation(tmp_path):
    target = tmp_path / "original"
    target.write_text("unchanged")
    linked = tmp_path / "browser-broker.lock"
    os.link(target, linked)
    with pytest.raises(PermissionError):
        private_file.open_private_lock(linked)
    assert target.read_text() == "unchanged"
    assert linked.read_text() == "unchanged"


def test_native_foreign_owner_descriptor_is_refused_without_changing_files():
    with windows_acl._security() as (kernel, api, _descriptor, owner):
        if owner == "S-1-5-18":
            pytest.skip("the fixture requires a non-SYSTEM current user")
        foreign = ctypes.c_void_p()
        try:
            assert api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:SYD:P(A;;FA;;;{owner})(A;;FA;;;SY)", 1, ctypes.byref(foreign), None,
            )
            with pytest.raises(PermissionError):
                windows_acl._verify(api, kernel, foreign, owner)
        finally:
            if foreign:
                kernel.LocalFree(foreign)


def test_native_foreign_owner_refusal_precedes_permission_mutation(tmp_path, monkeypatch):
    target = tmp_path / "original"
    target.write_text("unchanged")

    def refuse(path):
        raise PermissionError("synthetic foreign owner")

    monkeypatch.setattr(windows_acl, "verify_owner", refuse)
    monkeypatch.setattr(windows_acl, "_security", lambda: pytest.fail("must not mutate permissions"))
    with pytest.raises(PermissionError):
        windows_acl.protect_owner_and_system(target)
    assert target.read_text() == "unchanged"


def test_native_lock_survives_two_losing_contenders(tmp_path):
    import msvcrt

    lock = tmp_path / "broker" / "browser-broker.lock"
    private_file.private_directory(lock.parent)
    descriptor = private_file.open_private_lock(lock)
    os.write(descriptor, b"0")
    os.lseek(descriptor, 0, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    inode = lock.stat().st_ino
    source = """
import json, os, msvcrt, sys
from pathlib import Path
from computer_use.browser.private_file import open_private_lock
path = Path(sys.argv[1])
fd = open_private_lock(path)
acquired = False
try:
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    acquired = True
except OSError:
    pass
finally:
    os.close(fd)
try:
    path.unlink()
    removed = True
except PermissionError:
    removed = False
print(json.dumps({'acquired': acquired, 'removed': removed}))
"""
    try:
        for _ in range(2):
            result = subprocess.run([sys.executable, "-c", source, str(lock)],
                                    cwd=Path(__file__).resolve().parents[2],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == {"acquired": False, "removed": False}
            assert lock.stat().st_ino == inode
    finally:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)


def test_native_real_home_refused_when_userprofile_is_redirected(tmp_path, monkeypatch):
    actual = windows_acl.current_user_home()
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "isolated-home"))
    monkeypatch.setattr(windows_acl, "create_private_directory",
                        lambda path: pytest.fail("home guard must precede every mutation"))
    with pytest.raises(PermissionError):
        private_file.private_directory(actual / ".." / actual.name)
