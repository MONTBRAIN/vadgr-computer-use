# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Prepare or disarm a bounded child-only endpoint publication fault."""

import argparse
import json
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path


def checked(root: Path, path: Path) -> Path:
    root = root.absolute()
    if root.is_symlink() or not root.name.startswith("vadgr-cua-"):
        raise ValueError("a named isolated root is required")
    if root.parent.resolve() not in {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}:
        raise ValueError("the isolated root must be directly inside the temporary directory")
    if root.stat().st_uid != os.getuid() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError("the isolated root must be private and owned by the current user")
    lexical = path.absolute()
    path = lexical.resolve()
    root = root.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("the path must stay inside the isolated root")
    for item in [lexical, *lexical.parents]:
        if item.is_symlink():
            raise ValueError("links are not permitted in fault paths")
        if item.resolve() == root:
            break
        if item.exists() and item.stat().st_uid != os.getuid():
            raise ValueError("fault paths must belong to the current user")
    return path


def arm(root: Path, directory: Path, endpoint: Path, seconds: float) -> None:
    if os.name != "posix" or not 0 < seconds <= 120:
        raise ValueError("the POSIX fault duration must be between 0 and 120 seconds")
    directory, endpoint = checked(root, directory), checked(root, endpoint)
    if directory.parent != root.resolve() or endpoint.is_relative_to(directory):
        raise ValueError("the fault directory must be separate from endpoint storage")
    if not endpoint.is_file() or stat.S_IMODE(endpoint.stat().st_mode) != 0o600:
        raise ValueError("a protected stale endpoint must already exist")
    directory.mkdir(mode=0o700)
    configuration = {"endpoint": str(endpoint), "expires": time.time() + seconds}
    for name, value in [("configuration.json", json.dumps(configuration)), ("events.jsonl", "")]:
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
    shutil.copyfile(Path(__file__).with_suffix("") / "sitecustomize.py", directory / "sitecustomize.py")
    (directory / "sitecustomize.py").chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["arm", "disarm"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--endpoint", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()
    if args.action == "arm":
        if args.endpoint is None:
            parser.error("arm requires --endpoint")
        arm(args.root, args.directory, args.endpoint, args.seconds)
        print(json.dumps({"armed": True, "seconds": args.seconds, "permissions_changed": False}))
    else:
        directory = checked(args.root, args.directory)
        descriptor = os.open(directory / "disarmed", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        print(json.dumps({"disarmed": True, "permissions_changed": False}))


if __name__ == "__main__":
    main()
