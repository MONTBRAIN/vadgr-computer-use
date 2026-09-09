# 0.7.6 E2E helpers

These helpers prepare fixtures and capture evidence for the 0.7.6 runbook.

`observe_textedit.py` reads only the document attached to one prepared stock
TextEdit window ID. It checks the exact process identity before and after
each read and reports count, hash, prefix match and combined-session modifier
flags. It never reads another document, activates an app, types, signals a
process or changes settings. It accepts only an ASCII fixture inside the
validated isolated root. `--units` selects a planned prefix of that fixture.
The optional bounded wait observes the first nonempty document state; the
caller must inspect `strict_prefix` and must not infer a test verdict from
the exit code. Quartz must be available in the observing interpreter.

After the public driver creates the test window, use its recorded PID and
window ID, not the front document or a window title:

Before input, save the new empty plain-text document to a unique file inside
the isolated root. Verify its exact document path and zero-byte state. An
untitled TextEdit document can autosave into the owner's default cloud folder
even when later closed with saving disabled. Do not change TextEdit or cloud
preferences. Observe only this test document and retain its file for final
isolated-root cleanup. Each fresh-input leg uses a new empty file and window.

```sh
python E2E/0.7.6/harness/observe_textedit.py \
  --root /tmp/vadgr-cua-example --pid 1234 --window-id 5678 \
  --fixture-file /tmp/vadgr-cua-example/typing-fixture.txt \
  --units 100 --wait-for-prefix-seconds 20
```

This observer is macOS-only and does not invoke product operations. Verify
the public MCP screen size and screenshot before any pixel-input leg.
They do not drive the product, select actions, or decide a cell verdict.

- `server.py` serves the loopback browser fixture and records sanitized request metadata.
- `page.html` is the instrumented browser fixture for the browser cells.
- `redact_stream.py` captures JSONL while removing typed values and binary result data.
  It also removes the account subtree from CLI control responses.
  It retains an allowlisted public browser error code from a tool error and removes
  the surrounding message, which can contain local paths or page data.
  Agent shell command bodies are removed because they can contain typed fixture
  values; tool names, descriptions, outputs and exit codes remain. Return DOM
  oracle objects directly from `browser_eval`, not JSON-stringified objects.
  String-valued fields are deliberately redacted; a hidden value's length is
  not evidence that a hash or boolean matched.
- `lifecycle_control.py` prepares and verifies the Chrome lifecycle states required by C07.
- `stop_extension_worker.py` stops the exact isolated extension worker for A01,
  confirms the stopped event, and disconnects DevTools before the product call.
- `toggle_extension.py` changes only the CUA development extension's enable
  toggle in the isolated profile for A03/A04 and closes its management tab.
- `broker_fault_relay.py` prepares B09 transport cuts for one client. It forwards
  opaque bytes between loopback sockets without reading or logging the protocol.
- `pause_mcp.py` prepares a bounded POSIX scheduling fault for D04's explicit
  runtime deadline or a B06 claim barrier. It never issues product requests.
- `focus_window.ps1` verifies and focuses the exact Windows editor or Chrome for Testing window.

The worker and toggle helpers require the isolated profile's `DevToolsActivePort`
file and the `websockets` package. The worker helper also requires the exact
fixture page URL and extension ID. Missing prerequisites block A01 or A03/A04;
never substitute the owner's browser endpoint. The helpers prepare faults,
not product actions or verdicts.

Run each helper from this committed directory. Keep sensitive fixture text in
an untracked mode-0600 file below the isolated test root.

## B09 transport fault

The relay supports POSIX and native Windows. POSIX creates the alias with mode
0600. Windows creates the empty alias atomically with a protected DACL granting
only the current user full control, then verifies that DACL through the open
file handle before writing any credential bytes. Existing aliases are never
overwritten. A permission or write failure removes only the new alias and
preserves the original endpoint. No account identifier enters helper output.

Start the installed broker normally. Keep the second installed MCP client on
its original endpoint. Start the relay with `--root`, `--endpoint`, and `--alias`.
All paths must stay inside a named `vadgr-cua-*` root below the system temporary
directory. The alias must not exist. Its parent directory must already exist.
The original endpoint must name `127.0.0.1` and a valid port.

The relay creates a mode-0600 endpoint alias with its own loopback port. Set
`VADGR_CUA_BROKER_ENDPOINT` to that alias for only the first installed MCP
client. Keep that client process alive throughout both cuts. The alias contains
an ephemeral broker credential: never capture, print, or commit its contents.

Keep the relay's standard input open. Send `{"cut_seconds":8}` for the timely
reconnect and `{"cut_seconds":46}` for the expired lease. A cut closes only
the relay's connections and rejects new connections until automatic restoration.
Standard output records timestamps and connection metadata, not payloads.
Wait for the relay's restored event before the first client's next product
request. During the cut, let only its existing heartbeat encounter the fault.
An explicit request against a closed alias can trigger normal broker startup,
which would replace the intended reconnect experiment.
The agent still performs every product action and checks every cell oracle
through its installed MCP server. A relay event alone is not a cell verdict.

Send `{"stop":true}` or close standard input after the clients finish. The
relay closes its listener and connections and removes only the alias it created.
It never changes the original endpoint, host networking, or another client.
Missing isolated endpoint state blocks B09; do not use the owner's broker.

On Windows, put the per-cell root below the system temporary directory and
keep its name prefixed with `vadgr-cua-`. If the pass root is elsewhere, prepare
a private copy of only the test-owned endpoint in this per-cell root. Never
print its contents. Mount the alias for the first fresh installed MCP client
and the original endpoint for the second. Use the same 8-second and 46-second
cuts. Do not substitute a process scheduling pause: missed heartbeat accounting
alone does not prove the socket was closed and reconnected.

## B06 claim barrier

A streaming CLI can dispatch its first claim before it finishes emitting the
second claim in the same assistant message. Such a capture is not a race.
On POSIX, announce a bounded pause of both exact isolated MCP children after
both clients connect and the agent records a fresh unowned window and child.
Use two concurrent `pause_mcp.py` calls, each with its exact driver parent and
a 20-second duration. The identity and watchdog requirements below still apply.
Do not pause the CLI, browser, broker or host.

After both helpers report `paused`, signal readiness through an isolated local
file. The agent then emits both public competing claims in one message. Both
watchdogs resume their children automatically. Require both tool calls before
either result, one winner, one named conflict, and unchanged broker identity.
If the claims miss the pause interval or reconnection changes the precondition,
reject the attempt and prepare fresh targets. Release and close only those
targets. This setup has no typing plan or editor-prefix precondition.

## D04 scheduling fault

First announce the temporary pause of the exact installed test MCP process.
The agent must start a valid human typing plan with a caller deadline longer
than its planned cadence. Confirm a nonzero independent editor prefix and no
held modifiers before invoking the helper from a separate controller:

```text
python E2E/0.7.6/harness/pause_mcp.py --root <isolated-root> --pid <MCP-pid> --parent-pid <driver-pid> --seconds <bounded-duration>
```

The root must be a named `vadgr-cua-*` temporary directory. Its installed
entry point must be `runtime/bin/vadgr-cua`, invoked by the runtime's Python
without extra arguments. The process must belong to the current user and be
the stated driver's direct child. Unsupported launch shapes fail closed.
The pause must be greater than zero and no more than 120 seconds. Choose a
duration that crosses the already accepted caller deadline, not a preflight
refusal. Never pause the host, editor, browser, broker, or another MCP process.

A detached watchdog owns both STOP and CONT. It resumes the same process
identity after the bound even if the calling helper is terminated. It also
resumes on its own ordinary interruption. Do not kill the watchdog: SIGKILL,
machine shutdown, or a system scheduler failure cannot provide this guarantee.
POSIX process identity checks are not an atomic kernel process handle; keep
the owned process alive and do not restart it during the fault. Evidence keeps
only PID and timing metadata, never command lines or environment values.

Keep the helper's output attached to the evidence capture. Require its resumed
event, then let the agent inspect the actual named deadline result, stable
strict prefix, released modifiers, and absence of replay. The helper's output
does not decide the cell verdict. Windows refuses this helper; existing native
Windows scheduling-fault observations remain unchanged.
