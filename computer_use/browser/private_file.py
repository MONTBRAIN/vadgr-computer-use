# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Publish broker credentials only after their storage is private."""

from __future__ import annotations

import json
import os
import secrets
import stat
import sys
from pathlib import Path


def _ordinary(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise PermissionError("broker storage must not use links or special files")
    if not directory and info.st_nlink != 1:
        raise PermissionError("broker storage must not use hard links")
    if sys.platform != "win32" and info.st_uid != os.getuid():
        raise PermissionError("broker storage must belong to the current user")
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import verify_owner

        verify_owner(path)
    return info


def private_directory(path: Path) -> None:
    """Protect the application directory, never an existing ancestor or home."""
    path = path.absolute()
    canonical = path.resolve()
    homes = {Path.home().resolve()}
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import current_user_home

        homes.add(current_user_home().resolve())
    else:
        import pwd

        homes.add(Path(pwd.getpwuid(os.getuid()).pw_dir).resolve())
    if canonical in homes or canonical == Path(canonical.anchor):
        raise PermissionError("broker storage requires a dedicated directory")
    for ancestor in [path, *path.parents]:
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if getattr(info, "st_file_attributes", 0) & 0x400:
            raise PermissionError("broker storage must not use directory links")
        if stat.S_ISLNK(info.st_mode):
            # macOS supplies root-owned /tmp and /var aliases. User-controlled
            # aliases are never allowed to redirect permission changes.
            if ancestor == path or sys.platform == "win32" or info.st_uid != 0:
                raise PermissionError("broker storage must not use directory links")
    if not path.parent.exists():
        private_directory(path.parent)
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import (
            create_private_directory,
            protect_owner_and_system,
        )

        try:
            create_private_directory(path)
        except FileExistsError:
            _ordinary(path, directory=True)
        protect_owner_and_system(path)
        return
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    before = _ordinary(path, directory=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
            raise PermissionError("broker storage changed during protection")
        os.fchmod(descriptor, 0o700)
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
            raise PermissionError("broker directory protection failed")
    finally:
        os.close(descriptor)


def write_private(path: Path, value: dict[str, object]) -> None:
    private_directory(path.parent)
    try:
        _ordinary(path)
    except FileNotFoundError:
        pass
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
    if sys.platform == "win32":
        from computer_use.browser.windows_acl import create_private_file

        descriptor = create_private_file(temporary)
    else:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        if sys.platform == "win32":
            from computer_use.browser.windows_acl import protect_owner_and_system

            # Empty files inherit a private parent. Verify the exact file DACL
            # before serializing a credential, including replacement generations.
            protect_owner_and_system(temporary)
        else:
            os.fchmod(descriptor, 0o600)
            info = os.fstat(descriptor)
            if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
                raise PermissionError("broker file protection failed")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            _ordinary(path)
        except FileNotFoundError:
            pass
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def open_private_lock(path: Path) -> int:
    """Open only an ordinary same-owner lock inside the protected directory."""
    try:
        before = _ordinary(path)
    except FileNotFoundError:
        before = None
    if before is None and sys.platform == "win32":
        from computer_use.browser.windows_acl import create_private_file

        try:
            descriptor = create_private_file(path, read_write=True)
        except FileExistsError:
            before = _ordinary(path)
            descriptor = os.open(path, os.O_RDWR)
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        opened = os.fstat(descriptor)
        after = _ordinary(path)
        identity = opened.st_dev, opened.st_ino
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PermissionError("broker lock must be an ordinary unlinked file")
        if identity != (after.st_dev, after.st_ino) or (
            before is not None and identity != (before.st_dev, before.st_ino)
        ):
            raise PermissionError("broker lock changed during opening")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise
