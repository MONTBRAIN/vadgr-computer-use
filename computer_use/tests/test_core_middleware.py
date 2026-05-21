# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Middleware chain tests (auth, denylist, redaction, telemetry).

Pinned to the contract in ARCHITECTURE.md §5.6 (decorator wraps the call in
the middleware chain) and §5.7 (Chain of Responsibility pattern).
"""

import logging

import pytest


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


# --- Denylist middleware ---


class TestDenylistMiddleware:
    def test_blocks_denied_path_argument(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.denylist import DenylistMiddleware

        mw = DenylistMiddleware(patterns=["~/.ssh", "/etc/shadow"])
        call = ToolCall(name="fs_read", args=("~/.ssh/id_rsa",), kwargs={})

        with pytest.raises(PermissionError, match="denylist"):
            mw.before(call)

    def test_allows_safe_paths(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.denylist import DenylistMiddleware

        mw = DenylistMiddleware(patterns=["~/.ssh", "/etc/shadow"])
        call = ToolCall(name="fs_read", args=("/tmp/file.txt",), kwargs={})

        assert mw.before(call) is call  # passes through unchanged

    def test_empty_denylist_allows_everything(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.denylist import DenylistMiddleware

        mw = DenylistMiddleware(patterns=[])
        call = ToolCall(name="fs_read", args=("/etc/passwd",), kwargs={})

        assert mw.before(call) is call


# --- Redaction middleware ---


class TestRedactionMiddleware:
    def test_redacts_secret_in_args_for_logging(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.redaction import RedactionMiddleware

        mw = RedactionMiddleware(patterns=[r"sk-[A-Za-z0-9]+", r"AKIA[A-Z0-9]+"])
        call = ToolCall(
            name="type_text", args=("sk-abc123XYZ",), kwargs={"token": "AKIA1234567890XYZ"}
        )

        redacted = mw.redact_for_log(call)
        # Originals are intact in the real call.
        assert call.args == ("sk-abc123XYZ",)
        assert call.kwargs == {"token": "AKIA1234567890XYZ"}
        # Logging copy is masked.
        assert "sk-abc123XYZ" not in str(redacted.args)
        assert "AKIA1234567890XYZ" not in str(redacted.kwargs)
        assert "[REDACTED]" in str(redacted.args)
        assert "[REDACTED]" in str(redacted.kwargs)

    def test_real_call_is_not_mutated(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.redaction import RedactionMiddleware

        mw = RedactionMiddleware(patterns=[r"sk-\w+"])
        call = ToolCall(name="x", args=("sk-secret",), kwargs={})

        # The before-hook returns the original call unmodified so the actual
        # tool still sees the real value.
        result = mw.before(call)
        assert result.args == ("sk-secret",)

    def test_no_matches_leaves_args_unchanged(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.redaction import RedactionMiddleware

        mw = RedactionMiddleware(patterns=[r"sk-\w+"])
        call = ToolCall(name="x", args=("hello world",), kwargs={})

        redacted = mw.redact_for_log(call)
        assert redacted.args == ("hello world",)


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


# --- Auth middleware ---


class TestAuthMiddleware:
    def test_passes_with_valid_token(self):
        from computer_use.core.middleware.auth import AuthMiddleware
        from computer_use.core.middleware.base import ToolCall

        mw = AuthMiddleware(token="secret", required=True)
        call = ToolCall(
            name="x", args=(), kwargs={}, context={"auth_token": "secret"}
        )
        assert mw.before(call) is call

    def test_rejects_with_invalid_token(self):
        from computer_use.core.middleware.auth import AuthMiddleware
        from computer_use.core.middleware.base import ToolCall

        mw = AuthMiddleware(token="secret", required=True)
        call = ToolCall(
            name="x", args=(), kwargs={}, context={"auth_token": "wrong"}
        )
        with pytest.raises(PermissionError):
            mw.before(call)

    def test_disabled_when_not_required(self):
        from computer_use.core.middleware.auth import AuthMiddleware
        from computer_use.core.middleware.base import ToolCall

        mw = AuthMiddleware(token=None, required=False)
        call = ToolCall(name="x", args=(), kwargs={})
        assert mw.before(call) is call


# --- Integration: chain executes the dispatch correctly ---


class TestChainIntegration:
    def test_full_chain_executes_and_returns_result(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.chain import MiddlewareChain
        from computer_use.core.middleware.denylist import DenylistMiddleware
        from computer_use.core.middleware.redaction import RedactionMiddleware
        from computer_use.core.middleware.telemetry import TelemetryMiddleware

        chain = MiddlewareChain(
            [
                DenylistMiddleware(patterns=["~/.ssh"]),
                RedactionMiddleware(patterns=[r"sk-\w+"]),
                TelemetryMiddleware(logger=logging.getLogger("vcu.t")),
            ]
        )

        result = chain.dispatch(
            ToolCall(name="echo", args=("hello",), kwargs={}),
            lambda: "echo:hello",
        )
        assert result == "echo:hello"

    def test_full_chain_short_circuits_on_denylist(self):
        from computer_use.core.middleware.base import ToolCall
        from computer_use.core.middleware.chain import MiddlewareChain
        from computer_use.core.middleware.denylist import DenylistMiddleware

        chain = MiddlewareChain([DenylistMiddleware(patterns=["/etc/shadow"])])
        with pytest.raises(PermissionError):
            chain.dispatch(
                ToolCall(name="read", args=("/etc/shadow",), kwargs={}),
                lambda: "leaked",
            )
