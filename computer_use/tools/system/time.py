# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Clock + sleep primitives.

``time.now`` returns ISO-8601 with UTC offset; ``time.sleep`` is capped
so a buggy agent can't stall the MCP session indefinitely.
"""

from __future__ import annotations

import datetime as _dt
import time as _time
from typing import Any, Optional

_MAX_SLEEP_SECONDS = 60


def _now(tz: Optional[str]) -> str:
    if tz is None:
        return _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        from zoneinfo import ZoneInfo
    except ImportError as e:  # pragma: no cover — Python 3.9+ ships zoneinfo
        raise RuntimeError("zoneinfo not available on this interpreter") from e
    return _dt.datetime.now(ZoneInfo(tz)).isoformat()


def _sleep(seconds: float) -> dict[str, float]:
    if seconds < 0:
        seconds = 0
    if seconds > _MAX_SLEEP_SECONDS:
        seconds = _MAX_SLEEP_SECONDS
    _time.sleep(seconds)
    return {"slept": float(seconds)}


def time(op: str, seconds: float = 0, tz: Optional[str] = None) -> Any:
    """Dispatch a clock sub-operation.

    Args:
        op: ``now`` or ``sleep``.
        seconds: Sleep duration. Capped at 60 seconds.
        tz: IANA timezone for ``now`` (default UTC).
    """
    if op == "now":
        return _now(tz)
    if op == "sleep":
        return _sleep(seconds)
    raise ValueError(f"unknown time op {op!r}; expected now or sleep")
