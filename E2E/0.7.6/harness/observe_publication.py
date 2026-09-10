# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Observe isolated endpoint metadata without opening endpoint contents."""

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def validate(root: Path, endpoint: Path) -> tuple[Path, Path]:
    root, endpoint = root.absolute(), endpoint.absolute()
    if root.is_symlink() or not root.name.startswith("vadgr-cua-") or not root.is_dir():
        raise ValueError("a named isolated root is required")
    if root.parent.resolve() != Path(tempfile.gettempdir()).resolve():
        raise ValueError("the root must be directly inside the system temporary directory")
    if not endpoint.resolve().is_relative_to(root.resolve()) or endpoint.parent.resolve() == root.resolve():
        raise ValueError("the endpoint must use a dedicated directory inside the isolated root")
    for path in [endpoint.parent, *endpoint.parent.parents]:
        if path.is_symlink() or getattr(path.lstat() if path.exists() else None,
                                       "st_file_attributes", 0) & 0x400:
            raise ValueError("publication observer paths must not use links")
        if os.name == "posix" and path.exists() and path.stat().st_uid != os.getuid():
            raise ValueError("publication observer paths must belong to the current user")
        if path.resolve() == root.resolve():
            break
    return root, endpoint


def windows_metadata(path: Path) -> dict:
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:VADGR_CUA_OBSERVE_PATH
$owner = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]) | ForEach-Object {
    $sid = $_.IdentityReference.Value
    @{owner=($sid -eq $owner); system=($sid -eq 'S-1-5-18');
      rights=[int64]$_.FileSystemRights; inherited=$_.IsInherited;
      allow=($_.AccessControlType -eq 'Allow')}
})
@{protected=$acl.AreAccessRulesProtected; rules=$rules;
  owner_matches=($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq $owner)} |
    ConvertTo-Json -Depth 5 -Compress
"""
    environment = dict(os.environ, VADGR_CUA_OBSERVE_PATH=str(path))
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            env=environment, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise OSError("native Windows ACL observation failed")
    return json.loads(result.stdout)


def snapshot(endpoint: Path) -> list[dict]:
    paths = [("parent", endpoint.parent), ("endpoint", endpoint)]
    if endpoint.parent.exists():
        paths.extend(("temporary", path) for path in endpoint.parent.glob(f".{endpoint.name}.*.tmp"))
        paths.append(("legacy_temporary", endpoint.with_suffix(endpoint.suffix + ".tmp")))
    records = []
    for kind, path in paths:
        try:
            info = path.lstat()
        except FileNotFoundError:
            records.append({"kind": kind, "exists": False})
            continue
        row = {"kind": kind, "exists": True, "size": info.st_size,
               "inode": info.st_ino, "modified_ns": info.st_mtime_ns,
               "symlink": stat.S_ISLNK(info.st_mode), "links": info.st_nlink}
        if sys.platform == "win32":
            if row["symlink"] or getattr(info, "st_file_attributes", 0) & 0x400:
                row["unsafe_link"] = True
            else:
                try:
                    row["acl"] = windows_metadata(path)
                except OSError:
                    try:
                        path.lstat()
                    except FileNotFoundError:
                        # Atomic publication may remove a temporary between
                        # its metadata read and the independent ACL query.
                        row["vanished"] = True
                    else:
                        raise
        else:
            row.update(mode=stat.S_IMODE(info.st_mode), owner_matches=info.st_uid == os.getuid())
        records.append(row)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--endpoint", type=Path, required=True)
    parser.add_argument("--discovery", type=Path)
    parser.add_argument("--seconds", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 120:
        parser.error("seconds must be between 0 and 120")
    _root, endpoint = validate(args.root, args.endpoint)
    discovery = validate(args.root, args.discovery)[1] if args.discovery is not None else None
    finish, previous = time.monotonic() + args.seconds, None
    while True:
        current = [dict(row, surface="endpoint") for row in snapshot(endpoint)]
        if discovery is not None:
            current.extend(dict(row, surface="discovery") for row in snapshot(discovery))
        if current != previous:
            print(json.dumps({"time": time.time(), "metadata": current}), flush=True)
            previous = current
        if time.monotonic() >= finish:
            break
        time.sleep(min(0.05, max(0, finish - time.monotonic())))
    print(json.dumps({"observer_finished": True}), flush=True)


if __name__ == "__main__":
    main()
