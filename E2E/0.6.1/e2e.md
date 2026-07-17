# Browser tier 0.6.1 - end to end test runbook

Per-OS end to end validation of **multi-profile targeting** (which Chrome profile
does cua drive?). 0.6.1 inserts the **profile** dimension under the 0.6.0
registry (`browser -> profile -> windows -> tabs`). The load-bearing change is
multiplexing the native-host bond (previously single-listener) into a
per-profile connection registry, so cua can enumerate every connected profile,
tell them apart by what is open in each, and drive exactly the one the agent
chose. Unit tests prove the registry, the resolution ladder, and the handshake
in isolation; they do not prove the native-messaging pipe carries multiple
concurrent connections and that the agent lands in the right profile on real
hardware. Run this on each target OS and record the result in the table at the
bottom.

Target OSes: Linux, macOS, Windows (native), WSL (cua in WSL driving Windows Chrome).

Builds on the 0.6.0 runbook (`../0.6.0/e2e.md`); **Part P** below is the
new-in-0.6.1 gate, and **Part W** re-runs a 0.6.0 spot-check as the regression
part (the registry rework must not regress single-profile targeting).

> **Status: not yet run on hardware.** The automated gate (`pytest`, `vitest`,
> `npm run build`, `npm run typecheck`) is green on the PR branch — see
> *Automated gate* below — but a green unit suite is necessary, NOT sufficient.
> The live multi-profile run needs the extension loaded in **two real Chrome
> profiles** and is a **human verification round**; every per-OS row below is
> marked **not run (pending the per-OS verification round)** until that round
> records it, exactly as the 0.6.0 runbook was filled in.

## The approach: a Claude subagent over `claude -p`

Same as 0.4.0 / 0.5.0 / 0.6.0. Real end to end is driven by a real agent, never a
script. A `.py` script that calls `bridge.send` directly is an acceptance test
only, not the e2e. Goal-level task; the verdict comes from the `tool_use` /
`tool_result` stream (cua's real read-backs), not the agent's prose. A
self-reported success with no confirming read-back is a fail. One subagent at a
time, never in parallel.

> **Single-listener note (reconciled for 0.6.1).** The 0.4.0 / 0.6.0 runbooks
> carried a caveat: the cua native-host bond was *single-listener*, so if an
> orchestrating session already owned the extension, a subagent's own cua server
> saw `not_connected`, and tests had to route through the orchestrator's live
> connection. **0.6.1 changes the transport, not this operational rule.** cua now
> accepts and keeps *multiple* connections, but that is multiple *extension /
> profile* connections into **one** cua listener — it is NOT multiple cua servers
> sharing the extension. A second cua server still starts its own listener and
> the extension still binds to one native port, so the "one cua listener at a
> time; route subagents through the orchestrator's live connection" rule stands.
> What 0.6.1 adds is that the *one* listener can now hold the work profile and the
> personal profile at once and the agent selects between them. Kill stray cua
> servers before a run exactly as before.

## When a test surfaces a bug: fix it, then push to the PR branch

The e2e exists to *find* bugs, so finding one is a success, not a blocker. The
procedure when a run surfaces a real defect (a hang, a wrong read-back, a silent
success, a desync, a wrong-profile landing):

1. **Stop and root-cause it in the source** — cite the file:line, not a guess. A
   flaky environment is not a root cause; confirm it in the code.
2. **Fix it on this PR branch** (`feat/0.6.1-multi-profile`): change the code, add
   or extend a unit test that would have caught it, and rebuild the extension if
   the fix is extension-side.
3. **Verify the fix end-to-end — a unit test is NOT enough.** Restart the cua
   session (load the rebuilt server), reload the extension in **both** profiles,
   then re-drive the exact scenario that failed and watch the real read-back come
   back correct.
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
3. **Load `extension/dist` as an unpacked extension in TWO separate Chrome
   profiles** (e.g. a personal profile and a work profile), reload it after the
   rebuild, and accept the `debugger` permission in each. The pinned manifest
   `key` keeps the unpacked ID stable, so the native-host registration matches in
   both profiles. **No new permission is required in 0.6.1** (`storage` already
   covers `chrome.storage.local`, where the per-profile UUID is minted).
4. Give the two profiles **recognizably different** open tabs (e.g. work Gmail +
   Figma + GitHub in one, personal Gmail + YouTube in the other), so `profiles`
   recognition context is meaningful.
5. On WSL nothing else is needed: cua self-registers the native host and places
   the Windows relay shim automatically on startup. cua runs in WSL, Chrome on
   Windows. **WSL: rebuild the extension on the *Windows* side** (see
   `ENGINEERING.md` §4 gotcha) — a WSL-side `npm build` never reaches the Windows
   Chrome that loads the unpacked dist.
6. Sanity check: the agent's first `browser(op="status")` returns
   `connected: true` and a `profiles` array with **two** entries, each carrying
   `profile_id` + recognition context; `supported_ops` now includes `profiles`
   (alongside the 0.6.0 ops).

## Setup for the complete WSL run (every part, precise)

Goal: execute EVERY part on WSL (cua-in-WSL -> Windows Chrome), not a spot-check.
Prereq: the 0.6.1 extension loaded in **two** Chrome profiles (both windows open), cua
on the 0.6.1 branch, first `browser(op="status")` = `connected:true` with `profiles`
listing both. Each part's exact setup:

- **P1-P3, P6** — no extra setup; both profiles connected. Drive through the orchestrator
  cua (`profiles(list/use)`, `use_target`, DOM ops). P6 (WSL parity) is inherent to the
  bridge run.
- **P4 (`CUA_BROWSER_PROFILE` env pin)** — set the env on the cua server, then restart so
  cua re-reads it: in `Common/.mcp.json`, add to the `vadgr-computer-use` server
  `"env": {"CUA_BROWSER_PROFILE": "<a sample_tab_title substring of the profile to pin,
  e.g. Outlier>"}`, then **restart the session**. Expect: with both profiles connected,
  the pinned one is auto-`current` and a page op runs WITHOUT `profile_ambiguous`. Remove
  the env + restart afterward to return to normal.
- **P5 (single-profile back-compat)** — **close one profile's Chrome window** so only one
  profile stays connected (its extension disconnects). Expect: `profiles(list)` shows
  one; a page op auto-uses it, no `profile_ambiguous`. Re-open the window afterward.
- **Part W (W1-W7 regression)** — both profiles connected; `profiles(use)` one, then run
  the full 0.6.0 gate W1-W7 inside it.
- **Part I (multi-instance #26)** — the discovery-file coexistence (what #26's minimal fix
  delivers) is tested at the **cua-process level**, no browser needed:
  - **I2 (default):** the running cua (no env) writes the default `~/.vadgr-cua/browser.port`.
  - **I1 (coexistence):** launch two throwaway cua processes with distinct
    `VADGR_CUA_BROWSER_DISCOVERY=/tmp/cua-A/browser.port` and `.../cua-B/browser.port`;
    assert each writes ITS OWN file and none clobbers the other or the default.
  The full two-**browser** coexistence (each cua bonded to its own Chrome *instance*)
  needs the 0.6.2 launch capability and is out of scope for 0.6.1's transport fix.

## Part P: the 0.6.1 gate (run first)

Two Chrome profiles, each with the extension loaded and a recognizable set of
tabs. Each item is a goal-level task; the outcome is judged from the stream.
**Four-OS note:** the multi-connection registry is pure Python and the profile
handshake is a pure extension handshake (storage.local UUID + the existing tab
enumeration) with **no path boundary** (unlike `upload`), so the same behavior is
expected on Linux / Windows / macOS / WSL; P6 is the WSL parity check that the
bridge carries multiple concurrent connections and the profile handshake
round-trips.

- **P1 Enumerate two profiles with recognizable context.** With the extension
  connected from **both** profiles, run `profiles(op="list")` (and
  `browser(op="status")`). Expect **two** entries, each with a distinct
  `profile_id` and the recognition context `{window_count, tab_count,
  sample_tab_titles}` reflecting what is actually open in that profile (so a human
  reads "the one with work Gmail and Figma" vs "the one with personal Gmail and
  YouTube"). Neither is silently acted on yet.
- **P2 Two connected, none selected -> loud `profile_ambiguous`.** From the
  two-connected state with no selection made, the **first page op** (e.g.
  `navigate` / `read_text`) must raise a terminal **`profile_ambiguous`** error
  that **lists both choices** (id + recognition context) with remediation — NOT a
  silent pick of whichever connected first. Same "never silently wrong" doctrine
  as 0.6.0 `target_lost`.
- **P3 Select one and act only within it.** `profiles(op="use",
  profile_id=<work>)` (or `use_target(profile_id=<work>, ...)`). Then the 0.6.0
  `tabs` / `windows` / DOM ops must operate **only** within the selected profile:
  `tabs(op="list")` shows that profile's windows/tabs, `navigate` + a read-back
  land in it, and every result's `target` is coherent. Confirm from the stream
  that the OTHER profile is **untouched** — its tabs did not change, nothing was
  opened/navigated in it. Switch selection to the other profile
  (`profiles(op="use", profile_id=<personal>)`) and confirm ops now land there and
  the first profile is left alone.
- **P4 `CUA_BROWSER_PROFILE` pin.** Restart cua with
  `CUA_BROWSER_PROFILE=<a profile_id prefix OR a distinctive tab-title substring
  of the work profile>`. With both profiles connected and no explicit selection,
  the first op must land in the **pinned** profile (auto-resolved via the env
  rung of the ladder), not raise `profile_ambiguous`. Confirm via a read-back +
  `target` that it is the intended profile.
- **P5 Back-compat: single profile is unchanged.** With the extension connected
  from **one** profile only, `profiles(op="list")` shows a single entry and the
  first page op runs against it with **no** selection step and **no**
  `profile_ambiguous` (the sole-connection convenience). This proves single-profile
  users see no behavior change. (If an OLD, pre-0.6.1 extension is available, also
  confirm it registers under `profile_id="default"` and its normal ops still work;
  `profiles` against it raises `op_unsupported` — the standard capability gate.)
- **P6 WSL parity.** Run P1-P5 over the WSL bridge (cua-in-WSL driving Windows
  Chrome) with the extension in two Windows-Chrome profiles. Enumeration,
  selection, `profile_ambiguous`, and the env pin behave identically; assert the
  **two concurrent connections** and the profile handshake round-trip intact
  across the native-messaging pipe on real hardware (the multiplexed bond is the
  load-bearing change and WSL is its parity boundary).

Pass for Part P: every outcome confirmed from the stream; **P2 the
two-connected-none-selected first op raises `profile_ambiguous` listing both
choices (never a silent pick)**; **P3 the selected profile is driven and the
other is provably untouched**; **P4 the env pin resolves**; **P5 single-profile
is unchanged (back-compat)**; the agent verifies on its own.

**Agent-driven verify rhythm (ENGINEERING §4).** In addition to the op-level
gates, re-run a **motivating task end-to-end** through a naive goal-level
subagent — "in my work profile, open GitHub and read the repo name" (with both
profiles connected) — which must **select the work profile first** (or raise
`profile_ambiguous` and then select), act only within it, and never touch the
personal profile. Plus a **negative task**: with two profiles connected and an
ambiguous instruction ("open my email"), the first op must **surface the
`profile_ambiguous` choice** rather than guessing a profile.

## Part W: 0.6.0 single-profile regression (run after Part P)

Re-run the 0.6.0 gate (`../0.6.0/e2e.md`, Part W: W1-W7) **with a single connected
profile** to prove the multi-connection registry rework did not regress
single-profile window/tab targeting: W1 awareness/list, W2 per-op target context,
W3 loud `target_lost`, W4 fresh-nav self-heal, W5 switch without focus steal, W6
user-context safety, W7 WSL parity. Pass = same as 0.6.0 (every outcome confirmed
from the stream, `target_lost` terminal + recoverable, self-heal lands without
`force`). A spot-check of the 0.5.0 Part T / 0.4.0 Part A interaction ops is
sufficient if W1-W7 are clean, since 0.6.1 touches the transport/registry, not the
DOM/CDP op paths.

## Part I: multi-instance isolation (issue #26, run after Part W)

Two cua processes on one machine must not clobber each other's browser tier. Give
each cua instance AND the Chrome that hosts its extension a distinct
`VADGR_CUA_BROWSER_DISCOVERY` (on WSL also `VADGR_CUA_BROWSER_DISCOVERY_WINDOWS` for
the Windows-side copy).

- **I1 Coexistence (no clobber).** Start instance A (discovery path A) and bond its
  Chrome; `browser(op="status")` -> `connected: true`. Start instance B (discovery
  path B) and bond a second Chrome; B `status` -> `connected: true`. Instance A's
  browser ops must STILL work afterward (a `tabs(list)` / `navigate` on A succeeds) —
  B starting no longer kills A's browser tier, because each wrote its own discovery
  file instead of clobbering the one per-user path.
- **I2 Default path unchanged (back-compat).** With no env set, a single instance uses
  the per-user default discovery file exactly as before.

Note: **pixel / desktop-tier (Tier 2) contention is OUT of scope here.** The shared
screen + input cannot serve two agents at once; that single-owner-per-display lock is
tracked separately (the desktop-lock issue) and is future work. #26 makes instances
coexist; the browser tier is isolatable, so concurrent browser agents are safe.

## Automated gate (green on the PR branch — necessary, not sufficient)

Run before any live e2e; this is what the PR branch was validated against:

- `pytest computer_use/tests -q` — cua-side unit suite (the multi-connection
  registry keeps N connections + routes to `current`; the resolution ladder
  including the terminal `profile_ambiguous` that lists the profiles;
  `profiles(list/use)` params + returns; `use_target(profile_id)` selection;
  status grows the `profiles` array; back-compat missing `profile_id` -> `default`;
  NO `PROTOCOL_VERSION` change; `op_unsupported` for an extension lacking
  `profiles`; the tool count is now 26; and the #26 discovery-path env override
  (`resolve_discovery_path` honors `VADGR_CUA_BROWSER_DISCOVERY`, `ensure_server`
  writes to it) so concurrent instances get their own file). One pre-existing failure,
  `test_wlroots_uinput_when_writable`, also fails on clean `master` (desktop
  uinput, unrelated to the browser tier) and is ignored.
- `cd extension && npm test` — extension unit suite (`profile.test.ts`,
  `profiles_op.test.ts`: the per-profile UUID is minted once + stable across
  reloads via a storage.local fake, `hello` carries `profile_id` + context, the
  SW-resolved `profiles` handler; plus the full 0.6.0 suite unchanged).
- `npm run build` — must pass the content-script IIFE guard.
- `npm run typecheck` — `tsc --noEmit` clean.

## Per-OS results

Fill these in by running the runbook on each OS. Record the specific OS + Chrome
version in the status note so a future regression reproduces on the same build.

Legend: pass / fail / blocked (login or anti-bot) / not run

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part P (P1-P6) | not run | not run | not run | **P1-P3/P6 pass; P4/P5 pending** |
| Part I (I1-I2 multi-instance) | not run | not run | not run | **pass (transport)** |
| Part W (W1-W7 regression) | not run | not run | not run | **pass (full W1-W7)** |
| Overall | not run | not run | not run | **in progress; 1 finding fixed (re-verify pending)** |

**Live e2e for 0.6.1 is run on WSL only.** 0.6.1 is purely browser-tier — the
multi-connection registry, the profile handshake, and the discovery-file env
override are pure Python + a pure extension handshake with no filesystem/path
boundary, so Linux / macOS / Windows-native behave identically. WSL is the parity
boundary that actually exercises the multiplexed connections and the discovery
override across the bridge on real hardware, so the live round is WSL; the other OSes
rely on the OS-agnostic argument plus the automated gate. The live run needs the
extension loaded in two real Chrome profiles (Part P) and two cua instances (Part I),
so it is a human round. `P6` / `W7` (WSL parity) are N/A on non-WSL OSes. The
automated gate (`pytest` / `vitest` / `npm run build` / `npm run typecheck`) is green
on the PR branch — that is the bar this change was held to before the hardware round.

Status notes:
- **WSL (2026-07-17): full Part W + Part I run; one finding fixed.**
  - **Part I (multi-instance #26) pass (transport level).** I2: the running cua with no
    env writes the default `~/.vadgr-cua/browser.port`; I1: two cua instances with
    distinct `VADGR_CUA_BROWSER_DISCOVERY` write their own files with no clobber and the
    default untouched (exercised against the real `resolve_discovery_path` /
    `write_discovery`). The full two-*browser* coexistence is 0.6.2 (launch capability).
  - **Part W (W1-W7) pass — full gate, not a spot-check.** In a selected profile: W1
    awareness/list, W2 per-op target, W3 loud `target_lost`, W4 fresh-nav self-heal, W5
    switch without focus steal, W6 user-context safety (refused to close a user tab
    without `force`), W7 WSL parity (inherent). No regression from the registry rework.
  - **FINDING (fixed) — `profiles(list)` returned a stale `hello` snapshot.** After
    closing a profile's window, `profiles(list)` still reported its old `window_count` +
    tabs. Root cause: the recognition context was captured once in the `hello` handshake
    and cua returned it cached (`bridge.py` `_profile_list`); it never re-queried the live
    browser. Fix (`701ab92`, cua-side only): `profiles(list)` now re-queries each
    connected extension (its `profiles` op returns a live `buildProfileContext()`) and
    refreshes the cache; an unreachable session keeps its last-known value so the list
    never fails. Unit tests added (`test_browser_bridge.py`). **End-to-end re-verify
    pending** a cua restart (Python change): after restart, close a window and confirm
    `profiles(list)` reflects the new count.
  - **Remaining on WSL:** P4 (`CUA_BROWSER_PROFILE` env pin), P5 (single-profile
    back-compat), and the finding's e2e re-verify.
- **WSL (2026-07-15): Part P + Part W pass.** WSL2 Ubuntu 24.04.4 LTS, cua-in-WSL
  driving Windows Chrome over the bridge; the extension rebuilt on the Windows side
  (0.6.1 `dist`) and loaded in **two** Chrome profiles. Driven op-by-op through the
  orchestrator's live cua connection.
  - **P1 awareness/list** — `profiles(list)` returned both connected profiles with
    recognizable context: `cd17…` (chrome, 5 windows / 28 tabs — Slack/Zoom/Annotation/
    Claude Code) and `7abc…` (chrome, 1 window / 3 tabs — Outlier/Extensions).
  - **P2 loud ambiguity** — with both connected and none selected, `status.reason` =
    `profile_ambiguous` (the tier refuses to guess; the same doctrine as `target_lost`).
  - **P3 select and isolate** — `profiles(use 7abc…)` -> `is_current:true`; `tabs(list)`
    then showed ONLY that profile's single window (profile `cd17…`'s 5 windows were not
    visible). Opened an owned window + `navigate /login` + `fill` there; switching to
    `cd17…` and `windows(list)` showed its 5 original windows and **not** the owned
    window created in `7abc…` — the other profile was provably untouched. Then drove
    `cd17…` (the work profile): owned window -> GitHub -> repo name "vadgr-computer-use"
    (the motivating task). Bidirectional selection, each profile isolated.
  - **P6 WSL parity** — the entire run was cua-in-WSL -> Windows Chrome over the bridge;
    both profile connections and every op round-tripped intact on real hardware.
  - **P4 (`CUA_BROWSER_PROFILE` env pin) / P5 (single-profile back-compat)** — not run
    live (need a cua restart with the env / a single-profile config); covered by the
    unit suite.
  - **Part W regression (spot-check)** — inside a selected profile, navigate / query /
    fill / use_target / tabs / windows all clean; **W4 self-heal** (immediate `fill` on a
    fresh `navigate`, no `force`) and **W3 loud `target_lost`** (close current -> terminal
    `target_lost` + remediation) both held. The multi-connection registry rework did not
    regress 0.6.0 single-profile targeting.
  - **Part I (multi-instance #26)** — not run live: it needs two separate Chrome
    *instances* (distinct `--user-data-dir`, each with its own `VADGR_CUA_BROWSER_DISCOVERY`)
    and two cua servers, since profiles of one Chrome share the browser process and bond
    to one cua. Covered by the unit suite (`resolve_discovery_path` honors the env,
    `ensure_server` writes to it); the live two-instance run is an optional heavier setup.
- Linux / macOS / Windows-native: not run — 0.6.1 is OS-agnostic browser-tier (pure
  Python + a pure extension handshake, no path boundary), so WSL is the parity boundary;
  the others rely on that argument plus the green automated gate.
