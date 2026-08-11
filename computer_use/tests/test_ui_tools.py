# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The structured-tier tools, against a fake backend.

None of this proves the AT-SPI tier works - that is the runbook's job. It proves
the plumbing the tier is thin over: the ref lifecycle including element_gone, the
empty-match-is-ok rule, the named errors, ui_wait's timeout, and the honest
degrade when no backend resolves.
"""

from __future__ import annotations

from computer_use.tools.ui import tools as ui
from computer_use.tools.ui.backend import (
    ELEMENT_GONE,
    NO_TREE,
    UNSUPPORTED_ACTION,
    Bounds,
    Element,
    StructuredError,
)

_EL = Element(
    ref="atspi:3f1c/12/4/1",
    role="push button",
    name="Save",
    bounds=Bounds(812, 604, 74, 30),
    states=("enabled", "visible", "showing"),
)


class FakeBackend:
    """A StructuredBackend stand-in with scripted results and failures."""

    def __init__(self, *, elements=(), act=None, act_error=None, wait=None):
        self._elements = list(elements)
        self._act = act or {"state": _EL.as_dict()}
        self._act_error = act_error
        self._wait = wait

    def tree(self, depth):
        return {"root": _EL.as_dict(), "depth": depth}

    def find(self, role, name):
        return [
            e
            for e in self._elements
            if (not role or e.role == role) and (not name or e.name == name)
        ]

    def act(self, ref, action, text):
        if self._act_error is not None:
            raise self._act_error
        return self._act

    def wait(self, role, name, timeout_ms):
        return self._wait

    def capability(self):
        return {"bus_reachable": True, "backend": "fake"}


def _use(monkeypatch, backend):
    monkeypatch.setattr(ui, "resolve_backend", lambda: backend)


class TestDegradesHonestlyWhenUnavailable:
    """No backend must be at_spi_unavailable-with-a-remedy, never a crash."""

    def test_every_tool_reports_unavailable(self, monkeypatch):
        monkeypatch.setattr(ui, "resolve_backend", lambda: None)
        for result in (ui.ui_tree(), ui.ui_find(), ui.ui_act("r", "click"), ui.ui_wait()):
            assert result["ok"] is False
            assert result["error"] == "at_spi_unavailable"
            assert result["remedy"]  # a non-empty one-line remedy


class TestReadContract:
    def test_empty_match_is_ok_not_error(self, monkeypatch):
        _use(monkeypatch, FakeBackend(elements=[]))
        result = ui.ui_find(role="push button")
        assert result["ok"] is True
        assert result["elements"] == []

    def test_find_returns_ref_bounds_and_states(self, monkeypatch):
        _use(monkeypatch, FakeBackend(elements=[_EL]))
        result = ui.ui_find(name="Save")
        assert result["ok"] is True
        (el,) = result["elements"]
        assert el["ref"] == "atspi:3f1c/12/4/1"
        assert el["bounds"] == {"x": 812, "y": 604, "w": 74, "h": 30}
        assert "enabled" in el["states"]

    def test_tree_is_depth_capped_by_the_argument(self, monkeypatch):
        _use(monkeypatch, FakeBackend())
        assert ui.ui_tree(depth=3)["depth"] == 3

    def test_no_tree_is_a_named_error(self, monkeypatch):
        backend = FakeBackend()
        backend.tree = lambda depth: (_ for _ in ()).throw(
            StructuredError(NO_TREE, "gedit exposes no tree")
        )
        _use(monkeypatch, backend)
        result = ui.ui_tree()
        assert result["ok"] is False
        assert result["error"] == NO_TREE


class TestActContract:
    def test_stale_ref_is_element_gone_and_does_not_act(self, monkeypatch):
        _use(monkeypatch, FakeBackend(act_error=StructuredError(ELEMENT_GONE)))
        result = ui.ui_act("atspi:dead/9", "click")
        assert result["ok"] is False
        assert result["error"] == ELEMENT_GONE

    def test_unsupported_action_names_the_error(self, monkeypatch):
        err = StructuredError(UNSUPPORTED_ACTION, supported=["click", "focus"])
        _use(monkeypatch, FakeBackend(act_error=err))
        result = ui.ui_act("atspi:1/2", "toggle")
        assert result["error"] == UNSUPPORTED_ACTION
        assert result["supported"] == ["click", "focus"]

    def test_act_returns_the_reread_state(self, monkeypatch):
        _use(monkeypatch, FakeBackend(act={"state": {"checked": True}}))
        result = ui.ui_act("atspi:1/2", "toggle")
        assert result["ok"] is True
        assert result["state"] == {"checked": True}


class TestWaitContract:
    def test_timeout_reports_elapsed(self, monkeypatch):
        _use(monkeypatch, FakeBackend(wait=None))
        result = ui.ui_wait(role="dialog", timeout_ms=250)
        assert result["ok"] is False
        assert result["error"] == "timeout"
        assert result["elapsed_ms"] == 250

    def test_found_returns_the_element(self, monkeypatch):
        _use(monkeypatch, FakeBackend(wait=_EL))
        result = ui.ui_wait(name="Save")
        assert result["ok"] is True
        assert result["element"]["name"] == "Save"
