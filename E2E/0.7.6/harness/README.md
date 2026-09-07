# 0.7.6 E2E helpers

These helpers prepare fixtures and capture evidence for the 0.7.6 runbook.
They do not drive the product, select actions, or decide a cell verdict.

- `server.py` serves the loopback browser fixture and records sanitized request metadata.
- `page.html` is the instrumented browser fixture for the browser cells.
- `redact_stream.py` captures JSONL while removing typed values and binary result data.
- `lifecycle_control.py` prepares and verifies the Chrome lifecycle states required by C07.
- `focus_window.ps1` verifies and focuses the exact Windows editor or Chrome for Testing window.

Run each helper from this committed directory. Keep sensitive fixture text in
an untracked mode-0600 file below the isolated test root.
