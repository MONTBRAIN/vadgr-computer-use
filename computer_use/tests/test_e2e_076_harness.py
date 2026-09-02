# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""The 0.7.6 capture helper redacts typed values before evidence is written."""

import importlib.util
from pathlib import Path


def _redactor():
    path = Path(__file__).parents[2] / "E2E" / "0.7.6" / "harness" / "redact_stream.py"
    spec = importlib.util.spec_from_file_location("e2e_076_redactor", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redactor_removes_nested_text_values_and_literal_echoes():
    module = _redactor()
    secret = "fixture-input-never-filed"
    event = {
        "tool": {"input": {"text": secret, "selector": "#plain"}},
        "result": {"content": f'{{"value":"{secret}","ok":true}}'},
        "summary": f"typed {secret}",
    }
    redacted = module.redact(event, (secret,))
    rendered = str(redacted)
    assert secret not in rendered
    assert redacted["tool"]["input"]["text"] == {
        "redacted": True,
        "length": len(secret),
    }
    assert "[redacted typed fixture]" in rendered
