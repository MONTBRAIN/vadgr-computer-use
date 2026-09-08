# 0.7.6 E2E helpers

These helpers prepare fixtures and capture evidence for the 0.7.6 runbook.
They do not drive the product, select actions, or decide a cell verdict.

- `server.py` serves the loopback browser fixture and records sanitized request metadata.
- `page.html` is the instrumented browser fixture for the browser cells.
- `redact_stream.py` captures JSONL while removing typed values and binary result data.
  It retains an allowlisted setup error code from a tool error and removes
  the surrounding message, which can contain local paths or page data.
- `lifecycle_control.py` prepares and verifies the Chrome lifecycle states required by C07.
- `stop_extension_worker.py` stops the exact isolated extension worker for A01,
  confirms the stopped event, and disconnects DevTools before the product call.
- `toggle_extension.py` changes only the CUA development extension's enable
  toggle in the isolated profile for A03/A04 and closes its management tab.

The worker and toggle helpers require the isolated profile's `DevToolsActivePort`
file and the `websockets` package. The worker helper also requires the exact
fixture page URL and extension ID. Missing prerequisites block A01 or A03/A04;
never substitute the owner's browser endpoint. The helpers prepare faults,
not product actions or verdicts.
- `focus_window.ps1` verifies and focuses the exact Windows editor or Chrome for Testing window.

Run each helper from this committed directory. Keep sensitive fixture text in
an untracked mode-0600 file below the isolated test root.
