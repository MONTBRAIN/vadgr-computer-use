# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provider seams for the backend resolver.

A provider is a small, stateless object that knows (a) whether it applies to a
session and (b) how to construct its backend — nothing else. Capture and input
are two narrow protocols so a capture-only environment never implements input.
``create`` returns a *validated, working* backend or raises ``BackendUnavailable``;
this is what lets the resolver fall through a tool whose binary exists but no
longer functions (e.g. gnome-screenshot on GNOME 49+).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from computer_use.core.actions import ActionExecutor
from computer_use.core.screenshot import ScreenCapture
from computer_use.platform.resolver.session import SessionContext


class BackendUnavailable(Exception):
    """A provider applied to the session but could not produce a working backend."""


@runtime_checkable
class CaptureProvider(Protocol):
    name: str
    priority: int  # higher = tried first

    def supports(self, ctx: SessionContext) -> bool: ...
    def create(self, ctx: SessionContext) -> ScreenCapture: ...


@runtime_checkable
class InputProvider(Protocol):
    name: str
    priority: int

    def supports(self, ctx: SessionContext) -> bool: ...
    def create(self, ctx: SessionContext) -> ActionExecutor: ...
