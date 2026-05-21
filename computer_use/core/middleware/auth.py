# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Auth middleware: checks an opaque token in the call context."""

from __future__ import annotations

from typing import Any

from computer_use.core.middleware.base import ToolCall


class AuthMiddleware:
    """Block calls when the token is required but missing or wrong."""

    def __init__(self, token: str | None, required: bool = True):
        self._token = token
        self._required = required

    def before(self, call: ToolCall) -> ToolCall:
        if not self._required:
            return call
        supplied = call.context.get("auth_token")
        if supplied != self._token:
            raise PermissionError(
                f"auth: invalid token for tool {call.name!r}"
            )
        return call

    def after(self, call: ToolCall, result: Any) -> Any:
        return result
