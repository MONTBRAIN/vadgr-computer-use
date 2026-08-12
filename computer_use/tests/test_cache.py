# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The Cache GetItems parser, against a synthetic reply body.

The parsing is the pure part of the fast path, so it is proven without a live
bus: the node keying, the child grouping and ordering, the completeness check
that decides when to fall back to a live read, and the shared state decoding.
"""

from __future__ import annotations

import pytest

from computer_use.tools.ui.atspi import decode_states
from computer_use.tools.ui.cache import build_snapshot


def _item(bus, path, parent_path, index, child_count, role_enum, name,
          interfaces=(), states=(0, 0), app_path="/app"):
    # One GetItems struct: (ref, app, parent, index, child_count, interfaces,
    # name, role, description, states). refs are (so) = (bus_name, path).
    return [
        [bus, path], [bus, app_path], [bus, parent_path], index, child_count,
        list(interfaces), name, role_enum, "", list(states),
    ]


def _body():
    # frame -> [button "7", button "8"]; the frame declares 2 children.
    return [
        _item("bus", "/frame", "/app", 0, 2, 23, "Calculator"),
        _item("bus", "/b7", "/frame", 0, 0, 43, "7"),
        _item("bus", "/b8", "/frame", 1, 0, 43, "8"),
    ]


class TestSnapshotStructure:
    def test_keys_by_node_and_counts_items(self):
        snap = build_snapshot(_body(), decode_states)
        assert len(snap) == 3
        assert snap.has(("bus", "/frame"))
        assert snap.item(("bus", "/b7")).name == "7"
        assert snap.item(("bus", "/b7")).role_enum == 43

    def test_children_grouped_by_parent_in_index_order(self):
        # Feed the children out of order; they must come back sorted by index.
        body = [
            _item("bus", "/frame", "/app", 0, 2, 23, "Calculator"),
            _item("bus", "/b8", "/frame", 1, 0, 43, "8"),
            _item("bus", "/b7", "/frame", 0, 0, 43, "7"),
        ]
        snap = build_snapshot(body, decode_states)
        assert snap.children(("bus", "/frame")) == [("bus", "/b7"), ("bus", "/b8")]

    def test_role_enums_collected(self):
        snap = build_snapshot(_body(), decode_states)
        assert snap.role_enums() == {23, 43}
        assert snap.node_with_role(43) in (("bus", "/b7"), ("bus", "/b8"))


class TestCompleteness:
    def test_complete_node_holds_all_declared_children(self):
        snap = build_snapshot(_body(), decode_states)
        assert snap.is_complete(("bus", "/frame")) is True

    def test_incomplete_node_is_flagged_for_a_live_read(self):
        # The frame declares 2 children but only one is in the cache: not warm.
        body = [
            _item("bus", "/frame", "/app", 0, 2, 23, "Calculator"),
            _item("bus", "/b7", "/frame", 0, 0, 43, "7"),
        ]
        snap = build_snapshot(body, decode_states)
        assert snap.is_complete(("bus", "/frame")) is False

    def test_absent_node_is_not_complete(self):
        snap = build_snapshot(_body(), decode_states)
        assert snap.is_complete(("bus", "/missing")) is False


class TestStateDecodingMatchesLivePath:
    def test_states_decode_with_the_shared_function(self):
        # Word 0 bit 20 is pressed, exactly as the live GetState path decodes it.
        body = [_item("bus", "/t", "/app", 0, 0, 62, "Toggle",
                      states=(1 << 20, 0))]
        snap = build_snapshot(body, decode_states)
        assert "pressed" in snap.item(("bus", "/t")).states


# ---------------------------------------------------------------------------
# The client's use of the cache: serve from a warm snapshot, degrade without one
# ---------------------------------------------------------------------------

# dbus-fast is a Linux-only dependency (sys_platform == 'linux' in pyproject),
# so the client tests skip where it is absent while the pure parser tests above
# still run on every OS.
try:
    from dbus_fast import MessageType
    _HAS_DBUS_FAST = True
except ModuleNotFoundError:
    MessageType = None
    _HAS_DBUS_FAST = False

from computer_use.tools.ui.atspi import _DbusClient


class _Reply:
    def __init__(self, body, error_name=None):
        self.body = body
        self.error_name = error_name
        self.message_type = (
            MessageType.ERROR if error_name else MessageType.METHOD_RETURN
        )


class _FakeBus:
    """A stand-in bus: canned GetItems per app, and counted live calls.

    ``call`` returns a resolved reply (not a coroutine) and ``run`` passes it
    through, which is all _DbusClient needs, so no event loop is involved.
    """

    def __init__(self, get_items: dict, live_role="LIVE-ROLE"):
        self._get_items = get_items
        self._live_role = live_role
        self.live_calls = 0

    def call(self, dest, path, iface, member, signature="", body=None):
        if member == "GetItems":
            items = self._get_items.get(dest)
            if items is None:
                return _Reply(None, error_name="org.freedesktop.DBus.Error.UnknownMethod")
            return _Reply([items])
        # Any per-node read here is a live fallback; count it and answer plainly.
        self.live_calls += 1
        if member == "GetRoleName":
            return _Reply([self._live_role])
        if member == "GetChildren":
            return _Reply([[]])
        return _Reply([""])

    def run(self, value):
        return value

    def gather(self, calls):
        return [self.call(*spec) for spec in calls]


def _one_item(bus, path, parent, cc, role_enum, name):
    return [[bus, path], [bus, "/app"], [bus, parent], 0, cc, [], name,
            role_enum, "", [0, 0]]


@pytest.mark.skipif(not _HAS_DBUS_FAST,
                    reason="dbus-fast is installed on Linux only")
class TestClientServesFromCache:
    def test_role_and_name_come_from_the_snapshot_not_the_bus(self):
        body = [_one_item("gtk", "/btn", "/frame", 0, 43, "7")]
        bus = _FakeBus({"gtk": body})
        client = _DbusClient(bus)
        client.warm_caches(["gtk"])
        # role calibration is one live GetRoleName per distinct enum; after that,
        # reading the node's role and name touches the bus no further.
        calls_after_warm = bus.live_calls
        assert client.role_name(("gtk", "/btn")) == "LIVE-ROLE"  # calibrated name
        assert client.name(("gtk", "/btn")) == "7"
        assert bus.live_calls == calls_after_warm  # served from the snapshot

    def test_cache_absent_app_degrades_to_live(self):
        # The app exports no Cache (GetItems errors), so every read is a live call.
        bus = _FakeBus({})  # no app has items
        client = _DbusClient(bus)
        client.warm_caches(["chromium"])
        before = bus.live_calls
        client.role_name(("chromium", "/x"))
        client.name(("chromium", "/x"))
        assert bus.live_calls > before  # it went to the bus, not a snapshot

    def test_invalidate_drops_only_that_apps_snapshot(self):
        # Acting invalidates the target app's snapshot so the act-time reads are
        # live; every other app's snapshot stays warm.
        body_a = [_one_item("gtk", "/btn", "/frame", 0, 43, "7")]
        body_b = [_one_item("qt", "/btn", "/frame", 0, 43, "8")]
        bus = _FakeBus({"gtk": body_a, "qt": body_b})
        client = _DbusClient(bus)
        client.warm_caches(["gtk", "qt"])
        client.invalidate(("gtk", "/btn"))
        before = bus.live_calls
        client.name(("gtk", "/btn"))
        assert bus.live_calls > before  # the invalidated app reads live now
        before = bus.live_calls
        assert client.name(("qt", "/btn")) == "8"
        assert bus.live_calls == before  # the other app is still snapshot-served
