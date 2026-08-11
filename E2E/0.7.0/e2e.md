# 0.7.0 - a structured Tier 1 on Linux: e2e runbook

Until now the Linux desktop was Tier 2 only: `screenshot` plus mouse and
keyboard, driven from pixels. `0.7.0` adds a structured path: read the
accessibility tree, find an element by role and name, act on it by reference,
and wait for one to appear. Four new tools (`ui_tree`, `ui_find`, `ui_act`,
`ui_wait`), a `structured` block on `get_platform_info`, and nothing removed or
changed in Tier 2.

**This is a Linux-only tier this release.** Windows (UIA) is `0.8.0` and macOS
(AX) is `0.9.0`: separate future minors. On Windows, WSL and macOS the entire
footprint of `0.7.0` is that the platform backend has no structured tier, so the
tool surface is identical and the `ui_*` tools honestly report
`at_spi_unavailable`. Nothing on those platforms runs the AT-SPI tests, because
there is nothing there to run yet.

**The e2e drives only apps that ship by default on a stock GNOME desktop**, so
the runbook reproduces on a standard machine with nothing extra installed.
Nothing is pulled in for the occasion, not an editor and not a Qt app: the apps
are Calculator, Text Editor, Files and Clocks, and a pass proves the tier against
what a real user already has.

The claim this runbook has to prove is not "the tools return something". It is
three things a suite cannot reach:

1. **The tier reads and acts on real default apps** by role and by name, and
   `ui_act` observes the result by re-reading rather than trusting its own
   return. The sharpest form: drive Calculator's on-screen buttons to compute a
   sum and read the answer back from its display element.
2. **The tier fails honestly.** A stale reference is `element_gone` and clicks
   nothing; an app with no tree is `no_tree`; a missing bus is
   `at_spi_unavailable` with a remedy. A structured tier that fails dishonestly
   is worse than none, because the model loses the ability to tell "I acted"
   from "I think I acted".
3. **It is small text and fast.** Small structured data instead of a full image,
   and an action that returns in milliseconds. A structured read that is a
   quarter of a megabyte, or an action that stalls for seconds, defeats the
   point, and both were real defects this pass caught.

## The approach: a Claude subagent over `claude -p`, on default apps only

The driver is a real Claude agent over `claude -p`, given a **goal-level** task
("compute seven plus eight on the calculator and read the result off its
display"), never a script of tool calls. The model is whatever `claude` is
configured with; the MCP config is a one-server `.mcp.json` pointed at the
branch's `vadgr-cua`; the agent is told a goal and picks the tools.

**Part F, the Tier 2 regression, is deliberately not agent-driven**: its claim is
that *every* Tier 2 tool still works, and an agent cannot enumerate them without
a script, at which point the runbook tests the runbook. Part F speaks to the same
server directly and ground-truths each side effect outside the session, as the
`0.6.6` sweep did.

## The oracle is the JSON, never the agent's prose

**`E2E/README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative test must show
`is_error: true`, and with neither stream nor transcript the result is **not
verified** rather than a pass.

**One rule this tier adds: confirm a `ui_act` with a structured read-back, never
a screenshot.** `ui_act` re-reads the element and returns its new state, so the
read-back is in the same `tool_result`; a follow-up `ui_find` is the independent
confirmation. The Calculator pass is the clean case: the answer is read from the
display's own `text` field, not from the agent's arithmetic.

Every number, status and table row below comes from real captured tool output:
the teed `--output-format stream-json` run journals and the direct latency
measurements named where they were taken.

## Prerequisites (Linux only)

A real, attended, unlocked GNOME session with the accessibility stack present
(`at-spi2-core`, which is on a stock GNOME) and the bus running. The apps under
test all ship by default on GNOME:

- **Calculator** (`gnome-calculator`), the primary target: it is universal, and
  it gives a clean read plus act plus confirm loop (find the digit and operator
  buttons, click a sequence, read the display).
- **Text Editor** (`gnome-text-editor`): `set_text` into the document and confirm
  from the `text` field.
- **Files** (`nautilus`): a second GTK app for read breadth.
- **Clocks** (`gnome-clocks`): optional third default app.

**Nothing the operator cares about in the foreground for the acting parts**: they
click and type into real windows. Say so before starting.

There is **no Qt app installed by default** on this GNOME image and **no X11
session** on this box; both are recorded `not run` with that reason rather than
worked around by installing or reconfiguring.

## Setup

From a stated working directory, `<checkout>` the branch under test.

```bash
python3 -m venv /tmp/cua-070
/tmp/cua-070/bin/pip install -e "<checkout>[dev]"
/tmp/cua-070/bin/python -c "import dbus_fast; print('dbus-fast present')"
```

The `import dbus_fast` line is a check of its own: the structured tier needs it,
and it is a plain wheel (not PyGObject), so a plain install must resolve it.

Read every exit code directly. Do not pipe it into anything: `cmd | head` reports
`head`'s status.

## Automated gate (necessary, never sufficient)

```bash
/tmp/cua-070/bin/python -m pytest computer_use/tests -q
/tmp/cua-070/bin/ruff check computer_use
```

Expected: `pytest` all pass but one (the pre-existing, environment-sensitive
`test_wayland_no_mutter_no_evdev_raises`, which turns on this box's
`/dev/uinput` state and is unrelated to this release), `ruff` exit `0`. The
suite also holds the **30-tool surface** (the 26 of `0.6.6` plus `ui_tree`,
`ui_find`, `ui_act`, `ui_wait`), the 26 existing entries unchanged.

Green here proves the code paths and proves **nothing** about a real desktop.
Parts A to F are the gate.

## Coverage

| surface | part |
|---|---|
| `get_platform_info` reports the `structured` block on a live bus | A |
| the `ui_*` tools return `at_spi_unavailable` with a remedy when the bus is down | A (unit) |
| Calculator: read digit and operator buttons by role and name | B |
| Text Editor and Files read by role and name | B |
| Calculator: click 7, +, 8, =, then read `15` off the display | C |
| `ui_act` `set_text` on the Text Editor document, confirmed from the `text` field | C |
| `ui_act` re-read reflects the state after acting, not before | C |
| a ref used after it is stale gives `element_gone` and clicks nothing | D |
| an unknown verb gives `unsupported_action` listing what the element supports | D (unit) |
| on Wayland, `coordinate_trust` is `none` and bounds are not aimed at | E |
| every Tier 2 desktop tool still works, unchanged | F |
| Qt read | **not run**: no Qt app installed by default here |
| X11 grounding round trip | **not run**: no X11 session here |
| the browser tier | **uncovered**: AT-SPI does not touch it, the DOM path is unchanged |

## Part A: the capability is reported

**Task given to the agent:** "tell me whether this machine has the structured
accessibility tier". The agent must call `get_platform_info`.

**Verdict from the JSON:** the `structured` object carries `backend: "atspi"`,
`bus_reachable: true`, `available: true`, `coordinate_trust` (`none` on Wayland),
and a non-empty `toolkits_seen`. A machine with the bus stopped returns
`at_spi_unavailable` with a remedy from every `ui_*` tool, and the tools stay
listed; that arm is held by the unit suite this pass rather than staged live.

## Part B: read the default apps by role and by name

**Task given to the agent:** one goal per app, for example "list the calculator's
number buttons", "find the Files toolbar buttons".

**Verdict from the JSON:** `ui_find` by `role` and by `name` returns the expected
elements with a `ref`, `bounds` and decoded `states`; `ui_tree` returns a
depth-capped tree whose leaves are the real controls, not the wrapper containers.
An empty match is `ok` with an empty list, not an error. Each read records its
latency.

## Part C: act, and confirm from the re-read

**Task given to the agent:** compute `7 + 8` on the Calculator by clicking its
buttons and read the answer off the display; separately, `set_text` a sentence
into the Text Editor and confirm it landed.

**Verdict from the JSON:**

- The Calculator's display (`role: text box`) reads `15` after the click
  sequence, read from its `text` field rather than computed by the agent.
- Each `ui_act(click)` returns `ok` and its re-read state; the effect is
  confirmed on the display, not the button.
- `ui_act(set_text)` returns a `state.text` equal to what was written.
- Each `ui_act` records its latency.

## Part D: the honest failures

**Task given to the agent:** act on a reference that was never handed out.

**Verdict from the JSON:** the stale ref yields `element_gone` and **the pointer
does not move and nothing is clicked**. The unknown-verb `unsupported_action`
case is held by the unit suite this pass.

## Part E: grounding, which is X11-only

**Verdict from the JSON:** on Wayland `coordinate_trust` is `none` and bounds are
window-relative (origin withheld by the compositor), so a caller does not aim a
pixel click at them and uses `ui_act` instead. The X11 round trip is not run:
there is no X11 session here.

## Part F: the Tier 2 fallback still works, every tool

**Task:** drive `tools/call` for each Tier 2 desktop tool over raw JSON-RPC and
ground-truth every side effect outside the session, as in the `0.6.6` sweep. Not
run this pass; owed, and the surface being unchanged is held by the unit suite.

## When a part surfaces a bug: fix it, then re-run it

**A defect found during a pass is fixed during that pass**, with a test that
fails without it, and **the part is re-run from a clean state** before being
marked. This pass did exactly that: seven defects were found and fixed, each with
a red-then-green test, and the parts re-run. They are the `Findings` below.

## Repeatability

The interesting axis is the desktop and the display server, not repetition on one
box. The per-desktop table is the repeat unit, and the parts that carry real
repeat value are the reads, because a toolkit's accessibility implementation is
what differs between desktops. Compare structurally: every `ui_*` call on name,
input and the `tool_result`'s error code, and read the latency numbers, because a
call that is correct but slow is a finding an assertion cannot catch.

## Per-OS results

Legend: `pass` / `fail` mean it ran. `not run` means nobody ran it, which is
honest and visibly owed. `Not-Needed` means there is genuinely no OS-specific
surface, with its reason. A cell is marked from observation, never expectation.

### Linux, by desktop and display server

The structured tier is Linux's, and its behaviour differs by desktop and display
server, so the Linux column is its own table. GNOME Wayland was driven by a real
agent; the others are owed.

| part | GNOME Wayland | GNOME X11 | KDE (Qt) | wlroots | notes |
|---|---|---|---|---|---|
| A: capability | **pass** | not run | not run | not run | `get_platform_info` returned the structured block |
| B: read default apps | **pass** | not run | not run | not run | Calculator, Text Editor and Files read by role and name |
| C: act and confirm | **pass** | not run | not run | not run | Calculator computed `15` read off the display; `set_text` confirmed from `text` |
| D: honest failure | **pass** | not run | not run | not run | `element_gone` on a bogus ref, clicked nothing |
| E: grounding | **pass** | not run | Not-Needed | not run | Wayland reported `coordinate_trust: none`; X11 round trip not run (no X11 session) |
| F: Tier 2 regression | not run | not run | not run | not run | owed; the surface being unchanged is unit-covered |
| overall | **pass (structured)** | not run | not run | not run | GNOME Wayland structured tier driven end to end; other desktops owed |

Qt stays `not run` on every row: no Qt app is installed by default on this GNOME
image, and this runbook does not install one.

### Windows, WSL and macOS: no structured tier this release

These platforms are first class in this project, but the structured tier is not
theirs yet, so their `0.7.0` obligation is narrow and none of it is the AT-SPI
e2e.

| surface | Windows | WSL | macOS | notes |
|---|---|---|---|---|
| the structured (`ui_*`) tier | not in this release | not in this release | not in this release | Windows UIA lands in `0.8.0`, macOS AX in `0.9.0`; the platform backend has no structured tier, so `ui_*` honestly return `at_spi_unavailable` |
| the 30-tool surface still loads | Not-Needed live | Not-Needed live | Not-Needed live | unit-covered; the four tools are added to the catalogue on every OS, and cannot be live-driven from this Linux host |
| Tier 2 unchanged | Not-Needed live | Not-Needed live | Not-Needed live | `0.7.0` touches no Tier 2 tool; unit-covered, and there is no session on those OSes from here to drive it |

`not in this release` is deliberate and is not `not run`: there is no run owed,
because the tier does not exist on those platforms until `0.8.0` and `0.9.0`. It
is not `pass` either: nothing structured was exercised there.

### GNOME Shell 50 / Wayland, driven by a real agent (2026-08-11)

Ubuntu GNOME Shell 50 / Wayland, the structured tier driven by a Claude agent
over `claude -p --output-format stream-json` against a one-server `.mcp.json`
pointed at the branch's `vadgr-cua`, with `--dangerously-skip-permissions` and
`--strict-mcp-config`. Verdicts are read from the captured `tool_result` JSON.
Three agent sessions were run, one per default app, plus an honest-failure
session; the stream journals are the evidence. This pass was run before the PR
was updated, and it found seven defects the green unit suite had not; the results
here are the re-run after the fixes.

**Group A, capability, pass.** `get_platform_info` returned
`{"backend":"atspi","bus_reachable":true,"is_enabled":true,"coordinate_trust":"none","toolkits_seen":["clutter","gtk","GTK","Chromium"],"available":true}`.

**Group B, read, pass.** On **Calculator**, `ui_find(role="button", name="7")`,
and the same for `+`, `8` and `=`, each returned the button with its bounds and
states (role `button`, Chromium and GTK both name a plain button `button`). On
**Files**, `ui_find(role="button")` returned `Back`, `Forward`, `Home`,
`Current Folder Menu`, `View Options`, `Minimize`, `Maximize`, `Close`,
`Main Menu`, and `ui_find(role="toggle button")` returned `Current Folder Menu`,
`Search Current Folder`, `View Options`, `Search Everywhere`, `Main Menu`.
`ui_tree(depth 6)` on Files reached real leaves including `grid cell` and the
buttons, not only containers.

**Group C, act and confirm, pass.** On **Calculator**, the agent clicked `7`,
`+`, `8`, `=` with `ui_act(click)`, then `ui_find(role="text box")` returned the
display with `"text": "15"`: the computed answer read off the display element,
not from the agent. On **Text Editor**, `ui_act(set_text, "structured tier works")`
returned `state.text` equal to `"structured tier works"`, so the write is
confirmable from the response.

**Group D, honest failure, pass.** `ui_act(ref="atspi:deadbeef", action="click")`
returned `{"ok":false,"error":"element_gone","message":"ref does not resolve"}`
and clicked nothing.

**Group E, grounding, pass.** `coordinate_trust` came back `none` and every bound
had `x=0, y=0` (the compositor withholds the window origin on Wayland), so the
bounds are correctly not used to ground a pixel click.

**Latency (measured directly on the running apps).** `ui_act(click)` a digit ran
in about **9 ms** median (it was about 2 s before finding F6). `ui_find` ran in
**53 ms** median on the Text Editor, **74 ms** on the Calculator and **114 ms**
on Files (with occasional D-Bus contention spikes to several hundred ms), against
a Tier 2 `screenshot` at about **76 ms** on the same box: comparable wall time to
capturing a screenshot, but returning a few hundred bytes of exact structured
data rather than a 122 KB image a model must then reason about. `ui_tree(depth 6)`
ran in **97 ms** on the Text Editor, **193 ms** on the Calculator and **291 ms**
on Files, returning **3.2 KB, 12.2 KB and 12.9 KB** respectively after finding F7
(the Files tree was about **243 KB** before it).

**What this GNOME Wayland pass did not cover.** Qt (no default Qt app here), the
X11 grounding round trip (no X11 session), `focus` and `expand` verbs and the
`no_tree` and `unsupported_action` errors as agent cells (covered by the unit
suite), and Part F. Those stay `not run` above and are owed on a desktop that has
them.

## Evidence

The GNOME Wayland pass was captured as `--output-format stream-json` run
journals, one per agent session, with every `ui_*` `tool_result` in full: the
Calculator session (Groups A, B, C, E: the structured block, the four button
finds, the click sequence, and the display reading `15`), the Text Editor
session (`set_text` returning the `text` field), the Files session (the button
and toggle finds and the tree reaching leaves), and the honest-failure session
(`element_gone` on a bogus ref). The latency figures are from direct
measurements on the running apps, named in the results above. The owed
artifacts, at their own boundaries, are the dead-bus remedy, the Qt read, the X11
grounding round trip and Part F's Tier 2 sweep.

## Findings

All seven were found by the agent-driven pass and were invisible to the green
unit suite, which is the reason this pass exists. Each is fixed, and each fix has
a test that fails without it.

### F1 (fixed): ui_act returned the element's state from before the action

`ui_act(toggle)` returned a `state` still lacking `pressed` while an independent
read a moment later showed it set: the toolkit updates state asynchronously
(measured about 150 ms after `DoAction`), and the re-read read the stale value
back, breaking the tier's contract that an action confirms itself. The re-read now
settles until an observable field changes from the pre-action snapshot. **Proof:**
`ui_act(toggle)` now returns the new state in its own response; a unit test drives
a fake client whose change is delayed and which the old single read fails.

### F2 (fixed): set_text was not confirmable

`ui_act(set_text)` returned `ok` but no result carried the element's text.
Elements now carry a `text` field, read from `org.a11y.atspi.Text` for
text-bearing roles only. **Proof:** the Text Editor `set_text` returns
`state.text` equal to what was written, and the Calculator display reads its
value through the same field; a unit test asserts the re-read carries the set
text.

### F3 (fixed): ui_tree stopped at the wrapper containers

`ui_tree` returned only containers even at depth 14; the controls `ui_find` finds
were absent, because GTK4 stacks about sixteen anonymous wrappers between a
window and its buttons and the traversal spent its depth on them. Depth now
counts meaningful nodes only. **Proof:** `ui_tree(depth 6)` reaches the controls
on every app driven; a unit test asserts a control sixteen wrappers deep appears
and that the tree's leaves include what `ui_find` returns.

### F4 (fixed): some elements returned garbage bounds

An unrealised widget returned uninitialised memory as its extents (`w=612489008`)
with a correct `(iiii)` signature, so a caller could have aimed a pixel click at a
600-million-pixel rectangle. Implausible extents are now dropped. **Proof:** the
driven trees carried zero absurd bounds; a unit test asserts garbage extents yield
no bounds and sane ones are kept. `x=0, y=0` on Wayland is correct and untouched.

### F5 (fixed): an off-screen dialog's controls surfaced as if on screen

`ui_find` and `ui_tree` now prune non-showing subtrees, so an off-screen dialog's
buttons do not surface. **Proof:** a unit test builds a window with a non-showing
dialog whose button falsely reports `showing` and asserts it is not found while a
genuinely visible control still is.

### F6 (fixed): a plain click stalled for seconds

The settle-poll that makes a toggle confirm itself was applied to every verb, so a
plain click waited the full window for the clicked button's own state to change,
which it never does: a digit click took about **2 s** on the Calculator. The
settle now runs only for the verbs whose signal is the element's own field
(`toggle`, `expand`, `focus`, `set_text`); a plain click re-reads once. **Proof:**
the digit click dropped to about **9 ms**, and a unit test asserts a plain click
does not loop on the state while the toggle self-confirm still holds.

### F7 (fixed): ui_tree was not small text

After F3, `ui_tree` reached the controls but still emitted every anonymous
wrapper, so the Files tree came back about **243 KB**, larger in tokens than the
screenshot it is meant to replace. The wrappers are now collapsed out and their
meaningful descendants hoisted. **Proof:** the Files tree dropped to about
**13 KB** with the same leaves; a unit test asserts no anonymous wrapper role
appears while the deep control still does.

## What this runbook cannot prove

- **Any desktop it was not run on.** GNOME Wayland says nothing about KDE (Qt),
  wlroots, or GNOME X11; the per-desktop table keeps each `not run`.
- **Qt**, because no Qt app ships by default on this GNOME image and the runbook
  does not install one.
- **X11 grounding**, because there is no X11 session here; on X11 the bounds are
  true screen coordinates and the round trip (find bounds, click them, land) is
  owed.
- **The Windows, WSL and macOS structured tiers**, which do not exist until
  `0.8.0` and `0.9.0`; there the `ui_*` tools are listed and return
  `at_spi_unavailable`, and this runbook exercises none of a tier that is not
  there.
- **The browser tier.** AT-SPI's view of a browser is worse than the DOM's, and
  the DOM path is unchanged here, so it is out of scope by design.
