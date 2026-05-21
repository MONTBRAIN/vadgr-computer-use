# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Redaction middleware: masks secrets in tool args before logging.

The tool itself still sees the real values — only the logging copy is
masked. This keeps secrets out of telemetry without breaking the call.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Sequence

from computer_use.core.middleware.base import ToolCall


class RedactionMiddleware:
    """Compile regex patterns once and apply them to a copy of the call."""

    REDACTED = "[REDACTED]"

    def __init__(self, patterns: Sequence[str]):
        self._regexes = [re.compile(p) for p in patterns]

    def before(self, call: ToolCall) -> ToolCall:
        # Real call is never mutated — execution sees the unmasked args.
        return call

    def after(self, call: ToolCall, result: Any) -> Any:
        return result

    def redact_for_log(self, call: ToolCall) -> ToolCall:
        """Return a deep-copied ToolCall with secrets replaced by [REDACTED]."""
        clone = copy.deepcopy(call)
        clone.args = tuple(self._mask(a) for a in clone.args)
        clone.kwargs = {k: self._mask(v) for k, v in clone.kwargs.items()}
        return clone

    def _mask(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        masked = value
        for rx in self._regexes:
            masked = rx.sub(self.REDACTED, masked)
        return masked
