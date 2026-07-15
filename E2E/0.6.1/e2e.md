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

## Automated gate (green on the PR branch — necessary, not sufficient)

Run before any live e2e; this is what the PR branch was validated against:

- `pytest computer_use/tests -q` — cua-side unit suite (the multi-connection
  registry keeps N connections + routes to `current`; the resolution ladder
  including the terminal `profile_ambiguous` that lists the profiles;
  `profiles(list/use)` params + returns; `use_target(profile_id)` selection;
  status grows the `profiles` array; back-compat missing `profile_id` -> `default`;
  NO `PROTOCOL_VERSION` change; `op_unsupported` for an extension lacking
  `profiles`; the tool count is now 26). One pre-existing failure,
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
| Part P (P1-P6) | not run | not run | not run | not run |
| Part W (W1-W7 regression) | not run | not run | not run | not run |
| Overall | not run | not run | not run | not run |

Every row is **not run (pending the per-OS verification round)**: the live
multi-profile run needs the extension loaded in two real Chrome profiles and is a
human round. `P6` (WSL parity) is N/A on non-WSL OSes; `W7` likewise. The
automated gate (`pytest` / `vitest` / `npm run build` / `npm run typecheck`) is
green on the PR branch — that is the bar this change was held to before the
hardware round.

Status notes:
- _(pending the per-OS verification round — no live run recorded yet.)_
