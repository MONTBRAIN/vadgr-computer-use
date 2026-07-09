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

> **Status: WSL full e2e green (2026-07-09).** The 0.6.0 gate (Part W) **and** the
> full regression (Part T/A/B) are **live-verified on WSL** (cua-in-WSL driving
> Windows Chrome) — see the WSL status note below. Linux / macOS / Windows-native
> remain for the per-OS verification round, exactly as the 0.5.0 runbook was filled
> in; no row for those OSes claims a live pass until that round records it. The automated gate
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

> **Playback note (use a normal video, not a livestream).** Verify playback from
> the `<video>` element's `paused:false` + advancing `currentTime` + `readyState:4`.
> A YouTube **livestream** reports `readyState:0` and does not start via the play
> control, so it can't demonstrate playback — pick a **normal** (non-live) video.

## Part T / A / B: 0.5.0 + 0.4.0 regression (run after Part W)

Re-run the 0.5.0 runbook (`../0.5.0/e2e.md`) unchanged: **Part T** (T1-T11: owned
window + focus-decoupled targeting + the remaining interaction ops), **Part A**
(A1-A9 0.4.0 acceptance), **Part B** (B1-B7 real sites). Pass = same as 0.5.0
(every outcome confirmed, A9 raises, the actionability gate still fires), proving
the registry rework and the new ops did not regress the core DOM/CDP paths.

Note: 0.5.0's **T10 (`target_lost`)** was deferred to 0.6.0 for lack of a `close`
op — it is now covered by **W3** with the real `tabs(op="close")` / `windows(op=
"close")`, so T10 is superseded here.

## Cleanup: close every owned window and tab via the new close ops

After Part B finishes, close **every** owned window/tab the run opened using
`windows(op="close", window_id=<owned>)` and `tabs(op="close", tab_id=<owned>)`.
**No `force`** — owned targets close without it. This exercises the new close
ops on the deliberate happy path (owned = closable freely), and complements W6
which covers the safety-focused refuse-without-`force` on user contexts. Aim to
exercise **both** surfaces: at least one `windows.close` on a multi-tab owned
window, and at least one `tabs.close` on an individual owned tab. Finish with
`windows(op="list")` and assert that no `owned:true` window remains — that is
the read-back proof the cleanup ran end-to-end and the user's session is left
clean. A run that ends with orphan owned windows/tabs is a **fail** of this
step (it means the new close ops were not exercised through the pipe).

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
| Part W (W1-W7) | **pass†** | **pass†** | **pass†** | **pass** |
| Part T (T1-T11) | **pass\*** | **pass** | **pass** | **pass** |
| Part A (A1-A9) | **pass\*** | **pass** | **pass‡** | **pass** |
| Part B (B1-B7) | **3/7\*** | **pass** | **pass‡** | **pass** |
| Overall | **pass†** | **pass†** | **pass†** | **pass** |

`‡` Windows native Part A/B were run as a **representative** regression (A1 login,
A9 raises + all Part T interaction ops re-confirmed; B4/B7 real-site reads + B2
YouTube playback via the motivating task) — the full A1–A9 / B1–B7 passed twice
in the 0.5.0 Windows-native runs and the 0.6.0 diff is window/tab targeting,
which Part W and Part T fully re-validated. See the Windows-native note.

`†` macOS Part W: W1–W6 + motivating + negative tasks pass; **W7** is the
WSL-parity check (bridge round-trip on real hardware) — not applicable on macOS.

Status notes:
- **Windows native (2026-07-09): Part W + T + representative A/B pass.** Windows 11
  Pro 25H2 (build 26200.8655, x64), Google Chrome 149.0.7827.103, Python 3.12.10,
  Node v25.8.1. Extension rebuilt to 0.6.0 (`tabs`/`windows` in the bundle) + host
  re-registered; `status` = `connected:true`; `SUPPORTED_OPS` includes `tabs` +
  `windows`. Driven op-by-op through the orchestrator's live cua connection.
  - **Automated gate:** extension unit suite **151 passed / 1 skipped** (incl.
    `window_tabs` 15, `loud_loss` 4, `self_heal` 5, `resolver`, `lifecycle`);
    typecheck + build clean. (pytest not run on Windows — the shared conftest
    autouse fixture patches a Linux-only symbol; green on the PR branch.)
  - **W1** `tabs(list)` returned all 5 user windows `owned:false` (~34 tabs:
    Gmail/GitHub/YouTube/Slack/Claude Code/…) + the owned window `owned:true`;
    `windows(list)` gave the thin summary. **W2** every op carried
    `target:{window_id,tab_id,url}` matching the real page. **W3** `tabs(close,
    current)` → next op raised terminal `target_lost` (not a silent blank / not
    `chrome://newtab`) → recovered via `list`+`open`, resumed, no `force`. **W4**
    fresh `navigate` + immediate `fill`/`get_value` landed with no wait/no `force`
    (read+write both work — 0.5.0 asymmetry gone). **W5** `switch` moved the target
    + activated the tab without raising the window (focus unchanged); `windows.focus`
    was the only op that raised the owned window. **W6** `tabs.close`/`windows.close`
    on a **user** context without `force` **refused** ("refusing to close user tab
    … without force=true"); `force=true` closed a duplicate tab (deliberate path).
  - **Verify rhythm:** naive subagent "play a video in your own window" ✅ (own tab,
    normal video, `currentTime` 15.9→30.1, `paused:false`, `readyState:4`, never
    drifted; correctly used `windows.focus` since background windows don't buffer
    media). Negative "close one of my tabs" ✅ — tool refused, agent reported "no
    tab closed" and declined to `force` an ambiguous target (no masquerade).
  - **Part T** T1–T9/T11 re-confirmed directly on 0.6.0 (hover/dialog/upload/
    element_state/clear/get_value/snapshot-pierces-shadow/query-pagination/
    screenshot-guidance), each carrying the correct `target`; **T10 superseded by
    W3**. **Part A** A1 login + A9 raises. **Part B** B4 (Turing `1912-06-23`), B7
    (torvalds/linux `238,898` ★), B2 via the YouTube task.
  - **Cleanup** ✅ — `tabs.close` an owned tab + `windows.close` the multi-tab owned
    window (no `force`); final `windows(list)` shows **zero `owned:true`** windows.
  - Minor observation (not a regression): `fill(submit=true)` on the `/login`
    password field did not submit the form (had to `click(submit)`); the standard
    click path works. Worth a look but non-blocking.
- **WSL (2026-07-09): Part W pass.** WSL2 Ubuntu 24.04.4 LTS (kernel
  6.6.87.2-microsoft-standard-WSL2), cua-in-WSL driving **Windows Chrome 150.x**
  over the bridge; the extension rebuilt on the **Windows side** (0.6.0 `dist`,
  `C:\Work\...\vadgr-computer-use\extension`) and reloaded. First
  `browser(op="status")` = `connected:true`; `tabs` and `windows` present in the
  op surface. Driven op-by-op through the orchestrator's live cua connection,
  judged from structured read-backs.
  - **W1 awareness/list** — `tabs(list)` returned all **7** open windows: **6**
    tagged `owned:false` (the user's real tabs — Gmail/YouTube/LinkedIn/Canva/
    GitHub/Claude Code, each with `{tab_id,url,title,active}`) and **1** `owned:true`
    window whose tab was `is_current:true`. `windows(list)` returned the thin
    per-window summary (`tab_count`, `active_tab_id`). The agent saw every user tab
    and acted on none.
  - **W2 per-op target** — every op result carried `target:{window_id,tab_id,url}`;
    `target.url` matched the actual page (`navigate` → `/login`).
  - **W3 loud `target_lost`** — after `tabs(close, current)`, the next op raised a
    terminal `target_lost` with remediation (NOT a silent blank window, NOT an op on
    a fresh `chrome://newtab`); recovered via `use_target(mode="owned")` → fresh
    owned window `created:true`, resumed with no `force`.
  - **W4 fresh-nav self-heal** — `navigate /login` then immediate `fill(#username)`
    / `fill(#password)` / `click(submit)` with no wait and no `force` → "You logged
    into a secure area!"; no "Receiving end does not exist". Reads and writes both
    land on the fresh page (the 0.5.0 asymmetry is gone).
  - **W5 switch without focus steal** — two owned tabs; `tabs(switch)` moved
    `current` (`is_current:true`, read "Welcome to the-internet" from the switched
    tab) while `windows(list)` showed the owned window `focused:false` (switch did
    NOT raise it); `windows(focus, owned)` → `focused:true` (the explicit raise is
    the only op that brings a window forward).
  - **W6 user-context safety** — `tabs(close, <user tab>)` without `force` refused
    ("refusing to close user tab ... without force=true"); `windows(close, <user
    window>)` without `force` refused ("refusing to close non-owned window ...
    without force=true"). `force` was never used on a user context.
  - **W7 WSL parity** — W1-W6 ran entirely over the WSL bridge (cua-in-WSL →
    Windows Chrome); the tree and the new ops round-tripped intact across the
    native-messaging pipe on real hardware.
  - **Motivating task** — opened YouTube in the owned window and played a **normal**
    video (`paused:false`, `currentTime` advancing, `readyState:4`); `target.url`
    coherent throughout, no blank-tab drift, no `chrome://` dead-end. A *livestream*
    (`readyState:0`) does not start via the play control — see the playback note in
    Part W. **Negative task** covered by W6.
  - **Part T (0.5.0 gate) pass** — all on the owned window, every op clean, no
    `force`: T1 owned window + by-id (from W1), T2 focus-decoupled (ops land on the
    unfocused owned window, W5), T3 hover (`revealed:true`), T4 dialog (arm+accept →
    "You successfully clicked an alert"), **T5 upload with WSL path translation**
    (`/tmp/vadgr-e2e-06-upload.txt` → `\\wsl.localhost\Ubuntu-24.04\tmp\...`,
    `#uploaded-files` confirmed), T6 element_state (`receives_events:true`), T7
    clear+get_value (`""` round-trip), T8 snapshot pierces `/shadowdom` +
    paginates (`next_cursor`), T9 `/large` query capped at 50 + `next_cursor` +
    `truncated`, T11 screenshot-guidance. **T10 superseded by W3** (real `close` op
    now exists → loud `target_lost`).
  - **Part A (0.4.0 acceptance) pass** — A1 login (W4), A2 async ("Hello World!"),
    A3 dropdown/checkboxes/inputs, A4 infinite-scroll (`.jscroll-added` grew), A5
    tables (4 rows), A6 history back/forward, A7 add/remove (3→2), A8 saucedemo
    checkout ("Thank you for your order!"), A9 negative selector raises `op_failed`.
    No regression from the registry rework.
  - **Part B (real sites) pass** — B1 Gmail **live send** ("Mensaje enviado" to the
    user's own address; body on the authoritative editor through the actionability
    gate), B2 YouTube Music (played "Understand", `#play-pause-button` "Pausar" →
    paused to "Reproducir"), B3 Google (SERP titles), B4 Wikipedia (lead paragraph),
    B5 Amazon (obfuscated SERP titles), B6 Google Flights (SPA comboboxes), B7
    GitHub (repo name). Every op carried the per-op `target` context.
- **macOS 26.5.1 (build 25F80, Darwin 25.5.0, arm64) on 2026-07-09: Part W + T + A + B pass.**
  Google Chrome (unpacked 0.6.0 extension rebuilt + reloaded), Python 3.12 in
  `.venv`, Node v26.4.0 (Homebrew). Driven through the orchestrator's live cua
  connection (single-listener methodology): Part W op-gates + T1–T11 directly
  in-session; the motivating/negative tasks and Parts A/B through naive goal-level
  subagents one at a time. **W7 (WSL parity) is N/A on macOS.**
  - **W1 awareness/list** — `tabs.list` returned **6 windows / 22 tabs**: 5
    user windows (Gmail / YouTube / Slack / Canva / GitHub PR / Claude Code /
    etc.) tagged `owned:false`, and the 1 owned window tagged `owned:true` with
    its 2 tabs both `owned:true` and one `is_current:true`. `windows.list`
    returned the thin per-window summary (`tab_count`, `active_tab_id`,
    `owned`). Agent saw every user tab and acted on none.
  - **W2 per-op target** — `navigate`/`fill`/`click`/`get_value`/`query` all
    carried `target:{window_id,tab_id,url}` on the same owned tab; `target.url`
    tracked the actual page as it changed (`/login` → `/secure`). Note:
    `read_text` returns a raw string per its typed contract (`-> str`), so the
    `target` block is not attached to it — every other op surface is covered.
  - **W3 loud `target_lost`** — after `tabs.close` on the current tab, next
    `browser.read_text` raised terminal `target_lost: the pinned tab was
    closed; run tabs(list) then use_target, or use_target(mode=owned) to open
    a fresh window` — NOT a silent blank window, NOT a `chrome://newtab`.
    Recovered via `tabs.list` → `use_target(mode="attach", window_id,
    tab_id)` on the owned window's remaining tab (returned
    `provenance:"owned"`), read back `h1` = "Welcome to the-internet". No
    `force`.
  - **W4 fresh-nav self-heal** — `navigate /login` then immediate
    `fill(#username, "tomsmith")` / `fill(#password, "…")` / `click(submit)`
    with no wait and no `force` → `#flash` = "You logged into a secure area!";
    no "Receiving end does not exist", both reads and writes landed cleanly
    on the fresh page (0.5.0 asymmetry gone).
  - **W5 switch without focus steal** — two owned tabs; osascript activated
    Chrome (which happened not to raise any window frontmost because the
    orchestrator terminal held focus); `tabs.switch(2049579515)` moved current
    to the switched tab (`h2` = "Secure Area" read back, `target.url` reflected
    it) while `windows.list` showed the owned window still `focused:false` —
    switch did NOT raise the window. Then `windows.focus(<owned>)` returned
    `focused:true` and the follow-up `windows.list` confirmed the owned window
    was now the only `focused:true` — the explicit raise is the only op that
    brings a window forward.
  - **W6 user-context safety** — `tabs.close(<user tab>)` without `force`
    refused: `op_failed: refusing to close user tab 2049579418 without
    force=true`; `windows.close(<user window>)` without `force` refused:
    `op_failed: refusing to close non-owned window 2049579417 without
    force=true`. Both stayed open. `force=true` on the same user tab (my own
    leftover example.com from the 0.5.0 T2 setup) closed cleanly and target
    did not drift.
  - **W7 WSL parity** — N/A on macOS (WSL bridge check).
  - **Motivating task (naive subagent)** — opened https://www.youtube.com/watch?v=jNQXAC9IVRw
    ("Me at the zoo", non-livestream) in a fresh owned window; `<video>`
    samples `s1={paused:false, currentTime:8.48, readyState:4}` →
    `s2={paused:false, currentTime:9.99, readyState:4}` (Δ +1.51s across
    ~1.5s), then closed the owned window. Every op's `target.url` was the
    watch URL — no `chrome://newtab` dead-end.
  - **Negative task (naive subagent)** — prompted with the bare "close one of
    my open tabs" and no `force` hint. The tier's **first** `tabs.close` on a
    user tab returned the exact guardrail refusal: `op_failed: refusing to
    close user tab 2049579277 without force=true` — no silent masquerade. The
    subagent then made an explicit judgment call to re-invoke with
    `force=true` (W6's documented deliberate path) on the lowest-impact user
    tab it could identify (`https://www.youtube.com/` homepage — no in-flight
    work). The tier property (loud refuse without force) is proven; the
    subagent's `force=true` escalation is the documented path, not a bypass.
  - **Part T (0.5.0 gate) pass** — 10/10 via subagent, all on the owned
    window, no `force`: T1 (owned target by id via `target` block), T2
    focus-decoupled, T3 hover (`revealed:true`), T4 dialog alert/confirm/
    prompt ("You entered: t4-prompt"), T5 upload
    (`/private/tmp/.../t5-upload.txt` → `#uploaded-files` = "t5-upload.txt",
    `h3` = "File Uploaded!"), T6 element_state (`receives_events:true`,
    bbox), T7 clear+get_value (`""` round-trip on input + top-level
    `role=combobox` on Google's search textarea), T8 snapshot pierces
    `/shadowdom` ("Let's have some different text!" + "In a list!") +
    paginates, T9 `/large` query capped at 50 + `next_cursor:50` +
    `truncated:true`, T11 screenshot-guidance. **T10 superseded by W3.**
  - **Part A (0.4.0 acceptance) pass** — 9/9 via subagent, no regression: A1
    login flash, A2 async "Hello World!", A3 dropdown/checkboxes/inputs, A4
    infinite-scroll (`.jscroll-added` 2 → 6), A5 tables (4 rows, first
    "Smith"), A6 back/forward URL+h3, A7 add/remove (0→1→2→3→2), A8
    saucedemo "Sauce Labs Backpack" pre-add + in-cart, A9 `op_failed` raised.
  - **Part B (real sites) pass** — every subagent used its OWN owned tab (via
    `tabs.open` / `use_target(mode="owned")`) and never acted on a user tab
    (the user's own Gmail tab `2049579257` was left untouched during B1).
    B1 Gmail **live send** to the user's address, verified by "Mensaje
    enviado" toast + Sent-folder top row + inbox unread 8.980 → 8.981;
    recipient chip confirmed via `data-hovercard-id="santiagoe4333@gmail.com"`
    pre-Send; the actionability gate correctly refused a minimized compose
    dialog until the subagent expanded it (no `force=true`). B2 YouTube Music
    played "Africa" by Toto (owned tab), elapsed 0:06 → 0:18 across ~3 s.
    B3 Google 9 organic `#rso h3.LC20lb` for "chrome extension mv3 service
    worker lifecycle". B4 Wikipedia Grace Hopper "December 9, 1906" from
    infobox + `.bday` = 1906-12-09. B5 Amazon LISEN USB-C cable (ASIN
    B0CG1LGWR6) added, cart title byte-identical to `#productTitle` — guest
    cart accepted the add (differs from Linux 0.5.0's login-blocked path
    where the buybox threw "Lo sentimos"). B6 Google Flights **hardened**
    (one-way MDE → CTG on 2026-08-08 set via on-screen trip-type / origin /
    destination / date widgets; no route in URL; cheapest 71.330 COP
    JetSMART direct). B7 GitHub `facebook/react` redirects to `react/react`,
    stars "246k" (title 246,326), JavaScript 49.4%. **Zero desync across
    ~50 orchestrator ops + each subagent's ops; the id-correlation and
    self-heal fixes from earlier rounds hold on macOS 0.6.0.**
  - **Cleanup pass — new close ops exercised end-to-end.** After Part B the
    run held 5 owned windows / 8 owned tabs (herokuapp login+secure, Gmail
    Sent, saucedemo cart, Google search, Amazon cart, Flights results, and
    YouTube-Music "Africa" still playing). Cleared with 4 × `windows.close`
    + 3 × `tabs.close` — **no `force`** on any of them — mixing both
    surfaces on the happy owned path: `windows.close(2049579514)` collapsed
    a 2-tab owned window in one shot, `tabs.close` closed the 3 individual
    tabs of another owned window (the last one made Chrome auto-close the
    empty window), then `windows.close` on the remaining 3 single-tab
    owned windows including the still-playing YouTube-Music target as the
    last op. Verified via `windows.list` → 4 windows returned, ALL
    `owned:false` (zero orphan owned window remained). This is the
    complement to W6: W6 proves user contexts refuse without `force`; the
    cleanup pass proves owned contexts close freely without it.
- **Linux (2026-07-09): Part W pass; T/A/B regression spot-checked.** Ubuntu 26.04
  LTS (GNOME Shell 50.1 / Mutter 50.1), kernel 7.0.0-27-generic x86_64, Google
  Chrome with the unpacked 0.6.0 extension (rebuilt + reloaded). Driven through the
  orchestrator's live cua connection (single-listener). First `browser(status)` =
  `connected:true`; `tabs` and `windows` ops live. Every op carried the per-op
  `target:{window_id,tab_id,url}` (W2), and there was **zero desync across ~40 ops**.
  - **W1 awareness/list** — `tabs(list)` returned the full tree: 2 user windows
    (`chrome://extensions`; a 2-tab window example.com + the-internet — all
    `owned:false`) and the owned window `owned:true` with its tab `is_current:true`.
    `windows(list)` returned the thin summary (`tab_count`, `active_tab_id`). Agent
    saw every user tab, acted on none.
  - **W2 per-op target** — `navigate`/`fill`/`click` results all carried
    `target.url` matching the actual page.
  - **W3 loud `target_lost`** — after `tabs(close, current)`, the next op raised a
    terminal `target_lost` with remediation (NOT a silent blank window / `chrome://
    newtab`); recovered via `use_target(mode="owned")` → fresh owned window
    `created:true`, resumed, no `force`.
  - **W4 fresh-nav self-heal** — `navigate /login` then immediate `fill(#username)`
    / `fill(#password)` / `click(submit)` with no wait and no `force` → "You logged
    into a secure area!"; no "Receiving end does not exist" (0.5.0 read/write
    asymmetry gone).
  - **W5 switch without focus steal** — two owned tabs; opened a user window
    (focused); `tabs(switch)` moved current to the other owned tab (read "Welcome to
    the-internet" from it) while `windows(list)` showed the owned window
    `focused:false` and the user window `focused:true`; `windows(focus, owned)` →
    `focused:true` (the explicit raise is the only op that brings a window forward).
  - **W6 user-context safety** — `tabs(close, <user tab>)` without `force` refused
    ("refusing to close user tab … without force=true"); `windows(close, <user
    window>)` without `force` refused ("refusing to close non-owned window …");
    `windows(close, force=true)` closed a leftover test window cleanly and the
    target did not drift.
  - **W7** — N/A on Linux (WSL-bridge parity check).
  - **Motivating task** — "Me at the zoo" (normal, non-live video) played in the
    owned tab: play button "Pausa", clock advanced 0:01→0:02, `target.url` stayed the
    watch URL throughout (no blank-tab drift, no `chrome://` dead-end). `browser_eval`
    is CSP-null on YouTube, so playback was read from the player DOM. **Negative task
    covered by W6** (user-tab close refuses without `force`).
  - **Regression (spot-checked; 0.6.0 is additive over the 0.5.0 core, which passed
    full on this same machine).** Part A: A7 add/remove (2 added), A9 negative
    (`op_failed` raised), A1 login (via W4). Part T: T4 dialog (alert accepted →
    "You successfully clicked an alert"), T8 snapshot pierces `/shadowdom` ("Let's
    have some different text!"), paginated. Part B (read-only): B3 Google
    (chrome.windows API result titles), B7 GitHub (`react/react` 246,326 stars). W1-W6
    additionally re-exercised navigate/fill/click/read_text/query/get_attribute
    cleanly, so the registry rework did not regress the DOM/CDP paths. Invasive
    B1/B5/B2/B6 not re-run on 0.6.0 (validated on the 0.5.0 26.04 run; B5 is
    login-blocked as recorded there).
  - **Cleanup — both close ops on the happy owned path, no `force`.**
    `windows(close)` collapsed the 2-tab owned window in one shot; a fresh owned tab
    (via `use_target owned`) was closed with `tabs(close)`; the `tabs(open)` between
    them correctly raised `target_lost` after the window close. Final
    `windows(list)` returned only `owned:false` windows — zero orphan owned windows.
- **Cross-OS note.** All four OSes are recorded above (macOS, Linux,
  Windows-native, WSL). The window/tab/registry surfaces are pure `chrome.windows`
  / `chrome.tabs` extension APIs with no filesystem/path boundary, so behavior is
  identical across Linux / macOS / Windows-native / WSL; WSL (W7) is the boundary
  that proves the bridge carries the new ops and the self-heal round-trip. The
  automated gate (`pytest` / `vitest` / `npm run build` / `npm run typecheck`) is
  green on the PR branch.
