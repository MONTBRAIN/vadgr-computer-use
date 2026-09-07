# 0.7.6 - browser reliability and human-paced typing: e2e runbook

> **vadgr-computer-use 0.7.6 implementation:**
> `feature/0.7.6-browser-reliability` at product commit
> `d8276071fcec953d5aeab43622fa7326fc4f1aca`.
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
10. Before a pixel or screenshot group, compare current official capabilities
    and prices. Use GPT-5.6 Sol at medium reasoning with Codex or the current
    Claude Opus at medium reasoning with Claude Code. Choose between those
    qualified paths using availability, task fit and projected total cost. Do
    not substitute Terra, Sonnet or Gemini. Record the exact model, reasoning
    level, sources and hard ceiling. A higher reasoning level or cost tier
    requires a recorded medium-tier capability failure and owner approval.
11. Every remaining browser-tier cell uses a versioned Chrome for Testing
    executable, a fresh isolated profile, and the matching development
    extension. Never attach to the owner's normal browser process or profile.
12. Until the Vadgr-native E2E harness is production-ready, every live agent
    task uses permission bypass: `codex --yolo` or Claude Code with
    `--dangerously-skip-permissions`. The bypass prevents unattended approval
    stalls. It does not broaden a cell, authorize destructive work, waive an
    owner-dependent action, change the billing ceiling, or replace evidence and
    cleanup.

## Owner and environment requirements

Tell the owner about these requirements before the affected group starts.

| requirement | cells | owner action |
|---|---|---|
| Linux, native Windows, macOS, and WSL hosts | all OS rows | Provide one real interactive session on each host |
| Chrome for Testing with developer mode | A01-A04, B01-B17, C01-C07, E02 browser path | Approve the unpacked development extension only if the isolated browser asks |
| Browser restart and extension disable permission | A03-A04, B09 | Approve only the named browser action |
| Host suspend and resume | A02 | Resume the host if automation cannot do so safely |
| Native input permission | D01-D05, E02 pixel path | Grant only the normal OS accessibility or input permission |
| Stock plain-text editor | D01-D05, E02 pixel path | Keep Windows Notepad, macOS TextEdit, or the host's stock Linux text editor available; install no editor solely for these cells |
| Windows browser reachable from native Windows and WSL | B02a-B02f, B11-B17 | Keep both clients available during the convergence and lifecycle cells; provide hosts already configured for NAT and mirrored networking |
| Authenticated agent CLI and bounded billing | D01, D01a, D02b, D04, E02 | Keep one supported Claude or Codex login available; approve no unbounded or higher-cost fallback |

No product account or external test-site login is required. The visual driver
uses the separately declared authenticated agent CLI and billing ceiling. The
harness serves a local instrumented page. The pass changes browser test state
and creates isolated temporary roots. It does not change host network state or
privacy settings.

## Billed model selection

Recheck the [OpenAI models][models], [OpenAI pricing][openai-pricing],
[Anthropic models][claude-models] and [Anthropic pricing][claude-pricing] pages
on the execution day. Do not reuse the superseded Terra/Sonnet comparison from
the interrupted 2026-09-05 attempt.

| cells | provider/auth | required capabilities | selected model | hard ceiling | escalation |
|---|---|---|---|---|---|
| D01, D02b, D04, E02 | authenticated Codex owner login | image-result continuation and MCP tools | GPT-5.6 Sol, medium reasoning | USD 4 API-list-price equivalent for the accepted boundary | Stop at the first ceiling. Do not change the qualified model or reasoning level without a recorded failure and owner approval. |

The WSL pass rechecked the official OpenAI capability and pricing pages on
2026-09-06. GPT-5.6 Sol supports image input and tools. The comparison rates
were USD 4 per million input tokens, USD 0.40 per million cached input tokens,
and USD 20 per million output tokens.

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

The native Windows pass uses this temporary driver form for every remaining
live task:

```text
codex --yolo exec --json --model gpt-5.6-sol <MCP, working-directory and prompt options>
```

The command uses medium reasoning and invokes the exact isolated-wheel
`vadgr-cua` entry point. Record paths only in owner-private local state, never in
the public runbook or private evidence. The unrestricted agent driver may
perform ordinary in-scope local setup, such as opening and focusing the stock
editor, when a repository helper cannot. It must still use public product tools
for the action under test and capture the independent oracle and cleanup.

## Part A: recovery and setup diagnosis

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| A01 | Extension connected; one owned target exists | Let or force the MV3 worker idle, then request a DOM read | One bounded recovery restores the bridge and the original read runs once | Client JSON, broker log without page data; restore normal worker state | pass: one read recovered the same target at `c5c78b8` | not run: remote host | pass: isolated worker recovery preserved the selected profile and completed one read on the same target | not run: remote host |
| A02 | A01 passed | Suspend and resume the host, then request one DOM read | The read succeeds after bounded recovery, or returns the named recovery timeout without duplicate dispatch | Client JSON and timestamps; no host setting change | pass: one post-resume DOM read completed without retry at `26e7d05` | not run: remote host | not run: owner prohibited sleep and power actions while away | not run: remote host |
| A03 | Extension installed, then disabled | Request status and one read | The result says the extension is disabled and gives the matching remedy | Client JSON; re-enable the extension | pass: final bundle returned `extension_disabled` | not run: remote host | pass: isolated disable returned `extension_disabled`; extension restored | not run: remote host |
| A04 | Isolated native-host registration removed | Request status and one read | The result says the host is not installed and does not call it an idle worker | Client JSON and isolated registration listing; restore registration | pass: final bundle returned `not_set_up`; registration restored | not run: remote host | pass: isolated registration removal returned `not_set_up`; registration restored | not run: remote host |

## Part B: shared broker and target ownership

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| B01 | One profile; two independent MCP clients | Attach both clients and list profiles, windows, and tabs | Both remain connected through one broker and see one complete registry | Both JSON streams and broker identity | pass | not run: remote host | pass | not run: remote host |
| B02a | NAT host; WSL client starts before native Windows | Start both against the same Windows browser, then interleave separate owned-window mutations and reads | One Windows PID, process start, epoch, bundle hash, profile and registry; both read-backs are exact | Both streams, Windows listener and broker identity | Not-Needed: WSL always uses the stdio proxy; B02d covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02b | NAT host; native Windows client starts before WSL | Repeat B02a in the opposite startup order | Same B02a identity and routing oracle | Both streams, Windows listener and broker identity | Not-Needed: WSL always uses the stdio proxy; B02e covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02c | NAT host; neither client started | Start native Windows and WSL clients simultaneously, then repeat the B02a operations | The atomic Windows lock elects one winner and both clients converge on it | Both streams, winner identity and listener | Not-Needed: WSL always uses the stdio proxy; B02f covers this order | Not-Needed: no cross-OS seam | Not-Needed: no native Windows topology branch | Not-Needed: no cross-OS seam |
| B02d | Mirrored host; WSL client starts before native Windows | Repeat B02a | Same B02a identity and routing oracle; WSL uses the stdio proxy, not shared localhost | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | pass: paired WSL proxy and native Windows converged on one complete broker identity | Not-Needed: no cross-OS seam |
| B02e | Mirrored host; native Windows client starts before WSL | Repeat B02b | Same B02b identity and routing oracle; WSL uses the stdio proxy | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B02f | Mirrored host; neither client started | Repeat B02c | Same B02c winner and routing oracle; WSL uses the stdio proxy | Both streams, winner identity and listener | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B03 | Two clients in one profile | Each creates an owned window and two tabs, then interleaves reads and mutations | Responses return only to the caller; each sees foreign targets as owned by another client | Both streams and page event records; close test windows | pass | not run: remote host | pass | not run: remote host |
| B04 | B03 windows remain | Select a different current tab per client and interleave operations | Every request reaches its exact profile, window, and tab without cross-routing | Target ids and structured page records | pass | not run: remote host | pass | not run: remote host |
| B05 | One unowned tab in a shared user window | Client one claims the tab; client two reads it and attempts a window action | Client one can use tab-scoped DOM ops; client two receives `target_owned_by_another_client`; neither client changes window focus | Both streams and page record; release the tab | pass | not run: remote host | pass | not run: remote host |
| B06 | Unowned tab and window targets | Race two clients for the tab, then race a window claim against a foreign child lease | One atomic winner exists; every loser gets the named conflict before dispatch | Both streams and lease revision record; release winner | pass | not run: remote host | pass | not run: remote host |
| B07 | Owned window, child tabs, popup, and shared window | Open tabs with and without opener, a popup, and an unattributable shared-window child | Owned descendants inherit the correct lease; the unattributable shared child stays unowned | Registry snapshots; close created targets | pass | not run: remote host | pass | not run: remote host |
| B08 | Client owns one tab and one multi-tab window | Release each, then dispatch with the old revision | Browser state stays open, leases clear, and stale revisions fail | Registry and page records; close created state | pass: rerun after repair | not run: remote host | pass | not run: remote host |
| B09 | Client owns targets; second client stays connected | Break the first socket, reconnect inside 30 seconds, then repeat after heartbeat and grace expiry | Timely reconnect restores state; expired leases become orphaned and are explicitly reclaimable | Streams and monotonic timing; release reclaimed state | pass | not run: remote host | pass: timely reconnect restored state in 0.031 seconds; expired state was orphaned and explicitly reclaimed | not run: remote host |
| B10 | Browser resources remain open | Restart only the broker | New epoch marks rediscovered targets orphaned; old secrets and revisions fail; URL and title do not restore identity | Before and after registry plus epoch; reclaim or close test state | pass | not run: remote host | pass: new identity rejected old credentials; rediscovered state was orphaned, reclaimed and closed | not run: remote host |
| B11 | Windows and WSL clients share one broker | Exit only the WSL client, then operate from Windows | Windows continues through the same PID and epoch | Windows stream and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B12 | Windows and WSL clients share one broker | Exit only the Windows client, then operate from WSL | WSL continues through the proxy and the same Windows PID and epoch | WSL stream and broker identity | pass | Not-Needed: no cross-OS seam | pass | Not-Needed: no cross-OS seam |
| B13 | WSL client disconnected; Windows broker has a live Windows client or extension | Terminate only the test WSL distribution session | The Windows broker remains alive and usable | Windows process and operation read-back | pass: disposable distro stopped; native client kept the same broker | Not-Needed: no cross-OS seam | pass: a disposable distro stopped while the native client retained the same live broker PID, start identity, epoch, and bundle hash | Not-Needed: no cross-OS seam |
| B14 | Fresh verified bundle and endpoint | Corrupt isolated copies of the endpoint token and bundle | Bad authentication is refused and altered payload fails before execution | Named errors and unchanged live bundle hash; delete isolated copies | pass | Not-Needed: Windows-only packaging seam | pass: bad authentication was refused and an isolated tampered bundle was rejected before execution | Not-Needed: Windows-only packaging seam |
| B15 | Broker running with owned resources | Terminate only that broker process and reconnect both clients | One new Windows PID and epoch appear; rediscovered leases are orphaned | Before/after identity and registry | pass | Not-Needed: no cross-OS seam | pass: both clients converged on the new identity and rediscovered state was orphaned | Not-Needed: no cross-OS seam |
| B16 | Isolated stale and corrupt endpoint copies | Start both clients through the normal launcher | Startup rejects corrupt identity and safely recovers stale state without trusting its token | Named result, one Windows process and clean identity | pass | Not-Needed: Windows-only packaging seam | pass: corrupt identity was rejected and stale state safely replaced | Not-Needed: Windows-only packaging seam |
| B17 | Isolated WSL environment with Windows interop unavailable | Request browser status | A named interop remedy returns and no Linux/WSL broker starts | Error stream and process listing | pass: rerun after repair | Not-Needed: WSL-only negative seam | Not-Needed: proved by paired WSL row | Not-Needed: WSL-only negative seam |

## Part C: composed-tree actionability and browser typing

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| C01 | Owned target on the harness page | Click and type through one and nested open shadow roots | Each mutation succeeds and the DOM event record confirms the exact target and value | Client JSON and redacted event metadata; clear fields | pass | not run: remote host | pass | not run: remote host |
| C02 | C01 targets covered by document and nested-shadow overlays | Repeat click and type | Each action fails as covered and no page state changes | Error results and unchanged DOM record; remove overlays | pass | not run: remote host | pass | not run: remote host |
| C03 | Instrumented plain field | Run `fill`, fast `type`, and default-profile `type(human=true)` | Fill and fast type keep bulk behavior; human type emits ordered page events with varied intervals and exact read-back; evidence makes no `isTrusted` claim | Event kinds, trust flags, intervals, counts, and hashes only; never field text | pass: all three exact hashes matched; human input produced 54 distinct intervals | not run: remote host | pass: bulk and human paths produced exact read-backs with redacted timing evidence | not run: remote host |
| C03b | Instrumented field and event clock; text contains ordinary spaces plus clause, sentence, newline, and paragraph boundaries | Run long default-profile input and custom inputs at 10 and 200 WPM with IKI-CV 0 and 1 | Ordinary spaces add no separate pause; intervals show varied local runs without exact-message normalization; every read-back is exact; metadata reports the requested mode and realized rate | Redacted event timing and boundary-class records, batch rate summary, option metadata, and value hash; clear the field | pass: exact default and endpoint inputs; tracked multiline addendum covered newline and paragraph boundaries | not run: remote host | pass: exact default, endpoint and multiline boundary read-backs | not run: remote host |
| C04 | Debounce, typeahead, validation, counter, Unicode, timeout, cancellation, mismatch and client-exit controls | While a second client uses another window, complete a plan longer than 60 seconds with no timeout, then drive invalid input, explicit preflight and runtime deadlines, cancellation, mismatch and client EOF | Healthy long input completes while the other client stays responsive; invalid and preflight-deadline cases mutate nothing; runtime deadline, cancellation and EOF stop at the confirmed prefix and skip submit; fallback is counted; mismatch and uncertain dispatch never replay input | Both streams and redacted event metadata; reset page | pass: concurrent long inputs, both deadlines, cancellation, mismatch, client EOF and fresh streams observed | not run: remote host | pass: long input, invalid input, deadlines, cancellation, mismatch and client EOF produced the required exact-prefix oracles | not run: remote host |
| C05 | Owned unfocused window with one selected decoy tab and an exact leased harness tab where `focused=false`, `active=false`, and `is_current=true` | Without `tabs.switch` or `windows.focus`, run `wait_for`, `query`, `read_text`, `get_attribute`, DOM `click`, fast and human `type`, `fill`, `select`, `scroll`, `element_state`, `clear` and `get_value` against the leased tab | Each content operation reaches only the exact leased tab; paced typing has exact read-back; state remains false/false/true; the decoy is unchanged | Both tab states before and after, redacted event metadata and decoy hash; reset the harness and close only the owned window | pass: every content operation reached the leased inactive tab; the decoy stayed unchanged | not run: remote host | pass | not run: remote host |
| C06 | C05 state plus state-bearing pointer, reveal, focus, file-input, dialog and semantic controls | Run trusted `click`, `hover`, `focus`, `blur`, `upload`, `snapshot`, `accessibility_tree`, `eval`, navigation, reload, back and forward; arm the dialog on the leased tab while a decoy target also emits one | Every operation reaches the leased tab, carries an independent state/read-back oracle, ignores the decoy dialog and preserves false/false/true; cookie operations are excluded because they are profile/origin scoped | Before/after target state, state-bearing results, temporary upload hash and decoy hash; remove the temporary file and close only the owned window | pass | not run: remote host | pass | not run: remote host |
| C07 | C05 state, then separate discarded, frozen, browser-internal, Web Store and denied-file targets. Launch pinned isolated Chrome for Testing with `--remote-debugging-port=0`, enable its internal debugging pages, and use `harness/lifecycle_control.py` to establish and verify the exact lifecycle rows. | Call trusted `press` on the inactive harness and one page operation on each unavailable target; do not activate any target | `press` returns `inactive_tab_trusted_keyboard_unsupported`; unavailable targets return `target_discarded`, `target_frozen` or `target_restricted`; no action reports success, mutates a decoy, switches a tab or focuses a window | Exact Chrome version, DevTools protocol support, helper output, error codes and target state before/after; close only owned test windows and the isolated Chrome root | pass | not run: remote host | pass | not run: remote host |

## Part D: pixel typing

Use the operating system's stock plain-text editor for every cell in this part:
Windows Notepad on Windows and WSL, TextEdit in plain-text mode on macOS, and
the available stock plain-text editor on Linux. Use a fresh document and the
public pixel tools. Do not substitute a custom event recorder, test GUI, browser
field, or repository helper for the editor. Take one pixel screenshot before
typing and one after typing. The after screenshot must visibly confirm the
mutation. Do not save the document. Use the returned typing metadata for timing
assertions.

On WSL, invoke the committed foreground helper through a process-only execution
policy override; it does not change the host policy:

```bash
FOCUS_SCRIPT=$(wslpath -w E2E/0.7.6/harness/focus_window.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$FOCUS_SCRIPT" \
  -ExactTitle "$TEST_TITLE"
```

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| D01 | Fresh stock-editor document focused. On WSL, use `harness/focus_window.ps1 -ExactTitle` to verify the exact non-minimized Notepad window is foreground. | Run fast `type_text` and named-profile human `type_text` in separate fresh documents | Fast mode stays compatible; human metadata names the profile and reports complete varied input; each after screenshot visibly confirms the mutation | Redacted agent JSON with before and after screenshot results; close the test documents without saving | pass: Notepad fast mode completed 93 units in 0.107 seconds; profile mode completed 314 units in 53.563 seconds | not run: remote host | pass | not run: remote host |
| D01a | Fresh unsaved stock-editor document. Use Notepad on Windows and WSL, TextEdit in plain-text mode on macOS, and the available stock plain-text editor on Linux. Verify the exact non-minimized editor window is foreground. | Through the agent and public pixel tools, type the fixed sensitive-file value with `type_text(human=true)` and no timing override | Metadata names `us_adult_transcription_2026`, nominal WPM 68, all units complete and no unexpected fallback; the after screenshot visibly confirms the mutation; no browser or structured typing path is used | Redacted agent JSON, foreground identity, timing metadata, and before and after screenshot results; close without saving | pass: GPT-5.6 Sol medium completed 240 units in 38.729 seconds and produced the stronger saved-file hash oracle | not run: remote host | pass: GPT-5.6 Sol medium completed the public pixel mutation and independent read-back | not run: remote host |
| D02 | Fresh stock-editor document focused | Run custom WPM plus IKI-CV at both accepted endpoints in separate documents | Planned and achieved metadata are valid; IKI-CV zero removes marginal spread while the shared rank chain remains; each after screenshot visibly confirms the mutation | Redacted timing metadata and before and after screenshot results; close without saving | pass: Notepad completed the 10 WPM and 200 WPM endpoint plans in 15.112 and 2.075 seconds | not run: remote host | pass: both endpoint mutations completed with visible read-back; public metadata does not expose internal rank fields | not run: remote host |
| D02b | Fresh stock-editor document focused; text contains ordinary spaces and every semantic-boundary class | Run default and custom human input in separate documents | Metadata reports each requested mode; each after screenshot visibly confirms the mutation; browser cell C03b retains the independent boundary-timing oracle | Redacted metadata, boundary counts, and before and after screenshot results; close without saving | pass: Notepad completed 353-unit default and 90 WPM multiline inputs in 62.678 and 45.032 seconds | not run: remote host | pass | not run: remote host |
| D03 | Fresh empty stock-editor document focused | Try incomplete or mixed timing options, IKI-CV below 0 or above 1, and a deadline shorter than the plan | Each fails before input and leaves the document visibly empty | Error results and before and after screenshot results | pass: seven invalid or preflight-deadline requests failed before input; the document remained empty | not run: remote host | pass | not run: remote host |
| D04 | Fresh stock-editor document focused | Complete a plan longer than 60 seconds without a timeout, then exercise runtime deadline, cancellation and combining-mark or joined-emoji grapheme fallback in fresh documents | Long input completes; deadline and cancellation report a truthful prefix; modifiers are released; each grapheme stays whole; the after screenshot confirms visible input or the named fallback is reported; no whole-string retry or submit occurs after interruption | Redacted agent JSON with before and after screenshot results; release keys and close without saving | pass: Notepad completed 614 units in 100.634 seconds and the Unicode path named four fallbacks; prior runtime-deadline and cancellation evidence remains valid | not run: remote host | pass: the installed wheel completed 980 units in 160.907 seconds; the repaired Unicode path preserved seven graphemes and named four fallbacks; prior runtime-deadline and cancellation evidence remains valid | not run: remote host |
| D05 | Human pixel typing active in one fresh stock-editor document | Start a second pixel keyboard action against the same document | The product makes no parallel-safety claim; evidence records machine-global serialization or conflict behavior exactly | Both streams and before and after screenshot results; stop both operations, release keys, and close without saving | pass: synchronized Notepad clients overlapped and completed 314 and 228 units | not run: remote host | pass: two synchronized clients completed; evidence records the observed interleaving without a parallel-safety claim | not run: remote host |

## Part E: packaged and clean delivery

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| E01 | Fresh environment outside checkout | Install only the built wheel and start `vadgr-cua` through its entry point | Version is 0.7.6, readiness succeeds, the Unicode segmenter and fitted profile load, and source checkout is absent from import paths | Install log, path, version, wheel hash; remove environment | pass: clean wheel reported 0.7.6 and served the MCP outside the checkout | not run: remote host | pass: final wheel reported 0.7.6, served 33 tools and loaded both required payloads outside the checkout | not run: remote host |
| E02 | Matching store-equivalent extension and installed wheel. WSL uses D01's exact stock-editor setup before the pixel action. | Run one owned-window browser read, one human browser type longer than 60 seconds, and one human pixel type longer than 60 seconds | The installed package and matching extension execute the fitted cadence and long typing without an implicit total deadline | MCP JSON with input text removed plus before and after screenshot results for the pixel document; close without saving | pass: installed-wheel browser evidence retained 74 completed calls; Notepad completed 588 units in 101.429 seconds | not run: remote host | pass: the installed wheel completed a 980-unit browser type in 149.8 seconds and a 980-unit Notepad type in 164.719 seconds without an implicit deadline | not run: remote host |

## Per-OS results

| part | WSL | Linux | Windows | macOS |
|---|---|---|---|---|
| A: recovery and setup diagnosis | pass | not run: remote host | incomplete: A02 awaits owner permission for suspend/resume | not run: remote host |
| B: shared broker and target ownership | pass | not run: remote host | pass | not run: remote host |
| C: actionability and browser typing | pass | not run: remote host | pass | not run: remote host |
| D: pixel typing | pass | not run: remote host | pass | not run: remote host |
| E: packaged and clean delivery | pass | not run: remote host | pass | not run: remote host |
| overall | pass | not run: remote host | incomplete: A02 remains | not run: remote host |

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
