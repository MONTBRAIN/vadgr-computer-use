# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Hierarchical browser window and tab leases for the shared broker."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


class OwnershipConflict(Exception):
    code = "target_owned_by_another_client"

    def __init__(self, scope: str, target_id: int, owner_id: str) -> None:
        self.scope = scope
        self.target_id = target_id
        self.owner_id = owner_id
        super().__init__(f"{scope} {target_id} is owned by another browser client {owner_id}")


@dataclass
class Lease:
    owner_id: str | None
    revision: int
    orphaned: bool = False


class OwnershipRegistry:
    """Own windows normally and tabs only as the shared-window escape hatch."""

    def __init__(self, *, orphan_on_first_observe: bool = False) -> None:
        self._windows: dict[tuple[str, int], Lease] = {}
        self._tabs: dict[tuple[str, int], Lease] = {}
        self._tab_windows: dict[tuple[str, int], int] = {}
        self._epoch_orphan_windows: set[tuple[str, int]] = set()
        self._epoch_orphan_tabs: set[tuple[str, int]] = set()
        self._orphan_on_first_observe = orphan_on_first_observe
        self._observed_profiles: set[str] = set()
        self._revision = 0
        self._lock = RLock()

    def observe(self, profile_id: str, windows: list[dict]) -> None:
        with self._lock:
            window_keys = {(profile_id, int(window["window_id"])) for window in windows}
            tab_keys = {
                (profile_id, int(tab["tab_id"]))
                for window in windows
                for tab in window.get("tabs", [])
            }
            for key in [
                key for key in self._windows if key[0] == profile_id and key not in window_keys
            ]:
                self._windows.pop(key, None)
            for key in [key for key in self._tabs if key[0] == profile_id and key not in tab_keys]:
                self._tabs.pop(key, None)
            for key in [
                key for key in self._tab_windows if key[0] == profile_id and key not in tab_keys
            ]:
                self._tab_windows.pop(key, None)
            self._epoch_orphan_windows = {
                key
                for key in self._epoch_orphan_windows
                if key[0] != profile_id or key in window_keys
            }
            self._epoch_orphan_tabs = {
                key for key in self._epoch_orphan_tabs if key[0] != profile_id or key in tab_keys
            }
            for window in windows:
                wid = int(window["window_id"])
                for tab in window.get("tabs", []):
                    self._tab_windows[(profile_id, int(tab["tab_id"]))] = wid
            if self._orphan_on_first_observe and profile_id not in self._observed_profiles:
                self._epoch_orphan_windows.update(window_keys)
                self._epoch_orphan_tabs.update(tab_keys)
            self._observed_profiles.add(profile_id)
            for window in windows:
                wid = int(window["window_id"])
                for tab in window.get("tabs", []):
                    opener = tab.get("opener_tab_id")
                    if opener is not None:
                        self._inherit(profile_id, wid, int(tab["tab_id"]), int(opener))

    def _inherit(self, profile_id: str, window_id: int, tab_id: int, opener_id: int) -> None:
        opener_window = self._tab_windows.get((profile_id, opener_id))
        if opener_window is None:
            return
        _scope, lease = self._effective(profile_id, opener_window, opener_id)
        if lease is None or lease.owner_id is None or lease.orphaned:
            return
        if window_id != opener_window:
            current = self._windows.get((profile_id, window_id))
            if current is None:
                self._windows[(profile_id, window_id)] = Lease(lease.owner_id, self._next())
        elif (profile_id, tab_id) not in self._tabs:
            self._tabs[(profile_id, tab_id)] = Lease(lease.owner_id, self._next())

    def _next(self) -> int:
        self._revision += 1
        return self._revision

    def _effective(
        self, profile_id: str, window_id: int, tab_id: int | None
    ) -> tuple[str | None, Lease | None]:
        window = self._windows.get((profile_id, window_id))
        if window is not None:
            return "window", window
        if tab_id is not None:
            tab = self._tabs.get((profile_id, tab_id))
            if tab is not None:
                return "tab", tab
        return None, None

    def claim_window(self, profile_id: str, window_id: int, client_id: str) -> Lease:
        with self._lock:
            current = self._windows.get((profile_id, window_id))
            if current and current.owner_id not in (None, client_id) and not current.orphaned:
                raise OwnershipConflict("window", window_id, current.owner_id)
            for (profile, tab_id), lease in self._tabs.items():
                if profile != profile_id or self._tab_windows.get((profile, tab_id)) != window_id:
                    continue
                if lease.owner_id not in (None, client_id) and not lease.orphaned:
                    raise OwnershipConflict("tab", tab_id, lease.owner_id)
            lease = Lease(client_id, self._next())
            self._windows[(profile_id, window_id)] = lease
            self._epoch_orphan_windows.discard((profile_id, window_id))
            for key in [
                key
                for key, wid in self._tab_windows.items()
                if key[0] == profile_id and wid == window_id
            ]:
                self._tabs.pop(key, None)
                self._epoch_orphan_tabs.discard(key)
            return lease

    def claim_tab(self, profile_id: str, window_id: int, tab_id: int, client_id: str) -> Lease:
        with self._lock:
            self._tab_windows[(profile_id, tab_id)] = window_id
            # A recovered window marker has no live owner. Splitting it permits
            # the explicit shared-window tab claim while the sibling tab
            # markers remain orphaned and require their own claims.
            self._epoch_orphan_windows.discard((profile_id, window_id))
            scope, effective = self._effective(profile_id, window_id, tab_id)
            if effective and effective.owner_id == client_id and not effective.orphaned:
                return effective
            if effective and effective.owner_id is not None and not effective.orphaned:
                raise OwnershipConflict(
                    scope or "tab", window_id if scope == "window" else tab_id, effective.owner_id
                )
            lease = Lease(client_id, self._next())
            self._tabs[(profile_id, tab_id)] = lease
            self._epoch_orphan_tabs.discard((profile_id, tab_id))
            return lease

    def release_window(self, profile_id: str, window_id: int, client_id: str) -> int:
        with self._lock:
            lease = self._windows.get((profile_id, window_id))
            self._require_mine("window", window_id, lease, client_id)
            revision = self._next()
            self._windows.pop((profile_id, window_id), None)
            for key in [
                key
                for key, wid in self._tab_windows.items()
                if key[0] == profile_id and wid == window_id
            ]:
                self._tabs.pop(key, None)
            return revision

    def release_tab(self, profile_id: str, tab_id: int, client_id: str) -> int:
        with self._lock:
            lease = self._tabs.get((profile_id, tab_id))
            self._require_mine("tab", tab_id, lease, client_id)
            self._tabs.pop((profile_id, tab_id), None)
            return self._next()

    @staticmethod
    def _require_mine(scope: str, target_id: int, lease: Lease | None, client_id: str) -> None:
        if lease is None or lease.owner_id != client_id or lease.orphaned:
            owner = lease.owner_id if lease and lease.owner_id else "none"
            raise OwnershipConflict(scope, target_id, owner)

    def require(
        self,
        profile_id: str,
        window_id: int,
        tab_id: int,
        client_id: str,
        revision: int | None = None,
    ) -> Lease:
        with self._lock:
            scope, lease = self._effective(profile_id, window_id, tab_id)
            if lease is None or lease.owner_id != client_id or lease.orphaned:
                owner = lease.owner_id if lease and lease.owner_id else "none"
                raise OwnershipConflict(
                    scope or "tab", window_id if scope == "window" else tab_id, owner
                )
            if revision is not None and revision != lease.revision:
                raise OwnershipConflict(
                    scope or "tab",
                    window_id if scope == "window" else tab_id,
                    lease.owner_id or "none",
                )
            return lease

    def describe(
        self, profile_id: str, window_id: int, tab_id: int | None, client_id: str
    ) -> dict[str, object]:
        with self._lock:
            scope, lease = self._effective(profile_id, window_id, tab_id)
            if lease is None:
                window_orphan = (profile_id, window_id) in self._epoch_orphan_windows
                tab_orphan = tab_id is not None and (profile_id, tab_id) in self._epoch_orphan_tabs
                if window_orphan or tab_orphan:
                    return {
                        "state": "orphaned",
                        "scope": "window" if window_orphan else "tab",
                        "owner_id": None,
                        "revision": self._revision,
                    }
                return {
                    "state": "unowned",
                    "scope": None,
                    "owner_id": None,
                    "revision": self._revision,
                }
            state = (
                "orphaned"
                if lease.orphaned
                else ("mine" if lease.owner_id == client_id else "other")
            )
            return {
                "state": state,
                "scope": scope,
                "owner_id": lease.owner_id,
                "revision": lease.revision,
            }

    def orphan_client(self, client_id: str) -> None:
        with self._lock:
            for lease in (*self._windows.values(), *self._tabs.values()):
                if lease.owner_id == client_id and not lease.orphaned:
                    lease.orphaned = True
                    lease.revision = self._next()

    def clear_for_new_epoch(self) -> None:
        with self._lock:
            for lease in (*self._windows.values(), *self._tabs.values()):
                lease.orphaned = True
                lease.revision = self._next()
