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

    def test_unknown_child_count_is_never_complete(self):
        # A negative child count is AT-SPI for "unknown". LibreOffice exports
        # its document body with child_count=-1 and no cached children while a
        # live GetChildren returns the paragraph; trusting the cache here hides
        # the one element the document window exists for.
        body = [
            _item("bus", "/frame", "/app", 0, 1, 23, "Writer"),
            _item("bus", "/doc", "/frame", 0, -1, 55, "Document"),
        ]
        snap = build_snapshot(body, decode_states)
        assert snap.is_complete(("bus", "/doc")) is False

    def test_unknown_child_count_with_cached_children_is_still_not_complete(self):
        # Even with some children cached, a declared -1 cannot vouch that they
        # are all of them, so the read must go live.
        body = [
            _item("bus", "/menu", "/app", 0, -1, 33, "File"),
            _item("bus", "/item", "/menu", 0, 0, 35, "Open"),
        ]
        snap = build_snapshot(body, decode_states)
        assert snap.is_complete(("bus", "/menu")) is False


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


class _Variant:
    def __init__(self, value):
        self.value = value


class _FakeBus:
    """A stand-in bus: canned GetItems per app, and counted live calls.

    ``call`` returns a resolved reply (not a coroutine) and ``run`` passes it
    through, which is all _DbusClient needs, so no event loop is involved.

    ``texts`` maps (dest, path) to the node's real text. GetText answers the
    way LibreOffice's bridge does, because that is the behaviour the client
    must survive: an end offset past the character count returns "", never a
    clamped read (GTK clamps; LibreOffice does not).
    """

    def __init__(self, get_items: dict, live_role="LIVE-ROLE", live_children=None,
                 texts=None, hang_members=None, hang_dests=None,
                 action_names=None, blank_bulk_actions=False,
                 silent_settext=False):
        self._get_items = get_items
        self._live_role = live_role
        self._live_children = live_children or {}
        self._texts = texts or {}
        self._hang_members = hang_members or set()
        self._hang_dests = hang_dests  # None hangs every dest for a hung member
        self._action_names = action_names or {}
        self._blank_bulk_actions = blank_bulk_actions
        self._silent_settext = silent_settext
        self.extents_answer = None
        self.live_calls = 0

    _HANG = object()  # a call whose reply never arrives; run() raises on it

    def call(self, dest, path, iface, member, signature="", body=None):
        if member in self._hang_members and (
            self._hang_dests is None or dest in self._hang_dests
        ):
            # The real bus raises when the reply future is *awaited*, not when
            # the message is built, so the sentinel defers the raise to run().
            self.live_calls += 1
            return self._HANG
        if member == "GetExtents" and self.extents_answer is not None:
            self.live_calls += 1
            return _Reply([list(self.extents_answer)])
        if member == "GetActions":
            self.live_calls += 1
            names = self._action_names.get((dest, path), [])
            shown = ["" for _ in names] if self._blank_bulk_actions else names
            return _Reply([[[n, "", ""] for n in shown]])
        if member == "GetName" and iface == "org.a11y.atspi.Action":
            self.live_calls += 1
            names = self._action_names.get((dest, path), [])
            index = body[0]
            return _Reply([names[index] if index < len(names) else ""])
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
            kids = self._live_children.get((dest, path), [])
            return _Reply([[list(k) for k in kids]])
        if member == "SetTextContents":
            self.live_calls += 1
            if not self._silent_settext:
                self._texts[(dest, path)] = body[0]
            return _Reply([True])
        if member == "DeleteText":
            self.live_calls += 1
            value = self._texts.get((dest, path), "")
            start, end = body
            self._texts[(dest, path)] = value[:start] + value[end:]
            return _Reply([True])
        if member == "InsertText":
            self.live_calls += 1
            value = self._texts.get((dest, path), "")
            pos, text, length = body
            self._texts[(dest, path)] = value[:pos] + text[:length] + value[pos:]
            return _Reply([True])
        if member == "GetText":
            value = self._texts.get((dest, path), "")
            start, end = body
            if end == -1:
                end = len(value)
            if end > len(value):
                return _Reply([""])  # the LibreOffice out-of-range answer
            return _Reply([value[start:end]])
        if member == "Get" and body == ["org.a11y.atspi.Text", "CharacterCount"]:
            value = self._texts.get((dest, path), "")
            return _Reply([_Variant(len(value))])
        return _Reply([""])

    def run(self, value):
        if value is self._HANG:
            raise TimeoutError()
        return value

    def gather(self, calls):
        # Mirrors the real bus: each call is bounded on its own, so one that
        # never answers comes back as its exception rather than sinking the
        # whole batch.
        out = []
        for spec in calls:
            value = self.call(*spec)
            out.append(TimeoutError() if value is self._HANG else value)
        return out


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

    def test_unknown_child_count_falls_back_to_a_live_children_read(self):
        # The observed LibreOffice shape: the cache advertises the node but
        # declares child_count=-1 and holds no children for it, while a live
        # GetChildren returns the real child. The client must walk live rather
        # than trust the empty cached child list.
        body = [_one_item("soffice", "/doc", "/frame", -1, 55, "Document")]
        bus = _FakeBus(
            {"soffice": body},
            live_children={("soffice", "/doc"): [["soffice", "/para"]]},
        )
        client = _DbusClient(bus)
        client.warm_caches(["soffice"])
        kids = client.children(("soffice", "/doc"))
        assert kids == [("soffice", "/para")]

    def test_extents_timeout_degrades_to_no_bounds_and_trips_the_breaker(self):
        # The Ubuntu App Center's Flutter embedder never answers GetExtents
        # (observed: a dbind timeout from gi.Atspi too, so it is the app, not
        # the client). One unanswered call must read as "no bounds", and the
        # app must not be asked again: a per-element five-second stall would
        # turn one ui_tree of that app into minutes.
        bus = _FakeBus({}, hang_members={"GetExtents"})
        client = _DbusClient(bus)
        assert client.extents(("snapstore", "/btn")) is None
        calls_after_first = bus.live_calls
        assert client.extents(("snapstore", "/other")) is None
        assert bus.live_calls == calls_after_first  # breaker: no second ask

    def test_extents_breaker_is_per_app_not_global(self):
        bus = _FakeBus({}, hang_members={"GetExtents"}, hang_dests={"snapstore"})
        client = _DbusClient(bus)
        assert client.extents(("snapstore", "/btn")) is None
        # Another app still answers (the fake returns a plain empty reply body
        # for unknown members, which extents() cannot parse into four ints, so
        # give it a real answer).
        bus.extents_answer = (1, 2, 3, 4)
        assert client.extents(("gtk", "/btn")) == (1, 2, 3, 4)

    def test_a_getitems_timeout_leaves_other_apps_warm_and_is_not_reasked(self):
        # The Ubuntu App Center never answers Cache.GetItems (observed on the
        # wire: every warm_caches gathered it for five seconds and the raw
        # TimeoutError killed the whole find). The timed-out app degrades to
        # live reads, the other apps' snapshots still warm, and the app is not
        # asked for GetItems again: every later find would re-pay the stall.
        body = [_one_item("gtk", "/btn", "/frame", 0, 43, "7")]
        bus = _FakeBus({"gtk": body}, hang_members={"GetItems"},
                       hang_dests={"snapstore"})
        client = _DbusClient(bus)
        client.warm_caches(["snapstore", "gtk"])
        # gtk is warm: its name comes from the snapshot, no live call.
        before = bus.live_calls
        assert client.name(("gtk", "/btn")) == "7"
        assert bus.live_calls == before
        # A later warm never asks the timed-out app again.
        before = bus.live_calls
        client.warm_caches(["snapstore"])
        assert bus.live_calls == before

    def test_a_silent_settextcontents_falls_back_to_delete_plus_insert(self):
        # Flutter's embedder answers SetTextContents with success and writes
        # nothing (observed on the Ubuntu App Center search field), while its
        # InsertText lands. A write that does not read back is retried as
        # delete-plus-insert, and the return value is the read-back, not the
        # bridge's unconditional success flag.
        bus = _FakeBus({}, texts={("snapstore", "/entry"): "old"},
                       silent_settext=True)
        client = _DbusClient(bus)
        assert client.set_text(("snapstore", "/entry"), "blender") is True
        assert bus._texts[("snapstore", "/entry")] == "blender"

    def test_a_landed_settextcontents_needs_no_fallback_writes(self):
        bus = _FakeBus({}, texts={("gtk", "/entry"): "old"})
        client = _DbusClient(bus)
        assert client.set_text(("gtk", "/entry"), "new") is True
        assert bus._texts[("gtk", "/entry")] == "new"

    def test_a_write_that_never_lands_reports_false(self):
        # Both write paths refused: the client must say so, not return the
        # adaptor's unconditional True (the at-spi2 adaptor always answers
        # success, so the read-back is the only truth available).
        bus = _FakeBus({}, texts={("ro", "/para"): "locked"},
                       silent_settext=True, hang_members={"InsertText"})
        client = _DbusClient(bus)
        try:
            landed = client.set_text(("ro", "/para"), "new")
        except Exception:
            landed = False
        assert landed is False

    def test_a_per_node_read_that_never_answers_is_element_gone(self):
        # After the Ubuntu App Center navigates, its replaced nodes answer
        # nothing at all (GetState observed hanging; gi.Atspi times out on them
        # the same way). A node the app will not answer for is exactly an
        # unreachable node: ElementGone, which every walk already skips, rather
        # than a raw TimeoutError that kills the whole find.
        from computer_use.tools.ui.atspi import ElementGone
        bus = _FakeBus({}, hang_members={"GetState"})
        client = _DbusClient(bus)
        with pytest.raises(ElementGone):
            client.states(("snapstore", "/stale"))

    def test_unnamed_bulk_actions_fall_back_to_per_index_getname(self):
        # The Ubuntu App Center's Flutter embedder answers GetActions with the
        # right number of entries but every name empty, while the per-index
        # Action.GetName answers "Tap" and "Focus" (observed; gi.Atspi reads the
        # same). An empty bulk name is re-asked per index, or every Flutter
        # button reports two unnameable actions and no verb can resolve.
        bus = _FakeBus({}, action_names={("snapstore", "/btn"): ["Tap", "Focus"]},
                       blank_bulk_actions=True)
        client = _DbusClient(bus)
        assert client.actions(("snapstore", "/btn")) == ["Tap", "Focus"]

    def test_named_bulk_actions_need_no_extra_reads(self):
        bus = _FakeBus({}, action_names={("gtk", "/btn"): ["click"]})
        client = _DbusClient(bus)
        before = bus.live_calls
        assert client.actions(("gtk", "/btn")) == ["click"]
        assert bus.live_calls == before + 1  # one bulk read, no per-index calls

    def test_text_survives_a_bridge_that_rejects_out_of_range_reads(self):
        # LibreOffice answers GetText(0, end) with "" whenever end exceeds the
        # character count, where GTK clamps and answers with the full text. A
        # fixed-cap read therefore reported every Writer paragraph as empty,
        # which made a landed set_text look like a no-op. An empty first read
        # is re-checked against CharacterCount and re-read with the real range.
        bus = _FakeBus({}, texts={("soffice", "/para"): "landed text"})
        client = _DbusClient(bus)
        assert client.text(("soffice", "/para")) == "landed text"

    def test_text_of_a_truly_empty_element_stays_empty(self):
        bus = _FakeBus({}, texts={("soffice", "/para"): ""})
        client = _DbusClient(bus)
        assert client.text(("soffice", "/para")) == ""

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
