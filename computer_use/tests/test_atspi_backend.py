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
        pid=0, text=None,
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
        self.pid = pid
        self.text = text
        self.did = []  # (action_index) log
        # Models the toolkit's async state update: a queued change becomes
        # visible only after `reveal` more states() reads, so a re-read done too
        # eagerly sees the stale value (the D1 defect).
        self._pending = None
        self._reveal = 0


class FakeClient:
    """An in-memory accessibility tree keyed by opaque node ids."""

    def __init__(self, nodes: dict, root=("reg", "/root"), *,
                 reachable=True, enabled=False, act_lag=0):
        self._nodes = nodes
        self._root = root
        self._reachable = reachable
        self._enabled = enabled
        self._act_lag = act_lag

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
        fake = self._n(node)
        # Reveal a queued change once its countdown elapses, so an eager re-read
        # sees the pre-action value and a settling one sees the post-action value.
        if fake._reveal > 0:
            fake._reveal -= 1
            if fake._reveal == 0 and fake._pending is not None:
                fake.states.append(fake._pending)
                fake._pending = None
        return tuple(fake.states)

    def extents(self, node):
        ext = self._n(node).extents
        return tuple(ext) if ext is not None else None

    def text(self, node):
        return self._n(node).text

    def interfaces(self, node):
        return tuple(self._n(node).interfaces)

    def actions(self, node):
        return list(self._n(node).actions)

    def do_action(self, node, index):
        fake = self._n(node)
        fake.did.append(index)
        # A GTK toggle button gains "pressed" when its click action fires. With a
        # lag configured, the change is queued and only surfaces after that many
        # states() reads, modelling the toolkit's asynchronous update.
        if fake.role == "toggle button" and "pressed" not in fake.states:
            if self._act_lag > 0:
                fake._pending = "pressed"
                fake._reveal = self._act_lag
            else:
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

    def pid(self, node):
        return self._n(node).pid


def _session(server="wayland"):
    return SessionContext(server=server, compositor="gnome",
                          has_uinput=False, libs=frozenset())


def _tree_with_button(**button_kwargs):
    """A desktop -> app -> active window -> button, with the button tunable.

    The window and button are on screen (showing/visible) so the showing-prune
    keeps them; a test that wants an off-screen element sets its own states.
    """
    defaults = dict(
        role="push button", name="Save", extents=(0, 0, 74, 30),
        interfaces=[_ACCESSIBLE, _COMPONENT, _ACTION], actions=["Click"],
    )
    defaults.update(button_kwargs)
    bstates = list(defaults.get("states", ()))
    for s in ("showing", "visible"):
        if s not in bstates:
            bstates.append(s)
    defaults["states"] = bstates
    button = FakeNode(**defaults)
    nodes = {
        ("reg", "/root"): FakeNode("desktop frame", "main", children=[("app", "/a")]),
        ("app", "/a"): FakeNode("application", "gedit", toolkit="GTK",
                                children=[("win", "/w")]),
        ("win", "/w"): FakeNode("frame", "Doc - gedit",
                                states=["active", "showing", "visible"],
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


class TestActReReadIsPostAction:
    """D1: the returned state must be the element after acting, not before.

    The toolkit updates state asynchronously, so a re-read done the instant
    DoAction returns sees the stale value. The whole contract of ui_act is that
    the action confirms itself from its own response.
    """

    def test_toggle_state_change_survives_the_toolkit_lag(self):
        nodes = _tree_with_button()
        nodes[("btn", "/b")].role = "toggle button"
        # act_lag=2: the pressed state only appears on the second states() read
        # after DoAction, so an eager single read returns the old state.
        backend = _backend(nodes, act_lag=2)
        ref = backend.find("toggle button", "")[0].ref
        result = backend.act(ref, "toggle", "")
        assert "pressed" in result["state"]["states"]


class TestSetTextIsConfirmable:
    """D2: set_text is only trustworthy if the re-read shows the text landed."""

    def test_reread_carries_the_text_that_was_set(self):
        nodes = _tree_with_button(
            role="text box", interfaces=[_ACCESSIBLE, _EDITABLE_TEXT, "org.a11y.atspi.Text"],
            actions=[], text="",
        )
        backend = _backend(nodes)
        ref = backend.find("text box", "")[0].ref
        result = backend.act(ref, "set_text", "hello world")
        assert result["state"]["text"] == "hello world"

    def test_find_surfaces_text_for_text_roles(self):
        nodes = _tree_with_button(role="text box", text="already here",
                                  interfaces=[_ACCESSIBLE, "org.a11y.atspi.Text"])
        backend = _backend(nodes)
        el = backend.find("text box", "")[0]
        assert el.text == "already here"

    def test_a_button_carries_no_text_field(self):
        backend = _backend(_tree_with_button())
        assert backend.find("push button", "")[0].as_dict().get("text") is None


class TestTreeReachesControls:
    """D3: ui_tree must reach the same leaves ui_find reaches.

    GTK stacks anonymous wrapper containers between a window and its controls; a
    tree that stops at the wrappers is no substitute for a screenshot.
    """

    def _deeply_nested(self, wrapper_depth=16):
        # window -> N anonymous generic wrappers -> a named button.
        nodes = {
            ("reg", "/root"): FakeNode("desktop frame", "d", children=[("app", "/a")]),
            ("app", "/a"): FakeNode("application", "app", children=[("win", "/w")]),
        }
        chain = ("win", "/w")
        nodes[chain] = FakeNode("frame", "Win",
                                states=["active", "showing", "visible"])
        parent = chain
        for i in range(wrapper_depth):
            nid = ("g", f"/g{i}")
            nodes[nid] = FakeNode("generic", "", states=["showing", "visible"])
            nodes[parent].children = [nid]
            parent = nid
        btn = ("btn", "/b")
        nodes[btn] = FakeNode("push button", "Deep Save",
                              states=["showing", "visible"],
                              interfaces=[_ACCESSIBLE, _ACTION], actions=["Click"])
        nodes[parent].children = [btn]
        return nodes

    def _leaf_names(self, tree_node):
        names = []
        stack = [tree_node]
        while stack:
            n = stack.pop()
            if not n["children"]:
                names.append(n["name"])
            stack.extend(n["children"])
        return names

    def test_default_depth_reaches_a_control_sixteen_wrappers_deep(self):
        backend = _backend(self._deeply_nested(16))
        tree = backend.tree(depth=6)  # the default; wrappers must be transparent
        assert "Deep Save" in self._leaf_names(tree["root"])

    def test_tree_leaves_include_what_find_returns(self):
        nodes = self._deeply_nested(16)
        backend = _backend(nodes)
        found = {e.name for e in backend.find("push button", "")}
        leaves = set(self._leaf_names(backend.tree(depth=6)["root"]))
        assert found and found <= leaves


class TestBoundsAreSane:
    """D4: garbage extents (unrealised widgets) must not surface as bounds."""

    def test_garbage_extents_yield_no_bounds(self):
        nodes = _tree_with_button(extents=(0, 0, 612489008, 32573))
        backend = _backend(nodes)
        el = backend.find("push button", "")[0]
        assert el.bounds is None

    def test_sane_extents_are_kept(self):
        backend = _backend(_tree_with_button(extents=(10, 20, 74, 30)))
        el = backend.find("push button", "")[0]
        assert el.bounds.as_dict() == {"x": 10, "y": 20, "w": 74, "h": 30}

    def test_negative_size_is_rejected(self):
        backend = _backend(_tree_with_button(extents=(0, 0, -1, 30)))
        assert backend.find("push button", "")[0].bounds is None


class TestOffScreenIsNotSurfaced:
    """D5: an off-screen dialog's controls must not surface as if on screen."""

    def _window_with_hidden_dialog(self):
        return {
            ("reg", "/root"): FakeNode("desktop frame", "d", children=[("app", "/a")]),
            ("app", "/a"): FakeNode("application", "app", children=[("win", "/w")]),
            ("win", "/w"): FakeNode("frame", "Win",
                                    states=["active", "showing", "visible"],
                                    children=[("real", "/r"), ("dlg", "/d")]),
            ("real", "/r"): FakeNode("push button", "Visible Save",
                                     states=["showing", "visible"],
                                     interfaces=[_ACCESSIBLE, _ACTION], actions=["Click"]),
            # An off-screen close-confirmation dialog: not showing, but GTK still
            # reports its buttons as showing. Pruning at the dialog is what keeps
            # them out of the results.
            ("dlg", "/d"): FakeNode("dialog", "", states=["visible"],
                                    children=[("disc", "/disc")]),
            ("disc", "/disc"): FakeNode("push button", "Discard",
                                        states=["showing", "visible"],
                                        interfaces=[_ACCESSIBLE, _ACTION],
                                        actions=["Click"]),
        }

    def test_hidden_dialog_button_is_not_found(self):
        backend = _backend(self._window_with_hidden_dialog())
        assert backend.find("push button", "Discard") == []

    def test_the_visible_control_is_still_found(self):
        backend = _backend(self._window_with_hidden_dialog())
        assert [e.name for e in backend.find("push button", "")] == ["Visible Save"]

    def test_tree_omits_the_off_screen_dialog(self):
        backend = _backend(self._window_with_hidden_dialog())
        tree = backend.tree(depth=6)
        names = []
        stack = [tree["root"]]
        while stack:
            n = stack.pop()
            names.append(n["name"])
            stack.extend(n["children"])
        assert "Discard" not in names
        assert "Visible Save" in names


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


class TestForegroundWindow:
    """The Wayland foreground-window path, migrated off gi onto the client."""

    def _two_active_windows(self):
        # A chrome window then a terminal window, both active. GNOME orders the
        # most recently focused last, so the terminal must win.
        return {
            ("reg", "/root"): FakeNode("desktop frame", "main",
                                       children=[("chrome", "/c"), ("term", "/t")]),
            ("chrome", "/c"): FakeNode("application", "Google Chrome", pid=100,
                                       children=[("cw", "/cw")]),
            ("cw", "/cw"): FakeNode("frame", "Chrome", states=["active"],
                                    extents=(0, 0, 1920, 1080)),
            ("term", "/t"): FakeNode("application", "gnome-terminal", pid=200,
                                     children=[("tw", "/tw")]),
            ("tw", "/tw"): FakeNode("frame", "Terminal", states=["active"],
                                    extents=(0, 0, 800, 600)),
        }

    def test_last_active_window_wins(self, monkeypatch):
        monkeypatch.setattr(atspi, "_proc_comm", lambda pid: "")
        backend = _backend(self._two_active_windows())
        fg = backend.foreground_window()
        assert fg is not None
        assert fg.pid == 200
        assert fg.title == "Terminal"

    def test_app_name_prefers_proc_comm(self, monkeypatch):
        monkeypatch.setattr(atspi, "_proc_comm", lambda pid: "firefox")
        backend = _backend(self._two_active_windows())
        assert backend.foreground_window().app_name == "firefox"

    def test_none_when_no_active_window(self, monkeypatch):
        nodes = self._two_active_windows()
        nodes[("cw", "/cw")].states = []
        nodes[("tw", "/tw")].states = []
        backend = _backend(nodes)
        assert backend.foreground_window() is None

    def test_none_when_bus_unreachable(self):
        backend = _backend(self._two_active_windows(), reachable=False)
        assert backend.foreground_window() is None

    def test_module_helper_is_none_without_a_backend(self, monkeypatch):
        from computer_use.tools.ui import backend as be

        monkeypatch.setattr(be, "resolve_backend", lambda: None)
        assert atspi.foreground_window() is None


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


class TestEnablement:
    """Enablement is a layer: the bus and each toolkit are enabled separately."""

    def test_launch_env_turns_on_qt_accessibility(self):
        env = atspi.accessibility_launch_env({"HOME": "/home/x"})
        assert env["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] == "1"
        assert env["HOME"] == "/home/x"  # the base env is preserved, not replaced

    def test_chromium_flag_forces_renderer_accessibility(self):
        assert "--force-renderer-accessibility" in atspi.chromium_accessibility_flags()

    def test_bus_reachable_is_false_off_linux(self, monkeypatch):
        monkeypatch.setattr(atspi.sys, "platform", "darwin")
        assert atspi.bus_reachable() is False

    def test_enable_bus_is_false_off_linux(self, monkeypatch):
        monkeypatch.setattr(atspi.sys, "platform", "darwin")
        assert atspi.enable_bus() is False


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
