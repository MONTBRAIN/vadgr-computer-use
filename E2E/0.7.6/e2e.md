# 0.7.6 - browser reliability and human-paced typing: e2e runbook

> **vadgr-computer-use 0.7.6 implementation:**
> [implementation PR #93](https://github.com/MONTBRAIN/vadgr-computer-use/pull/93).
> **vadgr-computer-use 0.7.6 evidence PR:**
> private evidence PR #143.

Read this file and [`../README.md`](../README.md) completely before any live
cell. Build the exact branch-head wheel. Install it without editable mode in a
fresh environment outside the checkout. Install the matching unpacked extension
from this branch. The MCP configuration must call that environment's
`vadgr-cua` executable.

## The rules

1. Run the owner-dependent cells before unattended cells.
2. Run each host pass to a verdict without stopping for a progress report.
3. Reproduce each failure, fix it with a regression test, rebuild, then rerun
   every affected cell.
4. A mutation passes only after a structured read-back confirms its result.
5. File raw evidence while each group runs. Never reconstruct it later.
6. Never put typed text, credentials, field values, or the parent `.env` in
   evidence, Git, logs, screenshots, commands, or GitHub text.
7. Change no host DNS, firewall, proxy, VPN, route, adapter, or network service.
8. Give every cell a verdict and a reason for `blocked`, `not run`, or
   `Not-Needed`.
9. Confirm evidence is committed and pushed before cleanup. Stop only processes
   started by this pass and remove only validated isolated test roots.
10. Before a pixel or screenshot group, check current official capabilities
    and authenticated availability. Use GPT-5.6 Sol at medium reasoning with
    Codex or the current Claude Opus at medium reasoning with Claude Code.
    Choose between those
    qualified subscription paths using availability and task fit. Do
    not substitute Terra, Sonnet or Gemini. Record the exact model, reasoning
    level and sources. A higher reasoning level
    requires a recorded medium-tier capability failure and owner approval.
11. Every remaining browser-tier cell uses a versioned Chrome for Testing
    executable, a fresh isolated profile, and the matching development
    extension. Never attach to the owner's normal browser process or profile.
12. Until the Vadgr-native E2E harness is production-ready, every live agent
    task uses the CLI's existing interactive login and permission bypass. Do not
    require, read, export, or pass an OpenAI or Anthropic API key solely to drive
    this e2e. Start each task with `codex --yolo exec --json` or Claude Code with
    `--dangerously-skip-permissions`. The bypass prevents unattended approval
    stalls. It does not broaden a cell, authorize destructive work, waive an
    owner-dependent action, change the qualified model, or replace evidence and
    cleanup.
13. These CUA drivers use the owner's subscriptions, not API billing. Do not
    impose API-price-equivalent dollar or token ceilings or stop to request a
    higher ceiling. Record actual usage when available. Real account limits
    remain; do not enable paid extra usage or switch to API billing without
    explicit owner approval.

## Owner and environment requirements

Tell the owner about these requirements before the affected group starts.

| requirement | cells | owner action |
|---|---|---|
| Linux, native Windows, macOS, and WSL hosts | all OS rows | Provide one real interactive session on each host |
| Chrome for Testing with developer mode | A01-A04, B01-B17, C01-C07, E02 browser path | Approve the unpacked development extension only if the isolated browser asks |
| Browser restart and extension disable permission | A03-A04, B09 | Approve only the named browser action |
| Host suspend and resume | A02 | Resume the host if automation cannot do so safely |
| Native input permission | D01-D07 where applicable, E02 pixel path | Grant only the normal OS accessibility or input permission |
| Stock plain-text editor | D01-D07 where applicable, E02 pixel path | Keep Windows Notepad, macOS TextEdit, or the host's stock Linux text editor available; install no editor solely for these cells |
| Windows browser reachable from native Windows and WSL | B02a-B02f, B11-B17 | Keep both clients available during the convergence and lifecycle cells; provide hosts already configured for NAT and mirrored networking |
| Subscription-authenticated agent CLI | all agent-driven cells | Keep one supported Claude or Codex subscription login available; no provider API key is required; do not enable paid extra usage |

No product account or external test-site login is required. The visual driver
uses the separately declared subscription-authenticated agent CLI and model. The
harness serves a local instrumented page. The pass changes browser test state
and creates isolated temporary roots. It does not change host network state or
privacy settings.

## Subscription driver model selection

Recheck the [OpenAI models][models] and [Anthropic models][claude-models] pages
on the execution day. Do not reuse the superseded Terra/Sonnet comparison from
the interrupted 2026-09-05 attempt.

| cells | provider/auth | required capabilities | selected model | usage limits | escalation |
|---|---|---|---|---|---|
| all agent-driven cells | existing Codex or Claude Code subscription login | image-result continuation and MCP tools for visual cells | GPT-5.6 Sol or current Claude Opus, medium reasoning | real account limits only; no synthetic API budget | Do not change the qualified model or reasoning level without a recorded failure and owner approval. No API-key fallback or paid extra usage. |

The Linux pass rechecked the official OpenAI and Anthropic capability and
pricing pages on 2026-09-07. GPT-5.6 Sol supports image input and tools. Its
comparison rates are USD 4 per million input tokens, USD 0.40 per million
cached input tokens, and USD 20 per million output tokens. Those historical
comparison figures are not a bill or a stopping rule for subscription runs.
The owner clarified the CUA-only subscription rule on 2026-09-08. It supersedes
the former USD 4 and USD 10 API-price-equivalent ceilings. Existing raw usage
records remain historical evidence; they do not block remaining cells.

[models]: https://developers.openai.com/api/docs/models
[openai-pricing]: https://developers.openai.com/api/docs/pricing
[claude-models]: https://platform.claude.com/docs/en/models/overview
[claude-pricing]: https://platform.claude.com/docs/en/about-claude/pricing

## Paired surfaces this pass depends on

| repository | released surface | use in this pass |
|---|---|---|
| none | not applicable | This runtime is installed and driven through its own entry point |

## Setup and identity

Record the host OS, branch, exact commit, wheel SHA-256, installed distribution
version, resolved `vadgr-cua` path, extension version, browser version, agent CLI
and CLI version. Use a unique temporary root and evidence directory per host.
Run the secret, attribution, style, branch-point, unit, extension, build, clean
install, and diff checks before the live pass.

The committed harness must start the local instrumented page and capture each
MCP client's JSON stream. Helpers prepare state and capture output. They never
drive product operations or decide a verdict.

### Browser isolation for remaining hosts

Linux, native Windows, and macOS must use Chrome for Testing from the
[official versioned downloads][chrome-for-testing-downloads] for every browser
cell. Record the exact executable path, version, download URL, archive hash,
process id, and profile path. A normal Chrome, Chromium, or Edge process is not
a fallback.

Create a fresh `--user-data-dir` below the host's isolated test root. Load only
the matching built `extension/dist` as an unpacked development extension. Do
not copy or reuse the owner's browser profile, cookies, sign-in, preferences,
or extensions. Do not enable browser sync.

On native Linux and macOS, keep the fresh profile below the isolated home at a
profile root that `vadgr-cua browser-setup` and setup diagnosis both support.
Use `$HOME/.config/google-chrome` on Linux and
`$HOME/Library/Application Support/Google/Chrome` on macOS. Pass that exact
path to Chrome for Testing with `--user-data-dir`. The executable remains the
versioned Chrome for Testing build. Run `vadgr-cua browser-setup` before Chrome
starts, then verify `browser(op='status')` reports `connected: true` before
A01. Windows continues to use its registered native host.

On macOS, also pass `--use-mock-keychain` to the isolated Chrome for Testing
process. Its fresh home has no login keychain. Without this test flag, a
`Keychain Not Found` dialog can block browser startup. Do not create or reset
an owner keychain for this pass. Chromium documents the flag in its
[macOS build instructions](https://chromium.googlesource.com/chromium/src/+/main/docs/mac_build_instructions.md).

C05 and C06 deliberately connect multiple agent sessions to the same isolated
Chrome for Testing extension bridge. No independent pass shares that process,
profile, debugging endpoint, or extension state. After evidence is committed
and pushed, stop only the recorded process and remove only its profile root.

The completed 2026-09-06 WSL pass predates this environment rule. Its observed
product results remain valid. Every later WSL rerun must use the Windows Chrome
for Testing build and the extension built in the Windows checkout.

[chrome-for-testing-downloads]: https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json

Start the loopback fixture with one host-specific ready file and capture its
sanitized request log:

```bash
python E2E/0.7.6/harness/server.py --ready-file "$E2E_READY_FILE"
```

Pipe each agent CLI JSONL stream through the ingestion redactor. When a cell
uses fixed test text, place it only in an untracked mode-0600 file under the
isolated test root and pass that file with `--sensitive-file`; never put the
text itself in the command or retained evidence.

```bash
python E2E/0.7.6/harness/redact_stream.py --output "$E2E_STREAM_FILE" \
  --sensitive-file "$E2E_SENSITIVE_FILE"
```

Every remaining host uses this temporary driver form for each live task:

```text
codex --yolo exec --json --model gpt-5.6-sol <MCP, working-directory and prompt options>
claude --dangerously-skip-permissions --print --output-format stream-json <MCP, working-directory and prompt options>
```

Use the CLI's existing interactive login. Do not inspect, source, export, or pass
`OPEN_AI_API_KEY` or `ANTHROPHIC_API_KEY` for the driver. If neither CLI has an
active login, mark the agent-driven cells `blocked: authenticated agent CLI
unavailable`. Do not convert an API key into a substitute login.

The command uses the selected medium reasoning model and invokes the exact
isolated-wheel `vadgr-cua` entry point. Run it from an isolated working
directory. Pipe its JSON stream through `redact_stream.py`. Record paths only in
owner-private local state, never in the public runbook or private evidence. The
unrestricted agent driver may perform ordinary in-scope local setup, such as
opening and focusing the stock editor, when a repository helper cannot. It must
still use public product tools for the action under test and capture the
independent oracle and cleanup.

## Part A: recovery and setup diagnosis

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| A01 | Extension connected; one owned target exists | Let or force the MV3 worker idle, then request a DOM read | One bounded recovery restores the bridge and the original read runs once | Client JSON, broker log without page data; restore normal worker state | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | pass: verified worker stop recovered once on the same target at a1c24f3 |
| A02 | A01 passed | Suspend and resume the host, then request one DOM read | The read succeeds after bounded recovery, or returns the named recovery timeout without duplicate dispatch | Client JSON and timestamps; no host setting change | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | blocked: no contemporaneous sleep/wake event was verified |
| A03 | Extension installed, then disabled | Request status and one read | The result says the extension is disabled and gives the matching remedy | Client JSON; re-enable the extension | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | pass: two immediate and two settled disabled reads returned the named error at a1c24f3 |
| A04 | Isolated native-host registration removed | Request status and one read | The result says the host is not installed and does not call it an idle worker | Client JSON and isolated registration listing; restore registration | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | pass: missing registration returned not_set_up; all three isolated manifests restored at a1c24f3 |

## Part B: shared broker and target ownership

For B06, a streaming CLI may finish the first claim before emitting the second
claim in the same message. That is not overlapping dispatch. The POSIX claim
barrier in `harness/README.md` can pause only the two exact installed MCP
children while the agent emits both public requests. Announce the temporary
pause first. Preserve both call timestamps, automatic resumes, real conflict
results and broker identity; a sequential attempt cannot receive a pass.

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| B01 | One profile; two independent MCP clients | Attach both clients and list profiles, windows, and tabs | Both remain connected through one broker and see one complete registry | Both JSON streams and broker identity | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | pass: two independent clients shared one broker and registry with caller-specific target labels |
| B02a | NAT host; WSL client starts before native Windows | Start both against the same Windows browser, then interleave separate owned-window mutations and reads | One Windows PID, process start, epoch, bundle hash, profile and registry; both read-backs are exact | Both streams, Windows listener and broker identity | Not-Needed: WSL always uses the stdio proxy; B02d covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02b | NAT host; native Windows client starts before WSL | Repeat B02a in the opposite startup order | Same B02a identity and routing oracle | Both streams, Windows listener and broker identity | Not-Needed: WSL always uses the stdio proxy; B02e covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02c | NAT host; neither client started | Start native Windows and WSL clients simultaneously, then repeat the B02a operations | The atomic Windows lock elects one winner and both clients converge on it | Both streams, winner identity and listener | Not-Needed: WSL always uses the stdio proxy; B02f covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02d | Mirrored host; WSL client starts before native Windows | Repeat B02a | Same B02a identity and routing oracle; WSL uses the stdio proxy, not shared localhost | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | pass: paired WSL proxy and native Windows converged on one complete broker identity | Not-Needed: no cross-OS seam |
| B02e | Mirrored host; native Windows client starts before WSL | Repeat B02b | Same B02b identity and routing oracle; WSL uses the stdio proxy | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B02f | Mirrored host; neither client started | Repeat B02c | Same B02c winner and routing oracle; WSL uses the stdio proxy | Both streams, winner identity and listener | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B03 | Two clients in one profile | Each creates an owned window and two tabs, then interleaves reads and mutations | Responses return only to the caller; each sees foreign targets as owned by another client | Both streams and page event records; close test windows | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | pass: owned windows retained separate leases, target labels and exact DOM hashes |
| B04 | B03 windows remain | Select a different current tab per client and interleave operations | Every request reaches its exact profile, window, and tab without cross-routing | Target ids and structured page records | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | not run: target-label repair rerun owed; prior functional observations retained | pass: interleaved tab operations retained each caller's selected target and exact read-back |
| B05 | One unowned tab in a shared user window | Client one claims the tab; client two reads it and attempts a window action | Client one can use tab-scoped DOM ops; client two receives `target_owned_by_another_client`; neither client changes window focus | Both streams and page record; release the tab | pass | pass: the foreign client received `target_owned_by_another_client` without focus change | pass | pass: foreign DOM access and shared-parent window claims and closes failed without mutation |
| B06 | Unowned tab and window targets | Race two clients for the tab, then race a window claim against a foreign child lease | One atomic winner exists; every loser gets the named conflict before dispatch | Both streams and lease revision record; release winner | pass | pass: each race had one winner and named conflicts for every loser | pass | pass: overlapping tab and window-versus-child claims produced one winner and one conflict |
| B07 | Owned window, child tabs, popup, and shared window | Open tabs with and without opener, a popup, and an unattributable shared-window child | Owned descendants inherit the correct lease; the unattributable shared child stays unowned | Registry snapshots; close created targets | pass | pass: attributable descendants inherited leases and the shared child stayed unowned | pass | pass: owned descendants and opener-linked children inherited leases; unattributable shared-window child stayed unowned |
| B08 | Client owns one tab and one multi-tab window | Release each, then dispatch with the old revision | Browser state stays open, leases clear, and stale revisions fail | Registry and page records; close created state | pass: rerun after repair | pass: releases kept resources open and stale dispatches failed | pass | pass: tab and window release preserved resources and rejected stale writes without mutation |
| B09 | Client owns targets; second client stays connected | Break the first socket, reconnect inside 30 seconds, then repeat after heartbeat and grace expiry | Timely reconnect restores state; expired leases become orphaned and are explicitly reclaimable | Streams and monotonic timing; release reclaimed state | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | pass: timely reconnect retained identity and leases; expired leases required explicit reclaim |
| B10 | Browser resources remain open | Restart only the broker | New epoch marks rediscovered targets orphaned; old secrets and revisions fail; URL and title do not restore identity | Before and after registry plus epoch; reclaim or close test state | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | pass: both stale clients returned target_lost without new windows; explicit reclaim restored exact targets |
| B11 | Windows and WSL clients share one broker | Exit only the WSL client, then operate from Windows | Windows continues through the same PID and epoch | Windows stream and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B12 | Windows and WSL clients share one broker | Exit only the Windows client, then operate from WSL | WSL continues through the proxy and the same Windows PID and epoch | WSL stream and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B13 | WSL client disconnected; Windows broker has a live Windows client or extension | Terminate only the test WSL distribution session | The Windows broker remains alive and usable | Windows process and operation read-back | pass: disposable distro stopped; native client kept the same broker | Not-Needed: no cross-OS seam | pass: a disposable distro stopped while the native client retained the same live broker PID, start identity, epoch, and bundle hash | Not-Needed: no cross-OS seam |
| B14 | Fresh verified bundle and endpoint | Corrupt isolated copies of the endpoint token and bundle | Bad authentication is refused and altered payload fails before execution | Named errors and unchanged live bundle hash; delete isolated copies | pass | Not-Needed: Windows-only packaging seam | pass: bad authentication was refused and an isolated tampered bundle was rejected before execution | Not-Needed: Windows-only packaging seam |
| B15 | Broker running with owned resources | Terminate only that broker process and reconnect both clients | One new Windows PID and epoch appear; rediscovered leases are orphaned | Before/after identity and registry | not run: rerun the setup-diagnosis repair; prior observation retained | Not-Needed: no cross-OS seam | not run: rerun the setup-diagnosis repair; prior observation retained | Not-Needed: no cross-OS seam |
| B16 | Isolated stale and corrupt endpoint copies | Start both clients through the normal launcher | Startup rejects corrupt identity and safely recovers stale state without trusting its token | Named result, one Windows process and clean identity | pass | Not-Needed: Windows-only packaging seam | pass: corrupt identity was rejected and stale state safely replaced | Not-Needed: Windows-only packaging seam |
| B17 | Isolated WSL environment with Windows interop unavailable | Request browser status | A named interop remedy returns and no Linux/WSL broker starts | Error stream and process listing | pass: rerun after repair | Not-Needed: WSL-only negative seam | Not-Needed: proved by paired WSL row | Not-Needed: WSL-only negative seam |

## Part C: composed-tree actionability and browser typing

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| C01 | Owned target on the harness page | Click and type through one and nested open shadow roots | Each mutation succeeds and the DOM event record confirms the exact target and value | Client JSON and redacted event metadata; clear fields | pass | pass: document and nested-shadow actions produced exact event and value hashes | pass | pass: exact plain and nested-shadow hashes and event records at a1c24f3 |
| C02 | C01 targets covered by document and nested-shadow overlays | Repeat click and type | Each action fails as covered and no page state changes | Error results and unchanged DOM record; remove overlays | pass | pass: both covered actions failed twice without state mutation | pass | pass: eight covered-action errors with unchanged independent hashes and event counts |
| C03 | Instrumented plain field | Run `fill`, fast `type`, and default-profile `type(human=true)` | Fill and fast type keep bulk behavior; human type emits ordered page events with varied intervals and exact read-back; evidence makes no `isTrusted` claim | Event kinds, trust flags, intervals, counts, and hashes only; never field text | pass: all three exact hashes matched; human input produced 54 distinct intervals | pass: fill, fast and fitted human paths produced exact independent read-backs; human input used 69 distinct intervals | pass: bulk and human paths produced exact read-backs with redacted timing evidence | pass: bulk and human inputs had exact read-backs; 61 human units and 37 distinct intervals |
| C03b | Instrumented field and event clock; text contains ordinary spaces plus clause, sentence, newline, and paragraph boundaries | Run long default-profile input and custom inputs at 10 and 200 WPM with IKI-CV 0 and 1 | Ordinary spaces add no separate pause; intervals show varied local runs without exact-message normalization; every read-back is exact; metadata reports the requested mode and realized rate | Redacted event timing and boundary-class records, batch rate summary, option metadata, and value hash; clear the field | pass: exact default and endpoint inputs; tracked multiline addendum covered newline and paragraph boundaries | pass: exact default, endpoint and multiline read-backs covered every boundary class and both IKI-CV endpoints | pass: exact default, endpoint and multiline boundary read-backs | pass: exact default and endpoint inputs; full gap vector and newline addendum covered every boundary class |
| C04 | Debounce, typeahead, validation, counter, Unicode, timeout, cancellation, mismatch and client-exit controls | While a second client uses another window, complete a plan longer than 60 seconds with no timeout, then drive invalid input, explicit preflight and runtime deadlines, cancellation, mismatch and client EOF | Healthy long input completes while the other client stays responsive; invalid and preflight-deadline cases mutate nothing; runtime deadline, cancellation and EOF stop at the confirmed prefix and skip submit; fallback is counted; mismatch and uncertain dispatch never replay input | Both streams and redacted event metadata; reset page | pass: concurrent long inputs, both deadlines, cancellation, mismatch, client EOF and fresh streams observed | pass: concurrent long input, invalid input, both deadlines, cancellation, mismatch and client EOF produced the required exact or prefix oracles | pass: long input, invalid input, deadlines, cancellation, mismatch and client EOF produced the required exact-prefix oracles | pass: concurrent long input, invalid input, deadlines, cancellation, mismatch and client exit retained exact or stable prefixes without submit |
| C05 | Owned unfocused window with one selected decoy tab and an exact leased harness tab where `focused=false`, `active=false`, and `is_current=true` | Without `tabs.switch` or `windows.focus`, run `wait_for`, `query`, `read_text`, `get_attribute`, DOM `click`, fast and human `type`, `fill`, `select`, `scroll`, `element_state`, `clear` and `get_value` against the leased tab | Each content operation reaches only the exact leased tab; paced typing has exact read-back; state remains false/false/true; the decoy is unchanged | Both tab states before and after, redacted event metadata and decoy hash; reset the harness and close only the owned window | pass: every content operation reached the leased inactive tab; the decoy stayed unchanged | pass: all 15 content operations reached only the leased inactive tab and preserved false/false/true | pass | pass: every content operation reached the exact inactive leased tab; target state and decoys stayed unchanged |
| C06 | C05 state plus state-bearing pointer, reveal, focus, file-input, dialog and semantic controls | Run trusted `click`, `hover`, `focus`, `blur`, `upload`, `snapshot`, `accessibility_tree`, `eval`, navigation, reload, back and forward; arm the dialog on the leased tab while a decoy target also emits one | Every operation reaches the leased tab, carries an independent state/read-back oracle, ignores the decoy dialog and preserves false/false/true; cookie operations are excluded because they are profile/origin scoped | Before/after target state, state-bearing results, temporary upload hash and decoy hash; remove the temporary file and close only the owned window | pass | pass: all 14 state-bearing operations and independent dialog routing preserved false/false/true and the unchanged decoy | pass | pass: state-bearing operations and decoy-first dialog routing preserved the inactive leased target |
| C07 | C05 state, then separate discarded, frozen, browser-internal, Web Store and denied-file targets. Launch pinned isolated Chrome for Testing with `--remote-debugging-port=0`, enable its internal debugging pages, and use `harness/lifecycle_control.py` to establish and verify the exact lifecycle rows. | Call trusted `press` on the inactive harness and one page operation on each unavailable target; do not activate any target | `press` returns `inactive_tab_trusted_keyboard_unsupported`; unavailable targets return `target_discarded`, `target_frozen` or `target_restricted`; no action reports success, mutates a decoy, switches a tab or focuses a window | Exact Chrome version, DevTools protocol support, helper output, error codes and target state before/after; close only owned test windows and the isolated Chrome root | pass | pass: the inactive press and five unavailable targets returned the exact required errors without activation, focus change or mutation | pass | pass: all six named negative results preserved inactive target and decoy state; helper tabs closed |

## Part D: pixel typing

Use the operating system's stock plain-text editor for every cell in this part:
Windows Notepad on Windows and WSL, TextEdit in plain-text mode on macOS, and
the available stock plain-text editor on Linux. Use a fresh document and the
public pixel tools. Do not substitute a custom event recorder, test GUI, browser
field, or repository helper for the editor. Take one pixel screenshot before
typing and one after typing. The after screenshot must visibly confirm the
mutation. Use the returned typing metadata for timing assertions.

On macOS, save each new empty plain-text document to a unique file inside the
isolated root before input. Verify its exact path and empty state. This is the
macOS exception to the unsaved-document setup below: TextEdit can autosave an
untitled document into the owner's default cloud folder. Do not change editor
or cloud preferences. Keep only the test file for isolated-root cleanup. On
other operating systems, keep the fresh document unsaved as before.

For a POSIX D04 runtime-deadline scheduling fault, use the exact-process
`harness/pause_mcp.py` setup described in the harness README. Announce the
temporary installed-MCP pause first. Confirm actual input before the pause,
retain the independent watchdog's resumed event, and verify the deadline and
stable prefix through the agent. Never substitute a preflight refusal.

On WSL, invoke the committed foreground helper through a process-only execution
policy override; it does not change the host policy:

```bash
FOCUS_SCRIPT=$(wslpath -w E2E/0.7.6/harness/focus_window.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$FOCUS_SCRIPT" \
  -ExactTitle "$TEST_TITLE"
```

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| D01 | Fresh stock-editor document focused. On WSL, use `harness/focus_window.ps1 -ExactTitle` to verify the exact non-minimized Notepad window is foreground. | Run fast `type_text` and named-profile human `type_text` in separate fresh documents | Fast mode stays compatible; human metadata names the profile and reports complete varied input; each after screenshot visibly confirms the mutation | Redacted agent JSON with before and after screenshot results; close the test documents without saving | pass: Notepad fast mode completed 93 units in 0.107 seconds; profile mode completed 314 units in 53.563 seconds | pass: gedit completed 93 fast units and 314 fitted-profile units with visible read-back | pass | pass: b208cf7 completed 40 fast and 40 profile units with exact native hashes and released modifiers |
| D01a | Fresh unsaved stock-editor document. Use Notepad on Windows and WSL, TextEdit in plain-text mode on macOS, and the available stock plain-text editor on Linux. Verify the exact non-minimized editor window is foreground. | Through the agent and public pixel tools, type the fixed sensitive-file value with `type_text(human=true)` and no timing override | Metadata names `us_adult_transcription_2026`, nominal WPM 68, all units complete and no unexpected fallback; the after screenshot visibly confirms the mutation; no browser or structured typing path is used | Redacted agent JSON, foreground identity, timing metadata, and before and after screenshot results; close without saving | pass: GPT-5.6 Sol medium completed 240 units in 38.729 seconds and produced the stronger saved-file hash oracle | pass: GPT-5.6 Sol medium completed 240 public pixel units in 42.309 seconds with zero fallback | pass: GPT-5.6 Sol medium completed the public pixel mutation and independent read-back | pass: b208cf7 completed all 505 default-profile units in 95.628 seconds with exact native hash and released modifiers |
| D02 | Fresh stock-editor document focused | Run custom WPM plus IKI-CV at both accepted endpoints in separate documents | Planned and achieved metadata are valid; IKI-CV zero removes marginal spread while the shared rank chain remains; each after screenshot visibly confirms the mutation | Redacted timing metadata and before and after screenshot results; close without saving | pass: Notepad completed the 10 WPM and 200 WPM endpoint plans in 15.112 and 2.075 seconds | pass: gedit completed the 10 and 200 WPM endpoint plans with visible read-back | pass: both endpoint mutations completed with visible read-back; public metadata does not expose internal rank fields | pass: 10 and 200 WPM endpoints completed in 13.233 and 2.101 seconds with exact hashes and released modifiers |
| D02b | Fresh stock-editor document focused; text contains ordinary spaces and every semantic-boundary class | Run default and custom human input in separate documents | Metadata reports each requested mode; each after screenshot visibly confirms the mutation; browser cell C03b retains the independent boundary-timing oracle | Redacted metadata, boundary counts, and before and after screenshot results; close without saving | pass: Notepad completed 353-unit default and 90 WPM multiline inputs in 62.678 and 45.032 seconds | pass: gedit completed 408-unit default and 156-unit custom multiline inputs with every boundary class visible | pass | pass: full 505-unit default and custom multiline inputs retained exact hashes and released modifiers |
| D03 | Fresh empty stock-editor document focused | Try incomplete or mixed timing options, IKI-CV below 0 or above 1, and a deadline shorter than the plan | Each fails before input and leaves the document visibly empty | Error results and before and after screenshot results | pass: seven invalid or preflight-deadline requests failed before input; the document remained empty | pass: seven invalid or preflight requests completed zero units and left gedit visibly empty | pass | pass: nine actual error results each retained an independently verified empty document and released modifiers |
| D04 | Fresh stock-editor document focused | Complete a plan longer than 60 seconds without a timeout, then exercise runtime deadline, cancellation and combining-mark or joined-emoji grapheme fallback in fresh documents | Long input completes; deadline and cancellation report a truthful prefix; modifiers are released; each grapheme stays whole; the after screenshot confirms visible input or the named fallback is reported; no whole-string retry or submit occurs after interruption | Redacted agent JSON with before and after screenshot results; release keys and close without saving | pass: Notepad completed 614 units in 100.634 seconds and the Unicode path named four fallbacks; prior runtime-deadline and cancellation evidence remains valid | pass: gedit completed 500 units in 77.395 seconds; deadline and cancellation kept exact prefixes; six graphemes stayed whole with six named fallbacks | pass: the installed wheel completed 980 units in 160.907 seconds; the repaired Unicode path preserved seven graphemes and named four fallbacks; prior runtime-deadline and cancellation evidence remains valid | partial: long input, runtime deadline and cancellation prefixes observed with released modifiers; Unicode truncation reproduced twice, corrected-artifact rerun owed |
| D05 | Human pixel typing active in one fresh stock-editor document | Start a second pixel keyboard action against the same document | The product makes no parallel-safety claim; evidence records machine-global serialization or conflict behavior exactly | Both streams and before and after screenshot results; stop both operations, release keys, and close without saving | pass: synchronized Notepad clients overlapped and completed 314 and 228 units | pass: independent clients showed both interleaving and repeatable one-client portal conflict; no parallel-safety claim made | pass: two synchronized clients completed; evidence records the observed interleaving without a parallel-safety claim | pass: overlapping installed clients interleaved 200 human and 41 fast units; exact multiset and released modifiers observed without a parallel-safety claim |
| D06 | macOS only: fresh empty plain-text TextEdit file inside the isolated root, exact window focused and modifiers released | Through public pixel tools, seed ASCII with fast `type_text`, select all with `key_press` Cmd+A, then type a lowercase marker with public `type_text` | Independent exact-document count and hash match only the marker; all modifier flags and native modifier key states are released after the chord and after typing; public before/after screenshots confirm replacement | Redacted public tool stream, exact document identity, count/hash and modifier observations; close only the test document and remove its validated isolated file during cleanup | Not-Needed: macOS-only keyboard-source repair | Not-Needed: macOS-only keyboard-source repair | Not-Needed: macOS-only keyboard-source repair | pass: public Cmd+A replaced the seed with the exact 27-unit marker; native modifier states stayed released |
| D07 | macOS only: fresh empty plain-text TextEdit file inside the isolated root, exact window focused and modifiers released; fixture contains supplementary characters, emoji modifiers, regional indicators and joined emoji | Through the installed public pixel `type_text` tool, type the fixture with human=false | Independent exact-document UTF-8 byte hash, code-point count and UTF-16 unit count match the entire fixture; no supplementary character is truncated; native modifier flags and key states remain released; public before/after screenshots confirm visible input | Redacted public results, exact document identity, expected/actual counts and hashes, native modifier observations and screenshots; close only the test document and remove its validated isolated file during cleanup | Not-Needed: macOS-only native Unicode-length repair | Not-Needed: macOS-only native Unicode-length repair | Not-Needed: macOS-only native Unicode-length repair | not run: fast supplementary-character consumer requires the corrected installed artifact |

## Part E: packaged and clean delivery

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| E01 | Fresh environment outside checkout | Install only the built wheel and start `vadgr-cua` through its entry point | Version is 0.7.6, readiness succeeds, the Unicode segmenter and fitted profile load, and source checkout is absent from import paths | Install log, path, version, wheel hash; remove environment | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: rerun the setup-diagnosis repair; prior observation retained | not run: installed identity rerun owed after the macOS UTF-16 length repair; b208cf7 clean-install observation retained |
| E02 | Matching store-equivalent extension and installed wheel. WSL uses D01's exact stock-editor setup before the pixel action. | Run one owned-window browser read, one human browser type longer than 60 seconds, and one human pixel type longer than 60 seconds | The installed package and matching extension execute the fitted cadence and long typing without an implicit total deadline | MCP JSON with input text removed plus before and after screenshot results for the pixel document; close without saving | pass: installed-wheel browser evidence retained 74 completed calls; Notepad completed 588 units in 101.429 seconds | pass: the installed wheel completed 520 browser units in 89.730 seconds and 520 gedit units in 88.632 seconds without an implicit deadline | pass: the installed wheel completed a 980-unit browser type in 149.8 seconds and a 980-unit Notepad type in 164.719 seconds without an implicit deadline | pass: browser long-input proof retained; b208cf7 completed 505 pixel units in 95.628 seconds with exact read-back and no implicit deadline |

## Per-OS results

| part | WSL | Linux | Windows | macOS |
|---|---|---|---|---|
| A: recovery and setup diagnosis | incomplete: rerun A01-A04 after the setup-diagnosis repair | incomplete: rerun A01-A04 after the setup-diagnosis repair | incomplete: rerun A01-A04 after the setup-diagnosis repair | partial: A01, A03 and A04 passed on the repaired wheel; coordinated sleep/wake remains |
| B: shared broker and target ownership | incomplete: rerun B09, B10 and B15 after the repair | incomplete: rerun B09 and B10 after the repair | incomplete: rerun B09, B10 and B15 after the repair | pass: all applicable ownership, race, reconnect and restart cells observed |
| C: actionability and browser typing | pass | pass | pass | pass: exact state, cadence, interruption and inactive-target oracles observed |
| D: pixel typing | pass | pass | pass | partial: D01-D03, D05 and D06 passed; D04 Unicode repair rerun and D07 fast Unicode remain |
| E: packaged and clean delivery | incomplete: E01 identity on the repaired package | incomplete: E01 identity on the repaired package | incomplete: E01 identity on the repaired package | partial: both long-input paths passed; UTF-16 repair installed identity remains owed |
| overall | incomplete: setup and recovery reruns remain | incomplete: setup and recovery reruns remain | incomplete: setup and recovery reruns remain | partial: A02 sleep/wake, D04 Unicode repair rerun, D07, installed identity and final cleanup remain |

## Evidence

Store raw boundaries only under
`e2e_evidence/vadgr-computer-use-0.7.6/<os>/`. Each host records identity,
automated gates, one directory per part, findings, reruns, cleanup, and a final
manifest of hashes. Strip input text and field values at capture time. Never
copy the workspace `.env` or a credential into the evidence root.

## Cleanup

Confirm every evidence boundary is committed and pushed. Stop only the broker,
browser test profile, page server, MCP clients, and agent CLI processes started
by this pass. Close only test windows and tabs. Remove only the recorded fresh
environment and temporary root. Preserve browser owner state and every unrelated
process. Run the build system's standard clean command. Record space before and
after cleanup.

## Findings

- Two independent macOS D04 attempts in fresh TextEdit windows returned seven
  completed units and four fallbacks but produced the same truncated output:
  25 UTF-8 bytes instead of 40. The native Unicode setter received Python
  code-point counts where Quartz requires UTF-16 array lengths. The repair
  supplies the correct length in both fast and human pixel typing. Eight
  supplementary-character regressions fail without it; BMP controls pass.
  D04 human Unicode, new D07 fast Unicode and E01 installed identity require
  the corrected artifact. ASCII/BMP observations from b208cf7 remain valid,
  including D01-D03, D05, D06 and E02 long input: their native lengths do not
  change. Browser behavior, modifier chords and other operating systems are
  unchanged by this length-only repair.
- A macOS pixel observation completed its input but left Shift held. The
  repair gives `_type_char` and `key_press` a private keyboard event source
  and balanced modifier release. D01-D05 and the E02 pixel leg require fresh
  macOS observations; E01 requires the repaired installed artifact. D06 covers
  the affected public modifier-chord consumer. Earlier observations remain
  recorded but do not prove the repaired keyboard source. Browser B/C results
  and the E02 browser leg remain valid. Other operating systems are unchanged.
- The macOS ownership audit twice found another client's selected tab in the
  top-level `tabs.list` target label. The per-tab current flags and subsequent
  content dispatch stayed client-specific. The repair rebuilds the label from
  the caller's exact selection and omits it when that selection is absent or
  missing. Registry visibility and lease authority are unchanged. Three
  regressions fail without the repair. B01, B03/B04 and B10 require fresh
  target-label observations on each host, plus E01 and applicable B15 bundle
  identity. Prior content, typing and lease observations remain evidence for
  those unchanged behaviors, not for the corrected label.
- The macOS B10 pass reproduced an implicit retarget after broker restart
  for two independent clients. Rejected reconnect credentials created a fresh
  client state, and the next content request silently opened a new window.
  The repair requires explicit target selection after a rejected reconnect.
  Content now returns `target_lost` before creating a window or dispatching.
  Fresh clients keep their normal default workspace. Two regressions fail
  without the repair. B09, B10, applicable B15 and packaged E01 require
  refreshed-artifact reruns on affected hosts; existing recovery reruns remain
  owed. Connected content and pixel operations are unchanged.
- The macOS A03 continuation reproduced an immediate-disable race twice.
  Status initially retained the previous session or said waking. The first
  read waited for recovery and returned `recovery_timed_out`; a later read
  correctly returned `extension_disabled`. The recovery loop checked terminal
  setup state only before waiting. The repair rechecks terminal diagnosis
  during bounded recovery without retargeting or replaying the operation.
  Six transition regressions fail without the repair. A01-A04, B09, B10,
  applicable B15 and packaged E01 need fresh-artifact reruns on affected hosts.
- A repaired-wheel macOS A01 attempt returned `extension_disabled` after a
  verified worker stop. The unchanged-wheel repeat recovered successfully;
  the live failure is intermittent. A separate preference-probe regression
  consistently showed that an enabled current Chromium profile, which omits
  the old `state` field, was classified as disabled. Four cases failed before
  the probe repair. The repair uses disable reasons when `state` is absent and
  preserves explicit legacy disabled states. A01-A04, B09, B10, applicable
  B15 and E01 require the new bundle and reruns on each affected host.
- The macOS pass found that a selected browser profile entered recovery before
  checking a known missing or disabled installation. Status returned the setup
  diagnosis, but the read returned `recovery_timed_out` with an unrelated
  remedy. The repair checks terminal setup states before transient recovery
  and preserves the selected target. Three regression cases fail without the
  repair and pass with it. This shared broker change requires a new Windows
  bundle and reruns of A01-A04, B09, B10, Windows/WSL B15 and packaged identity
  E01 on earlier hosts. Positive content and pixel paths are unchanged.
- The macOS A02 driver used an older sleep/wake pair when reporting its result.
  Those events predate this pass and do not prove the requested suspension.
  The same-target read succeeded, but A02 remains blocked until a coordinated
  attempt records contemporaneous power events. No second sleep request ran.
- The Linux VM save/resume rerun completed one DOM read on the same window,
  tab, and ownership revision. The first attempt returned an error whose text
  was fully redacted; its retained length does not establish an exact code or
  cause. Separately, a deterministic regression proved that resumed heartbeats
  left the client marked disconnected. The fix restores liveness under the
  broker lock. The regression fails without the fix and passes with it.
- The A02 driver used the fixed installed-wheel entry point but started from
  the checkout directory instead of the required isolated working directory.
  This is a driver-method defect, not a clean-install proof. The recorded
  installed broker bytes match the fix. The observation covers VirtualBox
  save/resume, not separate bare-metal sleep. The stream proves one high-level
  post-resume call; extension wire-dispatch counting was not captured.
- The heartbeat fix required a new Windows broker bundle. A native Windows CI
  runner rebuilt the archive, manifest, and SBOM from
  `bc079f27886beb196ff4869cbaa168ad64ca9c56`, using the pinned standalone
  Python archive, uv, and PyInstaller. The integrity and startup checks passed.
  The new archive SHA-256 is
  `d9713151b8ced7bfcaf0a78c7f542f271025b3f4ffb3fd67ab99e6f063372450`.
  Rerun A02 and B09 on previously passing Windows and WSL hosts, and verify
  E01 packaged identity before those cells. macOS still owes its native matrix.
- The native Windows pass first tested product commit
  `b87685b5e621265b7b67bbfe079b4951b561e4b8`. D04 and E02 tested final product
  commit `d8276071fcec953d5aeab43622fa7326fc4f1aca`. Its final isolated wheel has
  SHA-256 `b6e742516efe8d65a362dab698a74864b8cd8ef8c60016d511ef5900c00af28c`,
  and its embedded Windows broker bundle has SHA-256
  `576fdb332d0e8b8ec628de9b1c83a39df8a2eaac80c8c80ec23e850e3b77ca60`.
- The Windows pass found that the WSL launcher resolved the broker proxy from
  a path that did not exist in an installed wheel. The repaired launcher
  resolves and verifies the embedded proxy before starting it. B02d-B02f and
  B11-B16 then converged the WSL and native clients on one complete Windows
  broker identity.
- A broker restart discards extension-local ownership provenance. The repaired
  close path still requires the restarted broker to validate an explicit
  orphan reclaim, then lets the extension close that broker-authorized window.
  The regression test and live B10 and B15 reruns cover the repair.
- The native Linux C07 pass found that the lifecycle helper could inspect
  `chrome://chrome-urls` before its shadow DOM rendered. The repaired helper
  waits for the exact internal-debugging control for at most five seconds. The
  regression fails without the wait and passes with it. The clean C07 rerun
  returned every required inactive, discarded, frozen, and restricted error.
- The native Windows pass remains incomplete. A02 was not run because the owner
  prohibited sleep and power actions while away. B13 passed without disturbing
  the active owner distribution: the rerun imported and terminated only a
  disposable WSL 2 distribution, while the native client retained the same live
  broker PID, process-start identity, epoch, and bundle hash. The owner
  distribution remained running throughout.
- The owner approved D04 and E02 after the recorded Windows billing ceiling was
  reached. D04 and E02 passed through unrestricted Codex drivers. The drivers
  used the installed wheel, preserved unrelated windows, and retained redacted
  streams. Failed driver attempts contribute to no passing verdict.
- Native Windows human typing treated every fitted plan unit as one Unicode code
  point. A combining sequence or joined emoji therefore failed before input.
  The repaired backend emits a complete multi-code-point grapheme through the
  existing UTF-16 SendInput fallback. The regression suite and live D04 rerun
  passed with seven graphemes and four fallback units.
- After the WSL pass, the owner required Chrome for Testing for all later cua
  browser e2e. The remaining hosts use a fresh isolated profile and cannot
  fall back to an owner's normal browser. This environment rule changes no
  product code and does not invalidate the completed WSL observations.
- The first pixel matrix proved timing only in an instrumented field. D01a now
  also drives the stock editor on every affected OS and verifies its saved bytes
  independently. The WSL observation used GPT-5.6 Sol at medium reasoning,
  completed every functional oracle and now closes D01a under rule 10.
- A later GPT-5.6 Sol medium driver did not converge on a clean Notepad setup.
  The owner stopped it before typing. A Sol high retry was also stopped by the
  owner before product mutation because it violated the reasoning boundary.
  Both redacted streams remain rejected attempts and do not change D01a's
  earlier passing observation.
- The owner rejected the custom Windows Forms event recorder during the WSL
  rerun. Every new positive pixel observation now uses Windows Notepad. The
  ruling invalidated custom-field results that depended on a visible field. It
  did not invalidate D01a or earlier negative and interruption observations
  whose oracles did not depend on that field.
- The accepted GPT-5.6 Sol medium boundary used USD 3.085261 of API-list-price
  equivalent tokens and stayed below the USD 4 ceiling. Rejected attempts raised
  the complete rerun to USD 4.866510. The run used an authenticated Codex
  subscription, so these values do not measure an extra owner charge.
- A save-dialog attempt typed a path into Notepad and was stopped. It created no
  test file and contributes to no pass. The accepted stock-editor observations
  use screenshots and metadata only and leave the owner document unsaved.
- The new D04 short-timeout probes failed during preflight and are retained as
  redundant diagnostics. The already accepted runtime-deadline and cancellation
  observations remain applicable because the 68 WPM default change and editor
  ruling did not affect their interruption or prefix oracles.
- A01 first changed the selected client from its restarting profile to the one
  remaining profile. The resulting stale target failed as foreign ownership.
  The repaired broker keeps an explicit profile pinned during bounded MV3
  recovery. The final run used one DOM read on the same target.
- The final D05 cadence rerun observed two concurrent WSL pixel calls. They
  completed 269 and 266 units in 49.119 and 50.362 seconds. The field oracle
  recorded a 535-unit interleaved result. This release makes no parallel
  pixel-safety claim.
- A04 first returned `extension_disabled` after the real Windows registration
  was absent because the broker checked a separate manifest copy. The repaired
  broker reads the actual HKCU registration. The sealed rerun returned
  `not_set_up`, and both registry keys were restored.
- B02a-B02c specified a NAT variant that does not exist in the product. Every
  WSL client uses the same stdio proxy without a network-mode branch. B02d-B02f
  already pass the three startup orders, so the NAT duplicates are Not-Needed.
- WSL human browser typing initially returned `typing_mismatch` for plain and
  nested-shadow inputs. A later strict inactive-tab diagnostic proved that CDP
  keyboard input could pass on a selected background-window tab yet be
  discarded when the exact target tab itself was inactive. The repaired path
  sends each planned unit through that tab's content channel and verifies every
  intermediate value. A preliminary live rerun passed with `focused=false`,
  `active=false`, and `is_current=true`; the sealed C05 rerun now passes that
  boundary without activation.
- The typing-progress rerun removed the old whole-operation ceiling. Four
  concurrent browser clients completed 142 to 151 second inputs, and final-wheel
  browser and pixel inputs completed in 93 and 125 seconds. Explicit browser
  and pixel deadlines, cancellation and client EOF retained exact prefixes.
- The pixel cancellation rerun exposed a generic MCP error translation. The
  final repair maps runtime `TypingCancelled` and `TypingDeadlineExceeded`
  exceptions to their named public errors without changing the exact prefix.
- A D03 setup prompt incorrectly treated finite `iki_cv=1.1` as invalid. The
  design permits every finite non-negative coefficient. That mutation is a
  rejected driver result; the accepted invalid combination mixes a named
  profile with custom WPM and IKI-CV and leaves the field empty.
- The later fitted-cadence ruling supersedes that first D03 range. The public
  custom range is now 0 through 1 inclusive. D03 must prove that 1.1 fails
  before mutation on the rebuilt product.
- The first multiline boundary attempt used the fixture's single-line input.
  That element could not retain newline or paragraph boundaries. The harness
  now tracks a textarea, and the accepted browser and pixel reruns retain all
  three newline units with exact read-back.
