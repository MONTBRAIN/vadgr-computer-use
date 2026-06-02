# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the sub-operation routing primitive in core/ops.py."""

import pytest

from computer_use.core.ops import OperationGroup


class TestOperationGroup:
    def test_registers_and_runs_handler_by_name(self):
        group = OperationGroup("demo")

        @group.operation("greet")
        def _greet():
            return "hi"

        assert group.run("greet") == "hi"

    def test_returns_handler_value(self):
        group = OperationGroup("demo")

        @group.operation("double")
        def _double(n):
            return n * 2

        assert group.run("double", n=21) == 42

    def test_unknown_op_raises_value_error_naming_valid_ops(self):
        group = OperationGroup("demo")

        @group.operation("alpha")
        def _alpha():
            return None

        @group.operation("beta")
        def _beta():
            return None

        with pytest.raises(ValueError) as exc:
            group.run("missing")
        message = str(exc.value)
        assert "demo" in message
        assert "missing" in message
        assert "alpha" in message
        assert "beta" in message

    def test_forwards_only_declared_kwargs(self):
        group = OperationGroup("demo")

        @group.operation("narrow")
        def _narrow(a):
            return a

        # Extra kwargs the handler does not declare must be dropped, not error.
        assert group.run("narrow", a=1, b=2, c=3) == 1

    def test_forwards_everything_to_var_keyword_handler(self):
        group = OperationGroup("demo")

        @group.operation("wide")
        def _wide(**kwargs):
            return kwargs

        assert group.run("wide", a=1, b=2) == {"a": 1, "b": 2}

    def test_rejects_duplicate_registration(self):
        group = OperationGroup("demo")

        @group.operation("once")
        def _once():
            return None

        with pytest.raises(ValueError):

            @group.operation("once")
            def _again():
                return None

    def test_names_are_sorted(self):
        group = OperationGroup("demo")

        @group.operation("zeta")
        def _zeta():
            return None

        @group.operation("alpha")
        def _alpha():
            return None

        assert group.names == ["alpha", "zeta"]
