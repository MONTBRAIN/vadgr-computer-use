# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Windows owner-and-SYSTEM ACL helper for broker secrets and locks."""

from __future__ import annotations

import ctypes
import os
import sys
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path


@contextmanager
def _security():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    pointer = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    api.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    api.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, pointer, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD)]
    api.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(pointer), pointer,
    ]
    api.GetSecurityDescriptorDacl.argtypes = [pointer, ctypes.POINTER(wintypes.BOOL),
                                             ctypes.POINTER(pointer), ctypes.POINTER(wintypes.BOOL)]
    api.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
                                        pointer, pointer, pointer, pointer]
    api.SetNamedSecurityInfoW.restype = wintypes.DWORD
    api.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD,
                                        pointer, pointer, pointer, pointer, ctypes.POINTER(pointer)]
    api.GetNamedSecurityInfoW.restype = wintypes.DWORD
    token = wintypes.HANDLE()
    sid_text, descriptor = pointer(), pointer()
    try:
        if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = wintypes.DWORD()
        api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        user = ctypes.create_string_buffer(size.value)
        if not api.GetTokenInformation(token, 1, user, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(user, ctypes.POINTER(pointer))[0]
        if not api.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise ctypes.WinError(ctypes.get_last_error())
        owner = ctypes.wstring_at(sid_text)
        # The current process token, not caller environment text, identifies the owner.
        sddl = f"O:{owner}D:P(A;OICI;FA;;;{owner})(A;OICI;FA;;;SY)"
        if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        yield kernel, api, descriptor, owner
    finally:
        if token:
            kernel.CloseHandle(token)
        for allocation in (sid_text, descriptor):
            if allocation:
                kernel.LocalFree(allocation)


def _verify(api, kernel, descriptor, owner: str) -> None:
    _verify_owner(api, kernel, descriptor, owner)
    pointer = ctypes.c_void_p
    api.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wintypes.WORD),
                                                ctypes.POINTER(wintypes.DWORD)]
    api.GetAclInformation.argtypes = [pointer, pointer, wintypes.DWORD, ctypes.c_int]
    api.GetAce.argtypes = [pointer, wintypes.DWORD, ctypes.POINTER(pointer)]
    control, revision = wintypes.WORD(), wintypes.DWORD()
    present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), pointer()
    if not api.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
        raise OSError("cannot verify broker ACL protection")
    if not control.value & 0x1000:
        raise OSError("broker ACL inheritance is not protected")
    if not api.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl),
                                          ctypes.byref(defaulted)) or not present.value or not dacl:
        raise OSError("broker ACL is missing")

    class AclSize(ctypes.Structure):
        _fields_ = [("count", wintypes.DWORD), ("used", wintypes.DWORD), ("free", wintypes.DWORD)]

    class Ace(ctypes.Structure):
        _fields_ = [("kind", wintypes.BYTE), ("flags", wintypes.BYTE), ("size", wintypes.WORD),
                    ("mask", wintypes.DWORD), ("sid", wintypes.DWORD)]

    info = AclSize()
    if not api.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2) or info.count != 2:
        raise OSError("broker ACL has unexpected entries")
    trustees = set()
    for index in range(info.count):
        entry, sid_text = pointer(), pointer()
        if not api.GetAce(dacl, index, ctypes.byref(entry)):
            raise OSError("cannot read broker ACL entry")
        ace = ctypes.cast(entry, ctypes.POINTER(Ace)).contents
        if ace.kind != 0 or ace.mask != 0x1F01FF or ace.flags & ~3:
            raise OSError("broker ACL has unexpected rights")
        if not api.ConvertSidToStringSidW(entry.value + Ace.sid.offset, ctypes.byref(sid_text)):
            raise OSError("cannot read broker ACL trustee")
        try:
            trustees.add(ctypes.wstring_at(sid_text))
        finally:
            kernel.LocalFree(sid_text)
    if trustees != {owner, "S-1-5-18"}:
        raise OSError("broker ACL has unexpected trustees")


def _verify_owner(api, kernel, descriptor, owner: str) -> None:
    pointer = ctypes.c_void_p
    api.GetSecurityDescriptorOwner.argtypes = [pointer, ctypes.POINTER(pointer),
                                              ctypes.POINTER(wintypes.BOOL)]
    sid, text, defaulted = pointer(), pointer(), wintypes.BOOL()
    if not api.GetSecurityDescriptorOwner(descriptor, ctypes.byref(sid), ctypes.byref(defaulted)):
        raise OSError("cannot verify broker storage owner")
    if not sid or not api.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise OSError("cannot identify broker storage owner")
    try:
        if ctypes.wstring_at(text) != owner:
            raise PermissionError("broker storage must belong to the current user")
    finally:
        kernel.LocalFree(text)


def verify_owner(path: Path) -> None:
    with _security() as (kernel, api, _descriptor, owner):
        observed = ctypes.c_void_p()
        try:
            result = api.GetNamedSecurityInfoW(str(path), 1, 1, None, None, None, None,
                                               ctypes.byref(observed))
            if result:
                raise ctypes.WinError(result)
            _verify_owner(api, kernel, observed, owner)
        finally:
            if observed:
                kernel.LocalFree(observed)


def current_user_home() -> Path:
    """Resolve the real user profile without trusting USERPROFILE."""
    with _security() as (kernel, api, _descriptor, _owner):
        userenv = ctypes.WinDLL("userenv", use_last_error=True)
        userenv.GetUserProfileDirectoryW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
        token = wintypes.HANDLE()
        try:
            if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
                raise ctypes.WinError(ctypes.get_last_error())
            size = wintypes.DWORD()
            userenv.GetUserProfileDirectoryW(token, None, ctypes.byref(size))
            buffer = ctypes.create_unicode_buffer(size.value)
            if not userenv.GetUserProfileDirectoryW(token, buffer, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            return Path(buffer.value)
        finally:
            if token:
                kernel.CloseHandle(token)


def protect_owner_and_system(path: Path) -> None:
    if sys.platform != "win32":
        return
    verify_owner(path)
    with _security() as (kernel, api, descriptor, owner):
        present, defaulted = wintypes.BOOL(), wintypes.BOOL()
        dacl, observed = ctypes.c_void_p(), ctypes.c_void_p()
        if not api.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl),
                                              ctypes.byref(defaulted)):
            raise OSError("cannot prepare broker ACL")
        result = api.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, dacl, None)
        if result:
            raise ctypes.WinError(result)
        try:
            result = api.GetNamedSecurityInfoW(str(path), 1, 5, None, None, None, None,
                                               ctypes.byref(observed))
            if result:
                raise ctypes.WinError(result)
            _verify(api, kernel, observed, owner)
        finally:
            if observed:
                kernel.LocalFree(observed)


def create_private_directory(path: Path) -> None:
    with _security() as (kernel, _api, descriptor, _owner):
        class Attributes(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p),
                        ("inherit", wintypes.BOOL)]

        kernel.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(Attributes)]
        attributes = Attributes(ctypes.sizeof(Attributes), descriptor, False)
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            error = ctypes.get_last_error()
            if error == 183:
                raise FileExistsError("broker directory exists")
            raise ctypes.WinError(error)


def create_private_file(path: Path, *, read_write: bool = False) -> int:
    import msvcrt

    with _security() as (kernel, _api, descriptor, _owner):
        class Attributes(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p),
                        ("inherit", wintypes.BOOL)]

        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.POINTER(Attributes), wintypes.DWORD,
                                      wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        attributes = Attributes(ctypes.sizeof(Attributes), descriptor, False)
        access = 0x40000000 | (0x80000000 if read_write else 0)
        # A held lock must not become delete-pending when a contender exits.
        share = 3 if read_write else 7
        handle = kernel.CreateFileW(str(path), access, share, ctypes.byref(attributes), 1, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            error = ctypes.get_last_error()
            if error in (80, 183):
                raise FileExistsError("broker file already exists")
            raise ctypes.WinError(error)
        try:
            return msvcrt.open_osfhandle(handle, os.O_RDWR if read_write else os.O_WRONLY)
        except BaseException:
            kernel.CloseHandle(handle)
            path.unlink()
            raise
