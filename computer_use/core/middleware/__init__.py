# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Middleware chain per ARCHITECTURE.md §5.6 / §5.7 (Chain of Responsibility).

Every tool call passes through an ordered chain:
    auth -> denylist -> redaction (logs) -> telemetry -> handler

Each middleware does one thing (SRP). Adding a concern = adding one new
middleware class; the chain itself is unchanged (OCP).
"""

from computer_use.core.middleware.auth import AuthMiddleware
from computer_use.core.middleware.base import Middleware, ToolCall
from computer_use.core.middleware.chain import MiddlewareChain
from computer_use.core.middleware.denylist import DenylistMiddleware
from computer_use.core.middleware.redaction import RedactionMiddleware
from computer_use.core.middleware.telemetry import TelemetryMiddleware

__all__ = [
    "Middleware",
    "ToolCall",
    "MiddlewareChain",
    "AuthMiddleware",
    "DenylistMiddleware",
    "RedactionMiddleware",
    "TelemetryMiddleware",
]
