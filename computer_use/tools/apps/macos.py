# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The macOS apps provider (stub until its minor builds the real launcher).

The seam is what ships now: this provider reports the apps tier is not built on
macOS yet, so ``apps`` and ``app_open`` return a clean named result there
instead of crashing. The macOS minor replaces this one class with an
``/Applications`` list and a real launch (``open -a``), and touches nothing in
the tools or the resolver.
"""

from __future__ import annotations

from computer_use.tools.apps.backend import UnsupportedAppsBackend


class MacOSAppsBackend(UnsupportedAppsBackend):
    platform_name = "macOS"
