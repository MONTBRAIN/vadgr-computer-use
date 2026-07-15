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

import os
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
    """The pre-flight report: is a browser usable right now?

    ``profiles`` (0.6.1) lists every connected browser profile with its
    recognition context, so the pre-flight shows the choices when more than one
    profile is connected (and which one, if any, is current).
    """

    connected: bool
    browsers: list[str]
    setup: bool
    reason: str | None
    profiles: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "browsers": self.browsers,
            "setup": self.setup,
            "reason": self.reason,
            "profiles": self.profiles,
        }


@runtime_checkable
class BrowserBridge(Protocol):
    """Send an op, await its result. Raises ``BrowserError`` on failure.

    ``op`` is positional-only so an op-group can carry a wire param literally
    named ``op`` (the sub-op) without a keyword collision — e.g.
    ``send("tabs", op="list")`` routes wire op ``tabs`` with ``params={"op":"list"}``.
    """

    def send(self, op: str, /, **params) -> Any: ...

    def status(self) -> BridgeStatus: ...


@dataclass
class BrowserSession:
    """One connected extension session in the registry.

    Subclass / override ``request`` with the live native-messaging round-trip;
    the base is a registry record carrying the negotiated capability list.

    ``profile_id`` + ``profile_context`` (0.6.1) carry the connection's profile
    identity: a stable per-profile UUID and its recognition context
    (``window_count`` / ``tab_count`` / ``sample_tab_titles``). An older
    extension sends none, so the default ``"default"`` keeps single-profile
    setups unchanged.
    """

    browser: str
    ext_version: str
    supported_ops: list[str] = field(default_factory=list)
    profile_id: str = "default"
    profile_context: dict[str, Any] = field(default_factory=dict)

    def request(self, op: str, params: dict[str, Any]) -> Any:  # pragma: no cover
        # The live round-trip is wired in the spike (socket -> native host ->
        # extension). The base record exists so the registry and routing are
        # unit-testable without a browser.
        raise NotImplementedError("live session round-trip is wired in the spike")


# --- the per-OS native-host manifest locations (browser.md) ---

def windows_user_home_mnt(windows_user: str | None = None) -> Path:
    """The WSL view of the Windows user's home: ``/mnt/c/Users/<user>``.

    ``windows_user`` is injectable for tests; otherwise it is resolved from the
    interop ``USERPROFILE``/``USERNAME`` the bridge daemon already relies on,
    falling back to the Linux ``USER`` (which usually matches).
    """
    user = windows_user or _detect_windows_user()
    return Path("/mnt/c/Users") / user


def _detect_windows_user() -> str:  # pragma: no cover - interop, mocked in tests
    import os

    for env in ("WIN_USER", "USERNAME"):
        val = os.environ.get(env)
        if val:
            return val
    # Best-effort interop probe; cheap and only on the WSL path.
    try:
        import subprocess

        out = subprocess.run(
            ["cmd.exe", "/c", "echo %USERNAME%"],
            capture_output=True, text=True, timeout=5,
            # Never inherit fd 0: under a stdio MCP server, fd 0 is the JSON-RPC
            # pipe, and a cmd.exe interop child that holds it stalls `initialize`.
            stdin=subprocess.DEVNULL,
        )
        name = out.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return os.environ.get("USER", "user")


def manifest_paths(
    platform: str | None = None, *, windows_user: str | None = None
) -> dict[str, Path]:
    """Per-OS native-host manifest paths, keyed by browser.

    Mirrors the table in ``0.4.0/browser.md``. Windows registers via a registry
    key pointing at the manifest file; the path returned there is where the
    setup script writes the manifest itself. On WSL the targets are the
    *Windows* Chrome locations, written from Linux via ``/mnt/c``.
    """
    plat = platform or sys.platform
    home = Path.home()
    if plat == "wsl":
        # cua-in-WSL drives Windows Chrome — register to the Windows locations.
        win = windows_user_home_mnt(windows_user)
        local = win / "AppData" / "Local"
        return {
            "chrome": local / "Google" / "Chrome" / "User Data"
            / "NativeMessagingHosts" / _MANIFEST_NAME,
            "edge": local / "Microsoft" / "Edge" / "User Data"
            / "NativeMessagingHosts" / _MANIFEST_NAME,
        }
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

    def send(self, op: str, /, **params) -> Any:
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

    # The env var that pins a default profile when more than one is connected:
    # matches a profile_id prefix, or a sample_tab_title substring.
    _PROFILE_PIN_ENV = "CUA_BROWSER_PROFILE"

    def __init__(self, *, auto_register: bool = True) -> None:
        # Keyed by (browser, profile_id): the accept loop keeps EVERY connection,
        # not a single-listener bond. `_current` selects which one ops route to.
        self._sessions: dict[tuple[str, str], BrowserSession] = {}
        self._current: tuple[str, str] | None = None
        # When an explicitly-selected profile disconnects, its id is remembered
        # here so the next op is LOUD instead of silently falling to another
        # profile (the "never silently wrong" doctrine). Cleared on a fresh
        # selection or when all connections are gone.
        self._dropped_selection: str | None = None
        self._auto_register = auto_register
        self._ensured = False

    # --- seams the spike fills (overridden in tests) ---

    def _maybe_self_register(self) -> None:
        """Write cua's own native-host wiring on first use, so there is no
        manual registration step. Best-effort — never break an op over it."""
        if not self._auto_register or self._ensured:
            return
        self._ensured = True
        try:
            from computer_use.setup.extension_setup import ensure_registered

            ensure_registered()
        except Exception:
            pass

    def _probe_setup(self) -> list[str]:
        self._maybe_self_register()
        return probe_manifests(manifest_paths())

    def _active_session(self) -> BrowserSession | None:
        # The session the resolution ladder points at, or None when it cannot
        # decide (zero connections, or multiple with no selection). Never raises
        # — `send`/`status` translate a None into the right loud error / report.
        key = self._current_key()
        return self._sessions.get(key) if key is not None else None

    # --- 0.6.1: the profile-connection registry + resolution ladder ---

    def _current_key(self) -> tuple[str, str] | None:
        """Resolve which connection ops route to, WITHOUT raising:

        1. an explicit selection (``profiles(use)`` / ``use_target(profile_id)``);
        2. the ``CUA_BROWSER_PROFILE`` env pin (profile_id prefix or a
           sample_tab_title substring), if it matches exactly one;
        3. the sole connection when there is exactly one;
        4. otherwise ``None`` (ambiguous — the caller raises ``profile_ambiguous``).
        """
        if not self._sessions:
            return None
        if self._current is not None and self._current in self._sessions:
            return self._current
        pin = os.environ.get(self._PROFILE_PIN_ENV)
        if pin:
            matches = [k for k, s in self._sessions.items()
                       if self._pin_matches(s, pin)]
            if len(matches) == 1:
                return matches[0]
        # The sole-connection convenience is suppressed while a selection is
        # lost, so a dropped explicit choice never silently lands on another.
        if len(self._sessions) == 1 and self._dropped_selection is None:
            return next(iter(self._sessions))
        return None

    @staticmethod
    def _pin_matches(session: BrowserSession, pin: str) -> bool:
        if session.profile_id.startswith(pin):
            return True
        titles = (session.profile_context or {}).get("sample_tab_titles", [])
        return any(pin.lower() in str(t).lower() for t in titles)

    def _profile_list(self) -> list[dict[str, Any]]:
        cur = self._current_key()
        out: list[dict[str, Any]] = []
        for key, s in self._sessions.items():
            ctx = s.profile_context or {}
            out.append({
                "profile_id": s.profile_id,
                "browser": s.browser,
                "is_current": key == cur,
                "window_count": ctx.get("window_count"),
                "tab_count": ctx.get("tab_count"),
                "sample_tab_titles": list(ctx.get("sample_tab_titles", [])),
            })
        return out

    def _ambiguous_error(self, reason: str | None = None) -> BrowserError:
        """Build the terminal ``profile_ambiguous`` error, listing the choices.

        The same "never silently wrong" doctrine as 0.6.0 ``target_lost``: with
        more than one profile connected and none selected, cua refuses to guess.
        """
        listing = "; ".join(
            f"{p['profile_id']} (browser={p['browser']}, "
            f"tabs={p['tab_count']}"
            + (f", open: {', '.join(map(str, p['sample_tab_titles'][:3]))}"
               if p["sample_tab_titles"] else "")
            + ")"
            for p in self._profile_list()
        )
        message = reason or (
            "more than one browser profile is connected and none is selected"
        )
        return BrowserError(
            BrowserErrorCode.PROFILE_AMBIGUOUS,
            f"{message}. Connected profiles: {listing or '(none)'}",
            remediation=(
                "pick one with profiles(op='use', profile_id=...) or "
                "use_target(profile_id=...), or set CUA_BROWSER_PROFILE to a "
                "profile_id prefix or a tab-title substring"
            ),
            fallback=PIXEL_FALLBACK,
        )

    def _select_profile(self, profile_id: str | None) -> tuple[str, str]:
        """Point ``current`` at the profile matching ``profile_id`` (exact or a
        unique prefix). Raises ``profile_ambiguous`` on zero or many matches."""
        if profile_id:
            matches = [k for k, s in self._sessions.items()
                       if s.profile_id == profile_id
                       or s.profile_id.startswith(profile_id)]
            if len(matches) == 1:
                self._current = matches[0]
                self._dropped_selection = None
                return matches[0]
        raise self._ambiguous_error(
            f"no connected profile matches {profile_id!r}"
        )

    def _profiles_op(self, params: dict[str, Any]) -> Any:
        """Answer the ``profiles`` op from cua's connection registry (the only
        place that knows every connection). ``list`` enumerates, ``use`` pins."""
        sub = str(params.get("op", "list"))
        if sub == "list":
            ref = self._active_session()
            if ref is not None and "profiles" not in ref.supported_ops:
                raise self._op_unsupported("profiles")
            return {"profiles": self._profile_list()}
        if sub == "use":
            key = self._select_profile(params.get("profile_id"))
            session = self._sessions[key]
            if "profiles" not in session.supported_ops:
                raise self._op_unsupported("profiles")
            return {
                "profile_id": session.profile_id,
                "browser": session.browser,
                "is_current": True,
            }
        raise BrowserError(
            BrowserErrorCode.OP_FAILED, f"unknown profiles sub-op {sub!r}"
        )

    @staticmethod
    def _op_unsupported(op: str) -> BrowserError:
        return BrowserError(
            BrowserErrorCode.OP_UNSUPPORTED,
            f"the connected extension does not support op {op!r}",
            remediation="update the vadgr-cua extension",
            fallback=PIXEL_FALLBACK,
        )

    def register_session(self, session: BrowserSession) -> None:
        key = (session.browser, session.profile_id or "default")
        self._sessions[key] = session

    def unregister_session(self, session: BrowserSession) -> None:
        """Drop a connection that closed. If it was ``current``, the pointer is
        cleared so the next op re-resolves (loud when still ambiguous)."""
        for key, s in list(self._sessions.items()):
            if s is session:
                del self._sessions[key]
                if self._current == key:
                    self._current = None
                    self._dropped_selection = s.profile_id
        # A full disconnect resets the loud-loss latch: a lone profile that
        # later reconnects gets the cold-start convenience again.
        if not self._sessions:
            self._dropped_selection = None

    # --- public API ---

    def status(self) -> BridgeStatus:
        browsers = self._probe_setup()
        profiles = self._profile_list()
        session = self._active_session()
        if session is not None:
            return BridgeStatus(
                connected=True, browsers=browsers or [session.browser],
                setup=True, reason=None, profiles=profiles,
            )
        if self._sessions:
            # Connected, but the ladder can't pick one (more than one profile,
            # none selected). Connected is true; the profiles array shows the
            # choices and the reason flags the ambiguity.
            return BridgeStatus(
                connected=True, browsers=browsers or [], setup=True,
                reason="profile_ambiguous", profiles=profiles,
            )
        if not browsers:
            return BridgeStatus(
                connected=False, browsers=[], setup=False, reason="not_set_up"
            )
        return BridgeStatus(
            connected=False, browsers=browsers, setup=True, reason="not_connected"
        )

    def send(self, op: str, /, **params) -> Any:
        # `profiles` is resolved cua-side (the connection registry is the only
        # place that knows every connection); it never round-trips to a session.
        if op == "profiles":
            return self._profiles_op(params)
        # A profile carried inline (use_target(profile_id=...)) pins `current`
        # first, then is consumed here — the extension never sees profile_id.
        profile_id = params.pop("profile_id", None)
        if profile_id is not None:
            self._select_profile(profile_id)
        session = self._active_session()
        if session is None:
            self._raise_no_session()
        if op not in session.supported_ops:
            raise self._op_unsupported(op)
        return session.request(op, params)

    def _raise_no_session(self) -> None:
        if self._dropped_selection is not None and self._sessions:
            raise self._ambiguous_error(
                f"the selected profile {self._dropped_selection!r} disconnected; "
                "choose a connected profile"
            )
        if len(self._sessions) > 1:
            raise self._ambiguous_error()
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
