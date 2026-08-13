# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""List and launch installed applications, the companion to reading them.

Reading a window is only useful if the model can bring one up first. These are
Tier 0 system tools, not structured reads: listing and launching are OS
operations. ``apps`` lists the installed launchable apps; ``app_open`` launches
one by id or name.

The OS is hidden behind an AppsBackend provider (see ``backend``): the tools
call ``list_apps`` / ``open_app`` here and never branch on the platform. Linux
lists the XDG desktop entries and launches through the desktop's own launchers;
Windows and macOS report the tier is not built yet until their minors land.
"""

from __future__ import annotations

from computer_use.tools.apps.backend import (
    APPS_UNSUPPORTED,
    AppsBackend,
    UnsupportedAppsBackend,
    list_apps,
    open_app,
    resolve_apps_backend,
)

__all__ = [
    "APPS_UNSUPPORTED",
    "AppsBackend",
    "UnsupportedAppsBackend",
    "list_apps",
    "open_app",
    "resolve_apps_backend",
]
