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

"""The resolver: walk providers by priority, return the first working backend.

Depends only on the provider protocols (not on any concrete backend), so adding
a desktop is a new provider, never an edit here. The ``Skip`` trail records why
each higher-priority provider was passed over and feeds ``vadgr-cua doctor``.
"""

from __future__ import annotations

from dataclasses import dataclass

from computer_use.core.errors import PlatformNotSupportedError
from computer_use.platform.providers import BackendUnavailable
from computer_use.platform.session import SessionContext


@dataclass(frozen=True)
class Skip:
    """A provider that was passed over, and why (surfaced by `doctor`)."""

    name: str
    reason: str


class BackendResolver:
    """Resolve a session to its highest-priority working backend."""

    def __init__(self, providers):
        self._providers = list(providers)

    def resolve(self, ctx: SessionContext):
        """Return (backend, skips). Raise PlatformNotSupportedError if none work."""
        skips: list[Skip] = []
        for provider in sorted(self._providers, key=lambda p: -p.priority):
            if not provider.supports(ctx):
                skips.append(Skip(provider.name, "not applicable to this session"))
                continue
            try:
                return provider.create(ctx), skips
            except BackendUnavailable as exc:
                skips.append(Skip(provider.name, str(exc)))
        raise PlatformNotSupportedError(_remediation(skips))


def _remediation(skips: list[Skip]) -> str:
    if not skips:
        return "No backend providers are registered for this session."
    tried = "; ".join(f"{s.name}: {s.reason}" for s in skips)
    return f"No working backend for this session. Tried — {tried}."
