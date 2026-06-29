# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""BackendResolver: priority order, supports()-gating, create()-fallthrough, Skips."""

import pytest

from computer_use.core.errors import PlatformNotSupportedError
from computer_use.platform.resolver.providers import BackendUnavailable
from computer_use.platform.resolver import BackendResolver, Skip
from computer_use.platform.resolver.session import SessionContext


def _ctx():
    return SessionContext(server="wayland", compositor="gnome", has_uinput=False, libs=frozenset())


class FakeProvider:
    def __init__(self, name, priority, *, supports=True, fail=None, value=None):
        self.name = name
        self.priority = priority
        self._supports = supports
        self._fail = fail
        self._value = value or object()

    def supports(self, ctx):
        return self._supports

    def create(self, ctx):
        if self._fail is not None:
            raise BackendUnavailable(self._fail)
        return self._value


class TestResolve:
    def test_picks_highest_priority_that_works(self):
        hi = FakeProvider("hi", 90)
        lo = FakeProvider("lo", 10)
        backend, skips = BackendResolver([lo, hi]).resolve(_ctx())
        assert backend is hi._value
        assert skips == []

    def test_skips_unsupported_then_picks_next(self):
        top = FakeProvider("top", 90, supports=False)
        win = FakeProvider("win", 50)
        backend, skips = BackendResolver([top, win]).resolve(_ctx())
        assert backend is win._value
        assert [s.name for s in skips] == ["top"]
        assert "not applicable" in skips[0].reason

    def test_falls_through_when_create_raises(self):
        broken = FakeProvider("broken", 90, fail="gnome-screenshot returned all methods failed")
        portal = FakeProvider("portal", 30)
        backend, skips = BackendResolver([portal, broken]).resolve(_ctx())
        assert backend is portal._value
        assert skips[0].name == "broken"
        assert "all methods failed" in skips[0].reason

    def test_raises_with_remediation_when_none_work(self):
        a = FakeProvider("a", 90, supports=False)
        b = FakeProvider("b", 10, fail="no device")
        with pytest.raises(PlatformNotSupportedError) as exc:
            BackendResolver([a, b]).resolve(_ctx())
        assert "a" in str(exc.value) and "b" in str(exc.value)

    def test_skip_trail_is_ordered_by_priority(self):
        a = FakeProvider("a", 90, fail="x")
        b = FakeProvider("b", 80, fail="y")
        c = FakeProvider("c", 70)
        _, skips = BackendResolver([c, a, b]).resolve(_ctx())
        assert [s.name for s in skips] == ["a", "b"]


class TestSkip:
    def test_skip_fields(self):
        s = Skip("grim", "not applicable to this session")
        assert s.name == "grim" and "not applicable" in s.reason
