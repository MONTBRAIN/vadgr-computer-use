# 0.7.0 - a structured Tier 1 on Linux: e2e runbook

Until now the Linux desktop was Tier 2 only: `screenshot` plus mouse and
keyboard, driven from pixels. `0.7.0` adds a structured path: read the
accessibility tree, find an element by role and name, act on it by reference,
and wait for one to appear. Four new tools (`ui_tree`, `ui_find`, `ui_act`,
`ui_wait`), a `structured` block on `get_platform_info`, and nothing removed or
changed in Tier 2.

The claim this runbook has to prove is not "the tools return something". It is
three things a suite cannot reach:

1. **The tier reads and acts on real toolkits** (GTK, Qt, Electron), by role and
   by name, and `ui_act` observes the result by re-reading rather than trusting
   its own return.
2. **The tier fails honestly.** A stale reference is `element_gone` and clicks
   nothing; an app with no tree is `no_tree`; a missing bus is
   `at_spi_unavailable` with a remedy. A structured tier that fails dishonestly
   is worse than none, because the model loses the ability to tell "I acted"
   from "I think I acted".
3. **It is faster than the pixels.** Tens of milliseconds and tens of tokens
   against one to four seconds and a full image. A structured call that returns
   the right answer but is not faster than a screenshot is a finding.

Target OSes: Linux (the platform under test). Windows, WSL and macOS get **Tier
2 regression only** and are `not run` for the new tools, because they have no
structured tier yet and a suite is not a session.

## The approach: a Claude subagent over `claude -p`

Same driver as every runbook here: a real Claude agent over `claude -p`, given a
**goal-level** task, never a script of tool calls. The model is whatever
`claude` is configured with; the MCP config is a one-server `.mcp.json` written
for the run and pointed at the branch's virtualenv; the agent is told a goal
("open the document named X and rename it", "turn on word wrap and confirm it
took") and left to choose the tier.

**One part is deliberately not agent-driven: Part F**, the Tier 2 regression.
Its claim is that *every* Tier 2 tool still works, and an agent cannot be made to
enumerate them without being handed a script, at which point the runbook tests
the runbook. So Part F speaks to the same server directly, calls each Tier 2
tool itself, and ground-truths the side effects outside the session, exactly as
the `0.6.6` sweep did.

**The environment is built fresh for the run.** The structured tier ships a new
runtime dependency (`dbus-fast`); a virtualenv that predates the branch would
either lack it or hold a stale copy, and would prove nothing about what a new
install resolves.

## The oracle is the JSON, never the agent's prose

**`E2E/README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative test must show
`is_error: true`, and with neither stream nor transcript the result is **not
verified** rather than a pass.

**One rule this tier adds: confirm a `ui_act` with a structured read-back, never
a screenshot.** `ui_act` already re-reads the element and returns its new state,
so the read-back is in the same `tool_result`; a follow-up `ui_find` is the
independent confirmation. Web and desktop state changes faster than a screenshot
can witness, and the whole point of the tier is that it knows what happened.

Name where this pass's JSON landed: the teed `--output-format stream-json` run
journals for the agent parts, and the raw request/response journal the Part F
driver writes as it runs. Record the elapsed time of every `ui_*`
`tool_result`, because latency is a claim here and an assertion cannot catch a
call that is correct but slow (the sweep that was entirely green while one case
ran 15.2s against 0.1s to 0.8s is the standing warning).

## Prerequisites (per OS)

**Linux (the platform under test).** A real, attended, unlocked desktop session
with the accessibility stack present and the bus running:

- `at-spi2-core` installed and `at-spi-bus-launcher` / `at-spi2-registryd`
  running in the session (they start on demand on a stock GNOME or KDE).
- At least one app of each toolkit open: a **GTK** app (`gnome-text-editor` or
  `nautilus`), a **Qt** app (`kate`, or any KDE app; launch it with
  `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` if it exposes no tree), and one
  **Electron** app (`code`, launched with `--force-renderer-accessibility`).
- **Nothing the operator cares about in the foreground for Part C and Part F**:
  those parts type into and click real windows. Say so before starting.

**Linux, the negative control for Part A.** A second session, or the same one
with the accessibility bus stopped, so the "no bus" branch can be observed
returning `at_spi_unavailable` rather than assumed.

**Linux display servers.** The grounding claim (Part E) differs by server: on
**X11** an element's bounds are true screen coordinates and a pixel click lands
on them; on **Wayland** the compositor withholds the surface origin, bounds come
back window-relative, and `coordinate_trust` is `none`. Both are worth a pass,
and the per-desktop table below keeps them as separate rows.

**Windows native, WSL, macOS.** Tier 2 regression only. A fresh install of the
branch and a way to drive the Tier 2 tools; the new `ui_*` tools are `not run`
on these and the per-OS table says so rather than inheriting a CI row.

## Setup

From a stated working directory, `<checkout>` the branch under test.

The environment under test, built fresh from the branch:

```bash
python3 -m venv /tmp/cua-070
/tmp/cua-070/bin/pip install -e "<checkout>[dev]"
/tmp/cua-070/bin/python -c "import dbus_fast; print('dbus-fast present')"
```

The `import dbus_fast` line is a check of its own: the structured tier needs it,
and it is a plain wheel (not PyGObject), so a plain install must resolve it.

For Part F, a second **non-editable** install, so what is served is the package
a new user gets rather than the working tree:

```bash
python3 -m venv /tmp/cua-070-sweep
/tmp/cua-070-sweep/bin/pip install <checkout>
cd /tmp && /tmp/cua-070-sweep/bin/python -c "import computer_use; print(computer_use.__file__)"
```

**The `cd /tmp` is load-bearing.** Run that check from the checkout and
`import computer_use` resolves to the working tree, the installed package is
never touched, and a broken install reports itself healthy. Start every Part F
server with `cwd=/tmp` for the same reason.

Read every exit code directly. Do not pipe it into anything: `cmd | head`
reports `head`'s status.

## Automated gate (necessary, never sufficient)

```bash
/tmp/cua-070/bin/python -m pytest computer_use/tests -q
/tmp/cua-070/bin/ruff check computer_use
```

Both read from their own exit codes. Expected: `pytest` exit `0` (one
pre-existing, environment-sensitive uinput test, `F10` in the `0.6.6` runbook,
may fail on a box whose `/dev/uinput` state differs; it is unrelated to this
release), `ruff` exit `0`.

**The wire surface, checked here rather than assumed.** `0.6.6` proved 26 tools
hashing identically across `mcp` majors; `0.7.0` is **30 tools** and a new hash,
deliberately. The runbook asserts the split, not one total:

- The 30 names read from `tools/list` over raw JSON-RPC equal the 26 of `0.6.6`
  plus `ui_tree`, `ui_find`, `ui_act`, `ui_wait`.
- **The 26 existing entries hash byte-identically** to their `0.6.6` values.
  Grabbing them from the new catalogue and hashing only those must reproduce the
  `0.6.6` sha256; if it does not, the addition altered an existing tool, which
  this release must not do.

Green here proves the code paths and proves **nothing** about a real desktop.
Parts A to F are the gate.

## Coverage

What this pass claims, and against what. A surface with no part is uncovered and
says so, because silence reads as covered.

| surface | part |
|---|---|
| `get_platform_info` reports the `structured` block on a live bus | A |
| a session with the bus stopped reports `at_spi_unavailable` with its remedy | A |
| the 30-tool catalogue, with the 26 existing tools hashing to `0.6.6` | automated gate + A |
| `ui_tree` and `ui_find` read a **GTK** app by role and by name | B |
| `ui_tree` and `ui_find` read a **Qt** app by role and by name | B |
| `ui_tree` and `ui_find` read an **Electron** app by role and by name | B |
| `ui_act` `click`, asserted on the re-read | C |
| `ui_act` `focus`, asserted on the re-read | C |
| `ui_act` `set_text`, asserted on the re-read | C |
| `ui_act` `toggle`, asserted on the re-read state change | C |
| `ui_act` `expand`, asserted on the re-read state change | C |
| `ui_wait` returns a matching element, and times out honestly | C |
| an app with no tree gives `no_tree`, naming the app | D |
| a ref used after its window closes gives `element_gone` and **clicks nothing** | D |
| an unknown verb gives `unsupported_action` listing what the element supports | D |
| `ui_find` bounds ground a Tier 2 `click` that lands, on **X11** | E |
| on **Wayland**, `coordinate_trust` is `none` and the bounds are not aimed at | E |
| every Tier 2 desktop tool still works, unchanged | F |
| the browser tier | **uncovered**: AT-SPI does not touch it, the DOM path is unchanged |
| Windows, WSL, macOS structured tier | **not run**: no structured tier there yet |

## Part A: the capability is reported, and absence has a remedy

The structured tier is discoverable in one read, and a machine where it cannot
work says so with a fix rather than a bare failure.

**Task given to the agent:** goal-level, "tell me what this machine can do:
which platform, and whether it has the structured accessibility tier". The agent
must call `get_platform_info`.

**Verdict from the JSON:**

- On the live-bus session, the `get_platform_info` `tool_result` carries a
  `structured` object with `backend: "atspi"`, `bus_reachable: true`,
  `available: true`, a `coordinate_trust` of `real` (X11) or `none` (Wayland),
  and a non-empty `toolkits_seen`.
- On the negative-control session (bus stopped), **every** `ui_*` tool called
  returns `is_error`-carrying `at_spi_unavailable` with a non-empty `remedy`
  string, and `get_platform_info`'s `structured` reports `bus_reachable: false`,
  `available: false`. The tools are still **listed** (a catalogue that varies per
  machine breaks every consumer's snapshot); only their capability differs.

**Expected result:** the block present and truthful on a live bus, the remedy
present and the tools still listed on a dead one, and the 30/26-hash surface
check from the gate confirmed.

## Part B: read GTK, Qt and Electron, by role and by name

The tier is only as good as the trees it can actually read, and toolkits differ.

**Task given to the agent:** one goal per toolkit, for example "in the text
editor, list the buttons in its header bar" (GTK), "in Kate, find the Save
button" (Qt), "in VS Code, find the Explorer control" (Electron). The agent must
call `ui_tree` and/or `ui_find` with a `role` and with a `name`.

**Verdict from the JSON:**

- For each toolkit, a `ui_find` `tool_result` returns at least one element with a
  `ref`, a `role`, a `name`, `bounds`, and decoded `states`. A find by `role`
  (for example `push button`) and a find by `name` (for example `Save`) each
  return the expected element.
- `ui_tree` returns a depth-capped tree whose root is the focused window and
  whose nodes carry the same fields.
- **Each `ui_find` records its latency**, and it is tens of milliseconds, not
  seconds. A `ui_find` slower than a `screenshot` on the same box is a finding
  even when it returns the right element.
- An empty match (a role/name that is genuinely absent) returns `ok` with an
  empty list, **not** an error: "found nothing" is a successful read.

**Expected result:** all three toolkits read by role and by name, empty matches
`ok`, and the latency comfortably under a screenshot's.

## Part C: act on each of the five verbs, asserted on the re-read

The re-read is the tier's whole claim, so every verb is judged on the element's
state after acting, never on the return code.

**Task given to the agent:** goal-level tasks that each exercise one verb, for
example: press a button (`click`); focus a text field (`focus`); set a field's
contents (`set_text`); turn a checkbox or toggle on (`toggle`); open an expander
or a menu button (`expand`).

**Verdict from the JSON:**

- `click`: the `ui_act` `tool_result` is `ok` and its re-read `state` reflects
  the click's effect (a dialog opened, a value changed); confirm the effect with
  an independent `ui_find`, never a screenshot.
- `focus`: the re-read `state` contains `focused`.
- `set_text`: a follow-up read of the element's text returns exactly what was
  set.
- `toggle`: the re-read `state` **changes** (`pressed` or `checked` appears or
  clears). A toggle whose state did not change is a fail even if `ui_act`
  returned `ok`.
- `expand`: the re-read `state` shows `expanded`, or the expanded content becomes
  findable by a follow-up `ui_find`.
- `ui_wait`: waiting for an element that appears returns it inside the timeout;
  waiting for one that never appears returns `timeout` with the elapsed
  milliseconds, not a hang and not a false positive.
- Each `ui_act` records its latency.

**Expected result:** all five verbs confirmed on the re-read (not the return
code), `ui_wait` both found and timed out honestly, latencies recorded.

## Part D: the honest failures

The group that matters most and is the easiest to skip. It is the only one that
proves the tier fails honestly.

**Task given to the agent:** goal-level tasks that provoke each failure:

- Point the tier at an app that exposes **no accessible tree** (a raw
  `xterm`, or an app started without its toolkit's accessibility enabled) and
  ask it to read the tree.
- Find an element, **close its window**, then act on the now-stale ref.
- Act on an element with a verb it does not support.

**Verdict from the JSON:**

- The no-tree app yields `no_tree`, naming the app, not an empty success and not
  a crash.
- The stale ref yields `element_gone`, and **the pointer does not move and
  nothing is clicked** (ground-truth this: watch the cursor position and any
  side effect independently; a click on the old coordinates is the exact failure
  the tier exists to remove and is a hard fail here).
- The unsupported verb yields `unsupported_action` whose payload lists the
  actions the element *does* support.

**Expected result:** all three named errors, and the stale-ref case proven to
have clicked nothing.

## Part E: grounding, which is X11-only

Tier 1.5 is a field on `ui_find`, not a tool: every found element carries
`bounds`, so grounding a Tier 2 click is reading a number the caller already
has. Whether that number is trustworthy depends on the display server.

**Task given to the agent:** "find the Save button, then click it using its
bounds with the pixel tools" (that is, `ui_find` then a Tier 2 `click` on the
returned `bounds`).

**Verdict from the JSON:**

- **On X11**, `coordinate_trust` is `real`; the `ui_find` bounds fed to a Tier 2
  `click` land on the element (confirm with a `ui_find` read-back that the click
  had its effect). This is the F8 round trip checked rather than assumed: bounds
  out, pixel click on them, effect observed.
- **On Wayland**, `coordinate_trust` is `none` and the bounds are window-relative
  (origin withheld by the compositor). The correct behaviour is that the
  capability **says so**, and a caller does not aim a pixel click at a Wayland
  origin. The verdict here is that `get_platform_info` reported `none` and the
  agent used `ui_act` (which needs no coordinates) rather than grounding onto a
  `(0,0)`-anchored rectangle.

**Expected result:** the round trip lands on X11; on Wayland the untrustworthy
coordinate is reported as such and not used.

## Part F: the Tier 2 fallback still works, every tool

Part A to E add a tier; this part proves they removed nothing. Driven directly,
not by an agent, so all of Tier 2 is enumerated.

**Task:** drive `tools/call` for each Tier 2 desktop tool over raw JSON-RPC
against the non-editable `/tmp/cua-070-sweep` install, one journal line per
request and response, and ground-truth every side effect outside the session
(the input-event rig or an independent read, as in the `0.6.6` sweep).

**Verdict from the JSON**, a row per tool: `screenshot`, `screenshot_region`,
`get_platform`, `get_platform_info`, `get_screen_size`, `move_mouse`, `click`,
`double_click`, `right_click`, `drag`, `scroll`, `type_text`, `key_press` each
return their declared shape and their ground truth matches, exactly as `0.6.6`
recorded them. Nothing in Tier 2 changed in this release, so any divergence from
the `0.6.6` result is the finding.

**Expected result:** every Tier 2 tool called and ground-truthed, none changed.

## When a part surfaces a bug: fix it, then re-run it

**A defect found during a pass is fixed during that pass**, with a test that
fails without it, and **the part is re-run from a clean state** before being
marked. Never logged and carried to the end: the diagnosis is never fresher than
the minute it was found, a later part may build on the broken behaviour and hand
you a second false result, and a pile of deferred findings is how a runbook ends
"green with notes", which is not green.

## Repeatability

The interesting axis is the desktop and the display server, not repetition on
one box: a second run on the same machine mostly re-proves the machine. So the
repeat unit is the per-desktop table below, and the parts that carry real repeat
value are the ones that read a toolkit's tree, because a toolkit's accessibility
implementation is exactly what differs between desktops.

Close the pass with **three independent observations** where the design calls
for them, each with its own port, database and server, compared structurally:
every `tool_use` on name, input and the `tool_result`'s `is_error` and error
code, every Part F entry on argv and exit code. Read the latency numbers with
the fixture pinned first: three identical latency figures suggest one result
reused rather than three real calls. Expect the agent's prose to differ every
time and the tool calls not to.

## Per-OS results

Legend: `pass` / `fail` mean it ran. `blocked` means it could not run, and says
what broke. `not run` means nobody ran it, which is honest and visibly owed.
`Not-Needed` means there is genuinely no OS-specific surface in that part, always
with its reason. A cell is marked from observation, never expectation, and never
inherits a CI row: a suite is not a session.

Because the structured tier's behaviour differs by **desktop and display
server**, the Linux column is expanded into its own table.

### Linux, by desktop and display server

| part | GNOME Wayland | GNOME X11 | KDE (Qt) | wlroots (Sway/Hyprland) | minimal / no-a11y | notes |
|---|---|---|---|---|---|---|
| A: capability + remedy | **pass** | not run | not run | not run | not run | driven: `get_platform_info` returned the structured block; the dead-bus remedy is covered by the unit suite, not staged live |
| B: read GTK/Electron | **pass** | not run | not run | not run | not run | GTK4 read by the agent; Electron read via the backend (agent blocked by focus, see below). Qt not run: no Qt app installed here |
| C: five verbs on re-read | **partial** | not run | not run | not run | not run | click/toggle/set_text driven and self-confirmed by the agent; focus/expand covered by the unit suite |
| D: honest failures | **pass** | not run | not run | not run | not run | `element_gone` driven by the agent on a bogus ref (clicked nothing); `no_tree`/`unsupported_action` in the unit suite |
| E: grounding | **pass** | not run | Not-Needed | not run | Not-Needed | Wayland reported `coordinate_trust: none` (do not ground); the X11 round trip is not run (no X11 session here) |
| F: Tier 2 regression | not run | not run | not run | not run | not run | unchanged from `0.6.6`; a divergence is the finding |
| overall | **pass (structured)** | not run | not run | not run | not run | GNOME Wayland structured tier driven end to end by a real agent; other desktops and X11 grounding owed |

### The other operating systems

| part | Windows native | WSL | macOS | notes |
|---|---|---|---|---|
| A to E (structured tier) | not run | not run | not run | no structured tier on these yet (`0.8.0` Windows, `0.9.0` macOS); the tools are listed and return `at_spi_unavailable` |
| F: Tier 2 regression | not run | not run | not run | Tier 2 is unchanged; re-run the `0.6.6` sweep to confirm no regression |

### GNOME Shell 50 / Wayland, driven by a real agent (2026-08-11)

Ubuntu GNOME Shell 50 / Wayland, the structured tier driven by a Claude agent
over `claude -p --output-format stream-json` against a one-server `.mcp.json`
pointed at the branch's `vadgr-cua`, with `--dangerously-skip-permissions` and
`--strict-mcp-config`. The verdicts below are read from the captured
`tool_result` JSON, not the agent's prose. Two agent sessions were run (a GTK4
read/act session and an honest-failure session); the stream journals are the
evidence.

This pass was run before the PR was opened, and it found five defects the 789
green unit tests had not: they are the `Findings` below, all fixed, each with a
test that fails without the fix. The results here are the re-run after those
fixes.

**Group A, capability, pass.** The agent's `get_platform_info` returned the
structured block verbatim:
`{"backend":"atspi","bus_reachable":true,"is_enabled":true,"coordinate_trust":"none","toolkits_seen":["clutter","gtk","GTK","Chromium"],"available":true}`.

**Group B, read, pass on GTK4.** `ui_tree(depth 6)` on GNOME Text Editor returned
a tree whose leaves include the real controls (role `button` and `toggle button`:
`Open`, `New Tab`, `Document Properties`, `Minimize`, `Maximize`, `Close`),
sixteen anonymous wrapper containers deep, not a tree that stops at the
containers. `ui_find(role="toggle button")` returned the three header toggles
with their bounds and states. **Electron** (`code` launched with
`--force-renderer-accessibility`) was read through the backend rather than the
agent: its window exposed a 427-node tree with 59 `push button` elements
(`Minimize`, `Close`, `Open Quick Access`, `Toggle Chat`, and more), a
`check box`, an `entry`, and tab controls. The agent-driven Electron read could
not be captured because no window held the AT-SPI `active` state at the moment
the agent ran (the same headless-session focus limitation the runbook notes
below); the read itself works, and its role names are Chromium's
(`push button`) where GTK4's are `button`.

**Group C, act, pass on the driven verbs.** `ui_act(toggle)` on the `Open` toggle
returned, in its own response, `state.states` containing `pressed`; a second
`ui_act(toggle)` returned `state.states` without `pressed`. The action confirms
itself from its own response, which is the whole contract (this is finding F1
after its fix). `ui_act(set_text, "hello from the e2e run")` on the document text
box returned `state.text` equal to `"hello from the e2e run"`, so the write is
confirmable from the response (finding F2 after its fix). `focus` and `expand`
were not driven this pass and rest on the unit suite.

**Group D, honest failure, pass.** `ui_act(ref="atspi:deadbeef", action="click")`
on a reference never handed out returned
`{"ok":false,"error":"element_gone","message":"ref does not resolve"}` and
clicked nothing. `no_tree` and `unsupported_action` rest on the unit suite this
pass.

**Group E, grounding, pass.** `coordinate_trust` came back `none` and every bound
had `x=0, y=0` (the compositor withholds the window origin on Wayland), so the
bounds are correctly not used to ground a pixel click. The X11 round trip is not
run: there is no X11 session on this box.

**Bounds sanity (finding F4 after its fix).** Across the 86-node showing tree of
the text editor, 84 elements carried bounds and 2 (unrealised tab panels) carried
`null`; no width or height was absurd. Before the fix those two returned
`w=612489008` from uninitialised toolkit memory.

**Latency.** `ui_find` returned in roughly 2 to 9 ms and `ui_tree(depth 6)` in
roughly 8 to 13 ms, against a Tier 2 `screenshot` at about 104 ms for a 122 KB
image on the same box: the structured tier is an order of magnitude faster and
returns small text, which is the tier's whole argument.

**What this GNOME Wayland pass did not cover.** The agent-driven Electron read
(focus), Qt (no Qt app installed here), the X11 grounding round trip (no X11
session), `focus`/`expand` verbs and `no_tree`/`unsupported_action` as agent
cells (covered by the unit suite), and Part F. Those stay `not run` in the table
above and are owed on a desktop that has them.

## Evidence

The GNOME Wayland pass was captured as `--output-format stream-json` run
journals, one per agent session, with every `ui_*` `tool_result` in full:

- the GTK4 read/act session (Groups A, B, C, E): `get_platform_info`'s structured
  block, `ui_tree(depth 6)` reaching the header controls, `ui_find` on the
  toggles, `ui_act(toggle)` returning `pressed` in its own response, and
  `ui_act(set_text)` returning the `text` field.
- the honest-failure session (Group D): `ui_act` on `atspi:deadbeef` returning
  `element_gone` and clicking nothing.

For the owner's fuller pass, the remaining artifacts are owed at their own
boundaries: the dead-bus `at_spi_unavailable` remedy, the Qt and agent-driven
Electron reads, the X11 grounding round trip, and Part F's Tier 2 sweep.

## Findings

All five were found by the agent-driven pass above and were invisible to the 789
green unit tests, which is the reason this pass exists. Each is fixed, and each
fix has a test that fails without it: the toolkit's async lag, the deep wrapper
nesting, the garbage extents and the hidden dialog are all modelled in the fake
client, and the fix was watched going from red to green.

### F1 (fixed): ui_act returned the element's state from before the action

`ui_act(toggle)` returned a `state` whose `states` still lacked `pressed` while an
independent `ui_find` a moment later showed `pressed` set. The toolkit updates an
element's state asynchronously: measured on a GTK4 toggle, `pressed` was still
false the instant `DoAction` returned and true about 150 ms later. The re-read
read the stale value straight back, which breaks the tier's core contract that an
action confirms itself from its own response. The re-read now settles: it re-reads
until an observable field (a state or the text) changes from the pre-action
snapshot, up to a bounded window, and returns the moment it does. **Proof:** the
agent's `ui_act(toggle)` now returns `pressed` in its own response, and the unit
test drives a fake client whose state change is delayed two reads, which the old
single read fails.

### F2 (fixed): set_text was not confirmable

`ui_act(set_text)` returned `ok` but no `ui_*` result carried the element's text,
so a caller could not tell whether the text landed. Elements now carry a `text`
field, read from `org.a11y.atspi.Text` for text-bearing roles only (so a button
is not charged a round trip for a field it has not got). **Proof:** the agent's
`ui_act(set_text, "hello from the e2e run")` now returns `state.text` equal to
that string, and a unit test asserts the re-read carries the set text.

### F3 (fixed): ui_tree stopped at the wrapper containers

`ui_tree` returned only containers even at depth 14; the controls `ui_find` finds
were absent. GTK4 stacks about sixteen anonymous `generic`/`group` wrappers
between a window and its buttons, and the old traversal spent its depth budget on
them. Depth now counts meaningful nodes only: a named or non-structural node
costs a level, an anonymous wrapper is transparent. **Proof:** the agent's
`ui_tree(depth 6)` now reaches the header buttons, and a unit test asserts a
control sixteen wrappers deep appears in the tree at the default depth and that
the tree's leaves include what `ui_find` returns.

### F4 (fixed): some elements returned garbage bounds

An unrealised widget (a hidden tab panel) returned uninitialised memory as its
extents, e.g. `w=612489008, h=32573`, with a correct `(iiii)` signature (so it was
toolkit garbage, not a decode bug). A caller could have aimed a pixel click at a
600-million-pixel rectangle. Implausible extents (a dimension past 100000 px, or
negative) are now dropped, so the element gets no bounds rather than a nonsense
one. **Proof:** the driven tree carried zero absurd bounds and `null` for the two
unrealised panels; a unit test asserts garbage extents yield no bounds and sane
ones are kept. `x=0, y=0` on Wayland is correct (the origin is withheld) and is
not touched.

### F5 (fixed): an off-screen dialog's controls surfaced as if on screen

Controls of a dialog that was not on screen were reported with `showing` and
`visible` and then vanished from a later identical `ui_find`. `ui_find` and
`ui_tree` now prune any non-showing subtree, so an off-screen dialog's buttons do
not surface. **Proof:** a unit test builds a window with a non-showing dialog whose
button falsely reports `showing`, and asserts the button is not found while a
genuinely visible control still is.

## What this runbook cannot prove

- **Any desktop it was not run on.** Qt and Electron accessibility differ from
  GTK, and wlroots compositors differ from GNOME and KDE; a green GNOME pass says
  nothing about them. The per-desktop table keeps each honest as `not run`.
- **The Windows, WSL and macOS structured tiers**, which do not exist yet
  (`0.8.0`, `0.9.0`). On those OSes the `ui_*` tools are listed and return
  `at_spi_unavailable`; this runbook exercises none of a tier that is not there.
- **The browser tier.** AT-SPI's view of a browser is worse than the DOM's, and
  the DOM path is unchanged here, so it is out of scope by design.
- **Screen-coordinate grounding on Wayland.** The compositor withholds the
  surface origin; this is a property of Wayland, not a defect this release can
  fix, and the honest response (report `coordinate_trust: none`) is what Part E
  checks instead.
