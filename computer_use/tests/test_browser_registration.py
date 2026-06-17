# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The browser tools register at Tier ONE with the right risk levels."""


def _load_registry():
    from computer_use import mcp_server  # noqa: F401
    from computer_use.core import REGISTRY

    return REGISTRY


def _by_name(registry, name):
    for t in registry.all():
        if t.name == name:
            return t
    return None


def test_browser_registered_tier_one_medium():
    from computer_use.core import Risk, Tier

    reg = _load_registry()
    t = _by_name(reg, "browser")
    assert t is not None
    assert t.tier == Tier.ONE
    assert t.risk == Risk.MEDIUM


def test_browser_eval_registered_tier_one_high():
    from computer_use.core import Risk, Tier

    reg = _load_registry()
    t = _by_name(reg, "browser_eval")
    assert t is not None
    assert t.tier == Tier.ONE
    assert t.risk == Risk.HIGH
