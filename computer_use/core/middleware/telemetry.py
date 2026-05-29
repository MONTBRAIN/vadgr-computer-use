# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Telemetry middleware: structured logging at INFO level."""

from __future__ import annotations

import logging
from typing import Any

from computer_use.core.middleware.base import ToolCall


class TelemetryMiddleware:
    """Emit start/end log lines for every tool call."""

    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or logging.getLogger("computer_use.telemetry")

    def before(self, call: ToolCall) -> ToolCall:
        self._logger.info("tool=%s phase=start", call.name)
        return call

    def after(self, call: ToolCall, result: Any) -> Any:
        self._logger.info("tool=%s phase=end status=ok", call.name)
        return result
