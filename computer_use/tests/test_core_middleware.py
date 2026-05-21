# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Middleware chain tests.

The chain is a lightweight observability hook only — it lets the runtime
emit structured telemetry events around tool calls. Authorization, denylist,
redaction, approval prompts, and auth-mode policy are NOT cua concerns;
those live in the host's agent loop (see vadgr's engine/policy/* modules).
"""

import logging


# --- Chain ordering / composition ---


class TestMiddlewareChain:
    def test_runs_in_registered_order(self):
        from computer_use.core.middleware.base import Middleware, ToolCall
        from computer_use.core.middleware.chain import MiddlewareChain

        order = []

        class Marker(Middleware):
            def __init__(self, label):
                self.label = label

            def before(self, call: ToolCall) -> ToolCall:
                order.append(f"before:{self.label}")
                return call

            def after(self, call: ToolCall, result):
                order.append(f"after:{self.label}")
                return result

        chain = MiddlewareChain([Marker("a"), Marker("b"), Marker("c")])
        chain.dispatch(
            ToolCall(name="x", args=(), kwargs={}), lambda: order.append("handler") or "r"
        )

        assert order == [
            "before:a",
            "before:b",
            "before:c",
            "handler",
            "after:c",
            "after:b",
            "after:a",
        ]

    def test_empty_chain_just_runs_handler(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.chain import MiddlewareChain

        chain = MiddlewareChain([])
        result = chain.dispatch(ToolCall(name="x", args=(), kwargs={}), lambda: 42)
        assert result == 42


# --- Telemetry middleware ---


class TestTelemetryMiddleware:
    def test_records_call_start_and_end(self, caplog):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.telemetry import TelemetryMiddleware

        mw = TelemetryMiddleware(logger=logging.getLogger("vcu.telemetry"))
        call = ToolCall(name="ping", args=(), kwargs={})

        with caplog.at_level(logging.INFO, logger="vcu.telemetry"):
            mw.before(call)
            mw.after(call, "pong")

        messages = [r.getMessage() for r in caplog.records]
        assert any("ping" in m and "start" in m.lower() for m in messages)
        assert any("ping" in m and ("end" in m.lower() or "ok" in m.lower()) for m in messages)


# --- Integration: chain + telemetry dispatch correctly ---


class TestChainIntegration:
    def test_full_chain_executes_and_returns_result(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.chain import MiddlewareChain
        from computer_use.core.middleware.telemetry import TelemetryMiddleware

        chain = MiddlewareChain(
            [TelemetryMiddleware(logger=logging.getLogger("vcu.t"))]
        )

        result = chain.dispatch(
            ToolCall(name="echo", args=("hello",), kwargs={}),
            lambda: "echo:hello",
        )
        assert result == "echo:hello"
