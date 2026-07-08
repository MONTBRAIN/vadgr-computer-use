# Browser tier 0.5.0 - end to end test runbook

Per-OS end to end validation of **browser round 2** — the window/tab **session
target** (focus-decoupled targeting) and the remaining interaction ops (`hover`,
`dialog`, `upload`, `element_state`, `focus`/`blur`, `clear`, `get_value`,
`snapshot`, shadow/frame piercing) — driven by a real agent. Unit tests prove
functions in isolation; they do not prove the native-messaging pipe, the
extension, the owned-window lifecycle, and real pages work on each platform. Run
this on each target OS and record the result in the table at the bottom.

Target OSes: Linux, macOS, Windows (native), WSL (cua in WSL driving Windows Chrome).

Builds on the 0.4.0 runbook (`../0.4.0/e2e.md`); the 0.4.0 acceptance + real-site
suites re-run here as the **regression** part, and Part T below is the new-in-0.5.0
gate.

## The approach: a Claude subagent over `claude -p`

Same as 0.4.0. Real end to end is driven by a real agent, never a script. A `.py`
script that calls `bridge.send` directly is an acceptance test only, not the e2e.
Goal-level task; the verdict comes from the `tool_use` / `tool_result` stream
(cua's real read-backs), not the agent's prose. A self-reported success with no
confirming read-back is a fail. One subagent at a time, never in parallel.

> Single-listener note (from 0.4.0): the cua native-host bond is single-listener,
> so if an orchestrating session already owns the extension, a subagent's own cua
> server sees `not_connected`. In that case route each test through the
> orchestrator's live cua connection, one naive goal-level subagent at a time,
> judged from verbatim read-backs (same no-parallel, DOM-as-ground-truth rules).

## Prerequisites (per OS)

1. Install cua from **this branch** into a venv: `pip install .`
2. Build the extension: `cd extension && npm run build`
3. Load `extension/dist` as an unpacked extension in Chrome or Edge, **reload it
   after the rebuild** (0.5.0 adds the `storage` permission — accept it), and
   accept the `debugger` permission. The pinned manifest `key` keeps the unpacked
   ID stable, so the native-host registration still matches.
4. On WSL nothing else is needed: cua self-registers the native host and places
   the Windows relay shim automatically on startup. cua runs in WSL, Chrome on Windows.
5. Sanity check: the agent's first `browser(op="status")` returns `connected: true`,
   and `supported_ops` now includes `use_target`, `hover`, `dialog`, `upload`,
   `element_state`, `focus`, `blur`, `clear`, `get_value`, `snapshot`.

## Part T: the 0.5.0 gate (run first)

Deterministic fixtures on `the-internet.herokuapp.com` (which has `/hovers`,
`/javascript_alerts`, `/upload`, `/shadowdom`, `/large`) plus a two-window setup.
Each is a goal-level task; the outcome is judged from the stream.

- **T1 Owned window + target by id.** From a cold start, have the agent act on a
  page. Expect it to open/own a dedicated window and every op to resolve by
  `{windowId, tabId}` (never `currentWindow`). `use_target` reports
  `{window_id, tab_id, created:true}`.
- **T2 Focus-decoupled targeting (THE headline — the 0.4.0 bug).** With the agent
  acting on its owned window, **focus a *second*, different Chrome window** (a
  human or a second opened window). The agent's next ops must still land on the
  **owned** window, not the focused one. Expect read-backs from the owned page;
  a change appearing in the focused window is a **fail**. This is the proof the
  active-tab-hijack bug is gone.
- **T3 hover.** On `/hovers`, hover the first avatar; expect the `:hover`-gated
  "name / View profile" caption to become visible (`{hovered:true, revealed:true}`).
- **T4 dialog.** On `/javascript_alerts`: arm then accept the JS alert; arm then
  dismiss the confirm; arm + text then accept the prompt. Expect each result text
  reflected on the page (`You entered: …`).
- **T5 upload.** On `/upload`, upload a small local file via `upload`; expect the
  input's `files.length` read back and the "File Uploaded!" confirmation. **On WSL
  this also exercises the cua-side path translation** (`/home/...` -> a Chrome-OS
  path); assert the Windows Chrome actually received the file.
- **T6 element_state.** On any control, read `element_state`; expect
  `{visible, enabled, focused, editable, receives_events, bbox}` with
  `receives_events` present (the CDP hit-test), not just the DOM flags.
- **T7 clear + get_value.** Type into an input, `clear` it (read-back `""`), type
  again, `get_value` (matches). Also `get_value` on a contenteditable / custom
  widget via the CDP path.
- **T8 snapshot + pierce.** On `/shadowdom`, `snapshot` the tree; expect nodes
  from **inside the shadow root** (pierced), each with role/name/state/ref. Confirm
  `snapshot` supersedes `accessibility_tree` (both present in `supported_ops`,
  `snapshot` paginated).
- **T9 query cap / pagination.** On `/large` (a big table), `query` a broad
  selector; expect a **capped, paginated** result with a `next_cursor`, not a
  multi-tens-of-thousands-char blob (the 0.4.0 token-budget blowout).
- **T10 target_lost.** 0.5.0 has **no `close` op** — window/tab management
  (open/focus/close/switch) lands in **0.6.0** (browser round 3). `target_lost` is
  designed to fire when the *user* closes the owned window, so trigger it that way:
  **manually close the owned window** (click its X) mid-task. Do **not** pixel-close
  it — a coordinate mis-hit could close one of your real tabs. Expect a terminal
  `target_lost` error with remediation on the next op; the tier must **never**
  silently retarget the user's active tab.
- **T11 screenshot guidance.** Call `browser(op="screenshot")`; expect the "that's
  the pixel `screenshot` tool, not a `browser` op" guidance, not a crash.

Pass for Part T: every outcome confirmed from the stream; **T2 proves focus does
not decide the target**; T10 is loud and terminal; the agent verifies on its own.

## Part A: 0.4.0 acceptance regression (run after Part T)

Re-run the 0.4.0 acceptance suite A1-A9 (`../0.4.0/e2e.md` Part A) unchanged, to
prove the targeting rework and the new ops did not regress the core DOM ops.
Pass = same as 0.4.0 (every outcome confirmed, A9 raises, the actionability gate
still fires).

## Part B: real sites (run last)

Re-run the 0.4.0 real-site suite B1-B7 (`../0.4.0/e2e.md` Part B) on the user's
real logged-in browser, with **B6 hardened**: the Google Flights search must use
the on-screen origin/destination/date fields (no route or dates in the URL) — this
is the R6 "force the on-screen widgets" hardening called for in 0.5.0. Run B2
(YouTube Music) last because it leaves a playing tab. A not-logged-in / captcha
situation is `blocked`, not a tier failure.

## Per-OS results

Fill these in by running the runbook on each OS. Record the specific OS + Chrome
version in the status note so a future regression reproduces on the same build.

Legend: pass / fail / blocked (login or anti-bot) / not run

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part T (T1-T11) | not run | not run | not run | not run |
| Part A (A1-A9) | not run | not run | not run | not run |
| Part B (B1-B7) | not run | not run | not run | not run |
| Overall | not run | not run | not run | not run |

Status notes:
- _(to be filled as each OS is run)_
