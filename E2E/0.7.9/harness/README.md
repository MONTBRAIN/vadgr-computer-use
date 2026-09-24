# 0.7.9 evidence helpers

`harness.py` prepares an isolated root, reports the written cell inventory,
checks prerequisites, hashes evidence and plans recoverable cleanup.
Its `mcp-config` command writes a local Claude configuration and prints the
equivalent Codex argument array. It isolates the product child's home and state,
and does not copy the subscription driver's credentials or start either driver.
Neither helper drives a browser, chooses tool calls or supplies a live verdict.
Run the installed `vadgr-cua` entry point through the selected subscription CLI.

These committed helpers travel with the runbook so commands work on every host.
Start with `python E2E/0.7.9/harness/harness.py --help`.
No helper can produce a synthetic signed fixture or mark an unobserved cell pass.

`windows_fixture.py` reuses the 0.7.8 released-wheel fixture, including its
marker, hash checks and safe process cleanup, and adds the exact released 0.7.8
wheel as a predecessor. Its child roots still use the `vadgr-cua-078-` prefix
inside the enclosing marked 0.7.9 root. It prepares and observes fixtures;
it does not drive a product operation. `process_fixture.html` exposes an input
counter for an independent no-replay DOM observation.

`windows_boundary.py` records retained artifact hashes, native-host registration
hashes and read-only process/port cleanup observations for explicitly supplied
test PIDs and port. It never stops a process, modifies registration or assigns
a live-cell verdict.
