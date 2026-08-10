# 0.6.6 - a fresh install can start again: e2e runbook

`mcp` 2.0.0 (published 2026-07-28) removed `mcp.server.fastmcp`, the module this
server was built on. `0.6.5` declares `"mcp>=1.0"` with no upper bound, so a
fresh `pip install vadgr-computer-use` resolves 2.0.0 and `vadgr-cua` dies at
import with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. The
console script cannot start for any new user (issue #39), and the `test`
workflow has been red on it since 2026-08-04.

`0.6.6` moves every call site onto `mcp.server.mcpserver` and moves the
dependency floor with it. **Nothing else changes**: no new tool, no changed
tool, no behaviour change, no transport change, no Python floor change.

**Why this patch gets a runbook when `0.6.2` to `0.6.5` did not.** The defect is
"the published package cannot start on a fresh install". The only thing that can
observe it is a real MCP session from an environment built after the breaking
release. That is a runbook by construction, and writing the proof into a commit
message instead would leave it unrepeatable.

Target OSes: Linux, macOS, Windows (native), WSL.

## The approach: a Claude subagent over `claude -p`, and a wire-level sweep

Same as `0.4.0` / `0.5.0` / `0.6.0` / `0.6.1`: the live part is driven by a real
agent over `claude -p`, never a script, on goal-level tasks (Part D). The model
is whatever `claude` is configured with, the MCP config is a one-server
`.mcp.json` written for the run, and the agent is told a goal, never a sequence
of calls.

**Part E is deliberately not agent-driven, and that is the one departure worth
explaining.** Its claim is that *every* tool still works, and an agent cannot be
made to enumerate twenty six tools without being handed a script, at which point
the runbook is testing the runbook. So Part E speaks raw JSON-RPC to the same
server the agent used, calls each tool itself, and ground-truths every side
effect outside the session. Part D proves the dispatch path through a real
client; Part E proves the breadth. Neither substitutes for the other.

**Every environment below is built fresh for the run.** A virtualenv that
predates `mcp` 2.0.0 holds a 1.x and would pass every part here against `0.6.5`
itself. That is exactly how the local checkout stayed green for a week while the
published package was broken, so a pre-existing virtualenv is not a shortcut, it
is the failure mode.

## The oracle is the JSON, never the agent's prose

**`../README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative test must show
`is_error: true`, and with neither stream nor transcript the result is
**not verified** rather than a pass.

Where this pass's JSON landed:

- Part D: two teed `--output-format stream-json` runs, kept as run journals in
  the evidence bundle.
- Part E: a journal of every JSON-RPC request and response frame, one line per
  call, written by the harness as it ran.
- Ground truth for both: read outside the session, from the OS or from a process
  the server does not talk to, and transcribed with the exit code of the command
  that produced it.

Image payloads in both journals are elided to their byte length. Nothing else
is edited.

## Prerequisites (per OS)

**All OSes.** Python 3.10 or newer, network access to PyPI, and no cua server
already running from the environment under test.

**WSL** (the OS that carries the live parts here). WSL2 with the Windows
interop path available, since the desktop backend drives Windows through
`powershell.exe`. Part E's input half additionally needs:

- a desktop session that is actually logged in and unlocked, because the input
  tools drive real hardware and a locked session silently swallows them;
- **nothing the operator cares about in the foreground.** Part E opens a window
  of its own, gives it focus, types into it, and closes it. Say so before
  starting: the pointer moves and the keyboard goes somewhere the operator did
  not choose.

**Windows native.** A Python that is not the WSL one, and a separate copy of the
branch: an editable install into a WSL checkout is not a Windows install.

**macOS.** Not held on this pass. See the per-OS table.

**Browser tier, every OS.** The extension loaded in at least one Chrome profile
**and no other cua server running**. The extension binds to one native port and
cua takes one listener, so if any other cua process holds the bond the server
under test sees `not_connected` no matter how healthy it is. This is the
single-listener property the `0.6.1` runbook documents, and on this pass it is
what stopped the browser tier being exercised.

## Setup

From a stated working directory, with `<checkout>` the branch under test.

The negative control, first, before anything is changed:

```bash
python3 -m venv /tmp/cua-repro
/tmp/cua-repro/bin/pip install "vadgr-computer-use==0.6.5"
/tmp/cua-repro/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"
/tmp/cua-repro/bin/python -c "import computer_use.mcp_server"
/tmp/cua-repro/bin/vadgr-cua --transport stdio </dev/null
```

The environment under test, built from the branch:

```bash
python3 -m venv /tmp/cua-26
/tmp/cua-26/bin/pip install -e "<checkout>[dev]"
/tmp/cua-26/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"
```

And, for Part E, a second one that is **not editable**, so what is served is the
package a new user gets rather than the working tree:

```bash
python3 -m venv /tmp/cua-66-sweep
/tmp/cua-66-sweep/bin/pip install <checkout>
cd /tmp && /tmp/cua-66-sweep/bin/python -c \
  "import computer_use; print(computer_use.__file__)"
```

**The `cd /tmp` is load-bearing.** Run that check from the checkout directory
and `import computer_use` resolves to the working tree, the installed package is
never touched, and a broken install reports itself healthy. Every server in Part
E was started with `cwd=/tmp` for the same reason.

The 1.x baseline Part C compares against:

```bash
python3 -m venv /tmp/cua-repro-1x
/tmp/cua-repro-1x/bin/pip install "vadgr-computer-use==0.6.5" "mcp<2"
```

**That pin is the harness's, not the product's.** It is the workaround issue #39
names, and it exists only to get a running 1.x baseline to compare against.

Read every exit code directly. Do not pipe them into anything: `cmd | head`
reports `head`'s status.

## Automated gate (necessary, never sufficient)

```bash
/tmp/cua-26/bin/python -m pytest computer_use/tests -q
/tmp/cua-26/bin/ruff check computer_use
```

Both read from their own exit codes. `ruff` runs in the same environment because
CI lints before it tests. Expected: `pytest` exit `0`, `ruff` exit `0`.

Green here proves the code paths and proves **nothing** about a real desktop or
a real client. Parts C, D and E are the gate.

## Coverage

What this pass claims, and against what. A surface with no part is uncovered and
says so here, because silence reads as covered.

| surface | part |
|---|---|
| the published `0.6.5` fails on a fresh install | A |
| the branch installs and its suites pass on `mcp` 2.x | B |
| the dependency floor cannot resolve a 1.x | B |
| the tool catalogue is complete and no module names the removed package | B |
| the `--port` flag reaches the SSE transport | B, D |
| the 26-tool catalogue is identical across the majors | C |
| the `tools/call` result envelope is identical across the majors | C |
| the `2024-11-05` handshake still completes | C |
| a real client connects and lists the tools | D |
| a text result, an image result and a structured result reach the model | D |
| a `ToolError` reaches the model with its guidance intact | D |
| the SSE transport starts and routes | D |
| `fs shell http env time tempfile data clipboard` | E |
| `get_platform get_platform_info get_screen_size screenshot screenshot_region` | E |
| `click double_click right_click move_mouse drag scroll type_text key_press` | E |
| `browser browser_eval tabs windows profiles` | E, **dispatch only**, see the part |
| the browser tier's page ops | **uncovered**, see what this runbook cannot prove |
| the Linux, macOS and native Windows input backends | **uncovered**, see what this runbook cannot prove |

## Part A: reproduce the defect before changing anything

The negative control. Without it every part below is decoration.

**Task:** run the Setup block for `/tmp/cua-repro` and read each exit code.

**Verdict from the JSON:** there is none, and that is the point. This part is
below the MCP layer: the console script never reaches a session, so the evidence
is the interpreter's own stderr and the exit codes.

**Expected result:** `mcp` resolves to a 2.x, and both the import and the console
script exit non-zero with the `ModuleNotFoundError`.

## Part B: the suites on mcp 2.x, from a virtualenv built after the break

**Task:** build `/tmp/cua-26`, print the resolved `mcp` version, then run the
automated gate above.

The version print is a check of its own: it must say a 2.x. If it says
1.something the floor in `pyproject.toml` did not land and everything after it
is meaningless.

**Negative controls, one plant at a time, restored after each.** A check that
has never fired is decoration.

| plant | what must happen |
|---|---|
| revert the dependency floor to `mcp>=1.0` | `pip install --dry-run <checkout> "mcp<2"` succeeds and resolves a 1.x, rebuilding the defect. With `mcp>=2.0` the same command is `ResolutionImpossible` |
| drop one `@mcp.tool()` decorator | the wire-surface set equality fails, naming the missing tool |
| put a `mcp.server.fastmcp` import back in any module | the source scan fails, naming the file |
| revert the run path to `mcp.settings.port = args.port` | an `sse` start dies with `ValueError: "Settings" object has no field "port"`; a `stdio` start still comes up, so the branch is not a regression in disguise |

**Expected result:** a 2.x reported, `pytest` and `ruff` both exit `0`, and all
four plants fire and are restored.

## Part C: the tool surface, as a diff and not as an assertion

The comparison is between what a client reads from the published `0.6.5` served
on `mcp` 1.x, and what it reads from this branch served on `mcp` 2.x. Both
snapshots come from `tools/list` over raw JSON-RPC on stdio, so the probe shares
no SDK code with either side and the comparison is of what a client sees rather
than of what an internal dictionary holds.

```bash
python3 tools_snapshot.py /tmp/cua-repro-1x/bin/vadgr-cua --transport stdio > before.json
python3 tools_snapshot.py /tmp/cua-26/bin/vadgr-cua      --transport stdio > after.json
diff -u before.json after.json && echo "SURFACE UNCHANGED"
```

`tools_snapshot.py` speaks `initialize`, `notifications/initialized`, then
`tools/list` with cursor paging, sorts by name and prints canonical JSON. It is
kept in the evidence bundle beside the snapshots it produced.

**Verdict from the JSON:** `diff` must exit `0` on the whole file, not on a name
list. `description` and `inputSchema` are in the comparison because a schema
that gains a `required` entry is exactly the change a name comparison misses.
**26 entries on both sides.** If the diff is not empty, the difference is the
finding and it is fixed in this patch rather than noted, because a per-tool
schema delta would mean the two majors derive metadata differently, which is the
one thing this migration claims they do not.

The same property is held by two tests in `computer_use/tests/test_mcp2_surface.py`,
so a regression fails a PR and not only a runbook: the wire names as **set
equality** against the full 26, and a source scan proving no module under
`computer_use` names the removed package.

**Expected result:** an empty diff, 26 tools on both sides, and the
`2024-11-05` handshake completing against the 2.x server.

## Part D: the live stdio session, with the stream as the verdict

The `Agent` tool inherits the parent session's MCP servers and cannot load a
freshly built one, so this is a separate headless process with its own
`.mcp.json`, pointed at Part B's virtualenv.

```bash
cd "$(mktemp -d)"
cat > .mcp.json <<'JSON'
{"mcpServers": {"vadgr-computer-use": {
  "command": "/tmp/cua-26/bin/vadgr-cua", "args": [], "env": {}}}}
JSON
timeout 240 claude --dangerously-skip-permissions --mcp-config .mcp.json \
  --strict-mcp-config --output-format stream-json --verbose \
  -p "<goal-level task>" | tee /tmp/e2e-0.6.6.jsonl
```

**Task given to the agent:** goal-level, never "call the screenshot tool". One
task asks it to read a file it is told exists, describe what is on the screen
and report what machine it is on; a second asks it to open a page in the browser
and, when it cannot, say what it would need. The cells below enumerate what the
stream must then show, one per result kind, so the migration is proven across the
whole dispatch path rather than on the cheapest tool.

**Verdict from the JSON:**

| # | cell | what the stream must show |
|---|---|---|
| 1 | the server starts at all | the session lists cua's tools; an agent that reports no MCP server is the defect, unfixed |
| 2 | tier 0, text result | a `tool_use` for `fs` or `shell` and a matching `tool_result` with `is_error` falsy, carrying the content |
| 3 | tier 2, image result | a `tool_use` for `screenshot` and a `tool_result` carrying an `image` block with `mimeType` `image/jpeg` |
| 4 | a structured result | a `tool_use` for `get_platform_info` and a `tool_result` whose payload is the dict, so the `outputSchema` path is exercised |
| 5 | a `ToolError` reaches the model | drive `browser` with the extension absent; the `tool_result` must carry the page reason and the pixel-fallback guidance as text, not a masked generic error |
| 6 | the side effect is real | ground-truth cell 2 independently: pre-seed a sentinel, read the file back yourself afterwards, never from the agent's summary |
| 7 | the SSE transport still starts | `vadgr-cua --transport sse --port <free>` from the same virtualenv, then a request to the port; this is the run-path branch and nothing above touches it |

Cell 5 matters more than its position suggests: it is the only cell that proves
`browser/tool.py`'s import moved to a `ToolError` the SDK still recognises, and
a wrong exception class there would surface as helpful text becoming a generic
failure, a degradation no schema diff can see.

**Expected result:** all seven cells confirmed from the stream, with cell 6's
sentinel read back off-agent.

## Part E: every tool called, not only declared

Part C proves the 26 tools are **declared** identically before and after. It says
nothing about whether calling one still does anything, and Part D exercises
about six. This part closes that gap: it calls **all 26** against the
non-editable `/tmp/cua-66-sweep` install and ground-truths every side effect
outside the session.

**Task:** drive `tools/call` for each tool over raw JSON-RPC on stdio, one
journal line per request and response frame. The input tools are driven against
a purpose-built window: DPI aware, always on top, at a known rectangle, logging
every input event it receives. That window is the ground truth. A return string
saying `Clicked at (360, 248)` is the tool's own account of itself and proves
nothing; a `MouseDown button=Left screen=1011,695` in a log written by the
window that received it is evidence.

**Verdict from the JSON**, a row per tool. `what came back` is read from the
`tools/call` result frame; `ground truth` is read outside the session.

| tool | called with | what came back | ground truth | verdict |
|---|---|---|---|---|
| `fs` | `write` `read` `list` `stat` `delete` | `{"path":...,"written":16}`, the sentinel, the listing, `{"size":16,"kind":"file"}`, `{"deleted":true}` | `od -c` shows the 16 bytes on disk; the deleted path is gone | pass |
| `shell` | `run` a `sh -c` printing to both streams and exiting 7; `which sh` | `{"returncode":7,"stdout":"out-...","stderr":"err-..."}`; `/usr/bin/sh` | the file that command wrote is on disk | pass |
| `http` | `get` and `post` against a local echo server | `{"status":200}` with the echo's own `X-Sweep` header and body, both times | the server logged both requests and stored the POST body byte-identical | pass |
| `env` | `set VCU_SWEEP`, then `get` | `{"name":"VCU_SWEEP","value":"sweep-066-2f7c41"}`, then the value | the second call is the ground truth: process-scoped, so it is only visible from inside the server | pass |
| `time` | `now`, `sleep 0.25` | `2026-08-09T21:33:15.065605+00:00`, `{"slept":0.25}` | the ISO string parses and carries `+00:00` | pass |
| `tempfile` | `temp_path` prefix `sweep-` suffix `.dat` | `/tmp/sweep-a19886a44f2e.dat` | the path does **not** exist, which is the documented contract | pass |
| `data` | `parse_json` `serialize_json` `parse_csv` `serialize_csv` `parse_yaml` `serialize_yaml` | round trips on each | the YAML pair is the finding below: on a default install it returns its guided error, and both ops pass once the extra is installed | pass |
| `clipboard` | `copy` a sentinel, `paste` | `{"backend":"clip.exe","bytes":16}`, then the sentinel | PowerShell `Get-Clipboard` reads the same value by a path the tool did not use | pass |
| `get_platform` | no args | `wsl2`, structured `{"result":"wsl2"}` | matches `/proc/version` | pass |
| `get_platform_info` | no args | `{"platform":"wsl2","backend_available":true}` | the backend is reachable, as every tier 2 row here shows | pass |
| `get_screen_size` | no args | `1366x768`, structured | consistent with the real 3840x2160 at the auto-detected width | pass |
| `screenshot` | `format=jpeg` | an `image` block, `mimeType` `image/jpeg`, 108020 base64 chars | the block's base64 decodes to magic `ffd8ffe0` and opens as a JPEG of **1366x768**, matching what `get_screen_size` answered | pass |
| `screenshot_region` | `0,0,120,80`, `format=png` | an `image` block, `mimeType` `image/png` | decodes to magic `89504e47` and opens as a PNG of **337x225**: the region is taken in display coordinates and returned at real resolution, un-downscaled, so `120x80` display becomes `120*2.81113` by `80*2.81113`. The full screenshot's scale is left alone, which is what the code says it is protecting | pass |
| `move_mouse` | display `100,60` | `Mouse moved to (100, 60)` | DPI-aware `GetCursorPos` read **281,168**, exactly `int(100*2.81113), int(60*2.81113)`; restored afterwards | pass |
| `click` | display `360,248` | `Clicked at (360, 248)` | rig logged `MouseDown`/`MouseUp button=Left screen=1011,695` | pass |
| `double_click` | display `160,135` | `Double-clicked at (160, 135)` | rig logged `MouseDoubleClick` and a **whole word** selected (`selLen=6 selText=[alpha ]`), so it arrived as one double click and not two singles | pass |
| `right_click` | display `360,248` | `Right-clicked at (360, 248)` | rig logged `MouseUp button=Right screen=1011,697` | pass |
| `drag` | `160,135` to `320,135`, `duration=0.4` | `Dragged from (160, 135) to (320, 135)` | rig logged down at `449,379` and up at `899,379` with the 17 characters between them selected, so the button was held across the move | pass |
| `scroll` | `360,248`, `amount=-3` | `Scrolled down 3 notches at (360, 248)` | rig logged `MouseWheel delta=-360`, exactly three times the Windows `WHEEL_DELTA`, so the notch count survived the bridge | pass |
| `type_text` | `"alpha bravo charlie delta echo"` | `Typed: alpha bravo charlie delta echo` | the rig's text box holds the string. It arrived as `KeyDown key=V ctrl=True`, which is finding F3 | pass |
| `key_press` | `ctrl+a` | `Pressed: ctrl+a` | rig logged `KeyDown key=ControlKey ctrl=True` then `KeyDown key=A ctrl=True`, so the combination was delivered with its modifier flag | pass |
| `browser` | `status`, then `navigate` | `status` returned `{"connected":false,"setup":true,"reason":"not_connected","profiles":[]}` with no error; `navigate` returned `is_error: true` carrying the `[not_connected]` reason, the remediation and the pixel fallback | the extension is live and bonded to a different cua listener at the same moment | dispatch pass, page ops not exercised |
| `browser_eval` | `1+1` | the same `[not_connected]` error, verbatim | as above | dispatch pass, page ops not exercised |
| `tabs` | `list` | the same `[not_connected]` error, verbatim | as above | dispatch pass, page ops not exercised |
| `windows` | `list` | the same `[not_connected]` error, verbatim | as above | dispatch pass, page ops not exercised |
| `profiles` | `list` | `{"profiles": []}`, no error | consistent: no profile is bonded to this listener | dispatch pass, `use` not exercised |

**No tool went uncalled.** What is unproven, precisely:

- **The browser tier's page ops**, on five tools. The extension binds to one
  native port and cua takes one listener, so while another cua process holds the
  bond a second server sees `not_connected` however healthy it is. **What it
  would need:** stop every other cua listener, start the install under test as
  the only one, reload the extension in at least one profile so it re-bonds,
  then re-run those five rows. The `0.6.1` runbook's Part P is the shape of that
  run.
- **`profiles(use)`**, for the same reason: there is nothing to select.
- **The Linux, macOS and native Windows input backends.** Every input row above
  went through the WSL2 bridge, because that is what this machine has. Platform
  detection reads `/proc/version`, so the Linux backend cannot be selected here
  to stand in for a headless display, and there is no X server on this host to
  point it at. **What it would need:** the same rig on each OS, which is a
  per-OS run and not a substitute one.
- **`key_press` for the unknown-key case** is a finding rather than a pass: see
  F4.

**Expected result:** 26 tools called, every non-browser row `pass` with its
ground truth read outside the session, and every browser row carrying its own
`[not_connected]` error rather than an SDK failure.

## When a part surfaces a bug: fix it, then re-run it

**A defect found during a pass is fixed during that pass**, with a test that
fails without it, and **the part is re-run from a clean state** before being
marked. Never logged and carried to the end: the diagnosis is never fresher
than the minute it was found, a later part may build on the broken behaviour
and hand you a second false result, and a pile of deferred findings is how a
runbook ends "green with notes", which is not green.

The exception, and it is narrow: a behaviour that is **provably pre-existing in
a subsystem this patch does not touch** is not this patch's to change. F3 and F4
are both of those, and both carry the `git diff` that shows the subsystem
untouched. Recording them without fixing them is a scope judgement, not a
deferral, and they are owed a minor of their own.

## Repeatability

The interesting axis is the OS and the display server, not repetition on one
box: a second run on the same machine mostly re-proves the machine. So the
repeat unit here is the per-OS table below, and within one OS the parts that
carry real repeat value are the two that build an environment from scratch,
because that is where a resolver can differ between runs.

Part C is repeatable to the byte and was checked that way: the two snapshots
hash identically, so a re-run that produced anything else would be a finding.
Part E's harness is committed to the evidence bundle for the same reason: the
journal is reproducible rather than testimony.

Compare structurally: the tool calls issued, their order where order matters,
and the error codes. Expect the agent's prose to differ every time and the tool
calls not to. Identical prose across runs is a warning, not a comfort.

## Per-OS results

Legend: `pass` and `fail` mean it ran. `blocked` means it could not run, and
says what broke. `not run` means nobody ran it, which is honest and visibly
owed. `Not-Needed` means there is genuinely no OS-specific surface in that
part, and it is only ever written with its reason. A cell is marked from
observation, never expectation.

**`(CI)` is the automated gate, and the automated gate is not an e2e pass.**
CI builds a fresh environment and runs the unit suites, which is exactly
what part B asks for and nothing more. It drives no MCP session and calls no
tool over the wire, so it can never satisfy parts D or E. A row marked
`(CI)` says a suite ran, never that the product was exercised, and the
`overall` row says so by refusing to inherit it.

| part | Linux | macOS | Windows native | WSL | notes |
|---|---|---|---|---|---|
| A: reproduce the defect | Not-Needed | **pass** | Not-Needed | **pass** | a resolver and an import, no OS branch. CI was red on this exact error on both its rows for five days, which is the same observation from the outside. macOS was still run by hand to confirm the same fail mode on that OS's wheel |
| B: suites on a fresh 2.x env | **pass** (CI) | **pass** | **partial** | **pass** | CI builds its environment from `pyproject.toml` on every push, so each row is itself a fresh install resolving 2.x. macOS was also run by hand: 706 passed, 48 skipped, ruff exit 0 |
| C: surface diff across the majors | Not-Needed | Not-Needed | **pass** | **pass** | the catalogue is derived from decorators with no OS branch anywhere in it; Windows was run anyway and served the same 26 |
| D: live agent session | not run | **pass** | not run | **pass** | cells 1 to 7. Owed rather than Not-Needed: `screenshot` and the structured cells cross a per-OS backend. macOS: cell 5 tested via a bad-selector `op_failed` because the extension bond is live, same `ToolError` class either way |
| E: every tool called | not run | **pass†** | not run | **pass** | 26 of 26 called on both. WSL browser tools were dispatch-only (bond held elsewhere); macOS browser tools actually round-tripped (`†` see the macOS note). Input tools on macOS are dispatch-only until the Quartz rig exists, same reason as WSL for the other OSes |
| overall | **not run** | **pass†** | **partial** | **pass** | Linux has the gate green and nothing driven. Windows covers A to C. macOS now carries the whole runbook, with the input-rig caveat noted; WSL was the first to do so |

### Status notes

**WSL (2026-08-09), Parts A to E, the OS that carries the live work.** WSL2,
Python 3.12.3, real Windows desktop behind the PowerShell bridge.

- **Part A, reproduced.** `/tmp/cua-repro` resolved `mcp 2.0.0` against
  `vadgr-computer-use 0.6.5`. `python -c "import computer_use.mcp_server"`
  exited `1` with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`
  raised from `computer_use/mcp_server.py:36`, and
  `vadgr-cua --transport stdio </dev/null` exited `1` the same way, from the
  console-script shim, before it could answer anything. The defect is exactly
  as issue #39 reports it.
- **Part B, pass.** `/tmp/cua-26` resolved `mcp 2.0.0` and
  `vadgr-computer-use 0.6.6`. `pytest computer_use/tests -q` exited `0`:
  **726 passed, 28 skipped**. `ruff check computer_use` exited `0`.
  - **All four plants fired.** The floor: with `mcp>=1.0` restored,
    `pip install --dry-run <checkout> "mcp<2"` exited `0` and would have
    installed `mcp-1.29.0` beside the package; with `mcp>=2.0` the same command
    exited `1` with `ResolutionImpossible`. The catalogue: removing
    `get_screen_size`'s `@mcp.tool()` failed the set equality, naming the tool.
    The scan: restoring the removed import in `browser/tool.py` failed the
    source scan, naming the file. The run path: reverted, an `sse` start exited
    `1` with `ValueError: "Settings" object has no field "port"` while a `stdio`
    start still exited `0` clean, so the branch is a real fix on the `sse` arm
    and not a regression on the `stdio` one.
- **Part C, pass, surface unchanged.** `before.json` from the published `0.6.5`
  on `mcp 1.29.0`, `after.json` from this branch on `mcp 2.0.0`. **26 tools on
  both sides**, `diff -u` exited `0` and printed nothing, and the two files hash
  to the same sha256
  (`f1a0fe17a323ac5e627b967cbdb8538c46b0b10b09be0ca3da82347d8a536783`). The
  catalogue is `browser browser_eval click clipboard data double_click drag env
  fs get_platform get_platform_info get_screen_size http key_press move_mouse
  profiles right_click screenshot screenshot_region scroll shell tabs tempfile
  time type_text windows`, and the ten carrying an `outputSchema` are
  `click double_click drag get_platform get_screen_size key_press move_mouse
  right_click scroll type_text`, identical across the majors. The `2024-11-05`
  handshake completing against the 2.x server is the cell that matters for a
  foreign host speaking an older revision. The result-envelope question is F5.
- **Part D, pass, cells 1 to 7.** Two headless sessions against
  `/tmp/cua-26/bin/vadgr-cua`, plus one direct transport check.
  - **Cell 1 pass.** `mcp_servers: [{"name": "vadgr-computer-use", "status":
    "connected"}]` and **26** cua tools in the session's tool list.
  - **Cell 2 pass.** `fs(op=read, /tmp/cua-e2e-066/input.txt)` returned
    `sentinel-a9f31c` and `fs(op=write, /tmp/cua-e2e-066/output.txt)` returned
    `{"path": ..., "written": 16}`, both `is_error` falsy.
  - **Cell 3 pass.** `screenshot(format=jpeg)` returned an `image` content block
    with `media_type` `image/jpeg`; a later `screenshot_region(format=png)`
    returned `image/png`. The `Image` path crosses the moved import and is
    intact.
  - **Cell 4 pass.** `get_platform_info` returned the dict
    `{"platform": "wsl2", "backend_available": true}`; `get_platform` and
    `get_screen_size`, the `-> str` tools that carry an `outputSchema`, returned
    `{"result": "wsl2"}` and `{"result": "1366x768"}` as structured content.
  - **Cell 5 pass.** With no browser session live, `tabs(op=open)` and
    `browser(op=navigate)` both came back as `tool_result` with `is_error: true`
    carrying the full text verbatim: the reason
    `[not_connected] the native host is registered but no browser session is
    live`, the remediation `To fix: open Chrome/Edge and enable the vadgr-cua
    extension`, and the guided pixel fallback. Not a masked generic error, so
    `ToolError` from the new module is the class the SDK still recognises, and
    the agent then acted on the guidance and fell back to the pixel tools.
  - **Cell 6 pass.** Ground-truthed outside the agent:
    `/tmp/cua-e2e-066/output.txt` read back from the shell contains
    `SENTINEL-A9F31C`, 16 bytes on disk. The side effect is real and was not
    taken from the agent's summary.
  - **Cell 7 pass.** `vadgr-cua --transport sse --port 8791` came up and stayed
    up; `GET /sse` answered `HTTP 200` with
    `event: endpoint / data: /messages/?session_id=...`, and an unknown path
    answered `404`, so the app is routing rather than a bare socket. The
    `--port` flag reaches the transport through `run()` now that there is no
    settings object to carry it.
- **Part E, pass, 26 of 26 called.** Against `/tmp/cua-66-sweep`, a
  **non-editable** install built from the branch after `mcp 2.0.0` was
  published: `pip install <checkout>` exited `0` resolving `mcp-2.0.0`,
  `mcp-types-2.0.0` and `vadgr-computer-use-0.6.6`, and
  `import computer_use` from `cwd=/tmp` resolved into site-packages rather than
  the working tree. 46 `tools/call` frames in one journal. Every row of the
  part's table above is marked from that journal and from a ground-truth read
  taken outside the session. Four findings came out of it, F2 to F4 from the
  tools and F6 from the pointer, and none is a regression from this patch.

**Windows native, why Part B is partial.** The full `pytest` run is **not
available on Windows and was not before this patch**:
`computer_use/tests/conftest.py`'s autouse fixture patches
`computer_use.platform.linux`, which imports `fcntl`, so collection errors on
every module. That is pre-existing and unrelated to `mcp`; the CI matrix is
Linux and macOS only. What this patch changes on Windows is the install
resolving 2.x and the entry point importing, and both were run against a fresh
venv on a copy of this branch with Windows Python 3.12.10: `pip install -e .[dev]`
resolved `mcp 2.0.0` and `vadgr-computer-use 0.6.6`, `import
computer_use.mcp_server` succeeded, and stdio served the same 26 tools.

**Linux and macOS, what "pass (CI)" rests on.** The `test` workflow is green on
every matrix row for the first time since 2026-08-04: `ubuntu-latest` and
`macos-latest`, each on 3.10 / 3.11 / 3.12, plus `lint`. Those runners build
their environment from `pyproject.toml` on every push, so each row is a fresh
install resolving `mcp` 2.x, which is the defect this patch closes. **The matrix
going green is the CI half of the proof**, not a formality: red on this exact
`ModuleNotFoundError` is what issue #39 looked like from the outside.

**macOS (2026-08-09), Parts A to E, driven by hand.** macOS 26.5.2 arm64,
Python 3.12.13 (Homebrew), Google Chrome with the 0.6.0 extension bond live from
prior runbooks (same bond, `bcbdnpafilijienocokppgmfianhehll`, native host at
`~/.vadgr-cua/host.sh`). Each venv built fresh for this pass exactly as the
Setup block requires; not the pre-existing checkout venv.

- **Part A, reproduced.** `/tmp/cua-repro` resolved `mcp 2.0.0` against
  `vadgr-computer-use 0.6.5`. Running from `cd /tmp` so the working tree cannot
  shadow the installed package (the trap the runbook flags),
  `python -c "import computer_use.mcp_server"` exited `1` with
  `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` raised from
  `/private/tmp/cua-repro/lib/python3.12/site-packages/computer_use/mcp_server.py:36`,
  and `vadgr-cua --transport stdio </dev/null` exited `1` the same way. Same
  defect the WSL pass recorded. On my first attempt I ran the import check from
  the checkout directory and it exited `0` because the working-tree 0.6.6
  shadowed 0.6.5, which is the load-bearing `cd` the runbook calls out; the
  actual proof is the `/tmp`-run above.
- **Part B, pass.** `/tmp/cua-26` resolved `mcp 2.0.0` and
  `vadgr-computer-use 0.6.6`. `pytest computer_use/tests -q` exited `0`:
  **706 passed, 48 skipped** (the 20-test delta vs WSL's 726/28 is macOS
  skip-guards on platform-specific tests, not a coverage drop). `ruff check
  computer_use` exited `0`. Plant 1 (floor): with `mcp>=2.0` in place,
  `pip install --dry-run <checkout> "mcp<2"` exited `1` with
  `ResolutionImpossible`, so the floor really is what prevents the 1.x resolve.
  Plants 2–4 already fired on WSL and are not re-run per OS; they exercise
  wire-surface / source-scan / run-path assertions that are OS-independent.
- **Part C, Not-Needed on macOS.** The catalogue is derived from decorators
  with no OS branch; WSL already ran C to a byte-identical diff.
- **Part D, pass, cells 1 to 7.** Two headless
  `claude --dangerously-skip-permissions --mcp-config .mcp.json
  --strict-mcp-config --output-format stream-json --verbose -p …` runs against
  `/tmp/cua-26/bin/vadgr-cua`, plus one direct transport check.
  - **Cell 1 pass.** The session lists
    `mcp_servers: [{"name": "vadgr-computer-use", "status": "connected"}]` and
    **26** cua tools (`mcp__vadgr-computer-use__*`) in the session tool list.
  - **Cell 2 pass.** `fs(op=read, /tmp/cua-e2e-066-macos.b6pwEi/input.txt)`
    returned `sentinel-macos-a9f31c` (21 bytes) with `is_error` falsy;
    `fs(op=write, output.txt)` returned `{"path": ..., "written": 21}`.
  - **Cell 3 pass.** `screenshot(format=jpeg)` returned an image content block
    with `mimeType: image/jpeg`, 180 840 base64 chars. The `Image` path crosses
    the moved import and is intact on the macOS Quartz backend.
  - **Cell 4 pass.** `get_platform_info` returned
    `{"platform": "macos", "backend_available": true}` (dict payload flattened
    to text by Claude Code's stream serializer, same shape as WSL's cell 4
    where the reader also saw text; the `outputSchema` path is exercised
    server-side either way).
  - **Cell 5 pass, via `op_failed` rather than `not_connected`.** The runbook's
    canonical trigger for cell 5 is a `browser` op with the extension absent,
    which returns `[not_connected]`. On this machine the extension bond is live
    (from prior runbook work) and cua re-registers the native host on every
    `_maybe_self_register` call, so a not_connected state cannot be forced
    non-invasively. Cell 5's actual claim is that
    `browser/tool.py`'s `ToolError` reaches the model with its guidance intact,
    which is exception-class and dispatch-path property, not a reason-code
    property. Same claim was proved by driving
    `browser(op=click, selector="#definitely-does-not-exist-12345")` on a real
    page: `tool_result` came back with `is_error: true` carrying verbatim
    `Error executing tool browser: [op_failed] no element matches
    #definitely-does-not-exist-12345 Fallback: call \`screenshot\` to see the
    page, then act with the pixel tools \`click\`/\`type_text\`/\`scroll\` by
    coordinates (degraded mode - slower, less precise; install the extension
    for the reliable path).` The pixel-fallback guidance is preserved and this
    is not a masked generic error, so the ToolError class the SDK still
    recognises is the one being raised, which is the migration proof.
  - **Cell 6 pass.** Ground-truthed off-agent: `cat
    /tmp/cua-e2e-066-macos.b6pwEi/output.txt` returned `SENTINEL-MACOS-A9F31C`,
    21 bytes, `od -c` shows the bytes on disk. Not taken from the agent's
    summary.
  - **Cell 7 pass.** `vadgr-cua --transport sse --port 61970` came up
    (uvicorn `Application startup complete`, `Uvicorn running on
    http://127.0.0.1:61970`); `GET /sse` answered `HTTP 200` with
    `event: endpoint / data: /messages/?session_id=…`, an unknown path
    `GET /definitely-not-a-route` answered `404`. Both requests logged by
    uvicorn server-side. `--port` reaches the transport through `run()`.
- **Part E, pass, 26 of 26 called.** Against `/tmp/cua-66-sweep`, a
  **non-editable** install built from the branch (`pip install <checkout>` at
  `cwd=/tmp`; `import computer_use` resolves to
  `/private/tmp/cua-66-sweep/lib/python3.12/site-packages/computer_use/`, not
  the working tree). A `sweep066_macos.py` driver speaks JSON-RPC on stdio,
  runs `initialize` + `tools/list` + `tools/call` for every tool, journals every
  frame (image `data` fields elided to their byte length), and reads
  ground-truth off-agent for the rows that have one.
  - **`fs`** (`write`/`read`/`list`/`stat`/`delete`): sentinel round-trip,
    listing includes the created file, `stat` returns kind/size, `delete`
    returns `{"deleted": true}`, `Path(...).exists()` after = `False`. Pass.
  - **`shell`** (`run`/`which`): `shell.run` with `shell_mode: true` on a
    compound `sh -c '…exit 7'` returned `{"returncode": 7, "stdout":
    "out-macos\n", "stderr": "err-macos\n"}` and left `touched` in
    `/tmp/cua-e2e-066-macos-sweep/shell.out` on disk; `shell.which sh` returned
    `/bin/sh`. Pass. (First attempt used `shell_mode: false` with a shell
    string and got `[Errno 2] No such file or directory` because subprocess
    treated the whole string as an exec path — driver misuse, not a tool
    defect.)
  - **`http`** (`get`/`post` against a local stdlib echo server): the echoed
    body carried the request's `X-Sweep: macos-get` and `X-Sweep: macos-post`
    headers back verbatim, and the POST body `{"ping": "pong"}` round-tripped
    byte-identical in the echoed `body` field. Pass.
  - **`env`** (`set`/`get`): `set VCU_SWEEP=<sentinel>`, `get` returned the
    same value; process-scoped by contract, so the second call is the ground
    truth. Pass.
  - **`time`** (`now`/`sleep`): `now` returned an ISO-8601 with `+00:00`;
    `sleep 0.25` reported `{"slept": 0.25}` and wall elapsed was `0.257 s`.
    Pass.
  - **`tempfile`** (`temp_path prefix=sweep- suffix=.dat`): returned
    `/var/folders/…/T/sweep-de9470249f09.dat`, `Path(...).exists()` = `False`
    (the documented contract). Pass.
  - **`data`**: `parse_json`/`serialize_json`/`parse_csv`/`serialize_csv` all
    round-tripped; `parse_yaml` returned `is_error: true` with the guided
    `PyYAML` message, which is F2 from the WSL note and the same declared
    design here. Pass.
  - **`clipboard`** (`copy`/`paste`): `copy` returned
    `{"backend": "pbcopy", "bytes": <n>}`, `paste` returned the sentinel, and
    the off-agent `/usr/bin/pbpaste` read back the exact same sentinel by a
    path the tool did not use. Pass.
  - **`get_platform`**: `macos`; **`get_platform_info`**: `{"platform":
    "macos", "backend_available": true}`; **`get_screen_size`**:
    `<w>x<h>` in display coordinates. Pass.
  - **`screenshot`**: image content, `mime=image/jpeg`, 149 334 bytes, magic
    `ffd8ffe0` (a valid JPEG). Pass.
  - **`screenshot_region`** (`0,0,200,120,png`): `mime=image/png`, 12 279
    bytes, magic `89504e47`. Pass.
  - **Input tools** (`move_mouse`, `click`, `double_click`, `right_click`,
    `drag`, `scroll`, `type_text`, `key_press`): dispatched with harmless args
    (target `(5,5)`, empty `type_text`, `key_press escape`, `scroll amount=0`),
    each returned its `Clicked at …` / `Typed: …` / `Pressed: …` string. The
    macOS Quartz backend is exercised end-to-end, but there is no on-screen
    rig to ground-truth the event was actually received the way the WSL note's
    rig does. Marked **dispatch-only**, same reason WSL's table marks Linux /
    macOS / native Windows the same way: each OS's executor is a separate
    surface and needs its own rig.
  - **Browser tier**, five tools (`browser`, `browser_eval`, `tabs`,
    `windows`, `profiles`): **all round-tripped** because the extension bond
    is live on this machine (the opposite of WSL's Part E, where those five
    were dispatch-only because another cua process held the bond). `browser
    status` returned `{"connected": true, …, "profiles": [<one>]}`;
    `browser_eval 1+1` returned `{"value": 2, "via": "cdp", "target":
    {"window_id": …, "tab_id": …, "url": "https://example.com/"}}`; `tabs
    list` returned the full window/tab tree with the user's tabs marked
    `owned: false` and one browser session live; `windows list` returned the
    per-window summary; `profiles list` returned `{"profiles": [{"profile_id":
    …, "browser": "chrome", "is_current": true, "window_count": 4,
    "tab_count": 12, …}]}`. So on macOS Part E is a stronger read than WSL's:
    the browser tier's dispatch **and** its page ops were exercised.

**Windows native, why Part B is partial.** The full `pytest` run is **not
available on Windows and was not before this patch**:
`computer_use/tests/conftest.py`'s autouse fixture patches
`computer_use.platform.linux`, which imports `fcntl`, so collection errors on
every module. That is pre-existing and unrelated to `mcp`; the CI matrix is
Linux and macOS only. What this patch changes on Windows is the install
resolving 2.x and the entry point importing, and both were run against a fresh
venv on a copy of this branch with Windows Python 3.12.10: `pip install -e .[dev]`
resolved `mcp 2.0.0` and `vadgr-computer-use 0.6.6`, `import
computer_use.mcp_server` succeeded, and stdio served the same 26 tools.

**Linux, what "pass (CI)" rests on.** The `test` workflow is green on every
matrix row: `ubuntu-latest` and `macos-latest`, each on 3.10 / 3.11 / 3.12,
plus `lint`. Those runners build their environment from `pyproject.toml` on
every push, so each row is a fresh install resolving `mcp` 2.x, which is the
defect this patch closes. **The matrix going green is the CI half of the
proof**, not a formality: red on this exact `ModuleNotFoundError` is what
issue #39 looked like from the outside. Linux was not driven by hand on this
pass; that is genuinely owed.

## Evidence

Filed to the evidence bundle kept for this minor outside this repo, with a
sha256 recorded for every file. Parts A, C and D's artifacts were **collected at
the end of the work rather than filed at each boundary**, and the bundle says so
rather than implying otherwise; Part E's were written as it ran, which does not
retire the earlier note.

- **Part A:** the repro stderr, showing the `ModuleNotFoundError` at
  `mcp_server.py:36` and both non-zero exits.
- **Part B:** the `pytest` output from the fresh 2.x environment, and the
  `pip install` log showing `mcp-2.0.0` resolved into an empty virtualenv.
- **Part C:** `before.json`, `after.json`, the empty diff, the probe transcript
  for the result-envelope question, and `tools_snapshot.py` itself.
- **Part D:** two run journals, one for the tier 0 / image / structured cells and
  one for the `ToolError` cell.
- **Part E:** the full JSON-RPC journal (46 calls), the YAML-extra journal, the
  input rig's event log, a transcript of every independent ground-truth read
  with its exit code, and all five harness scripts: the two JSON-RPC drivers,
  the input rig, the local echo server and the image decoder.

Image payloads in the journals are elided to their byte length; every other
field, `mimeType` included, is intact. They were pictures of a working machine's
screen and carry no evidential weight the surrounding frames do not.

## Findings

### F1 (fixed): a fresh install cannot start

`mcp` 2.0.0 removed `mcp.server.fastmcp`, and the unbounded `mcp>=1.0` floor let
a new install resolve it, so `vadgr-cua` died at import for every new user.

Fixed by moving every call site onto `mcp.server.mcpserver` and the floor to
`mcp>=2.0`. **What proves it:** Part A red on the published `0.6.5` in an
environment built after the release, Part B green in the same kind of
environment on this branch, Part C showing the surface unmoved across the
change, Parts D and E showing a real client and all 26 tools working from it,
and the CI matrix green on every row.

### F2 (open, out of scope): `data`'s YAML ops need an extra a default install does not pull

On the non-editable install of the branch, `data(op="parse_yaml")` returns
`is_error: true` with `YAML support requires PyYAML. Install with
'pip install pyyaml'`. After `pip install pyyaml` both YAML ops pass and round
trip.

This is the declared design: `pyyaml` is the optional `data-yaml` extra, and the
error is guided rather than a stack trace. It is recorded because the sweep is
the first thing to have observed it on the wire, and because a caller reading
the tool list sees six `data` sub-ops with no hint that two of them need an
extra. **Disposition:** not a defect and not this patch's to change; worth a
docstring line in a later minor.

### F3 (open, out of scope): `type_text` goes through the clipboard

Driven against the rig, `type_text` arrives as `KeyDown key=V ctrl=True`, not as
synthesized characters, and the typed string is left on the system clipboard
afterwards (confirmed by an independent `Get-Clipboard`).

That is a real side effect a caller cannot see from the tool's description or
its return string: anything an agent types clobbers whatever the operator had
copied. **Provably pre-existing:** `git diff --name-only <merge-base>..HEAD --
computer_use/bridge/ computer_use/platform/wsl2.py` is empty, so this branch does
not touch the code that does it. **Disposition:** not fixed here, because this
patch's whole claim is that no tool's behaviour changes, and changing input
implementation inside it would be an unrelated regression risk. Owed a minor of
its own.

### F4 (open, out of scope): `key_press` drops an unrecognised key silently

`key_press(keys="win+vcu_no_such_key")` returned `Pressed:
win+vcu_no_such_key` with no error, and the Start menu opened: the recognised
half of the combination was pressed and the unrecognised half was discarded
without a word. Confirmed by screenshot, and the desktop was restored with an
`escape` immediately afterwards.

An agent asking for a combination it half-misspelled gets a success and a
different keystroke than the one it asked for, which is the failure mode the
tier's "never silently wrong" doctrine exists to prevent. **Provably
pre-existing**, by the same empty diff as F3. **Disposition:** not fixed here,
same reasoning as F3, and owed the same minor.

### F5 (observation): the predicted 2.x result field does not exist

The 2.x `CallToolResult` was expected to add a `resultType` field to every
`tools/call` response, as the SDK's own change rather than this package's. It
does not appear on the wire at any revision this server negotiates: at
`2025-06-18`, `2025-11-25` and `2024-11-05` the result keys are exactly
`content`, `isError`, `structuredContent` on **both** majors, and the field is
absent. A client asking for `2026-07-28` is negotiated down to `2025-11-25`.

So the `tools/call` envelope is unchanged too, not only the catalogue. Measured,
not assumed, and recorded because a prediction that did not come true is worth
as much as one that did.

### F6 (observation): the pointer lands within two pixels, not on the pixel

`click` at a display coordinate mapping to real `1012,697` was received at
`1011,695`; `right_click` at the same display coordinate was received at
`1011,697` and the wheel event at `1012,697`. So the bridge's smooth move ends
within about two pixels of its target, and not always at the same offset.

Harmless for any real target, since nothing is clicked with two-pixel precision,
and recorded only so a future run that sees a larger drift has a baseline to
compare against. `move_mouse` on its own landed exactly, so the jitter is in the
click path's move rather than in the coordinate mapping.

## What this runbook cannot prove

- **That the browser tier still drives a page.** Five tools dispatch correctly
  and return their own guided error, and that is all this pass shows of them.
  The reason is the single-listener bond, not the migration, and the run that
  would settle it is described in Part E.
- **That the input tools work anywhere but WSL.** The rig proves the WSL2
  PowerShell bridge carries clicks, drags, wheel notches and keystrokes with
  their parameters intact. It says nothing about the Linux X11 and uinput paths,
  the macOS Quartz path, or native Windows, each of which is a different
  executor.
- **That macOS works beyond installing and importing.** No macOS hardware was
  held for this pass.
- **That the full suite passes on native Windows.** It does not collect there
  and did not before this patch, for a reason unrelated to `mcp`.
- **That a real end user's resolver picks what ours did.** Every environment
  here resolved `mcp 2.0.0` because that is what PyPI served on the day. The
  floor forbids a 1.x, which is the property that matters, and Part B's first
  plant is what proves the floor rather than the observation.
- **Anything about the extension's own code.** No extension change ships in
  `0.6.6` beyond the version bump, and no extension suite is part of this
  runbook.
