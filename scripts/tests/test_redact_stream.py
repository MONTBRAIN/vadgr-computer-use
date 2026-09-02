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
