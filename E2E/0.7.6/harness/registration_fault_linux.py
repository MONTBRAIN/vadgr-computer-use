#!/usr/bin/env python3
# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare a bounded registration fault in an isolated Linux browser home."""

import argparse
import hashlib
import json
import math
import os
import signal
import stat
import sys
import time
from pathlib import Path


def manifests(root):
    return tuple(
        root / "home" / ".config" / browser / "NativeMessagingHosts" / "com.vadgr.cua.json"
        for browser in ("google-chrome", "chromium", "microsoft-edge")
    )


def checked(path, root, *, missing=False):
    """Refuse aliases and paths that another user can replace."""
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(root):
        raise ValueError("isolated path required")
    current = root
    for part in (None, *path.relative_to(root).parts):
        if part is not None:
            current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == path and missing:
                return None
            raise ValueError("required isolated path absent") from None
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                or (current == root and info.st_mode & 0o077)):
            raise ValueError("owned unshared path required")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("directory required")
    return info


def regular(path, root):
    info = checked(path, root)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("single regular file required")
    return info


def validate(root, backup, ready, done, seconds):
    if sys.platform != "linux":
        raise ValueError("Linux required")
    if (isinstance(seconds, bool) or not math.isfinite(seconds)
            or not 0 < seconds <= 180):
        raise ValueError("bound must be between 0 and 180 seconds")
    if (not root.is_absolute() or root.parent != Path("/tmp")
            or not root.name.startswith("vadgr-cua-") or root.name == "vadgr-cua-"):
        raise ValueError("named isolated root below /tmp required")
    if not stat.S_ISDIR(checked(root, root).st_mode):
        raise ValueError("isolated directory required")
    controls = (backup, ready, done)
    if len(set(controls)) != 3:
        raise ValueError("distinct controls required")
    for path in controls:
        if path.parent != root or checked(path, root, missing=True) is not None:
            raise ValueError("fresh direct-child controls required")
    for path in manifests(root):
        regular(path, root)


def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        # Only the newly created fixture file receives its saved mode.
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def emit(**fields):
    print(json.dumps({"pid": os.getpid(), "timestamp": time.time(), **fields}), flush=True)


def fault(root, backup, ready, done, seconds):
    validate(root, backup, ready, done, seconds)
    paths = manifests(root)
    originals = [path.read_bytes() for path in paths]
    modes = [stat.S_IMODE(path.stat().st_mode) for path in paths]
    hashes = [hashlib.sha256(data).hexdigest() for data in originals]
    backup.mkdir(mode=0o700)
    if stat.S_IMODE(backup.stat().st_mode) != 0o700:
        raise ValueError("private backup directory required")
    for index, data in enumerate(originals):
        write_new(backup / f"manifest-{index}.bak", data)
    if any((backup / f"manifest-{i}.bak").read_bytes() != data
           for i, data in enumerate(originals)):
        raise ValueError("backup verification failed")

    removed = []
    try:
        for index, path in enumerate(paths):
            regular(path, root)
            if path.read_bytes() != originals[index]:
                raise ValueError("manifest changed during setup")
            removed.append(index)
            path.unlink()
        checked(ready, root, missing=True)
        write_new(ready, json.dumps({"ready": True, "manifest_count": 3,
                                    "backups_verified": True}).encode())
        emit(ready=True, manifest_count=3, backups_verified=True, hashes=hashes)
        deadline = time.monotonic() + seconds
        while True:
            if checked(done, root, missing=True) is not None:
                regular(done, root)
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("registration fault bound expired")
            time.sleep(min(.05, max(0, deadline - time.monotonic())))
    finally:
        restored = True
        # Attempt every restoration even if one file cannot be restored.
        for index in removed:
            try:
                path = paths[index]
                if checked(path, root, missing=True) is not None:
                    regular(path, root)
                    if (path.read_bytes() != originals[index]
                            or stat.S_IMODE(path.stat().st_mode) != modes[index]):
                        raise ValueError("restoration destination occupied")
                    continue
                write_new(path, originals[index], modes[index])
            except (OSError, ValueError):
                restored = False
        for index, path in enumerate(paths):
            try:
                regular(path, root)
                restored = (path.read_bytes() == originals[index]
                            and hashlib.sha256(path.read_bytes()).hexdigest() == hashes[index]
                            and stat.S_IMODE(path.stat().st_mode) == modes[index]
                            and restored)
            except (OSError, ValueError):
                restored = False
        emit(restored=restored, verified=restored, hashes_verified=restored,
             manifest_count=3, hashes=hashes)
        if not restored:
            raise RuntimeError("restoration verification failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--done", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=180)
    args = parser.parse_args(argv)
    def interrupted(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        fault(args.root, args.backup, args.ready, args.done, args.seconds)
    except (Exception, KeyboardInterrupt):
        # Exceptions can contain private manifest paths or contents.
        emit(failed=True)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
