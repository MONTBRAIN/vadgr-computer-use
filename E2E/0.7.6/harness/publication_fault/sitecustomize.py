# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Child-only, time-bounded publication refusal; imports no product module."""

import json
import os
import stat
import sys
import time
from pathlib import Path


def install():
    directory = Path(__file__).absolute().parent
    configuration = json.loads((directory / "configuration.json").read_text(encoding="utf-8"))
    endpoint = Path(configuration["endpoint"])
    expires = float(configuration["expires"])
    if os.name != "posix" or not endpoint.is_absolute() or not 0 < expires - time.time() <= 120:
        return
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        return
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        return

    def audit(event, args):
        if event != "os.rename":
            return
        destination = Path(args[1]).absolute()
        if sys.platform == "darwin":
            # macOS exposes system-owned aliases for its private temp trees.
            # Normalize only those prefixes, never links inside the test root.
            for alias in (Path("/tmp"), Path("/var")):
                canonical = Path("/private") / alias.name
                if destination.is_relative_to(alias) and alias.resolve() == canonical:
                    destination = canonical / destination.relative_to(alias)
                    break
        if destination != endpoint:
            return
        if time.time() >= expires or (directory / "disarmed").exists():
            return
        source = Path(args[0])
        info = source.lstat()
        lock = endpoint.with_name("browser-broker.lock")
        record = {
            "event": "publication_refused", "pid": os.getpid(), "time": time.time(),
            "temporary_mode": stat.S_IMODE(info.st_mode), "temporary_size": info.st_size,
            "lock_present": lock.is_file(), "destination_present": endpoint.is_file(),
        }
        descriptor = os.open(directory / "events.jsonl", os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        raise PermissionError("isolated endpoint publication fault")

    sys.addaudithook(audit)


install()
