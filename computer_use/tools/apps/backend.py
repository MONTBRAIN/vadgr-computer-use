# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The apps tier's per-OS provider seam.

The ``apps`` and ``app_open`` tools are thin over an AppsBackend: they resolve
the provider for the running OS and call it. One provider per OS resolves behind
this seam and the tools never branch on the platform, exactly as the structured
tier resolves an AT-SPI / UIA / AX backend. A new OS joins by adding a provider,
never by editing the tools or this resolver.

Off the platform a provider is built for, the tier degrades to a reported
capability rather than a crash or a silent empty list: the Windows and macOS
stubs answer ``apps_unsupported`` with a reason until their own minors build the
real launcher, the same way the structured tier answers "no structured tier on
this platform".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from computer_use.core.types import Platform
from computer_use.platform.detect import detect_platform

# Named error code the stub providers return (the contract; the loop and the
# model read this, not prose). An unsupported OS is a reported capability level,
# never an exception and never a silent empty list.
APPS_UNSUPPORTED = "apps_unsupported"


@runtime_checkable
class AppsBackend(Protocol):
    """What a per-OS apps provider must provide: list installed, launch one.

    The surface is deliberately small (list and open). A window read belongs to
    the structured tier, not here, so this Protocol never grows toward it.
    """

    def list_apps(self) -> dict: ...
    def open_app(self, target: str, timeout_ms: int) -> dict: ...


class UnsupportedAppsBackend:
    """Honest degradation for an OS whose real launcher is not built yet.

    Substitutable behind AppsBackend: it returns the same shape (a dict, never a
    raise) so a caller reads one named result instead of catching an error. The
    per-OS subclasses name themselves so the future minor replaces exactly one
    class without touching the tools or the resolver.
    """

    platform_name = "this platform"

    def _reason(self) -> str:
        return f"No apps tier on {self.platform_name} yet."

    def list_apps(self) -> dict:
        # An empty list, but flagged: a silent [] would read as "nothing
        # installed" rather than "this OS is not built yet".
        return {"apps": [], "ok": False, "error": APPS_UNSUPPORTED,
                "reason": self._reason()}

    def open_app(self, target: str, timeout_ms: int = 5000) -> dict:
        return {"ok": False, "error": APPS_UNSUPPORTED, "target": target,
                "reason": self._reason()}


# The resolved provider is cached for the process, mirroring the structured
# tier's resolver: the OS does not change mid-session, so the provider is built
# at most once and reused.
_CACHED_BACKEND: AppsBackend | None = None
_RESOLVED = False


def _build_backend() -> AppsBackend:
    """Build the provider for the running OS. Never raises, never returns None.

    WSL2 is Linux with Windows-routed input, but its apps are Linux apps behind
    the XDG entries and gio/gtk-launch (WSLg), so it takes the Linux provider.
    Windows and macOS take their honest stubs until their minors land.
    """
    try:
        platform = detect_platform()
    except Exception:
        platform = None
    if platform in (Platform.LINUX, Platform.WSL2):
        from computer_use.tools.apps.linux import LinuxAppsBackend

        return LinuxAppsBackend()
    if platform == Platform.WINDOWS:
        from computer_use.tools.apps.windows import WindowsAppsBackend

        return WindowsAppsBackend()
    if platform == Platform.MACOS:
        from computer_use.tools.apps.macos import MacOSAppsBackend

        return MacOSAppsBackend()
    return UnsupportedAppsBackend()


def resolve_apps_backend() -> AppsBackend:
    """Return the process's apps provider, building it once and caching it."""
    global _CACHED_BACKEND, _RESOLVED
    if _RESOLVED:
        return _CACHED_BACKEND
    _RESOLVED = True
    _CACHED_BACKEND = _build_backend()
    return _CACHED_BACKEND


def list_apps() -> dict:
    """List installed launchable apps, through the resolved provider."""
    return resolve_apps_backend().list_apps()


def open_app(target: str, timeout_ms: int = 5000) -> dict:
    """Launch an app by id or name and confirm it, through the resolved provider."""
    return resolve_apps_backend().open_app(target, timeout_ms)
