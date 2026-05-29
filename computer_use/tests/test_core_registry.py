# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the new core/ framework: @tool decorator + ToolRegistry +
Tier and Risk enums. Pinned to the contract in ARCHITECTURE.md §5.6, §5.7.
"""

import pytest


@pytest.fixture
def fresh_registry():
    """Yield an isolated ToolRegistry instance (does not touch the global)."""
    from computer_use.core.registry import ToolRegistry

    yield ToolRegistry()


# --- Tier enum ---


class TestTierEnum:
    def test_has_zero(self):
        from computer_use.core.tier import Tier

        assert Tier.ZERO.value == 0

    def test_has_half(self):
        from computer_use.core.tier import Tier

        # Tier 0.5 — CLI wrappers per §5.1
        assert Tier.HALF.value == 0.5

    def test_has_one(self):
        from computer_use.core.tier import Tier

        assert Tier.ONE.value == 1

    def test_has_two(self):
        from computer_use.core.tier import Tier

        assert Tier.TWO.value == 2

    def test_no_three(self):
        from computer_use.core.tier import Tier

        values = {t.value for t in Tier}
        assert 3 not in values


# --- Risk enum ---


class TestRiskEnum:
    def test_has_read_only(self):
        from computer_use.core.risk import Risk

        assert Risk.READ_ONLY.value == "read_only"

    def test_has_low(self):
        from computer_use.core.risk import Risk

        assert Risk.LOW.value == "low"

    def test_has_medium(self):
        from computer_use.core.risk import Risk

        assert Risk.MEDIUM.value == "medium"

    def test_has_high(self):
        from computer_use.core.risk import Risk

        assert Risk.HIGH.value == "high"


# --- @tool decorator ---


class TestToolDecorator:
    def test_decorates_and_registers(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        @tool(name="dummy_a", tier=Tier.TWO, risk=Risk.LOW)
        def dummy():
            return "ok"

        entry = fresh_registry.get("dummy_a")
        assert entry is not None
        assert entry.name == "dummy_a"
        assert entry.tier == Tier.TWO
        assert entry.risk == Risk.LOW

    def test_decorator_preserves_function_call(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        @tool(name="dummy_b", tier=Tier.TWO, risk=Risk.LOW)
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_decorator_preserves_function_metadata(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        @tool(name="dummy_c", tier=Tier.TWO, risk=Risk.LOW)
        def my_func(x):
            """A docstring."""
            return x

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "A docstring."

    def test_rejects_invalid_tier(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk

        tool = make_tool_decorator(fresh_registry)

        with pytest.raises((TypeError, ValueError)):

            @tool(name="bad_tier", tier=3, risk=Risk.LOW)
            def bad():
                pass

    def test_rejects_invalid_risk(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        with pytest.raises((TypeError, ValueError)):

            @tool(name="bad_risk", tier=Tier.TWO, risk="extreme")
            def bad():
                pass

    def test_rejects_blank_name(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        with pytest.raises(ValueError):

            @tool(name="", tier=Tier.TWO, risk=Risk.LOW)
            def bad():
                pass

    def test_rejects_duplicate_name(self, fresh_registry):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(fresh_registry)

        @tool(name="dup", tier=Tier.TWO, risk=Risk.LOW)
        def one():
            return 1

        with pytest.raises(ValueError, match="already registered"):

            @tool(name="dup", tier=Tier.TWO, risk=Risk.LOW)
            def two():
                return 2


# --- ToolRegistry ---


class TestToolRegistry:
    def _make_some(self, registry, *, count=3):
        from computer_use.core.decorator import make_tool_decorator
        from computer_use.core.risk import Risk
        from computer_use.core.tier import Tier

        tool = make_tool_decorator(registry)
        tiers = [Tier.ZERO, Tier.ONE, Tier.TWO, Tier.HALF]
        risks = [Risk.READ_ONLY, Risk.LOW, Risk.MEDIUM, Risk.HIGH]
        for i in range(count):
            t = tiers[i % len(tiers)]
            r = risks[i % len(risks)]

            @tool(name=f"t_{i}", tier=t, risk=r)
            def fn(_i=i):
                return _i

        return registry

    def test_count_starts_at_zero(self, fresh_registry):
        assert fresh_registry.count() == 0

    def test_count_grows(self, fresh_registry):
        self._make_some(fresh_registry, count=4)
        assert fresh_registry.count() == 4

    def test_all_returns_iterable(self, fresh_registry):
        self._make_some(fresh_registry, count=3)
        names = {t.name for t in fresh_registry.all()}
        assert names == {"t_0", "t_1", "t_2"}

    def test_get_unknown_returns_none(self, fresh_registry):
        assert fresh_registry.get("does-not-exist") is None

    def test_by_tier(self, fresh_registry):
        from computer_use.core.tier import Tier

        self._make_some(fresh_registry, count=8)
        # tiers cycle through ZERO, ONE, TWO, HALF, ZERO, ONE, TWO, HALF
        zero = list(fresh_registry.by_tier(Tier.ZERO))
        assert {t.name for t in zero} == {"t_0", "t_4"}
        two = list(fresh_registry.by_tier(Tier.TWO))
        assert {t.name for t in two} == {"t_2", "t_6"}

    def test_by_risk(self, fresh_registry):
        from computer_use.core.risk import Risk

        self._make_some(fresh_registry, count=8)
        # risks cycle through READ_ONLY, LOW, MEDIUM, HIGH, READ_ONLY, LOW, MEDIUM, HIGH
        ro = list(fresh_registry.by_risk(Risk.READ_ONLY))
        assert {t.name for t in ro} == {"t_0", "t_4"}

    def test_tier_breakdown(self, fresh_registry):
        from computer_use.core.tier import Tier

        self._make_some(fresh_registry, count=8)
        breakdown = fresh_registry.tier_breakdown()
        assert breakdown[Tier.ZERO] == 2
        assert breakdown[Tier.ONE] == 2
        assert breakdown[Tier.TWO] == 2
        assert breakdown[Tier.HALF] == 2

    def test_global_singleton_exists(self):
        from computer_use.core import REGISTRY

        # The module-level REGISTRY is the singleton used by the @tool
        # decorator that the public core API exposes.
        assert REGISTRY is not None
        assert hasattr(REGISTRY, "all")
        assert hasattr(REGISTRY, "get")
