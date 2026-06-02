# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""HTTP GET / POST via the standard library.

No third-party HTTP dep — ``urllib.request`` covers both verbs and lets
us bind the result schema cleanly.
"""

from __future__ import annotations

import urllib.error
import urllib.request as urllib_request
from typing import Any, Optional

from computer_use.core.ops import OperationGroup

_DEFAULT_TIMEOUT = 30

_ops = OperationGroup("http")


def _request(method: str, url: str, body: Optional[str], headers: Optional[dict], timeout: int) -> dict[str, Any]:
    data = body.encode("utf-8") if body is not None else None
    req = urllib_request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
            response_headers = dict(resp.headers.items()) if hasattr(resp.headers, "items") else {}
    except urllib.error.HTTPError as e:
        # 4xx / 5xx still carry a usable body — return it instead of raising.
        return {
            "status": e.code,
            "headers": dict(e.headers.items()) if e.headers else {},
            "body": e.read().decode("utf-8", errors="replace") if e.fp else "",
        }
    return {
        "status": status,
        "headers": response_headers,
        "body": raw.decode("utf-8", errors="replace"),
    }


@_ops.operation("get")
def _get(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    return _request("GET", url, None, headers, timeout)


@_ops.operation("post")
def _post(
    url: str,
    body: Optional[str] = None,
    headers: Optional[dict] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    return _request("POST", url, body, headers, timeout)


def http(
    op: str,
    url: str,
    body: Optional[str] = None,
    headers: Optional[dict] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Any:
    """Dispatch an HTTP sub-operation.

    Args:
        op: ``get`` or ``post``.
        url: Absolute URL.
        body: Request body for POST (sent as utf-8 bytes).
        headers: Optional request headers.
        timeout: Seconds before the request is aborted.

    Returns:
        ``{"status": int, "headers": dict, "body": str}`` for both verbs.
    """
    return _ops.run(op, url=url, body=body, headers=headers, timeout=timeout)
