# 0.7.6 E2E helpers

These helpers prepare fixtures and capture evidence for the 0.7.6 runbook.
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
  runtime deadline. It never types or issues product requests.
- `focus_window.ps1` verifies and focuses the exact Windows editor or Chrome for Testing window.

The worker and toggle helpers require the isolated profile's `DevToolsActivePort`
file and the `websockets` package. The worker helper also requires the exact
fixture page URL and extension ID. Missing prerequisites block A01 or A03/A04;
never substitute the owner's browser endpoint. The helpers prepare faults,
not product actions or verdicts.

Run each helper from this committed directory. Keep sensitive fixture text in
an untracked mode-0600 file below the isolated test root.

## B09 transport fault

This relay supports POSIX hosts only. Native Windows refuses alias creation
before writing a credential because an owner-only Windows ACL implementation
is not present. A POSIX mode bit is not a Windows privacy guarantee. Existing
Windows B09 observations use their own recorded setup and remain unchanged.

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
