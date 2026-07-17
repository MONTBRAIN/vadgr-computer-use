# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Wire-protocol schema + version negotiation (no browser)."""

import pytest

from computer_use.browser import protocol as P


class TestConstants:
    def test_protocol_version_is_one(self):
        assert P.PROTOCOL_VERSION == 1

    def test_supported_ops_covers_the_0_4_0_core(self):
        expected = {
            "navigate", "back", "forward", "reload", "wait_for", "query",
            "read_text", "get_attribute", "click", "type", "fill", "select",
            "scroll", "cookies", "status", "eval",
            # CDP universal path (chrome.debugger).
            "press", "accessibility_tree",
        }
        assert expected <= set(P.SUPPORTED_OPS)

    def test_supported_ops_covers_the_0_5_0_ops(self):
        # Session targeting + the remaining interaction ops landed in 0.5.0.
        expected = {
            "use_target", "hover", "dialog", "upload", "element_state",
            "focus", "blur", "clear", "get_value", "snapshot",
        }
        assert expected <= set(P.SUPPORTED_OPS)

    def test_supported_ops_covers_the_0_6_0_ops(self):
        # Window/tab management op-groups landed in 0.6.0 (additive).
        assert {"tabs", "windows"} <= set(P.SUPPORTED_OPS)

    def test_supported_ops_covers_the_0_6_1_profiles_op(self):
        # Multi-profile enumerate/select landed in 0.6.1 (additive).
        assert "profiles" in set(P.SUPPORTED_OPS)

    def test_supported_ops_excludes_still_later_minor_ops(self):
        # Ops deferred past 0.6.1 (capture / downloads / storage).
        forbidden = {"storage", "screenshot", "downloads", "captureVisibleTab"}
        assert forbidden.isdisjoint(set(P.SUPPORTED_OPS))

    def test_the_profiles_op_does_not_bump_the_protocol_version(self):
        # Growing supported_ops (and the additive hello profile fields) is
        # additive — the envelope integer stays 1 in 0.6.1.
        assert P.PROTOCOL_VERSION == 1


class TestProfileHandshake:
    def test_parse_hello_reads_profile_id_and_context(self):
        server = {
            "type": "hello", "proto": 1, "ext_version": "0.6.1",
            "browser": "chrome",
            "profile_id": "9f2c-uuid",
            "profile": {"window_count": 3, "tab_count": 21,
                        "sample_tab_titles": ["Gmail - work", "GitHub"]},
            "supported_ops": ["navigate", "profiles"],
        }
        info = P.parse_server_hello(server)
        assert info.profile_id == "9f2c-uuid"
        assert info.profile == {"window_count": 3, "tab_count": 21,
                                "sample_tab_titles": ["Gmail - work", "GitHub"]}

    def test_missing_profile_id_parses_empty_for_backcompat(self):
        # An old (pre-0.6.1) extension sends no profile fields; cua treats it as
        # the synthetic default profile downstream. Parsing must not fail.
        server = {"type": "hello", "proto": 1, "ext_version": "0.6.0",
                  "browser": "chrome", "supported_ops": ["navigate"]}
        info = P.parse_server_hello(server)
        assert info.profile_id == ""
        assert info.profile is None

    def test_profile_ambiguous_code_is_terminal(self):
        err = P.BrowserError(P.BrowserErrorCode.PROFILE_AMBIGUOUS, "pick one")
        assert err.retryable is False


class TestHelloHandshake:
    def test_build_client_hello(self):
        msg = P.client_hello(cua_version="0.4.0")
        assert msg == {"type": "hello", "proto": 1, "cua_version": "0.4.0"}

    def test_parse_matching_server_hello(self):
        server = {
            "type": "hello", "proto": 1, "ext_version": "0.4.0",
            "browser": "chrome", "supported_ops": ["navigate", "click"],
        }
        info = P.parse_server_hello(server)
        assert info.proto == 1
        assert info.ext_version == "0.4.0"
        assert info.browser == "chrome"
        assert info.supported_ops == ["navigate", "click"]

    def test_mismatched_proto_raises_proto_mismatch(self):
        server = {"type": "hello", "proto": 2, "ext_version": "9.9.9",
                  "browser": "chrome", "supported_ops": []}
        with pytest.raises(P.BrowserError) as ei:
            P.parse_server_hello(server)
        assert ei.value.code == P.BrowserErrorCode.PROTO_MISMATCH
        assert ei.value.retryable is False

    def test_wrong_type_rejected(self):
        with pytest.raises(P.BrowserError):
            P.parse_server_hello({"type": "result", "proto": 1})


class TestOpMessages:
    def test_build_op_message(self):
        msg = P.op_message(7, "click", {"selector": "#submit"})
        assert msg == {"type": "op", "id": 7, "op": "click",
                       "params": {"selector": "#submit"}}

    def test_parse_ok_result(self):
        res = P.parse_result({"type": "result", "id": 7, "ok": True,
                              "result": {"clicked": True}})
        assert res == {"clicked": True}

    def test_parse_error_result_raises_browser_error(self):
        msg = {"type": "result", "id": 7, "ok": False,
               "error": {"code": "not_found", "message": "no element matches #x"}}
        with pytest.raises(P.BrowserError) as ei:
            P.parse_result(msg)
        assert ei.value.code == P.BrowserErrorCode.OP_FAILED
        assert "no element matches" in str(ei.value)


class TestBrowserError:
    def test_terminal_codes_are_not_retryable(self):
        for code in (
            P.BrowserErrorCode.NOT_SET_UP,
            P.BrowserErrorCode.NOT_CONNECTED,
            P.BrowserErrorCode.OP_UNSUPPORTED,
            P.BrowserErrorCode.PROTO_MISMATCH,
        ):
            err = P.BrowserError(code, "x")
            assert err.retryable is False

    def test_waking_is_retryable(self):
        err = P.BrowserError(P.BrowserErrorCode.WAKING, "asleep")
        assert err.retryable is True

    def test_carries_remediation_and_fallback(self):
        err = P.BrowserError(
            P.BrowserErrorCode.NOT_CONNECTED, "no session",
            remediation="open Chrome", fallback="use screenshot",
        )
        assert err.remediation == "open Chrome"
        assert err.fallback == "use screenshot"
