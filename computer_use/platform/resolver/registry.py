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

"""Provider registry — the open/closed seam.

A new desktop backend is added by writing a provider and registering it here (or
self-registering on import). The resolver and the rest of the platform tier are
untouched. The registration helpers return the provider so they double as
decorators.
"""

from __future__ import annotations

from computer_use.platform.resolver.providers import CaptureProvider, InputProvider

CAPTURE_PROVIDERS: list[CaptureProvider] = []
INPUT_PROVIDERS: list[InputProvider] = []


def register_capture(provider: CaptureProvider) -> CaptureProvider:
    CAPTURE_PROVIDERS.append(provider)
    return provider


def register_input(provider: InputProvider) -> InputProvider:
    INPUT_PROVIDERS.append(provider)
    return provider
