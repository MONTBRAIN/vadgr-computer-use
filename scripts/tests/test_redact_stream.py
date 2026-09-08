"""Regression tests for the 0.7.6 E2E stream redactor."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "E2E" / "0.7.6" / "harness" / "redact_stream.py"
SPEC = importlib.util.spec_from_file_location("redact_stream", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


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
        "text": '{"connected":true,"target_id":"fixture","value":'
        '{"redacted":true,"length":6}}',
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
