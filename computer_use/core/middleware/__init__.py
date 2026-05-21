# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Lightweight middleware chain for observability.

The chain lets the runtime emit structured telemetry events around tool
calls. It is intentionally minimal — `vadgr-computer-use` does not host
authorization, denylist, redaction, approval prompts, or any other policy
concern. Those live in the host's agent loop. cua exposes tools, `tier` +
`risk` metadata, and telemetry events; the host decides what to do with
them.
"""

from computer_use.core.middleware.base import Middleware, ToolCall
from computer_use.core.middleware.chain import MiddlewareChain
from computer_use.core.middleware.telemetry import TelemetryMiddleware

__all__ = [
    "Middleware",
    "ToolCall",
    "MiddlewareChain",
    "TelemetryMiddleware",
]
