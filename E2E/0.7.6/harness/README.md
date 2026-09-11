# 0.7.6 E2E helpers

These helpers prepare fixtures and capture evidence for the 0.7.6 runbook.

## Endpoint publication observation and fault

`observe_publication.py` records only metadata for the exact endpoint, its
dedicated parent, and matching temporary files. It never opens their contents.
Start it before F06 or F08 startup and keep its stdout attached to the capture:

```sh
python E2E/0.7.6/harness/observe_publication.py \
  --root /tmp/vadgr-cua-example \
  --endpoint /tmp/vadgr-cua-example/broker/browser-broker.json \
  --discovery /tmp/vadgr-cua-example/home/.vadgr-cua/browser.port --seconds 60
```

The root must be a current-user-owned `vadgr-cua-*` directory directly inside
the system temporary directory. The endpoint uses a dedicated child directory.
The parent and endpoint may initially be absent. The observation lasts at most
120 seconds. Polling can miss a short-lived temporary file; it cannot establish
first-byte protection. Attach the deterministic publication tests separately.
The observer emits changes plus an explicit completion record, not a verdict.
The `--discovery` argument adds the browser's token-bearing discovery file and
its parent/temporary files. Include both surfaces in F06-F08. Resolve the actual
discovery location from the isolated setup: the broker uses the default
`HOME/.vadgr-cua/browser.port` on POSIX and
`LOCALAPPDATA/vadgr-cua/browser.port` on Windows. The legacy standalone browser
server can use a discovery override; that does not change the broker's default
path selection. Never observe or copy the owner's normal discovery file.

For Windows and WSL F08, run this same helper with native Windows Python and
native Windows paths. It uses native `Get-Acl` and reports owner/SYSTEM matches,
rights and inheritance without names or token content. Windows PowerShell must
be available. Do not infer an ACL from a WSL mount's POSIX mode. Use the source
helper directly or a byte-verified copy; it imports no product module.
If a temporary disappears between its metadata and ACL reads, the observer
records `vanished` without an ACL claim. Any ACL failure for a still-present
path stops the observer. A disappearance is not proof of private permissions.

`publication_fault.py` prepares the POSIX F07 failure. First stop only the
recorded disposable broker and verify its exit. Keep its protected stale
endpoint and original browser document. The installed public launcher removes
the stale lock after checking the old process. Do not weaken parent permissions:
that blocks lock creation before publication and does not exercise this cell.

```sh
python E2E/0.7.6/harness/publication_fault.py arm \
  --root /tmp/vadgr-cua-example --directory /tmp/vadgr-cua-example/f07-fault \
  --endpoint /tmp/vadgr-cua-example/broker/browser-broker.json --seconds 60
```

The root must be mode 0700, and the existing endpoint must be mode 0600. All
paths stay inside the root without links. The fresh fault directory is a
direct child, separate from endpoint storage. The helper copies only the
committed `publication_fault/sitecustomize.py` into it. No product source is
copied or placed on `PYTHONPATH`.

On macOS, the fault comparison recognizes the system `/tmp` and `/var`
aliases for `/private/tmp` and `/private/var`. It verifies only those system
prefixes and does not resolve links inside the isolated root. Prefer canonical
paths consistently in live setup; arbitrary linked fixture paths remain refused.

Set `PYTHONPATH` to that copied directory in only the failing installed MCP
child's environment. Preserve the caller environment. The subscribed agent
still invokes the installed public entry point and requests readiness. Python's
audit hook refuses only replacement of the exact endpoint. It cannot refuse
lock creation or native registration. Its metadata-only `events.jsonl` records
the publication attempt, temporary size/mode, lock presence and destination
presence. A failed request without `publication_refused` is an earlier failure
and does not close F07. The event proves only fault setup, not a live verdict.

The fault expires automatically after the stated duration, at most 120 seconds.
Disarm it explicitly after the public failure, even if the request fails:

```sh
python E2E/0.7.6/harness/publication_fault.py disarm \
  --root /tmp/vadgr-cua-example --directory /tmp/vadgr-cua-example/f07-fault
```

No permission, registration or owner environment change needs restoration.
The disarmed marker also disables the hook in already running children.
Remove the fault `PYTHONPATH` setting for the successful restart and identity
proof. Verify the failed broker's exit, unchanged protected stale endpoint and
absence of temporary files. Then let the agent request readiness, explicitly
reclaim and read the original document. Retain only metadata and public streams;
the fault configuration contains private paths and does not enter the capture.
Keep the isolated directory for the pass's bounded final cleanup.

`scripts/tests/test_publication_helpers.py` proves that a child reaches the
real publisher after synthetic lock and registration setup, exits on the
publication fault, preserves the previous endpoint, and succeeds after disarm
or expiry. This acceptance trace is not a browser session. Run it before the
live group and retain its output with the separate security tests.

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
  Optional `--timing-output <fresh-file>` records each accepted line's zero-based
  index, redacted-line SHA-256, and monotonic/UTC receipt times in nanoseconds.
  It changes no event payload and stores no raw text in the timing file.
  Run both recorders on the same OS host to compare monotonic clocks. These
  timestamps order received CLI events, not browser dispatch. For a claim
  race, combine them with both clients' started/completed events and the exact
  MCP pause traces; a later conflict alone does not prove an overlapping claim.
  Existing event and timing files are never overwritten. The two paths must
  differ. Do not add timestamps to an old capture after the run.
  It also removes the account subtree from CLI control responses.
  It retains an allowlisted public browser error code from a tool error and removes
  the surrounding message, which can contain local paths or page data.
  Agent shell command bodies are removed because they can contain typed fixture
  values; tool names, descriptions, outputs and exit codes remain. Return DOM
  oracle objects directly from `browser_eval`, not JSON-stringified objects.
  String-valued fields are deliberately redacted; a hidden value's length is
  not evidence that a hash or boolean matched.
  A Codex stream and a Claude stream are not the same shape, and sealing has to
  know it. Claude carries each tool result twice, once as a bare string under
  `content` inside `message.content` and once under `tool_use_result` at the top
  of the row, and it puts shell output in both. A sealer that keys on `stdout`,
  `stderr` or `aggregated_output` alone matches neither copy and still reports
  the output removed. Map each result to its `tool_use` name, keep it only when
  the call was an `mcp__` product call, and replace every other output with its
  length. `command` is already a sensitive key here, so shell bodies are removed
  at ingestion on either shape.
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
- `registration_fault_windows.py` removes only the two current-user CUA native
  registration default values for a bounded A04 fault, then restores their exact
  values and registry types. It never drives a product request.
- `registration_fault_linux.py` removes only the three isolated Linux CUA native
  manifests for a bounded A04 fault, then restores their exact bytes and modes.
  It never drives a product request.

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
Verify that its test-owned broker is still alive and reachable before copying
the endpoint. A stale endpoint can cause the two clients to start separate
brokers. Require matching complete public broker identities and a real relay
connection before applying either fault.

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

Prepare the timed sequence before starting a cut. For the timely leg, request
the cut and wait for restoration inside one bounded setup call, then make the
first client's public read immediately. Do not spend intervening agent turns
polling metadata or writing notes. Measure actual `connection_opened` minus
`cut`, not just `restored` minus `cut`: the reconnect must occur inside the
30-second grace period and retain its lease. A late driver request is an
invalid timely precondition, not a product failure. The second client's normal
heartbeat stays active; verify its original lease and document before and
after both cuts.

On POSIX, `control_broker_fault.py` performs the cut and restoration wait in
one setup call. Prepare a current-user-owned mode-0700 `/tmp/vadgr-cua-*`
root, an existing FIFO connected to the relay's standard input, and its
existing JSONL output log. Both paths and their parents must belong to the
current user inside that root, without symlinks or hard links. Keep the FIFO's
reader alive. The helper refuses a missing reader instead of blocking.

```sh
python E2E/0.7.6/harness/control_broker_fault.py \
  --root /tmp/vadgr-cua-example \
  --control /tmp/vadgr-cua-example/relay-control \
  --events /tmp/vadgr-cua-example/logs/b09-relay.jsonl \
  --seconds 8 --timeout 20
```

Use `--seconds 46 --timeout 55` for the expired leg. The timeout must exceed
the cut duration and cannot exceed 60 seconds. The helper records the initial
log offset, sends exactly one command, and reads appended events through
partial writes. It prints the actual new cut and restoration objects, then
their measured timestamp difference and the helper's elapsed time. Missing
events, malformed events, another cut, log replacement or observed truncation
fail the setup. An unfinished event already present at startup also fails.
No other controller may send a command during this call. The helper reads
no endpoint file, imports no product code, and makes no network or MCP call.
Require exit zero, then perform the first client's public read immediately.
This output proves fixture restoration only; the public read and actual relay
connection timing still determine the B09 result. Native Windows uses the
control handshake below instead of this POSIX FIFO helper.

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
For a file-based control handshake under Windows PowerShell 5, use the
two-argument `File.Move` only when the destination is absent and `File.Replace`
when it already exists. Its .NET Framework does not provide the three-argument
`File.Move` overwrite overload. Write JSON without a UTF-8 byte-order mark and
fail a setup command immediately if its atomic replacement fails.

## Windows B09 coordinator and control

The native Windows coordinator launches the subscribed driver with three
independent installed MCP clients:

```text
python scripts/select_cua_e2e_driver.py
python E2E/0.7.6/harness/coordinate_broker_fault_windows.py --root <isolated-root> --prompt <prompt-file> --driver <selected-driver>
```

Prepare `runtime/Scripts/vadgr-cua.exe`, the browser, and the prompt inside the
existing named root first. The root must be below the system temporary folder
or the workspace `.tmp` folder. Each attempt requires fresh `b09-*` output
names. The coordinator sets `LOCALAPPDATA=root/local`, `APPDATA=root/roaming`,
`VADGR_CUA_BROKER_ROOT=root/broker`, and browser discovery to
`root/discovery.json` in each MCP configuration. It requires the driver selected
by the quota command. Codex uses `--yolo exec --json --ephemeral
--ignore-user-config --skip-git-repo-check`, GPT-5.6 Luna and medium reasoning.
Claude Code uses `--dangerously-skip-permissions`, a strict owner-private MCP
configuration and Claude Sonnet 5. Existing subscription authentication remains
in use. The runbook also permits high reasoning for separately configured Codex
tasks when its reason is recorded.

`cua_two` and `cua_three` use the canonical broker endpoint directly. Their
normal installed startup establishes the broker. The coordinator checks the
live test-owned broker executable and loopback listener before preparing an
owner-only endpoint copy and relay alias. `broker_stdio_gate_windows.py`
then releases `cua_one` into the installed entry point with inherited stdio.
The gate does not read or generate MCP protocol messages.

After the driver verifies matching public broker identities, its owned targets,
and a real relay connection, request each cut in one bounded shell call:

```text
python E2E/0.7.6/harness/control_broker_fault_windows.py --root <isolated-root> --sequence 1 --seconds 8
python E2E/0.7.6/harness/control_broker_fault_windows.py --root <isolated-root> --sequence 2 --seconds 46
```

Run the two commands at their separate B09 steps. Each atomically writes one
request, waits for the matching actual relay cut and restoration, and returns
only numeric timing metadata. The default timeout is 58 seconds; `--timeout`
must exceed the cut duration and cannot exceed 60 seconds. Duplicate sequence
controllers, stale events, disconnected cuts and stopped coordinators fail.
Require exit zero, then make `cua_one`'s product read immediately. Do not add
intervening notes or state polling. The public read and actual reconnection
timing still determine the verdict.

After B09, release or close its targets through the product. Use only the two
direct clients, `cua_two` and `cua_three`, for B10/B15. Prepare their owned
targets before the restart. The alias retains the previous broker address and
must not be used for restart cells. The driver still performs every product
operation and verifies every public result.

The coordinator captures the driver through the committed ingestion redactor
into `b09-driver.jsonl`. `b09-relay.jsonl` records safe events without ports,
endpoints or tokens. `b09-state.json` carries the control handshake;
`b09-processes.json` and `b09-result.json` contain only safe process metadata
and completion status. The owner-only `b09-gate-private.json` contains a private
path and must not enter evidence. Inspect exit codes and the actual product
stream; a helper exit alone is not a cell verdict.

The coordinator passes `--retain-alias` to the relay. This option retains its
owner-only alias on exit and retains failed alias writes. The coordinator also
retains the original private endpoint copy and control artifacts. It stops only
its own relay process, never the driver, browser or broker. Failed setup can
leave a driver alive; the safe result and process metadata identify that state
for the parent controller. No automatic file or directory deletion occurs.

## A04 Linux registration fault

Prepare the isolated browser and installed MCP clients before this fault.
Use a current-user-owned, mode-0700 `vadgr-cua-*` directory directly below `/tmp`.
The three original `com.vadgr.cua.json` manifests must already exist beneath
`home/.config/{google-chrome,chromium,microsoft-edge}/NativeMessagingHosts/`
inside that root. The helper refuses symlinks, hard-linked manifests, missing
originals and paths owned by another user. It does not change owner files,
ownership, browser settings or host networking.

```sh
python E2E/0.7.6/harness/registration_fault_linux.py \
  --root /tmp/vadgr-cua-example \
  --backup /tmp/vadgr-cua-example/a04-backup \
  --ready /tmp/vadgr-cua-example/a04-ready \
  --done /tmp/vadgr-cua-example/a04-done --seconds 180
```

The backup directory and both control files must be fresh, distinct direct
children of the isolated root. Use unique names for each attempt. The helper
creates a mode-0700 backup directory with three mode-0600 exact copies and
verifies their bytes before removing any manifest. Backups contain private
state: retain them for recovery and final isolated-root cleanup, and never
print, commit or include them in evidence. Do not run an installer or modify
the manifests or their parent directories while the fault is active.

Start the helper as a separate setup process and wait for the ready file.
The agent requests the public status and read errors through its installed MCP.
Create the done file after those read-backs. The helper restores in `finally`
on done, timeout, ordinary exceptions, keyboard interruption or SIGTERM.
It verifies exact bytes, hashes and file modes. Output contains only hashes,
counts, booleans, PID and timestamps. Require exit zero and `restored: true`
with `verified: true` before accepting the setup and making the recovery read.
A timeout restores files but exits nonzero, so it cannot pass as a completed
handshake. The ready file is not a cell verdict. SIGKILL or host shutdown cannot
run restoration; never forcibly terminate an active fault. An occupied restore
destination is refused and all other removed manifests still receive a restore
attempt. Retain the backups if restoration fails.

This helper requires Linux and Python 3.10 or later. Windows uses its registry
helper; macOS and a WSL browser hosted on Windows require their native setup.
Missing isolated manifests block this Linux A04 setup.

## A04 Windows registration fault

Prepare the isolated browser, both installed MCP clients and the parent's
registration backup before this fault. The helper changes only the default
values of the current-user Chrome and Edge `com.vadgr.cua` registration keys.
It never deletes or creates registry keys and preserves sibling values and
key permissions. Do not run another installer or registration setup while the
fault is active.

```text
python E2E/0.7.6/harness/registration_fault_windows.py --root <isolated-root> --snapshot-file <new-private-snapshot> --ready-file <new-ready-file> --done-file <new-done-file> --seconds 180
```

All three files must be fresh, distinct and inside a named isolated CUA root
below the system temporary directory or the workspace's `.tmp` directory.
The helper creates and verifies an owner-only snapshot file before writing
registration values, types and security descriptors. The snapshot contains
private state. Never print, commit or include it in evidence. Keep it for the
parent's cleanup or recovery; this helper does not delete it.

Start the helper as a separate hidden setup process and wait for its ready file.
Pass executable and argument paths as data, for example through a Python
`subprocess.Popen` argument list with `CREATE_NO_WINDOW`. Windows PowerShell
`Start-Process -ArgumentList` joins its array into a command line; an unquoted
path containing spaces can fail before the helper starts. Preserve that launch
failure and use fresh control files for the accepted attempt.
The agent then requests the public status and read errors through the installed
MCP. Create the done file after those read-backs. The helper restores defaults
in `finally`, whether done arrives, its three-minute bound expires, or an
ordinary Python interruption occurs. Require exit zero and `restored` with
`verified: true` before the subsequent public recovery read. The ready file
alone does not prove restoration or a cell verdict. Forced process termination
or host shutdown cannot run `finally`; retain the private snapshot and never
kill this helper while its fault is active. The helper changes no host power
state, network setting or registration ACL.

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
On Linux and WSL, identity uses kernel start ticks, not `ps` wall-clock start
text. That text can change by a second for the same live process. The helper
checks the kernel identity before and after reading the other process fields.

Keep the helper's output attached to the evidence capture. Require its resumed
event, then let the agent inspect the actual named deadline result, stable
strict prefix, released modifiers, and absence of replay. The helper's output
does not decide the cell verdict. Windows refuses this helper; existing native
Windows scheduling-fault observations remain unchanged.
