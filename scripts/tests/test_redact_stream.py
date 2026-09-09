"""Regression tests for the 0.7.6 E2E stream redactor."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness" / "redact_stream.py"
SPEC = importlib.util.spec_from_file_location("redact_stream", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_redacts_account_only_from_cli_control_response():
    account = {"email": "fixture@example.test", "organization": "synthetic-account"}
    source = {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "initialize-fixture",
            "response": {"account": account, "commands": [], "ready": True},
        },
    }
    result = MODULE.redact(source, ())
    assert result == {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "initialize-fixture",
            "response": {"account": {"redacted": True}, "commands": [], "ready": True},
        },
    }
    assert source["response"]["response"]["account"] == account
    oracle = {"value": {"account": {"count": 2, "selected": True}}}
    assert MODULE.redact(oracle, ()) == oracle


def test_redacts_image_payload_but_keeps_media_identity():
    result = MODULE.redact(
        {"type": "image", "data": "base64-payload", "mimeType": "image/png"},
        (),
    )

    assert result == {
        "type": "image",
        "data": {"redacted": True, "length": 14},
        "mimeType": "image/png",
    }


def test_keeps_structured_tool_result_while_redacting_nested_typed_values():
    result = MODULE.redact(
        {
            "type": "text",
            "text": '{"connected":true,"target_id":"fixture","value":"secret"}',
        },
        (),
    )

    assert result == {
        "type": "text",
        "text": '{"connected":true,"target_id":"fixture","value":{"redacted":true,"length":6}}',
    }


def test_redacts_unstructured_text_content():
    result = MODULE.redact({"type": "text", "text": "agent prose"}, ())

    assert result == {
        "type": "text",
        "text": {"redacted": True, "length": 11},
    }


def test_preserves_named_browser_error_without_retaining_its_message():
    message = "[recovery_timed_out] private page detail. To fix: private path."
    result = MODULE.redact({"type": "text", "text": message}, ())

    assert result["text"] == {
        "redacted": True,
        "length": len(message),
        "error_code": "recovery_timed_out",
    }


def test_does_not_extract_unknown_or_embedded_error_like_text():
    for message in ("[private_value] details", "page says [recovery_timed_out]"):
        assert MODULE.redact({"type": "text", "text": message}, ())["text"] == {
            "redacted": True,
            "length": len(message),
        }


def test_keeps_only_setup_code_from_wrapped_tool_error():
    message = "Error executing tool browser: [extension_disabled] confidential detail"
    result = MODULE.redact({"type": "text", "text": message}, ())

    assert result["text"] == {
        "redacted": True,
        "length": len(message),
        "error_code": "extension_disabled",
    }


def test_redacts_credentials_in_structured_tool_result():
    result = MODULE.redact(
        {
            "type": "text",
            "text": '{"token":"abc123","authorization":"Bearer abc123"}',
        },
        (),
    )

    assert result == {
        "type": "text",
        "text": '{"token":{"redacted":true,"length":6},'
        '"authorization":{"redacted":true,"length":13}}',
    }


@pytest.mark.parametrize(
    "code",
    [
        "not_connected",
        "op_unsupported",
        "proto_mismatch",
        "waking",
        "op_failed",
        "target_lost",
        "profile_ambiguous",
        "target_owned_by_another_client",
        "typing_mismatch",
        "typing_deadline_exceeded",
        "typing_cancelled",
        "typing_state_uncertain",
        "inactive_tab_trusted_keyboard_unsupported",
        "target_discarded",
        "target_frozen",
        "target_restricted",
    ],
)
@pytest.mark.parametrize("tool", ["browser", "browser_eval", "tabs", "windows", "profiles"])
def test_preserves_public_browser_codes_needed_by_remaining_cells(code, tool):
    message = f"Error executing tool {tool}: [{code}] private page or input detail"
    assert MODULE.redact({"type": "text", "text": message}, ())["text"] == {
        "redacted": True,
        "length": len(message),
        "error_code": code,
    }


@pytest.mark.parametrize("tool", ["tabs", "windows", "profiles"])
@pytest.mark.parametrize("code", ["target_owned_by_another_client", "unknown_private_code"])
def test_target_errors_keep_only_allowlisted_code_not_private_details(tool, code):
    message = (
        f"Error executing tool {tool}: [{code}] "
        r"private target C:\fixture-private\page.txt token=synthetic-credential"
    )
    result = MODULE.redact({"type": "text", "text": message}, ())
    expected = {"redacted": True, "length": len(message)}
    if code == "target_owned_by_another_client":
        expected["error_code"] = code
    assert result == {"type": "text", "text": expected}


@pytest.mark.parametrize(
    "message",
    [
        "Error executing tool type_text",
        "Error executing tool type_text: typing_options_require_human",
        "Error executing tool type_text: timing_profile and custom timing are mutually exclusive",
        "Error executing tool type_text: custom timing requires both wpm and iki_cv",
        "Error executing tool type_text: wpm must be an integer",
        "Error executing tool type_text: wpm must be from 10 through 200",
        "Error executing tool type_text: iki_cv must be finite and from 0 through 1",
        "Error executing tool type_text: timeout must be a positive finite number of milliseconds",
    ],
)
def test_keeps_exact_fixed_typing_error_text_without_inventing_wire_error_flag(message):
    result = MODULE.redact({"type": "text", "text": message}, ())
    assert result["text"] == {
        "redacted": True,
        "length": len(message),
        "error_message": message,
    }
    assert "isError" not in result


@pytest.mark.parametrize("code", ["typing_cancelled", "typing_deadline_exceeded"])
@pytest.mark.parametrize("completed", [0, 37])
def test_retains_anchored_pixel_interruption_prefix_metadata(code, completed):
    message = f"Error executing tool type_text: {code}: {completed} complete units"
    assert MODULE.redact({"type": "text", "text": message}, ())["text"] == {
        "redacted": True,
        "length": len(message),
        "error_code": code,
        "completed_units": completed,
    }


@pytest.mark.parametrize(
    "message",
    [
        "Error executing tool type_text: private input",
        "Error executing tool type_text: custom timing requires both wpm and iki_cv PRIVATE",
        "page says Error executing tool type_text",
        "Error executing tool type_text: typing_cancelled: 37 complete units PRIVATE",
        "Error executing tool type_text: unsupported timing profile 'private input'",
    ],
)
def test_does_not_retain_unknown_or_extended_typing_error_text(message):
    assert MODULE.redact({"type": "text", "text": message}, ())["text"] == {
        "redacted": True,
        "length": len(message),
    }


def test_keeps_real_wire_error_flag_when_driver_includes_it():
    assert MODULE.redact({"isError": True, "content": []}, ()) == {
        "isError": True,
        "content": [],
    }


@pytest.mark.parametrize("media_type", ["image", "audio"])
def test_redacts_claude_nested_media_source(media_type):
    original = {
        "type": media_type,
        "source": {
            "type": "base64",
            "media_type": f"{media_type}/fixture",
            "data": "fixture-payload",
        },
    }
    assert MODULE.redact(original, ()) == {
        "type": media_type,
        "source": {
            "type": "base64",
            "media_type": f"{media_type}/fixture",
            "data": {"redacted": True, "length": 15},
        },
    }


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "tool_use",
            "name": "Bash",
            "input": {
                "command": "printf synthetic-typed-fixture",
                "description": "Prepare fixture hash",
            },
        },
        {
            "type": "command_execution",
            "command": "printf synthetic-typed-fixture",
            "exit_code": 0,
            "aggregated_output": "fixture hash prepared",
        },
    ],
)
def test_redacts_shell_commands_without_requiring_known_typed_literals(event):
    result = MODULE.redact(event, ())
    original = event.get("input", event)
    actual = result.get("input", result)
    assert actual["command"] == {"redacted": True, "length": len(original["command"])}
    assert {k: v for k, v in actual.items() if k != "command"} == {
        k: v for k, v in original.items() if k != "command"
    }
