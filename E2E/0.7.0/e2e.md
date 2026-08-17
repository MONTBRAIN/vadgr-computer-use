# 0.7.0 - a structured Tier 1 on Linux: e2e runbook

Until now the Linux desktop was Tier 2 only: `screenshot` plus mouse and
keyboard, driven from pixels. `0.7.0` adds a structured path: read the
accessibility tree, find an element by role and name, act on it by reference,
and wait for one to appear. Four structured tools (`ui_tree`, `ui_find`,
`ui_act`, `ui_wait`), the expansion's `ui_windows`, `apps` and `app_open`, a
`structured` block on `get_platform_info`, and nothing removed or changed in
Tier 2.

**This is a Linux-only tier this release.** Windows (UIA) is `0.8.0` and macOS
(AX) is `0.9.0`: separate future minors. On Windows, WSL and macOS the entire
footprint of `0.7.0` is that the platform backend has no structured tier, so the
tool surface is identical and the `ui_*` tools honestly report
`at_spi_unavailable`. Nothing on those platforms runs the AT-SPI tests, because
there is nothing there to run yet.

**The e2e drives only apps that ship by default on a stock GNOME desktop**, so
the runbook reproduces on a standard machine with nothing extra installed.
The exception is the enablement and grounding groups (8 to 11), whose whole
subject is the non-default toolkits: they drive whatever Chromium, Electron
and Flutter apps the box already has (here Chrome, VS Code and the App
Center), and a box without one marks that group `not run` naming the missing
app.
Nothing is pulled in for the occasion, not an editor and not a Qt app. The suite
is one group per app: **Calculator, Text Editor, Files, Settings, Clocks and
Characters**, plus a cross-cutting group and an unfocused-targeting group. A
pass proves the tier against what a real user already has, and Settings is in
the set deliberately: it is the most complex default app, and a tier that can
read it, act on it, confirm the change and revert it has proven the whole verb
loop on real glass.

A later revision adds the **workflow groups (12 to 16)**: multi-step tasks
over the same defaults, two of which also drive VS Code under the same
exception Group 8 established, because a chain of confirmed steps stresses
what a single action cannot. They are authored below and driven live on GNOME
Wayland, all five pass.

The claim this runbook has to prove is not "the tools return something". It is
three things a suite cannot reach:

1. **The tier reads and acts on real default apps** by role and by name, and
   `ui_act` observes the result by re-reading rather than trusting its own
   return. The sharpest forms: Calculator's buttons compute a sum that is read
   back off the display element, and a Settings switch turns on, is confirmed,
   and is turned back off, with the change also confirmed outside the session.
2. **The tier fails honestly.** A stale reference is `element_gone` and clicks
   nothing; an app name that matches no window is `no_tree`; an element whose
   toolkit exports no matching action is `unsupported_action` listing what it
   does export; an empty match is `ok` with an empty list; a missing bus is
   `at_spi_unavailable` with a remedy.
3. **It is small text and fast.** Small structured data instead of a full
   image, and an action that returns in milliseconds. Every cell below records
   its latency, read from the run journal.

## The approach: a Claude subagent over `claude -p`, one session per app

The driver is a real Claude agent over `claude -p`, given a **goal-level** task
per app ("compute 7 + 8 on the Calculator by clicking its buttons and report
the answer read from its display"), never a script of tool calls. The MCP
config is a one-server `.mcp.json` pointed at the branch's `vadgr-cua`;
`claude -p` loads a fresh server from the current code on every session, so no
run ever tests a stale connection. The journal is
`--output-format stream-json`, teed through a timestamper so every tool call
carries its own latency.

**The driver session is denied every non-MCP tool** (file edit, file write,
shell) with `--disallowedTools`. This is not decoration: an early Settings
session, blocked by a missing verb mapping, edited the product source mid-run
to get past it. The edit was reverted and redone properly with a failing test
first, and the denial went into the runner so a driver can only ever drive.

**Part F, the Tier 2 regression, is deliberately not agent-driven**: its claim
is that *every* Tier 2 tool still works, and an agent cannot enumerate them
without a script, at which point the runbook tests the runbook. Part F speaks
to the same server directly and ground-truths each side effect outside the
session, as the `0.6.6` sweep did.

## The oracle is the JSON, never the agent's prose

**`E2E/README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative tests must show the named
error, and with no journal the result is **not verified** rather than a pass.

Two rules this tier adds:

- **Confirm a `ui_act` with a structured read-back, never a screenshot.**
  `ui_act` re-reads the element and returns its new state, so the first
  confirmation is in the same `tool_result`; a follow-up `ui_find` is the
  independent one.
- **Where a change is visible outside the session, read it there too.** The
  Settings group's switch is backed by a gsetting, so the pass reads
  `gsettings get` before, between and after the two agent sessions, from a
  shell the agent never touches.

Every number, status and table row below comes from real captured tool output:
the timestamped run journals and the ground-truth files named in the evidence
section.

## Prerequisites (Linux only)

A real, attended, unlocked GNOME session with the accessibility stack present
(`at-spi2-core`, which is on a stock GNOME) and the bus running. The apps under
test all ship by default on GNOME:

- **Calculator** (`gnome-calculator`): the read plus act plus confirm loop.
- **Text Editor** (`gnome-text-editor`): `set_text` confirmed from `text`.
- **Files** (`nautilus`): the rich read, and a toolbar toggle with revert.
- **Settings** (`gnome-control-center`): the complex app; a benign switch
  turned on, confirmed, and reverted.
- **Clocks** (`gnome-clocks`): tab navigation confirmed from selection state.
- **Characters** (`gnome-characters`): a read-only breadth pass.

Each binary is confirmed present with `which` before its group runs; an app
genuinely absent is that group marked `not run` with the reason, never a
fabricated pass.

**Nothing the operator cares about in the foreground for the acting parts**:
they click and type into real windows. Say so before starting.

**Preconditions are stated, not inherited.** Before the pass: none of the six
apps is running, and the Text Editor's saved session is cleared
(`~/.local/share/org.gnome.TextEditor/`), because `app_open` otherwise restores
whatever document was open last time and `set_text` would overwrite a real
file's buffer. The first run of this pass hit exactly that: the editor restored
a repo file, the buffer was replaced in place, and only the kill-without-saving
plus an empty `git diff` kept it an incident instead of damage. The Settings
group additionally records `gsettings get org.gnome.desktop.interface
enable-hot-corners` before it starts.

There is **no Qt app installed by default** on this GNOME image and **no X11
session** on this box; both are recorded `not run` with that reason rather than
worked around by installing or reconfiguring.

## Setup

From a stated working directory, `<checkout>` the branch under test.

```bash
python3 -m venv /tmp/cua-070-build
/tmp/cua-070-build/bin/pip install build
/tmp/cua-070-build/bin/python -m build --wheel --outdir /tmp/cua-070-dist <checkout>
python3 -m venv /tmp/cua-070-installed
/tmp/cua-070-installed/bin/pip install /tmp/cua-070-dist/vadgr_computer_use-0.7.0-py3-none-any.whl
/tmp/cua-070-installed/bin/vadgr-cua doctor
cd /tmp
command -v /tmp/cua-070-installed/bin/vadgr-cua
```

The wheel install is the product under test. The driving agent's MCP config
must invoke `/tmp/cua-070-installed/bin/vadgr-cua` from outside the checkout.
Its `doctor` result proves the structured tier's `dbus-fast` dependency and
the delivered 33-tool surface load through the installed command.

Read every exit code directly. Do not pipe it into anything: `cmd | head`
reports `head`'s status.

## Automated gate (necessary, never sufficient)

```bash
python3 -m venv /tmp/cua-070-gates
/tmp/cua-070-gates/bin/pip install "<checkout>[dev]"
/tmp/cua-070-gates/bin/python -m pytest <checkout>/computer_use/tests -q
/tmp/cua-070-gates/bin/ruff check <checkout>/computer_use   # ruff==0.16.0, the CI pin
```

Expected: `pytest` all pass but one (the pre-existing, environment-sensitive
`test_wayland_no_mutter_no_evdev_raises`, which turns on this box's
`/dev/uinput` state and is unrelated to this release), `ruff` exit `0` under
the CI-pinned version. The suite also holds the **33-tool surface** (the 26 of
`0.6.6`, the four structured tools, and the expansion's `ui_windows`, `apps`
and `app_open`), the 26 existing entries unchanged.

Green here proves the code paths and proves **nothing** about a real desktop.
The groups below are the gate.

## Targeting note: the app name is the accessibility name

`ui_find(app=...)` matches case-insensitively against the name the app exports
on the accessibility bus, which is not always the launcher name: this pass
observed `gnome-calculator` (which "Calculator" matches as a substring),
`gnome-text-editor` (which "Text Editor" does **not** match: `no_tree`),
`org.gnome.Nautilus`, `gnome-control-center`, `org.gnome.clocks` and
`org.gnome.Characters`. The reliable pattern, and what the driven agents did
after one honest `no_tree`: take `window.app_name` from `app_open`'s result or
from `ui_windows`, and target with that.

## The suite: one group per app

Every acting group has the same skeleton, and a group is only a pass when all
four hold:

1. **Open**: `app_open` returns `ok` with a `window` ref, and `ui_windows`
   lists the window.
2. **Read**: `ui_find` by role and by name returns the expected elements with
   `ref`, `bounds` and decoded `states`; counts and samples are reported.
3. **Act**: `ui_act` on a found ref, asserted on the **re-read state or an
   independent read-back value**, never the return code alone. Anything
   toggled is toggled back.
4. **Latency**: every cell's latency is read from the journal.

### Group 0: cross-cutting capability and honest failures

- `get_platform_info` returns the `structured` block: `backend: "atspi"`,
  `bus_reachable`, `available`, `coordinate_trust` (`per_window` on Wayland,
  `real` on X11), and a non-empty `toolkits_seen`.
- `ui_act(ref="atspi:deadbeef", action="click")` is `element_gone` and clicks
  nothing.
- `ui_find(app="NoSuchAppZzz", role="button")` is `no_tree` naming the app.
- The dead-bus arm (`at_spi_unavailable` with its remedy from every `ui_*`
  tool, with the tools still listed) is held by the unit suite, not staged
  live.

### Group 1: Calculator (`gnome-calculator`)

- **Open**: `app_open("Calculator")`; `ui_windows` shows `gnome-calculator`.
- **Read**: `ui_find(app, role="button")` returns the keypad; `ui_find(app,
  name="7")` returns the digit; `ui_find(app, role="button",
  name="zzz-no-such-button")` is `ok` with an **empty list**, the
  empty-match-is-ok rule as its own cell.
- **Act**: click `7`, `+`, `8`, `=` by ref, then read the display
  (`role="text box"`) and take its `text` field as the only valid answer. The
  agent is told never to compute the arithmetic itself.
- **Pass**: the display's own `text` is `"15"`.

### Group 2: Text Editor (`gnome-text-editor`)

- **Precondition**: saved session cleared, so the window is an empty draft.
  The agent is told to check the title from `ui_windows` first and stop rather
  than write into anything that names an existing file.
- **Open**: `app_open("Text Editor")`; the returned window title must be a new
  draft.
- **Read**: find the document (`role="text box"`, via `ui_tree` if needed).
- **Act**: `ui_act(set_text, "the structured tier drove this editor over the
  wire")`.
- **Pass**: the `ui_act` response's `state.text` equals the sentence, and an
  independent `ui_find` re-read returns the same text. The file is never
  saved.

### Group 3: Files (`nautilus`)

- **Open**: `app_open("Files")`; `ui_windows` shows it with its title.
- **Read** (the rich one): toolbar buttons by role with names; toggle buttons
  by role with names; the sidebar `Documents` row by name; the folder listing
  as `grid cell` elements with names.
- **Act**: toggle `Search Current Folder` on, confirm `pressed` in the re-read
  and in an independent find, toggle it back, confirm again.
- **Documented boundary, not a failure**: nautilus's sidebar rows and grid
  cells export **no activation action** over AT-SPI (`supported: []`, and
  `["listitem.scroll-to"]` on a grid cell), so structural navigation by
  clicking a sidebar place is not reachable on this app; the attempt must fail
  honestly as `unsupported_action` listing exactly that.

### Group 4: Settings (`gnome-control-center`), the interact-and-confirm proof

Two agent sessions with an outside ground truth read between them. The chosen
control is deliberately benign: **Multitasking's Hot Corner switch**, backed by
`org.gnome.desktop.interface enable-hot-corners`, harmless in both states and
reverted before the group ends. Nothing else in Settings is touched: no
network, no users, no power.

- **Open**: `app_open("Settings")`; `ui_windows` shows `gnome-control-center`.
- **Read**: the `Multitasking` sidebar row by name; the panel confirmed open
  by `ui_wait(name="Hot Corner")`; the switch by `role="switch"` plus name.
- **Act (session one)**: `ui_act(toggle)` on the switch; the re-read state
  must show `checked` appeared; an independent `ui_find` confirms; the session
  leaves it on.
- **Ground truth**: `gsettings get org.gnome.desktop.interface
  enable-hot-corners` read from outside before session one and after each
  session; it must go `false`, `true`, `false`.
- **Act (session two)**: `ui_act(toggle)` again; `checked` gone in the re-read
  and the follow-up find.
- **Documented boundary**: the sidebar rows export no activation action here
  either; the panel is opened by `ui_act(focus)` on the row plus an Enter key,
  the one sanctioned keyboard use in the suite, and the panel being open is
  still confirmed structurally.

### Group 5: Clocks (`gnome-clocks`)

- **Open**: `app_open("Clocks")`; `ui_windows` shows `org.gnome.clocks`.
- **Read**: the tab strip (`role="tab"`): World, Alarms, Stopwatch, Timer.
- **Act**: click the `Alarms` tab; confirm from an independent
  `ui_find(role="tab")` that `selected` moved to Alarms, and that an
  Alarms-only control (`New Alarm`) is now findable. Then the same for
  `Stopwatch`, confirmed by `selected` and its `Start` button. Nothing is
  added, started or deleted.

### Group 6: Characters (`gnome-characters`), read-only

- **Open**: `app_open("Characters")`; `ui_windows` shows it.
- **Read**: `ui_tree(depth=6)` reaches real leaves; `ui_find(role="list
  item")` returns the category list. No `ui_act` at all: this group widens
  read coverage.

### Group 7: the unfocused app, targeted by name

The expansion's motivating case, kept as its own group: with another app
holding focus, the Calculator is driven **without ever being focused or
raised**.

- `ui_windows` must show `gnome-calculator` with `active: false` and some
  other window active, quoted as the precondition.
- `ui_find(app="Calculator", ...)` finds `C`, `9`, `+`, `=`; clicks compute
  `9 + 9`; the display's `text` field is the answer.
- **Pass**: the display reads `"18"` while the Calculator stayed inactive.

## When a group surfaces a bug: fix it, then re-run it

**A defect found during a pass is fixed during that pass**, with a test that
fails without it, and **the group is re-run from a clean state** before being
marked. The first pass of this runbook did exactly that seven times (F1 to
F7); this per-app pass did it twice more (F8, F9) and kept each failing
attempt's journal in the evidence bundle next to the re-run.

## The enablement and grounding groups (added with the finish pass)

The first passes drove GTK4 defaults. Real desktops also run the toolkits that
do not expose a tree unless asked: Chromium and Electron gate it at launch,
and Flutter builds it only for assistive tools. This pass adds those, plus the
grounding rung.

### Group 8: Chromium and Electron launch enablement

- **Baseline**: a Chromium-family app launched without the flag exposes only
  bare frames. Read one with `ui_tree(app=...)` and record the node count.
- **Open**: `app_open` a Chromium or Electron entry (VS Code here). The result
  must report `method: "exec"`: the launchers run the `Exec` line as written
  and cannot carry the flag, so the entry dispatches the expanded `Exec` with
  `--force-renderer-accessibility` appended.
- **Read**: `ui_find(app, role="menu item")` returns the real menu bar;
  `ui_tree` reaches the deep tree. The process's own cmdline carries the flag,
  read from /proc outside the session.

### Group 9: no screen-reader flag, and honest tree-only degradation

There is no pulse. The tier never raises `org.a11y.Status.ScreenReaderEnabled`,
because on GNOME that property is bridged to the
`org.gnome.desktop.a11y.applications screen-reader-enabled` gsetting, which
autostarts a screen reader that then speaks.

- **Trigger**: `ui_find` against an app whose walk meets no meaningful node (an
  unflagged already-running Chromium is the live thin case). An outside witness
  samples `org.a11y.Status.ScreenReaderEnabled` across the whole read.
- **Pass**: the witness sees the flag stay `false` the whole time; the tier
  never sets it. No screen reader (Orca) starts at any point: no Orca process
  appears, and the `screen-reader-enabled` gsetting stays `false`. The thin
  window reads tree-only, returning the frames it has with no forced content.
- **Remedy**: a thin already-running Chromium or Electron window is relaunched
  through `app_open` (Group 8), which appends `--force-renderer-accessibility`
  and then exposes the full tree; Chrome itself is driven through the browser
  tier. These are the honest path in place of a forced enable.

### Group 10: post-navigation reads on Flutter

- Click a navigation element in the App Center, then call `ui_find`
  immediately, with no pause. The read must return the settled new page: the
  new page's headers present, the old page's gone. Repeat across three pages.

### Group 11: the grounded pixel click (Tier 1.5)

- `ui_find` an element in an XWayland window on the Wayland session; it must
  carry `coordinate_trust: "real"`. A Tier 2 `click` at the bounds center must
  land: confirm structurally (the effect appears in an immediate `ui_find`),
  then revert (Escape) and confirm the revert structurally.
- A Wayland-native window's elements carry `coordinate_trust: "none"` and are
  not aimed at; their paths are native actions and `focus` plus a key.

## Workflow groups: multi-step tasks that stress the tier (12 to 16, authored, not yet run)

The groups above prove each verb once per app: open, one action, one
read-back. That is the right first gate and the wrong last one, because real
agent work is a chain, and a chain fails in ways a single action cannot show:
a reference that goes stale after the app redraws, a dialog that swallows
focus mid-task, a read that races the app's own settle, two tools disagreeing
about one artifact. The groups below give the tier real work: several
mutations per group, each confirmed structurally before the next step starts,
and two groups spanning two applications that must agree on one file.

**These groups were driven live on GNOME Wayland on 2026-08-14, all five pass**,
with their journals in the workflow-suite evidence bundle. Their cells below and
in the per-desktop matrix carry that result. Each result is a reading of a
journal, never a substitute for one.

The standing rules, stated once for all five:

- **The structured tier discovers and drives**: `ui_find` and `ui_tree`
  locate, `ui_act` acts, and every mutation is confirmed by the act's own
  re-read plus an independent `ui_find`, **between steps, never only at the
  end**. A step's confirmation must appear in the journal before the next
  step's first call. A screenshot may independently confirm an action
  happened; it never locates, decides or drives.
- **The keyboard is used only where the app exports no matching action** (the
  sanction Group 4 established for Enter), and the effect of every key is
  still confirmed structurally.
- **Tier 0 (`shell`, `fs`) appears only for setup and for cross-tier
  verification**, never to drive the app under test.
- **Real, but safe**: everything created lives under a `mktemp -d` path and
  is deleted at the end, every buffer that must not persist is discarded,
  nothing is pushed anywhere. Each group names its cleanup.
- **An unexported action stays a first-class honest result**: it is recorded
  as `unsupported_action` with the element's real action list, never worked
  around by dropping to pixels.
- **The oracle is the `tool_use` / `tool_result` JSON in the journal**, never
  the agent's prose, exactly as everywhere else in this runbook.

### Group 12: Files (`nautilus`), a folder lifecycle

Group 3 read the listing and flipped one toolbar toggle. This group does file
management the way a user does: create a folder, rename it, watch a file land
inside it, delete it, and read the listing between every step, so a stale
listing snapshot or a dialog that never closed is caught at the step that
caused it.

- **Setup (Tier 0)**: `STAGE=$(mktemp -d)`; the group touches nothing outside
  it.
- **Open**: `app_open("Files")`; target with the returned `window.app_name`.
  Navigate to `$STAGE`: nautilus exports no activation on its rows (Group 3's
  boundary), so the sanctioned path is Ctrl+L, then `ui_find` the location
  entry (`role="text box"`), `ui_act(set_text, "$STAGE")` confirmed from
  `state.text`, then Enter. **Confirm**: `ui_windows` shows the window titled
  with the stage directory's basename, and the listing has no grid cells
  (`ok` with an empty list).
- **Create**: Ctrl+Shift+N (no exported new-folder action); `ui_wait` for the
  dialog's name entry; `ui_act(set_text, "wf-folder")` confirmed from
  `state.text`; `ui_find` the dialog's `Create` button and click it by ref.
  **Confirm**: an independent `ui_find(name="wf-folder")` returns exactly one
  grid cell, and the dialog's entry is gone (`ok` with an empty list).
- **Rename**: `ui_act(focus)` on the `wf-folder` cell (the cells export focus
  even where they export no activation; if focus is also unexported, the
  journal records `unsupported_action` with the real list and the group stops
  honestly there), then F2; `ui_wait` for the rename entry, whose `text` must
  read `wf-folder`; `ui_act(set_text, "wf-renamed")` confirmed from
  `state.text`; Enter. **Confirm**: `ui_find(name="wf-renamed")` returns the
  cell and `ui_find(name="wf-folder")` is `ok` with an empty list.
- **A file lands**: Tier 0 writes `$STAGE/wf-renamed/inside.txt` (setup, not
  driving); back in Files, `ui_act(focus)` on `wf-renamed` plus Enter opens
  the folder (the same sanction), and the structured read
  `ui_find(name="inside.txt")` must return the file's cell: **the app under
  test witnesses the artifact**, which is the cross-tier point of the step.
- **Delete**: Alt+Up back to `$STAGE` (confirmed from the window title in
  `ui_windows`), focus `wf-renamed`, Shift+Delete; if a confirmation dialog
  appears, its `Delete` button is found and clicked by ref. **Confirm**:
  `ui_find(name="wf-renamed")` is `ok` with an empty list.
- **Cleanup**: Ctrl+W closes the window, confirmed gone from `ui_windows`;
  Tier 0 `rm -rf "$STAGE"`.
- **Pass**: every confirmation above present in the journal in order; any
  unexported step recorded as its named error, never skipped over.

### Group 13: Text Editor (`gnome-text-editor`), an edit cycle read back at every step

Group 2 wrote one sentence once. This group runs an editing session: write,
transform, undo, clear, with the buffer read back before every next mutation,
so the tier proves it can carry a document through several states rather than
land one.

- **Precondition**: as Group 2, the saved session is cleared and the window
  must be a new draft; the agent stops rather than write into a window that
  names an existing file.
- **Open**: `app_open("Text Editor")`; find the document (`role="text box"`,
  via `ui_tree` if needed).
- **M1, write**: `ui_act(set_text, P1)` where P1 is a three-sentence
  paragraph containing the token `wf-editor-p1`. **Confirm**: `state.text`
  equals P1, and an independent `ui_find` re-read equals P1.
- **M2, transform**: the agent builds P2 **from the read-back, not from
  memory**: it takes the re-read text, replaces `wf-editor-p1` with
  `wf-editor-p2`, and writes it with `ui_act(set_text, P2)`. **Confirm**: the
  re-read equals P2 and no longer contains `wf-editor-p1`.
- **M3, undo**: Ctrl+Z (the editor exports no undo action; the sanctioned
  keyboard). **Confirm from the re-read, with two honest outcomes**: if the
  text equals P1, the undo stack integrated the structured write; if it still
  equals P2, the toolkit does not journal AT-SPI text replacement onto its
  undo stack, and that is recorded as a documented boundary with the
  read-back quoted, never a silent pass and never a failure invented over it.
- **M4, clear**: `ui_act(set_text, "")`. **Confirm**: the re-read `text` is
  empty.
- **Cleanup**: the buffer is never saved. Ctrl+W closes; if the discard
  dialog appears, its `Discard` button is found and clicked by ref; the
  window is confirmed gone from `ui_windows`.
- **Pass**: M1, M2 and M4 confirmed from `state.text` plus the independent
  re-read; M3 resolved to one of its two named outcomes with the journal
  quote.

### Group 14: Calculator (`gnome-calculator`), a calculation that carries state

Group 1 proved one sum. This group chains three operations where each step
continues on the previous result, so one stale display read poisons every
step after it, which is exactly the property worth stressing.

- **Open**: `app_open("Calculator")`; target with the returned `app_name`.
  The operator buttons (multiply, subtract, divide, equals) are discovered
  with `ui_find(role="button")` and matched by the names the app itself
  exports, never guessed from the labels printed here.
- **Step 1**: click `1`, `2`, multiply, `1`, `2`, equals, each by ref.
  **Confirm**: the display (`role="text box"`) reads `144` from its `text`
  field, in the act's re-read and in an independent `ui_find`.
- **Step 2**: continue on the result, never retyping it: click subtract, `4`,
  `4`, equals. **Confirm**: the display's `text` is `100`.
- **Step 3**: click divide, `4`, equals. **Confirm**: the display's `text` is
  `25`.
- The agent is told, as in Group 1, never to compute arithmetic itself: the
  display element's `text` is the only valid value at every step, and each
  step's confirmation must appear in the journal before the next step's first
  click.
- **Cleanup**: click the clear button; **confirm** the display reads `0`;
  Ctrl+W closes the window, confirmed gone from `ui_windows`.
- **Pass**: the three display reads are `144`, `100`, `25`, in order, each
  from the journal.

### Group 15 (two apps): Text Editor writes, VS Code reads the same file

Two structured-tier apps must agree on one artifact: the editor writes and
saves a file, VS Code opens the same path, and the structured read of VS
Code's buffer must show the same content. The group crosses toolkits (GTK4 to
Electron), exercises Group 8's Chromium enablement inside a real task, and
keeps the file system as the meeting point rather than the oracle: the final
confirmation is structural, in the second app.

- **Setup (Tier 0)**: `STAGE=$(mktemp -d)`; `touch "$STAGE/handoff.txt"`;
  launch `gnome-text-editor "$STAGE/handoff.txt"` from the shell (setup: the
  editor must open this exact file, which `app_open` cannot express).
  **Confirm**: `ui_windows` shows the editor window titled `handoff.txt`.
  Group 2's stop rule does not fire here: the file is the group's own
  artifact under `$STAGE`, created two lines up.
- **Write**: find the document, `ui_act(set_text, S)` where S is a two-line
  body containing the token `wf-handoff-070`. **Confirm**: `state.text`
  equals S and an independent re-read agrees.
- **Save**: Ctrl+S (the editor exports no save action). **Confirm across the
  tiers**: Tier 0 `fs` reads `$STAGE/handoff.txt` back equal to S
  (verification, not driving), and the title re-read from `ui_windows` no
  longer carries the modified marker, recorded as observed.
- **Open in VS Code**: `app_open` the VS Code entry, which must report
  `method: "exec"` with the accessibility flag carried (Group 8's mechanism,
  now inside a workflow); confirm its window in `ui_windows`. Then Tier 0
  `code "$STAGE/handoff.txt"` hands the path to the flagged instance (setup:
  the file must reach this exact window).
- **The second app agrees**: `ui_wait` for an element named `handoff.txt` in
  the VS Code window (the tab), then `ui_find` the editor document and read
  its text. **Pass**: the structured read from inside VS Code contains
  `wf-handoff-070`. If the document element exports no readable text over the
  bus, the honest result is that named gap quoted from the journal, never a
  screenshot standing in for the read.
- **Cleanup**: close the VS Code window and the editor window (Ctrl+W each,
  confirmed gone from `ui_windows`); Tier 0 `rm -rf "$STAGE"`.

### Group 16 (two apps): a dev scaffold, shell to VS Code and back to disk

The closing stress, shaped like real agent work: Tier 0 scaffolds a project,
the structured tier does the editing inside VS Code, and the result is
confirmed twice, structurally in the editor and independently on disk. It
stacks the hard parts on purpose: Chromium enablement, a deep Electron tree,
a workspace-trust dialog, keyboard input into an editor that exports no
text-setting action, and cross-tier verification.

- **Setup (Tier 0)**: `PROJ=$(mktemp -d)`; `git init "$PROJ"`; write
  `$PROJ/main.py` containing the single line `print("wf-scaffold-070")`;
  commit it with an inline throwaway identity
  (`git -C "$PROJ" add -A`, then `git -C "$PROJ" -c user.name=wf -c
  user.email=wf@example.invalid commit -m scaffold`), so the later status
  check can tell an edit from an untracked file. The repository never gets a
  remote and nothing is pushed at any point.
- **Open**: `app_open` VS Code (`method: "exec"`, flag carried), confirmed in
  `ui_windows`; Tier 0 `code "$PROJ"` hands the folder to the flagged
  instance. If the workspace-trust dialog appears, its trust button is found
  with `ui_find` and clicked with `ui_act`, and the dialog confirmed gone
  from a follow-up find: the dialog is part of the test, not an obstacle.
- **Open the file structurally**: Ctrl+P (quick open); `ui_wait` for the
  picker's entry; prefer `ui_act(set_text, "main.py")` on it. If Chromium
  exports no settable text there, the `unsupported_action` is recorded with
  the element's real actions, and the sanctioned fallback is keyboard typing
  into the focused entry, still confirmed structurally: the picker row for
  `main.py` must appear in a `ui_find` before Enter is pressed. **Confirm**:
  an element named `main.py` appears as the active editor tab.
- **Edit**: `ui_act(focus)` on the editor document; Ctrl+End to the end, then
  type a second line `print("wf-scaffold-edited")` (Monaco exports no
  text-setting action; the keyboard here is the sanctioned path). **Confirm
  structurally before saving**: a re-read of the editor document's accessible
  text contains `wf-scaffold-edited`; if that text is not readable over the
  bus, the gap is recorded honestly and the on-disk check below is stated as
  the group's only confirmation of the edit.
- **Save**: Ctrl+S. **Confirm on both sides**: Tier 0 `fs` reads
  `$PROJ/main.py` and it contains both lines in order, and
  `git -C "$PROJ" status --porcelain` shows `main.py` as the only change: the
  scaffold, the editor and the disk tell the same story.
- **Cleanup**: close the VS Code window, confirmed gone from `ui_windows`;
  Tier 0 `rm -rf "$PROJ"`.
- **Pass**: the edit witnessed twice (the structured read and the Tier 0 file
  read), the status check clean of surprises, and every dialog crossed on the
  way crossed structurally.

### Group 17: Qt toolkit read and act (SpeedCrunch)

The other groups drive GTK, Chromium, Electron and Flutter. This one proves the
Qt toolkit, so a Qt app is read and driven over AT-SPI the same way. SpeedCrunch
(Qt5) is installed for this group with `apt-get install speedcrunch`.

- **Enablement (the finding this group exists for)**: Qt gates its AT-SPI tree on
  `org.a11y.Status.IsEnabled`. With the flag false a Qt app registers nothing on
  the bus. `IsEnabled` is the tier's safe flag and does not start a screen reader
  (Orca stays absent, confirmed). Qt reads the flag at launch, so the app must
  start with it already true.
- **Open**: `app_open("SpeedCrunch")` returns `method: "exec"` and a confirmed
  window (`SpeedCrunch`). A shell-launched detached instance did not map a
  window; the session launcher did.
- **Read**: `ui_tree` returns a real Qt tree: a menu bar with `Session`, `Edit`,
  `View`, `Settings`, `Help` by name, a read-only result area, and an editable
  expression input, each with roles and states.
- **Act**: `ui_act(set_text, "6*7")` on the input, confirmed `state.text ==
  "6*7"`; then Enter (the sanctioned keyboard step, SpeedCrunch evaluates on
  Enter).
- **Confirm**: an independent `ui_find(role="text")` re-read shows the result
  area text `6*7\n= 42`, and the input cleared.
- **Pass**: a Qt app read by role and name, driven, and its computed result read
  back over AT-SPI.

## Finish-pass results, GNOME Shell 50 / Wayland, driven 2026-08-13

Run id `20260813-034845-finish-070`, one timestamped `stream-json` journal per
group plus the probe transcripts. Every cell is read from those files.

| group | result | evidence |
|---|---|---|
| regression: LibreOffice read and write | **pass**: two Writer drafts read by role, `set_text` landed in the targeted draft only, both texts read back verbatim, each element naming its window | `v1-libreoffice.jsonl`, `v1b-lo-write.jsonl` |
| regression: App Center read, click, set_text | **pass**: 72 elements, search field `set_text` read back `"firefox"`, sidebar click landed, post-click read settled | `v2-appcenter.jsonl` |
| regression: app_open single-instance snap | **pass**: `libreoffice_writer.desktop` confirmed by the new window `Untitled 3 - LibreOffice Writer` in 5.7 s | `v3b-appopen-snap.jsonl` |
| 8: Chromium launch enablement | **pass**: VS Code via `method: "exec"`, cmdline carries the flag, 7 menu items with real bounds, about 111 KB tree at depth 5; the unflagged Chrome exposes 2 nodes per frame | `w1-vscode-launch.jsonl`, `probe-pulse-chrome.txt` |
| 9: no screen-reader flag | **pass**: the tier never sets `ScreenReaderEnabled`. A witness took 107 samples with the flag false and no Orca, while a thin Chrome read stayed tree-only. | closed |
| 10: post-navigation reads | **pass**: three page changes, each immediate header read settled (117 ms, 462 ms, 151 ms), old headers gone | `w4-flutter-nav.jsonl` |
| 11: grounded click | **pass**: File menu item `coordinate_trust: "real"`, pixel click at (120, 49) opened the menu (`New Text File` found structurally), Escape closed it (empty list confirmed) | `w3b-grounding.jsonl` |

### The Wayland-native grounding boundary, probed

A Wayland-native window's elements cannot ground a pixel click, and this pass
proved that as a probed verdict rather than an impression. Every plausible
path was tried on the real target:

- `org.gnome.Shell.Introspect.GetWindows` (window origins) and
  `org.gnome.Shell.Screenshot.ScreenshotWindow` (a window image to locate in
  the full screenshot): both **Access denied**; GNOME allowlists their
  callers. `gnome-screenshot -w` is not on the allowlist either and falls to
  a broken X11 path (transcripts in the evidence bundle).
- Mutter `ScreenCast.RecordWindow` (window-relative input injection): callable
  from this session, but with no `window-id` it returns a stage-sized stream,
  and the only source of window ids is the denied Introspect API
  (`probe-mutter-recordwindow.txt`, `probe-recordwindow-groundclick.txt`).
- The gnome-shell accessibility stage exposes only the shell's own chrome,
  no client window geometry (`probe-shell-a11y-geometry.txt`).
- GTK4 reports screen extents of (0, 0) and real extents only in window
  coordinates (`probe-gtk4-coordtypes.txt`), so even its own bounds carry no
  origin.

The quantified need is small: across five real apps, 94.3 percent of 264
interactive elements expose a native action, and the remainder are mostly
focusable (`probe-actionability-census2.txt`). The forward path, if demand
ever asks for it, is the portal window-cast with a persisted restore token,
which trades a one-time user grant for per-window streams; it is a project,
not a patch.

### The screen-reader pulse was removed

The pulse set `org.a11y.Status.ScreenReaderEnabled` to force a thin toolkit to
build its tree. On GNOME that property is bridged to the
`org.gnome.desktop.a11y.applications screen-reader-enabled` gsetting, which
autostarts a screen reader within about 130 ms (probed live on GNOME 50.1); the
screen reader then speaks on the user's desktop. The pulse's original
beneficiary, thin Flutter, no longer needs it: modern Flutter exposes its tree
with every accessibility flag false. So the pulse was removed. A thin
already-running Chromium or Electron window now reads tree-only, and the remedy
is `app_open` (which appends `--force-renderer-accessibility`) or the browser
tier.

## Per-app results, GNOME Shell 50 / Wayland, driven 2026-08-12

Run id `20260812-041617-per-app-suite`, one timestamped `stream-json` journal
per group. Every cell below is read from those journals; the latency column is
the journal gap between the tool call and its result, and cells the model
issued in parallel (where the gap is not attributable) are excluded from the
numbers rather than guessed.

| group | open | read | act, confirmed on re-read | verdict |
|---|---|---|---|---|
| 0 crosscut | n/a | `structured` block: `atspi`, bus reachable, `coordinate_trust: none`, toolkits `clutter, gtk, Chromium, GTK` (194 ms) | `element_gone` on `atspi:deadbeef` in 13 ms, clicked nothing; `no_tree` for `NoSuchAppZzz` in 47 ms | **pass** |
| 1 Calculator | `ok`, gio, window ref returned (919 ms); `ui_windows` lists it, active | 30 buttons by role (226 ms); `7` by name (35 ms); bogus name is `ok` + empty list (32 ms) | clicks `7 + 8 =` at 19 to 25 ms each (one 729 ms outlier); display `text` reads `"15"` (44 ms) | **pass** |
| 2 Text Editor | `ok`, gtk-launch, title `New Document (Draft)` (1630 ms) | document found via `ui_tree(depth=8)` (52 ms); `app="Text Editor"` honestly `no_tree`, re-targeted `gnome-text-editor` | `set_text` returns `state.text` equal to the sentence (27 ms); independent re-read equal (27 ms) | **pass** |
| 3 Files | `ok`, gtk-launch, title `Home` (261 ms) | 10 buttons named (Back, Forward, ...); 5 toggle buttons named; `Documents` row found; Home listing 11 grid cells, all named (38 ms) | `Search Current Folder` toggle: `pressed` in the act's own re-read (304 ms), independent find agrees; revert clean (290 ms). Sidebar row activation `unsupported_action` with `supported: []`, the app's own export | **pass** (navigation cell: honest `unsupported_action`) |
| 4 Settings | `ok`, gtk-launch (1125 ms); `ui_windows` lists it | `Multitasking` row (416 ms); panel confirmed by `ui_wait` on `Hot Corner` (530 ms); switch by role+name (655 ms) | toggle on: `checked` in the act's re-read (278 ms) + independent find (368 ms); **gsettings outside the session: false, true, false**; revert confirmed | **pass** |
| 5 Clocks | `ok`, gtk-launch (750 ms) | tabs World, Alarms, Stopwatch, Timer by role | Alarms click (56 ms): `selected` moved to Alarms in the follow-up find, `New Alarm` findable; Stopwatch click (15 ms): `selected` moved, `Start` found and not clicked | **pass** |
| 6 Characters | `ok`, gtk-launch (1569 ms) | `ui_tree(depth=6)` about 6.5 KB reaching leaf labels and buttons (454 ms); 17 list items, categories named (98 ms) | none by design | **pass** (read-only) |
| 7 unfocused | already open; `ui_windows`: `gnome-calculator` `active: false`, `org.gnome.Characters` active (220 ms) | `C`, `9`, `+`, `=` by name under `app="Calculator"`; `role="push button"` honestly empty (GTK4 exports `button`) | `C 9 + 9 =` clicked at 17 to 86 ms each; display `text` reads `"18"`, window never focused | **pass** |

Latency summary across the journals: `ui_act(click)` 15 to 86 ms typical,
`ui_act(toggle)` 278 to 304 ms including its settle to the new state,
`ui_find` mostly 24 to 226 ms with occasional first-touch spikes (an app's
first read warms its cache), `app_open` 261 ms to 1.6 s to a confirmed window.
Small text throughout: the biggest read in the pass, the Characters tree, is
about 6.5 KB.

## Coverage

| surface | group |
|---|---|
| `get_platform_info` reports the `structured` block on a live bus | 0 |
| `at_spi_unavailable` with a remedy when the bus is down | 0 (unit) |
| read by role and by name on six default apps | 1 to 6 |
| empty match is `ok` with an empty list | 1, 7 |
| act confirmed from the act's own re-read | 3, 4 |
| act confirmed from an independent follow-up find | 1, 3, 4, 5, 7 |
| act confirmed from outside the session entirely | 4 (gsettings) |
| revert after a mutating act | 3, 4 |
| `element_gone` on a bogus ref, clicking nothing | 0 |
| `no_tree` for an app with no window | 0, 2, 4 |
| `unsupported_action` listing the element's real actions | 3, 4 |
| `set_text` confirmed from `state.text` | 2 |
| `ui_wait` for a panel to appear | 4 |
| target a non-focused app by name | 7 (and 3, 4 incidentally) |
| `app_open` confirming a real window before `ok` | 1 to 6 |
| `app_open` confirming a single-instance snap by window newness | finish pass |
| Chromium and Electron launched with the tree enabled | 8 |
| the tier never raises `ScreenReaderEnabled`; a thin read stays tree-only | 9 |
| reads immediately after a Flutter navigation return the settled tree | 10 |
| per-window `coordinate_trust`, and a grounded Tier 2 click on `real` | 11 |
| on Wayland, untrusted bounds are not aimed at | 0, 11 |
| a multi-step chain confirmed structurally between steps, never only at the end | 12 to 16: **pass** |
| a folder lifecycle in Files: create, rename, witness a file, delete | 12: **pass** |
| an edit cycle in the editor: write, transform, undo, clear, each read back | 13: **pass** (undo boundary recorded) |
| a calculation that carries state across chained operations | 14: **pass** (144, 100, 25) |
| two apps agreeing on one file, GTK4 to Electron | 15: **pass** (`wf-handoff-070` read inside VS Code) |
| a scaffold edited structurally and verified on disk and in git | 16: **pass** (structural, disk, `git status`) |
| dialogs crossed structurally mid-task (create, rename, discard, delete, trust) | 12, 13, 16: **pass** (trust is a Restricted Mode banner, named gap) |
| every Tier 2 desktop tool still works, unchanged | **pass** (Part F): screenshot, clipboard round trip, type, click, scroll, drag and double-click all driven live; nothing saved |
| Qt read and act | 17: **pass** (SpeedCrunch): tree read by role and name, `6*7` set and evaluated, result `= 42` read back |
| X11 grounding round trip | **to be run in 0.1x.x**: needs a real X11 login session, driven on GNOME X11 in a perfectionism minor |
| the browser tier | **uncovered**: AT-SPI does not touch it, the DOM path is unchanged |

## Per-OS results

Legend: `pass` / `fail` mean it ran. `not run` means nobody ran it yet on a
target this release did drive (GNOME Wayland), honest and visibly owed before
the release closes. `to be run in 0.1x.x` means the target is scheduled for a
future perfectionism minor in the 0.1x.x range, not this release: the other
Linux desktops are driven there, not here. `Not-Needed` means there is genuinely
no OS-specific surface, with its reason. A cell is marked from observation,
never expectation.

### Linux, by desktop and display server

The structured tier is Linux's, and its behaviour differs by desktop and
display server, so the Linux column is its own table. GNOME Wayland was driven
by a real agent; the other desktops are scheduled for a 0.1x.x perfectionism
minor, and closing one is running `vadgr-cua install-deps` plus this runbook
there, not writing code.

| group | GNOME Wayland | GNOME X11 | KDE (Qt) | wlroots | notes |
|---|---|---|---|---|---|
| 0: capability and honest failure | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | structured block, `element_gone`, `no_tree` all observed |
| 1: Calculator | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | `15` read off the display element |
| 2: Text Editor | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | `set_text` confirmed from `state.text` |
| 3: Files | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | rich read; toggle acted and reverted; sidebar activation honestly unsupported |
| 4: Settings | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | switch on, confirmed, reverted; gsettings false/true/false |
| 5: Clocks | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | tab selection moved and confirmed |
| 6: Characters | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | read-only breadth |
| 7: unfocused by name | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | `18` computed on an inactive window |
| 8: Chromium launch enablement | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | VS Code full tree under the injected flag |
| 9: no screen-reader flag | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | witness 107/107 samples: ScreenReaderEnabled false, no Orca; thin Chrome stayed tree-only |
| 10: Flutter post-navigation reads | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | three immediate reads, all settled |
| 11: grounded click (Tier 1.5) | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | XWayland window: `real` trust, click landed, confirmed structurally |
| grounding on Wayland-native windows | Not-Needed | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | probed fundamental: every origin source denied or absent (see the boundary section); native actions and focus cover the need; the X11 round trip is owed on X11 |
| 12: Files folder lifecycle | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | create, rename, witness a file inside, delete: every step confirmed structurally |
| 13: Text Editor edit cycle | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | four buffer states read back; set_text is not on the undo stack, recorded honestly |
| 14: Calculator carried state | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | 144, 100, 25 carried across chained operations, each read back |
| 15: editor to VS Code handoff | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | `wf-handoff-070` read structurally from inside VS Code, matched on disk |
| 16: dev scaffold in VS Code | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | edit confirmed structurally, on disk, and in `git status`; trust banner is a named gap |
| F: Tier 2 regression | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | pixel tools all work, ground-truthed via the clipboard; nothing saved |
| 17: Qt toolkit read and act | **pass** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | SpeedCrunch: tree read by role and name; `6*7` set, evaluated, result `= 42` read back |
| overall | **pass (structured)** | to be run in 0.1x.x | to be run in 0.1x.x | to be run in 0.1x.x | 19 groups driven end to end on real glass, the workflow groups 12 to 16 and the Qt group 17 included |

Qt is now covered on GNOME Wayland by Group 17 (SpeedCrunch, installed with
`apt-get install speedcrunch`). Qt gates its AT-SPI tree on
`org.a11y.Status.IsEnabled`: with the flag false a Qt app registers nothing, and
with it true (the tier's safe flag, which does not start a screen reader) the
app registers and reads and drives exactly like GTK. Qt reads the flag at launch,
so the app must start with it already true; `app_open` launches it in the session
and confirms the window. The KDE (Qt) desktop column stays `to be run in 0.1x.x`:
that is the desktop, a separate target from the Qt toolkit proven here on GNOME.

### Windows, WSL and macOS: no structured tier this release

These platforms are first class in this project, but the structured tier is
not theirs yet, so their `0.7.0` obligation is narrow and none of it is the
AT-SPI e2e.

| surface | Windows | WSL | macOS | notes |
|---|---|---|---|---|
| the structured (`ui_*`) tier | not in this release | not in this release | not in this release | Windows UIA lands in `0.8.0`, macOS AX in `0.9.0`; the platform backend has no structured tier, so `ui_*` honestly return `at_spi_unavailable` |
| the 33-tool surface still loads | Not-Needed live | Not-Needed live | Not-Needed live | unit-covered; the seven new tools are added to the catalogue on every OS, and cannot be live-driven from this Linux host |
| the unit suite runs there | pass (CI) | Not-Needed | pass (CI) | a CI row is a suite result, never a session; this pass also fixed the suite so it collects on a machine without `dbus-fast` (F11) |
| Tier 2 unchanged | Not-Needed live | Not-Needed live | Not-Needed live | `0.7.0` touches no Tier 2 tool; unit-covered, and there is no session on those OSes from here to drive it |

`not in this release` is deliberate and is not `not run`: there is no run
owed, because the tier does not exist on those platforms until `0.8.0` and
`0.9.0`. It is not `pass` either: nothing structured was exercised there.

## Findings

Nine runtime defects were found by agent-driven passes and were invisible to
the green unit suite, which is the reason this gate exists. Each is fixed, and
each fix has a test that was watched to fail without it. F1 to F7 are the
first pass's; F8 and F9 are this per-app pass's. F10 and F11 are automated-gate
defects this pass caught by actually running the gate.

### F1 (fixed): ui_act returned the element's state from before the action

`ui_act(toggle)` returned a `state` still lacking `pressed` while an
independent read a moment later showed it set: the toolkit updates state
asynchronously, and the re-read read the stale value back. The re-read now
settles until an observable field changes from the pre-action snapshot.
**Proof:** a unit test drives a fake client whose change is delayed and which
the old single read fails.

### F2 (fixed): set_text was not confirmable

`ui_act(set_text)` returned `ok` but no result carried the element's text.
Elements now carry a `text` field, read from `org.a11y.atspi.Text` for
text-bearing roles only. **Proof:** the Text Editor `set_text` returns
`state.text` equal to what was written; a unit test asserts it.

### F3 (fixed): ui_tree stopped at the wrapper containers

GTK4 stacks about sixteen anonymous wrappers between a window and its buttons
and the traversal spent its depth on them. Depth now counts meaningful nodes
only. **Proof:** `ui_tree(depth 6)` reaches the controls on every app driven;
a unit test asserts a control sixteen wrappers deep appears.

### F4 (fixed): some elements returned garbage bounds

An unrealised widget returned uninitialised memory as its extents
(`w=612489008`) with a correct signature. Implausible extents are now dropped.
**Proof:** zero absurd bounds in the driven trees; a unit test asserts garbage
extents yield no bounds. `x=0, y=0` on Wayland is correct and untouched.

### F5 (fixed): an off-screen dialog's controls surfaced as if on screen

`ui_find` and `ui_tree` now prune non-showing subtrees. **Proof:** a unit test
builds a non-showing dialog whose button falsely reports `showing` and asserts
it is not found while a genuinely visible control still is.

### F6 (fixed): a plain click stalled for seconds

The settle-poll was applied to every verb, so a plain click waited the full
window for the clicked button's own state to change, which it never does. The
settle now runs only for the verbs whose signal is the element's own field; a
plain click re-reads once. **Proof:** a digit click dropped from about 2 s to
milliseconds; a unit test asserts a plain click does not loop.

### F7 (fixed): ui_tree was not small text

After F3 the tree still emitted every anonymous wrapper, so the Files tree
came back about 243 KB. Wrappers are collapsed out and their meaningful
descendants hoisted. **Proof:** the same tree dropped to about 13 KB with the
same leaves; a unit test asserts no wrapper role appears.

### F8 (fixed, this pass): ui_act read through a stale cache snapshot

The expansion moved reads onto the warm `Cache.GetItems` snapshot, and `act`'s
settle poll read element states from it, so the poll could never observe the
change and returned the pre-action state as the confirmation: on Files,
`ui_act(toggle)` returned no `pressed` while an independent `ui_find` 24 ms
later (which re-warms the cache) showed it. The first diagnosis, a
too-short settle window, was wrong and was reverted when the live numbers
contradicted it. Acting now invalidates that app's snapshot first, so the
pre-action snapshot, the settle polls and the final re-read are live.
**Proof:** on real glass the toggle's own response now carries the new state
(304 ms on, 290 ms off); a backend test serves states from a stale overlay and
fails without the invalidation; a client test asserts invalidating one app
leaves another's snapshot warm.

### F9 (fixed, this pass): the toggle verb could not fire a real switch

GNOME Settings exports its switches with a single AT-SPI action named
`Toggle`, and the verb map resolved `toggle` to the native action `click`
only, so the one control the verb exists for answered `unsupported_action`
listing `["Toggle"]`. The verb now resolves to `toggle` then `click`.
**Proof:** the Hot Corner switch toggles structurally with the change in its
own re-read and in gsettings; a unit test builds a switch whose only action is
`Toggle` and fails without the mapping.

### F10 (fixed, this pass): a NameError on the Qt launch-env path

`accessibility_launch_env()` used `os.environ` without importing `os`; every
existing test passed a base dict and dodged it, and the CI-pinned linter
flagged it as an undefined name. **Proof:** a test calls it with no arguments
and fails with `NameError` without the import.

### F11 (fixed, this pass): the suite did not collect off Linux

`test_cache.py` imported `dbus_fast` unconditionally, and the dependency is
Linux-only by design, so the whole module errored on the macOS CI matrix and
took the run red. The client tests now skip where `dbus_fast` is absent while
the pure parser tests still run everywhere. Nine further CI-pinned lint
findings were fixed in the same sweep, so the lint gate is exit `0` again.

## Evidence

The pass is filed to an evidence bundle keyed by run id under
`e2e_evidence/vadgr-computer-use-0.7.0/20260812-041617-per-app-suite/`,
written while the pass ran, never reconstructed after: one timestamped
`stream-json` journal per group (the failing attempts kept beside their
re-runs, named for what went wrong), the preconditions file, the gsettings
ground-truth timeline for the Settings group, the latency table generated from
the journals, the full unit-suite tail, and a `SUMMARY.md` plus `MANIFEST`
indexing them. The earlier core-pass and expansion-pass artifacts remain in
their own bundles beside it.

The workflow groups (12 to 16), Group 9 and Part F were driven on 2026-08-14 and
are filed under `e2e_evidence/vadgr-computer-use-0.7.0/20260814-194219-workflow-suite/`:
one `stream-json` journal per group, the Group 9 screen-reader witness log, the
Settings gsettings timeline, the Group 16 `git status` and on-disk captures, and
a `SUMMARY.md` plus `MANIFEST`. All 18 groups pass on GNOME Wayland; the run used
the machine's swap and did not exhaust memory.

## What this runbook cannot prove

- **Any desktop it was not run on.** GNOME Wayland says nothing about KDE
  (Qt), wlroots, or GNOME X11; the per-desktop table schedules each for a
  0.1x.x perfectionism minor.
- **X11-session grounding**, because there is no X11 session here; the
  XWayland round trip (find bounds with `real` trust, click them, land) was
  driven, and the pure-X11 session is scheduled for a 0.1x.x perfectionism
  minor on GNOME X11.
- **Structural activation of GTK4 list rows.** Nautilus and Settings export
  no activation action on their sidebar rows; the tier reports that honestly
  and the runbook records it as the app's boundary, not a pass.
- **The Windows, WSL and macOS structured tiers**, which do not exist until
  `0.8.0` and `0.9.0`.
- **The browser tier.** AT-SPI's view of a browser is worse than the DOM's,
  and the DOM path is unchanged here, so it is out of scope by design.
