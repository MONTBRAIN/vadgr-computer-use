# mcp 2.x migration 0.6.6 - end to end test runbook

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

## The approach

Same as `0.4.0` / `0.5.0` / `0.6.0` / `0.6.1`: the live part is driven by a real
agent over `claude -p`, never a script, on goal-level tasks. The verdict is the
`tool_use` / `tool_result` stream, not the agent's prose (`../README.md`).

**The one addition no previous runbook needed: every environment below is built
fresh for the run.** A virtualenv that predates `mcp` 2.0.0 holds a 1.x and
would pass every cell here against `0.6.5` itself. That is exactly how the local
checkout stayed green for a week while the published package was broken, so a
pre-existing virtualenv is not a shortcut, it is the failure mode.

Each group states the environment it needs. The environments are built once at
the start of their group; nothing in a group invalidates what a later member of
it needs.

## Group 0 - reproduce the defect before changing anything

The negative control. Without it every group below is decoration.

```bash
python3 -m venv /tmp/cua-repro
/tmp/cua-repro/bin/pip install "vadgr-computer-use==0.6.5"
/tmp/cua-repro/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"
/tmp/cua-repro/bin/python -c "import computer_use.mcp_server"
/tmp/cua-repro/bin/vadgr-cua --transport stdio </dev/null
```

Read the exit codes directly. Do not pipe them into anything: `cmd | head`
reports `head`'s status.

Expected: `mcp` resolves to a 2.x, and both the import and the console script
exit non-zero with the `ModuleNotFoundError`.

## Group 1 - the repo's suites, on mcp 2.x, from a fresh virtualenv

```bash
python3 -m venv /tmp/cua-26
/tmp/cua-26/bin/pip install -e "<checkout>[dev]"
/tmp/cua-26/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"
/tmp/cua-26/bin/python -m pytest computer_use/tests -q
/tmp/cua-26/bin/ruff check computer_use
```

The version print is a cell of its own: it must say a 2.x. If it says
1.something the floor in `pyproject.toml` did not land and everything after it
is meaningless. `ruff` runs in the same environment because CI lints before it
tests.

**Negative controls, one plant at a time, restored after each.** A check that
has never fired is decoration.

| plant | what must happen |
|---|---|
| revert the dependency floor to `mcp>=1.0` | `pip install --dry-run <checkout> "mcp<2"` succeeds and resolves a 1.x, rebuilding the defect. With `mcp>=2.0` the same command is `ResolutionImpossible` |
| drop one `@mcp.tool()` decorator | the wire-surface set equality fails, naming the missing tool |
| put a `mcp.server.fastmcp` import back in any module | the source scan fails, naming the file |
| revert the run path to `mcp.settings.port = args.port` | an `sse` start dies with `ValueError: "Settings" object has no field "port"`; a `stdio` start still comes up, so the branch is not a regression in disguise |

## Group 2 - the tool surface, as a diff and not as an assertion

The comparison is between what a client reads from the published `0.6.5` served
on `mcp` 1.x, and what it reads from this branch served on `mcp` 2.x. Both
snapshots come from `tools/list` over raw JSON-RPC on stdio, so the probe shares
no SDK code with either side and the comparison is of what a client sees rather
than of what an internal dictionary holds.

`/tmp/cua-repro-1x` is the published `0.6.5` with `mcp<2` pinned alongside it.
**That pin is the harness's, not the product's**: it is the workaround issue #39
names, and it exists only to get a running 1.x baseline to compare against.

```bash
python3 -m venv /tmp/cua-repro-1x
/tmp/cua-repro-1x/bin/pip install "vadgr-computer-use==0.6.5" "mcp<2"

python3 tools_snapshot.py /tmp/cua-repro-1x/bin/vadgr-cua --transport stdio > before.json
python3 tools_snapshot.py /tmp/cua-26/bin/vadgr-cua      --transport stdio > after.json
diff -u before.json after.json && echo "SURFACE UNCHANGED"
```

`tools_snapshot.py` speaks `initialize`, `notifications/initialized`, then
`tools/list` with cursor paging, sorts by name and prints canonical JSON. It is
reproduced in the evidence directory beside the snapshots it produced.

`diff` must exit `0` on the whole file, not on a name list: `description` and
`inputSchema` are in the comparison because a schema that gains a `required`
entry is exactly the change a name comparison misses. **26 entries on both
sides.** If the diff is not empty, the difference is the finding and it is fixed
in this patch rather than noted, because a per-tool schema delta would mean the
two majors derive metadata differently, which is the one thing this migration
claims they do not.

The same property is held by two tests in `computer_use/tests/test_mcp2_surface.py`,
so a regression fails a PR and not only a runbook: the wire names as **set
equality** against the full 26, and a source scan proving no module under
`computer_use` names the removed package.

## Group 3 - the live stdio session, with the stream as the verdict

The `Agent` tool inherits the parent session's MCP servers and cannot load a
freshly built one, so this is a separate headless process with its own
`.mcp.json`, pointed at the group 1 virtualenv.

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

Tasks are goal-level, never "call the screenshot tool". The cells enumerate
rather than sample, one per tier, so the migration is proven across the whole
dispatch path rather than on the cheapest tool.

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

## Group 4 - platform coverage

This patch touches no OS-specific surface: no socket, no path, no process spawn,
no registry. What is genuinely per-OS is the install resolving `mcp` 2.x and the
entry point importing, so that is what each platform must show.

## Automated gate

`pytest` (fresh 2.x virtualenv) and `ruff check computer_use`, both read from
their own exit codes. A green suite is necessary, never sufficient: groups 2 and
3 are the gate.

## Results

> **Status: WSL and Windows-native run complete (2026-08-09) - pass, no defect
> found.** Groups 0 to 3 ran on WSL; group 1's install-and-serve half also ran on
> Windows native. The tool surface diffs clean at 26 tools across both majors.

- **Group 0 (WSL, 2026-08-09) - reproduced.** `/tmp/cua-repro` resolved
  `mcp 2.0.0` against `vadgr-computer-use 0.6.5`.
  `python -c "import computer_use.mcp_server"` exited `1` with
  `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` raised from
  `computer_use/mcp_server.py:36`, and `vadgr-cua --transport stdio </dev/null`
  exited `1` the same way, from the console-script shim, before it could answer
  anything. The defect is exactly as issue #39 reports it.

- **Group 1 (WSL, 2026-08-09) - pass.** `/tmp/cua-26` resolved `mcp 2.0.0` and
  `vadgr-computer-use 0.6.6`. `pytest computer_use/tests -q` exited `0`:
  **726 passed, 28 skipped**. `ruff check computer_use` exited `0`.
  - All four negative controls fired. The floor: with `mcp>=1.0` restored,
    `pip install --dry-run <checkout> "mcp<2"` exited `0` and would have
    installed `mcp-1.29.0` beside the package; with `mcp>=2.0` the same command
    exited `1` with `ResolutionImpossible`. The catalog: removing
    `get_screen_size`'s `@mcp.tool()` failed the set equality, naming the tool.
    The scan: restoring the removed import in `browser/tool.py` failed the
    source scan, naming the file. The run path: reverted, an `sse` start exited
    `1` with `ValueError: "Settings" object has no field "port"` while a `stdio`
    start still exited `0` clean, so the branch is a real fix on the `sse` arm
    and not a regression on the `stdio` one.

- **Group 2 (WSL, 2026-08-09) - pass, surface unchanged.** `before.json` from
  the published `0.6.5` on `mcp 1.29.0`, `after.json` from this branch on
  `mcp 2.0.0`. **26 tools on both sides**, `diff -u` exited `0` and printed
  nothing, and the two files hash to the same sha256
  (`f1a0fe17a323ac5e627b967cbdb8538c46b0b10b09be0ca3da82347d8a536783`). The
  catalog is `browser browser_eval click clipboard data
  double_click drag env fs get_platform get_platform_info get_screen_size http
  key_press move_mouse profiles right_click screenshot screenshot_region scroll
  shell tabs tempfile time type_text windows`, and the ten carrying an
  `outputSchema` are `click double_click drag get_platform get_screen_size
  key_press move_mouse right_click scroll type_text`, identical across the
  majors.
  - **Observation, recorded because it contradicts what was expected.** The 2.x
    `CallToolResult` was expected to add a `resultType` field to every
    `tools/call` response, as the SDK's own change rather than cua's. It does
    not appear on the wire at any revision this server negotiates: at
    `2025-06-18`, `2025-11-25` and `2024-11-05` the result keys are exactly
    `content`, `isError`, `structuredContent` on **both** majors, and the field
    is absent. A client asking for `2026-07-28` is negotiated down to
    `2025-11-25`. The `tools/call` envelope is therefore unchanged too, not only
    the catalog. Measured, not assumed.
  - The `2024-11-05` handshake completing against the 2.x server is the cell
    that matters for a foreign host speaking an older revision.

- **Group 3 (WSL, 2026-08-09) - pass, cells 1 to 7.** Two headless sessions
  against `/tmp/cua-26/bin/vadgr-cua`, plus one direct transport check.
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
  - **Cell 6 pass.** Ground-truthed outside the agent: `/tmp/cua-e2e-066/output.txt`
    read back from the shell contains `SENTINEL-A9F31C`, 16 bytes on disk. The
    side effect is real and was not taken from the agent's summary.
  - **Cell 7 pass.** `vadgr-cua --transport sse --port 8791` came up and stayed
    up; `GET /sse` answered `HTTP 200` with
    `event: endpoint / data: /messages/?session_id=...`, and an unknown path
    answered `404`, so the app is routing rather than a bare socket. The
    `--port` flag reaches the transport through `run()` now that there is no
    settings object to carry it.

- **Group 4 - platform coverage.**
  - **WSL (2026-08-09) - pass.** WSL2, Python 3.12.3. Groups 0 to 3 above ran
    here in full.
  - **Windows native (2026-08-09) - pass.** Windows Python 3.12.10, a fresh venv
    on a copy of this branch. `pip install -e .[dev]` resolved `mcp 2.0.0` and
    `vadgr-computer-use 0.6.6`, `import computer_use.mcp_server` succeeded, and
    the stdio server served the same **26** tools to the raw JSON-RPC probe. The
    full `pytest` run is **not available on Windows and was not before this
    patch**: `computer_use/tests/conftest.py`'s autouse fixture patches
    `computer_use.platform.linux`, which imports `fcntl`, so collection errors
    on every module. That is pre-existing and unrelated to `mcp`; the CI matrix
    is Linux and macOS only. What this patch changes on Windows is the install
    resolving 2.x and the entry point importing, and both are shown above.
  - **Linux - covered by CI, not run by hand.** The `test` workflow runs the
    suite on Linux across 3.10 / 3.11 / 3.12. WSL2 is the same interpreter and
    the same code path for everything this patch touches; there is no Linux-only
    surface in it.
  - **macOS - not run, no hardware.** Covered by the same CI matrix. Stated
    rather than claimed: no macOS cell here was watched by anybody.
