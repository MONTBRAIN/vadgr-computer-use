# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""``BrowserBridge`` — the seam that makes the tool testable with no browser.

The ``browser`` tool depends on the ``BrowserBridge`` Protocol, never on
native messaging directly:

- ``NativeMessagingBridge`` — the real bridge: a session registry, the
  per-OS native-host manifest probe, ``status()`` (pre-flight), and ``send()``
  that routes an op to the active session.
- ``FakeBridge`` — scripted responses for unit tests, no browser.

The live socket/native-messaging plumbing (session registration over the IPC
socket) is the spike's job; the registry, routing and error model below are
fully unit-tested.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from computer_use.browser.protocol import BrowserError, BrowserErrorCode

# The guided pixel fallback appended to terminal browser errors. cua never
# auto-substitutes pixel actions; it names the fallback so the LLM can choose.
PIXEL_FALLBACK = (
    "Fallback: call `screenshot` to see the page, then act with the pixel "
    "tools `click`/`type_text`/`scroll` by coordinates (degraded mode — slower, "
    "less precise; install the extension for the reliable path)."
)

_MANIFEST_NAME = "com.vadgr.cua.json"


@dataclass
class BridgeStatus:
    """The pre-flight report: is a browser usable right now?"""

    connected: bool
    browsers: list[str]
    setup: bool
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "browsers": self.browsers,
            "setup": self.setup,
            "reason": self.reason,
        }


@runtime_checkable
class BrowserBridge(Protocol):
    """Send an op, await its result. Raises ``BrowserError`` on failure."""

    def send(self, op: str, **params) -> Any: ...

    def status(self) -> BridgeStatus: ...


@dataclass
class BrowserSession:
    """One connected extension session in the registry.

    Subclass / override ``request`` with the live native-messaging round-trip;
    the base is a registry record carrying the negotiated capability list.
    """

    browser: str
    ext_version: str
    supported_ops: list[str] = field(default_factory=list)

    def request(self, op: str, params: dict[str, Any]) -> Any:  # pragma: no cover
        # The live round-trip is wired in the spike (socket -> native host ->
        # extension). The base record exists so the registry and routing are
        # unit-testable without a browser.
        raise NotImplementedError("live session round-trip is wired in the spike")


# --- the per-OS native-host manifest locations (browser.md) ---

def manifest_paths(platform: str | None = None) -> dict[str, Path]:
    """Per-OS native-host manifest paths, keyed by browser.

    Mirrors the table in ``0.4.0/browser.md``. Windows registers via a registry
    key pointing at the manifest file; the path returned there is where the
    setup script writes the manifest itself.
    """
    plat = platform or sys.platform
    home = Path.home()
    if plat == "darwin":
        base = home / "Library" / "Application Support"
        return {
            "chrome": base / "Google" / "Chrome" / "NativeMessagingHosts" / _MANIFEST_NAME,
            "edge": base / "Microsoft Edge" / "NativeMessagingHosts" / _MANIFEST_NAME,
            "chromium": base / "Chromium" / "NativeMessagingHosts" / _MANIFEST_NAME,
        }
    if plat.startswith("win"):
        base = home / "AppData" / "Local" / "vadgr-cua" / "NativeMessagingHosts"
        return {"chrome": base / _MANIFEST_NAME, "edge": base / _MANIFEST_NAME}
    # linux / other posix
    cfg = home / ".config"
    return {
        "chrome": cfg / "google-chrome" / "NativeMessagingHosts" / _MANIFEST_NAME,
        "chromium": cfg / "chromium" / "NativeMessagingHosts" / _MANIFEST_NAME,
        "edge": cfg / "microsoft-edge" / "NativeMessagingHosts" / _MANIFEST_NAME,
    }


def probe_manifests(paths: dict[str, Path]) -> list[str]:
    """Return the browsers whose native-host manifest is present on disk."""
    return [name for name, p in paths.items() if Path(p).exists()]


class FakeBridge:
    """Scripted bridge for unit tests — no browser, no native messaging.

    ``responses`` maps op name → a value, a callable ``(**params) -> value``,
    or a ``BrowserError`` to raise. ``connected=False`` makes every ``send``
    raise ``not_connected``.
    """

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        connected: bool = True,
        status: BridgeStatus | None = None,
    ) -> None:
        self._responses = responses or {}
        self._connected = connected
        self._status = status
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send(self, op: str, **params) -> Any:
        self.calls.append((op, params))
        if not self._connected:
            raise BrowserError(
                BrowserErrorCode.NOT_CONNECTED,
                "no live browser session",
                fallback=PIXEL_FALLBACK,
            )
        value = self._responses.get(op)
        if isinstance(value, BrowserError):
            raise value
        if callable(value):
            return value(**params)
        return value

    def status(self) -> BridgeStatus:
        if self._status is not None:
            return self._status
        return BridgeStatus(
            connected=self._connected,
            browsers=["chrome"] if self._connected else [],
            setup=True,
            reason=None if self._connected else "not_connected",
        )


class NativeMessagingBridge:
    """The real bridge: manifest probe + session registry + op routing.

    The socket/native-messaging plumbing that registers a live
    ``BrowserSession`` is wired in the spike. ``_probe_setup`` and
    ``_active_session`` are the two seams the spike fills; the status/error
    logic on top of them is unit-tested via overrides.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}

    # --- seams the spike fills (overridden in tests) ---

    def _probe_setup(self) -> list[str]:
        return probe_manifests(manifest_paths())

    def _active_session(self) -> BrowserSession | None:
        # First registered session wins (single-session in 0.4.0; multi-target
        # routing matures in 0.6.0).
        for sess in self._sessions.values():
            return sess
        return None

    def register_session(self, session: BrowserSession) -> None:
        self._sessions[session.browser] = session

    # --- public API ---

    def status(self) -> BridgeStatus:
        browsers = self._probe_setup()
        session = self._active_session()
        if session is not None:
            return BridgeStatus(
                connected=True, browsers=browsers or [session.browser],
                setup=True, reason=None,
            )
        if not browsers:
            return BridgeStatus(
                connected=False, browsers=[], setup=False, reason="not_set_up"
            )
        return BridgeStatus(
            connected=False, browsers=browsers, setup=True, reason="not_connected"
        )

    def send(self, op: str, **params) -> Any:
        session = self._active_session()
        if session is None:
            if not self._probe_setup():
                raise BrowserError(
                    BrowserErrorCode.NOT_SET_UP,
                    "no native-host manifest registered for any browser",
                    remediation="run extension setup (`vadgr-cua browser-setup`)",
                    fallback=PIXEL_FALLBACK,
                )
            raise BrowserError(
                BrowserErrorCode.NOT_CONNECTED,
                "the native host is registered but no browser session is live",
                remediation="open Chrome/Edge and enable the vadgr-cua extension",
                fallback=PIXEL_FALLBACK,
            )
        if op not in session.supported_ops:
            raise BrowserError(
                BrowserErrorCode.OP_UNSUPPORTED,
                f"the connected extension does not support op {op!r}",
                remediation="update the vadgr-cua extension",
                fallback=PIXEL_FALLBACK,
            )
        return session.request(op, params)
