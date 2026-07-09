# Browser tier 0.6.0 - end to end test runbook

Per-OS end to end validation of **browser round 3** — window/tab **management**
(the multi-context session model) and the reliability fixes that stop the agent
getting lost: **loud loss** (a mid-task target loss raises `target_lost` instead
of a silent blank re-open), a **per-op `target` context** on every result, and
**content-script self-heal for mutating ops**. Unit tests prove functions in
isolation; they do not prove the native-messaging pipe, the extension, the
window/tab registry, and real pages work on each platform. Run this on each
target OS and record the result in the table at the bottom.

Target OSes: Linux, macOS, Windows (native), WSL (cua in WSL driving Windows Chrome).

Builds on the 0.5.0 runbook (`../0.5.0/e2e.md`); the 0.5.0 Part T/A/B suites re-run
here as the **regression** part, and Part W below is the new-in-0.6.0 gate.

> **Status: NOT YET RUN.** This document is the runbook only. The per-OS live
> runs are executed by the dedicated per-OS verification agents on real hardware
> (the human verification round), exactly as the 0.5.0 runbook was filled in. No
> row below claims a live pass until that round records it. The automated gate
> (`pytest`, `vitest`, `npm run build`, `npm run typecheck`) is green on the PR
> branch — see *Automated gate* below — but a green unit suite is necessary, NOT
> sufficient; Part W is the milestone gate.

## The approach: a Claude subagent over `claude -p`

Same as 0.4.0 / 0.5.0. Real end to end is driven by a real agent, never a script.
A `.py` script that calls `bridge.send` directly is an acceptance test only, not
the e2e. Goal-level task; the verdict comes from the `tool_use` / `tool_result`
stream (cua's real read-backs), not the agent's prose. A self-reported success
with no confirming read-back is a fail. One subagent at a time, never in parallel.

> Single-listener note (from 0.4.0): the cua native-host bond is single-listener,
> so if an orchestrating session already owns the extension, a subagent's own cua
> server sees `not_connected`. In that case route each test through the
> orchestrator's live cua connection, one naive goal-level subagent at a time,
> judged from verbatim read-backs (same no-parallel, DOM-as-ground-truth rules).

## When a test surfaces a bug: fix it, then push to the PR branch

The e2e exists to *find* bugs, so finding one is a success, not a blocker. The
procedure when a run surfaces a real defect (a hang, a wrong read-back, a silent
success, a desync):

1. **Stop and root-cause it in the source** — cite the file:line, not a guess. A
   flaky environment is not a root cause; confirm it in the code.
2. **Fix it on this PR branch** (`feat/0.6.0-window-tab-management`): change the
   code, add or extend a unit test that would have caught it, and rebuild the
   extension if the fix is extension-side.
3. **Verify the fix end-to-end — a unit test is NOT enough.** Restart the cua
   session (load the rebuilt server), reload the extension, then re-drive the
   exact scenario that failed and watch the real read-back come back correct.
4. **Record the finding** in the per-OS status note: what broke, the root cause
   (file:line), the fix commit, AND the end-to-end re-run that confirmed it.
5. **Commit and push to the PR branch** so the fix ships with the feature, then
   resume the run from where it stopped.

Do NOT paper over a bug by changing the test to avoid it, do NOT claim a fix
works on the strength of a unit test alone, and do NOT mark a tier `pass` with a
known unfixed defect — record it `fail` with the finding until it is verified
end-to-end.

## Prerequisites (per OS)

1. Install cua from **this branch** into a venv: `pip install .`
2. Build the extension: `cd extension && npm run build`.
3. Load `extension/dist` as an unpacked extension in Chrome or Edge, **reload it
   after the rebuild**, and accept the `debugger` permission. The pinned manifest
   `key` keeps the unpacked ID stable, so the native-host registration still
   matches. No new permission is required in 0.6.0 (`tabs` already covers
   `chrome.windows`/`chrome.tabs`).
4. On WSL nothing else is needed: cua self-registers the native host and places
   the Windows relay shim automatically on startup. cua runs in WSL, Chrome on
   Windows. **WSL: rebuild the extension on the *Windows* side** (see
   `ENGINEERING.md` §4 gotcha) — a WSL-side `npm build` never reaches the Windows
   Chrome that loads the unpacked dist.
5. Sanity check: the agent's first `browser(op="status")` returns
   `connected: true`, and `supported_ops` now includes `tabs` and `windows`
   (alongside the 0.5.0 ops).

## Part W: the 0.6.0 gate (run first)

Deterministic fixtures on `the-internet.herokuapp.com` (`/login`, `/`) plus a
two-window setup. Each is a goal-level task; the outcome is judged from the
stream. **Four-OS note:** `tabs`/`windows` are pure `chrome.windows` /
`chrome.tabs` extension APIs with **no path boundary** (unlike `upload`), so the
same behavior is expected on Linux / Windows / macOS / WSL; W6 is the WSL parity
check that the bridge carries the new ops and the self-heal round-trip.

- **W1 Awareness / list.** From a cold start, open the owned window, then open a
  **second, separate** Chrome window with two tabs (a "user" window). Run
  `tabs(op="list")`. Expect the full `window -> tabs -> {tab_id, url, title,
  active, owned, is_current}` tree covering **both** windows, with the owned
  window tagged `owned:true` / one tab `is_current:true`, and the user window
  tagged `owned:false`. `windows(op="list")` returns the thin per-window summary
  (`tab_count`, `active_tab_id`). The agent SEES the user's tabs but does not act
  on them.
- **W2 Per-op target context.** Any normal op (`navigate`, `fill`, `read_text`,
  `click`) returns a result that also carries `target: {window_id, tab_id, url}`.
  Confirm the `target.url` matches the page the agent is actually on (so a
  surprise `chrome://newtab` would be visible immediately).
- **W3 Drift recovery via LOUD `target_lost` (the motivating bug, live).** Make an
  owned tab `current` and act on it. Then **close `current`** (via
  `tabs(op="close", tab_id=<current>)`, or manually close the owned window). The
  **next op** must return a terminal **`target_lost`** error with remediation —
  **not** a silent blank owned window and **not** an op that ran against a fresh
  `chrome://newtab`. Then recover: `tabs(op="list")` -> `use_target(window_id,
  tab_id)` the real tab -> resume, all **without `force`**. (Cold-start auto-open
  still works: a brand-new session with no target opens the owned window on the
  first op — that convenience is intact; only a *mid-task* loss is loud.)
- **W4 Fresh-nav mutation via self-heal (the read/write split, live).**
  `navigate` to `/login`, then **immediately** `fill(#username)` / `click`
  **without any wait and without `force`**. The mutating op must land (self-heal:
  the content script is re-injected once and the op delivered), verified by a
  `get_value` / `read_text` read-back — **no** `"Receiving end does not exist"`,
  **no** need for `force`. Confirm a read op and a write op on the same fresh page
  both succeed (the 0.5.0 "reads work, writes fail" asymmetry is gone).
- **W5 Switch without stealing focus.** Open two owned tabs. Focus a **separate**
  user Chrome window (or leave the user's window foregrounded). `tabs(op="switch",
  tab_id=<the other owned tab>)`. The agent's read-backs must prove it now acts on
  the switched tab (`is_current:true`, reads from that page), while the user's
  foreground window **stays focused** — `switch` activates the tab within its own
  window but never raises the window (no `windows.update({focused})`). Then
  `windows(op="focus", window_id=<owned>)` is the **explicit** raise; confirm it
  does bring the owned window forward (the only op that does).
- **W6 User-context safety.** From `tabs(op="list")`, pick a **user** tab (one the
  agent did not open, `owned:false`, not `is_current`). `tabs(op="close",
  tab_id=<user tab>)` **without `force`** must **refuse** (`op_failed`, "refusing
  to close user tab ... without force=true") and the tab must stay open. The agent
  must **never** navigate / act on / close a user context that is not `current`.
  `windows(op="close", window_id=<user window>)` without `force` likewise refuses
  (owned only unless `force`). Repeat with `force=True` to confirm the deliberate
  path works.
- **W7 WSL parity.** Run W1-W6 over the WSL bridge (cua-in-WSL driving Windows
  Chrome). `tabs.list` / `switch` / loud-loss / self-heal behave identically
  (`getAll` is a pure extension API, no path boundary). Assert the tree and the
  new ops round-trip intact across the native-messaging pipe on real hardware.

Pass for Part W: every outcome confirmed from the stream; **W3 loud `target_lost`
is terminal and recoverable (never a silent blank window)**; **W4 the fresh-nav
mutation lands via self-heal without `force`**; **W5 `switch` does not steal
focus**; **W6 a user context is never closed/acted-on without `force`**; the
agent verifies on its own.

**Agent-driven verify rhythm (ENGINEERING §4).** In addition to the op-level
gates, re-run the **motivating task end-to-end** through a naive goal-level
subagent — "open YouTube in your own window and play a video" — which must now
complete **without getting lost** (no blank-tab drift, no `chrome://` dead-end).
Plus a **negative task**: "close one of my open tabs" with no `force` hint must
**refuse**, never masquerade as success.

## Part T / A / B: 0.5.0 + 0.4.0 regression (run after Part W)

Re-run the 0.5.0 runbook (`../0.5.0/e2e.md`) unchanged: **Part T** (T1-T11: owned
window + focus-decoupled targeting + the remaining interaction ops), **Part A**
(A1-A9 0.4.0 acceptance), **Part B** (B1-B7 real sites). Pass = same as 0.5.0
(every outcome confirmed, A9 raises, the actionability gate still fires), proving
the registry rework and the new ops did not regress the core DOM/CDP paths.

Note: 0.5.0's **T10 (`target_lost`)** was deferred to 0.6.0 for lack of a `close`
op — it is now covered by **W3** with the real `tabs(op="close")` / `windows(op=
"close")`, so T10 is superseded here.

## Automated gate (green on the PR branch — necessary, not sufficient)

Run before any live e2e; this is what the PR branch was validated against:

- `pytest computer_use/tests -q` — cua-side unit suite (tabs/windows params +
  returns, per-op target threaded onto the result, `target_lost` terminal
  `ToolError` with remediation, protocol negotiation with the longer
  `supported_ops` and NO `PROTOCOL_VERSION` change, `op_unsupported` for an
  extension lacking the ops).
- `cd extension && npm test` — extension unit suite (`registry.test.ts`,
  `enumeration.test.ts`, `loud_loss.test.ts`, `self_heal.test.ts`,
  `window_tabs.test.ts`, plus the extended `resolver.test.ts` / `lifecycle.test.ts`).
- `npm run build` — must pass the content-script IIFE guard.
- `npm run typecheck` — `tsc --noEmit` clean.

## Per-OS results

Fill these in by running the runbook on each OS. Record the specific OS + Chrome
version in the status note so a future regression reproduces on the same build.

Legend: pass / fail / blocked (login or anti-bot) / not run

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part W (W1-W7) | not run | not run | not run | not run |
| Part T (T1-T11) | not run | not run | not run | not run |
| Part A (A1-A9) | not run | not run | not run | not run |
| Part B (B1-B7) | not run | not run | not run | not run |
| Overall | not run | not run | not run | not run |

Status notes:
- **All OSes: not run (pending the per-OS verification round).** The window/tab/
  registry/storage surfaces are pure `chrome.windows` / `chrome.tabs` extension
  APIs with no filesystem/path boundary, so Linux / Windows / macOS / WSL are
  expected to behave identically; WSL (W7) is the boundary that proves the bridge
  carries the new ops and the self-heal round-trip. These live runs require real
  hardware / a real browser session per OS and are performed by the dedicated
  per-OS verification agents (the human verification round), exactly as the 0.5.0
  runbook was filled in. The automated gate above is green on the PR branch.
