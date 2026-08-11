# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The AT-SPI backend's logic, against an in-memory fake client.

This proves what the runbook cannot cheaply reach on every push: the ref
lifecycle including element_gone, the verb-to-interface mapping and its
unsupported_action listing, the state-bit decoding, the "no active window is
no_tree" rule, and the coordinate_trust that separates X11 from Wayland. The
live bus is the runbook's job; this is the plumbing the tier is thin over, and a
fake client lets every branch be driven deterministically.
"""

from __future__ import annotations

import pytest

from computer_use.platform.resolver.session import SessionContext
from computer_use.tools.ui import atspi
from computer_use.tools.ui.atspi import AtspiBackend, ElementGone, decode_states
from computer_use.tools.ui.backend import StructuredError

_ACCESSIBLE = "org.a11y.atspi.Accessible"
_COMPONENT = "org.a11y.atspi.Component"
_ACTION = "org.a11y.atspi.Action"
_EDITABLE_TEXT = "org.a11y.atspi.EditableText"


class FakeNode:
    def __init__(
        self, role, name, *, states=(), extents=(0, 0, 0, 0),
        interfaces=(), actions=(), children=(), gone=False, toolkit=None,
    ):
        self.role = role
        self.name = name
        self.states = list(states)
        self.extents = extents
        self.interfaces = list(interfaces)
        self.actions = list(actions)
        self.children = list(children)
        self.gone = gone
        self.toolkit = toolkit
        self.did = []  # (action_index) log
        self.text = None


class FakeClient:
    """An in-memory accessibility tree keyed by opaque node ids."""

    def __init__(self, nodes: dict, root=("reg", "/root"), *,
                 reachable=True, enabled=False):
        self._nodes = nodes
        self._root = root
        self._reachable = reachable
        self._enabled = enabled

    def _n(self, node) -> FakeNode:
        fake = self._nodes.get(node)
        if fake is None or fake.gone:
            raise ElementGone(str(node))
        return fake

    def reachable(self):
        return self._reachable

    def is_enabled(self):
        return self._enabled

    def root(self):
        return self._root

    def children(self, node):
        return list(self._n(node).children)

    def role_name(self, node):
        return self._n(node).role

    def name(self, node):
        return self._n(node).name

    def states(self, node):
        return tuple(self._n(node).states)

    def extents(self, node):
        ext = self._n(node).extents
        return tuple(ext) if ext is not None else None

    def interfaces(self, node):
        return tuple(self._n(node).interfaces)

    def actions(self, node):
        return list(self._n(node).actions)

    def do_action(self, node, index):
        fake = self._n(node)
        fake.did.append(index)
        # A GTK toggle button gains "pressed" when its click action fires; model
        # that so a toggle's re-read is observably different.
        if fake.role == "toggle button" and "pressed" not in fake.states:
            fake.states.append("pressed")
        return True

    def set_text(self, node, text):
        self._n(node).text = text
        return True

    def grab_focus(self, node):
        fake = self._n(node)
        if "focused" not in fake.states:
            fake.states.append("focused")
        return True

    def toolkits(self):
        seen = []
        for fake in self._nodes.values():
            if fake.toolkit and fake.toolkit not in seen:
                seen.append(fake.toolkit)
        return tuple(seen)


def _session(server="wayland"):
    return SessionContext(server=server, compositor="gnome",
                          has_uinput=False, libs=frozenset())


def _tree_with_button(**button_kwargs):
    """A desktop -> app -> active window -> button, with the button tunable."""
    defaults = dict(
        role="push button", name="Save", extents=(0, 0, 74, 30),
        interfaces=[_ACCESSIBLE, _COMPONENT, _ACTION], actions=["Click"],
    )
    defaults.update(button_kwargs)
    button = FakeNode(**defaults)
    nodes = {
        ("reg", "/root"): FakeNode("desktop frame", "main", children=[("app", "/a")]),
        ("app", "/a"): FakeNode("application", "gedit", toolkit="GTK",
                                children=[("win", "/w")]),
        ("win", "/w"): FakeNode("frame", "Doc - gedit", states=["active"],
                                extents=(0, 0, 800, 600),
                                children=[("btn", "/b")]),
        ("btn", "/b"): button,
    }
    return nodes


def _backend(nodes, server="wayland", **client_kwargs):
    return AtspiBackend(FakeClient(nodes, **client_kwargs), _session(server))


class TestStateDecoding:
    def test_pressed_and_has_popup_bits_decode(self):
        # The exact words a real GTK4 "Main Menu" toggle returned after a click:
        # word 0 has focusable/sensitive/showing/visible/pressed, word 1 bit 10
        # is has_popup (state index 42).
        states = decode_states(1125124096, 1024)
        assert "pressed" in states
        assert "has_popup" in states

    def test_no_bits_is_empty(self):
        assert decode_states(0, 0) == ()


class TestCapability:
    def test_coordinate_trust_is_none_on_wayland(self):
        backend = _backend(_tree_with_button(), server="wayland")
        cap = backend.capability()
        assert cap["coordinate_trust"] == "none"
        assert cap["backend"] == "atspi"
        assert cap["bus_reachable"] is True

    def test_coordinate_trust_is_real_on_x11(self):
        backend = _backend(_tree_with_button(), server="x11")
        assert backend.capability()["coordinate_trust"] == "real"

    def test_unreachable_bus_reports_no_toolkits(self):
        backend = _backend(_tree_with_button(), reachable=False)
        cap = backend.capability()
        assert cap["bus_reachable"] is False
        assert cap["toolkits_seen"] == []


class TestReadPath:
    def test_tree_returns_active_window_root_with_children(self):
        backend = _backend(_tree_with_button())
        result = backend.tree(depth=6)
        assert result["root"]["role"] == "frame"
        assert result["root"]["children"][0]["name"] == "Save"

    def test_tree_depth_caps_recursion(self):
        backend = _backend(_tree_with_button())
        # depth 0 returns the window itself with no children expanded.
        result = backend.tree(depth=0)
        assert result["root"]["children"] == []

    def test_find_by_role_returns_ref_bounds_states(self):
        backend = _backend(_tree_with_button(states=["enabled"]))
        elements = backend.find("push button", "")
        assert len(elements) == 1
        el = elements[0]
        assert el.ref.startswith("atspi:")
        assert el.bounds.as_dict() == {"x": 0, "y": 0, "w": 74, "h": 30}
        assert "enabled" in el.states

    def test_find_by_name_is_case_insensitive_substring(self):
        backend = _backend(_tree_with_button())
        assert backend.find("", "sav")  # substring, lowered
        assert backend.find("", "nope") == []

    def test_no_active_window_is_no_tree(self):
        nodes = _tree_with_button()
        nodes[("win", "/w")].states = []  # nothing is active
        backend = _backend(nodes)
        with pytest.raises(StructuredError) as exc:
            backend.find("push button", "")
        assert exc.value.code == "no_tree"


class TestRefLifecycle:
    def test_find_ref_resolves_in_a_later_act(self):
        backend = _backend(_tree_with_button())
        ref = backend.find("push button", "")[0].ref
        result = backend.act(ref, "click", "")
        assert result["state"]["name"] == "Save"

    def test_unknown_ref_is_element_gone(self):
        backend = _backend(_tree_with_button())
        with pytest.raises(StructuredError) as exc:
            backend.act("atspi:deadbeef", "click", "")
        assert exc.value.code == "element_gone"

    def test_ref_to_a_vanished_element_is_element_gone(self):
        nodes = _tree_with_button()
        backend = _backend(nodes)
        ref = backend.find("push button", "")[0].ref
        nodes[("btn", "/b")].gone = True  # the element goes away after the find
        with pytest.raises(StructuredError) as exc:
            backend.act(ref, "click", "")
        assert exc.value.code == "element_gone"

    def test_same_element_reuses_its_ref(self):
        backend = _backend(_tree_with_button())
        first = backend.find("push button", "")[0].ref
        second = backend.find("push button", "")[0].ref
        assert first == second


class TestActVerbs:
    def test_click_fires_the_named_action(self):
        nodes = _tree_with_button()
        backend = _backend(nodes)
        ref = backend.find("push button", "")[0].ref
        backend.act(ref, "click", "")
        assert nodes[("btn", "/b")].did == [0]  # index of "Click"

    def test_toggle_rereads_the_new_state(self):
        nodes = _tree_with_button()
        nodes[("btn", "/b")].role = "toggle button"
        backend = _backend(nodes)
        ref = backend.find("toggle button", "")[0].ref
        result = backend.act(ref, "toggle", "")
        assert "pressed" in result["state"]["states"]

    def test_focus_grabs_when_component_present(self):
        nodes = _tree_with_button()
        backend = _backend(nodes)
        ref = backend.find("push button", "")[0].ref
        result = backend.act(ref, "focus", "")
        assert "focused" in result["state"]["states"]

    def test_set_text_writes_editable_text(self):
        nodes = _tree_with_button(role="entry",
                                  interfaces=[_ACCESSIBLE, _EDITABLE_TEXT],
                                  actions=[])
        nodes[("btn", "/b")].role = "entry"
        backend = _backend(nodes)
        ref = backend.find("entry", "")[0].ref
        backend.act(ref, "set_text", "hello")
        assert nodes[("btn", "/b")].text == "hello"

    def test_unknown_verb_lists_supported(self):
        backend = _backend(_tree_with_button())
        ref = backend.find("push button", "")[0].ref
        with pytest.raises(StructuredError) as exc:
            backend.act(ref, "levitate", "")
        assert exc.value.code == "unsupported_action"
        assert "click" in exc.value.extra["supported"]

    def test_click_on_element_without_click_action_lists_its_actions(self):
        nodes = _tree_with_button(actions=["Expand"])
        backend = _backend(nodes)
        ref = backend.find("push button", "")[0].ref
        with pytest.raises(StructuredError) as exc:
            backend.act(ref, "click", "")
        assert exc.value.code == "unsupported_action"
        assert exc.value.extra["supported"] == ["Expand"]

    def test_set_text_without_editable_interface_is_unsupported(self):
        backend = _backend(_tree_with_button())  # button has no EditableText
        ref = backend.find("push button", "")[0].ref
        with pytest.raises(StructuredError) as exc:
            backend.act(ref, "set_text", "x")
        assert exc.value.code == "unsupported_action"

    def test_focus_without_component_is_unsupported(self):
        nodes = _tree_with_button(interfaces=[_ACCESSIBLE, _ACTION])
        backend = _backend(nodes)
        ref = backend.find("push button", "")[0].ref
        with pytest.raises(StructuredError) as exc:
            backend.act(ref, "focus", "")
        assert exc.value.code == "unsupported_action"


class TestBusUnavailable:
    def test_every_read_and_act_needs_a_reachable_bus(self):
        backend = _backend(_tree_with_button(), reachable=False)
        for call in (
            lambda: backend.tree(3),
            lambda: backend.find("push button", ""),
            lambda: backend.act("atspi:1", "click", ""),
            lambda: backend.wait("push button", "", 0),
        ):
            with pytest.raises(StructuredError) as exc:
                call()
            assert exc.value.code == "at_spi_unavailable"
            assert exc.value.extra["remedy"]


class TestWait:
    def test_returns_the_first_match_immediately(self):
        backend = _backend(_tree_with_button())
        element = backend.wait("push button", "", 1000)
        assert element is not None
        assert element.name == "Save"

    def test_returns_none_on_timeout(self):
        backend = _backend(_tree_with_button())
        assert backend.wait("dialog", "", 0) is None


class TestBuildBackend:
    def test_off_linux_there_is_no_backend(self, monkeypatch):
        monkeypatch.setattr(atspi.sys, "platform", "darwin")
        assert atspi.build_atspi_backend() is None


class TestStructuredCapabilityHelper:
    """tools.ui.backend.structured_capability is what get_platform_info reads."""

    def test_reports_unavailable_when_no_backend_resolves(self, monkeypatch):
        from computer_use.tools.ui import backend as be

        monkeypatch.setattr(be, "resolve_backend", lambda: None)
        cap = be.structured_capability()
        assert cap["available"] is False
        assert cap["backend"] is None

    def test_reports_the_backends_capability_when_resolved(self, monkeypatch):
        from computer_use.tools.ui import backend as be

        b = _backend(_tree_with_button(), server="x11")
        monkeypatch.setattr(be, "resolve_backend", lambda: b)
        cap = be.structured_capability()
        assert cap["backend"] == "atspi"
        assert cap["coordinate_trust"] == "real"
        # available tracks bus reachability: a resolved backend on a reachable
        # bus is usable, which is what a caller checks before choosing the tier.
        assert cap["available"] is True


class TestPlatformDefaultIsHonest:
    """The other three platforms answer 'no structured tier', never a stub."""

    def test_base_backend_reports_no_structured_tier(self):
        from computer_use.platform.base import PlatformBackend

        class _Bare(PlatformBackend):
            def get_screen_capture(self):
                raise NotImplementedError

            def get_action_executor(self):
                raise NotImplementedError

            def is_available(self):
                return True

            def get_foreground_window(self):
                return None

        cap = _Bare().structured_capability()
        assert cap["available"] is False
        assert cap["backend"] is None
