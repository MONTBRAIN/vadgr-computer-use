# 0.7.6 - browser reliability and human-paced typing: e2e runbook

> **vadgr-computer-use 0.7.6 implementation:**
> `feature/0.7.6-browser-reliability` at product commit
> `4401329ba788da0b0bb148cd51f5dc0332c53d89`.
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

## Owner and environment requirements

Tell the owner about these requirements before the affected group starts.

| requirement | cells | owner action |
|---|---|---|
| Linux, native Windows, macOS, and WSL hosts | all OS rows | Provide one real interactive session on each host |
| Chrome or Chromium with developer mode | A01-A04, B01-B10, C01-C04 | Approve the unpacked extension load if the browser asks |
| Browser restart and extension disable permission | A03-A04, B09 | Approve only the named browser action |
| Host suspend and resume | A02 | Resume the host if automation cannot do so safely |
| Native input permission | D01-D05 | Grant only the normal OS accessibility or input permission |
| Windows browser reachable from native Windows and WSL | B02a-B02f, B11-B17 | Keep both clients available during the convergence and lifecycle cells; provide hosts already configured for NAT and mirrored networking |

No paid account or external site login is required. The harness serves a local
instrumented page. The pass changes browser test state and creates isolated
temporary roots. It does not change host network state or privacy settings.

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

## Part A: recovery and setup diagnosis

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| A01 | Extension connected; one owned target exists | Let or force the MV3 worker idle, then request a DOM read | One bounded recovery restores the bridge and the original read runs once | Client JSON, broker log without page data; restore normal worker state | pass: one read recovered the same target at `c5c78b8` | not run: remote host | not run: remote host | not run: remote host |
| A02 | A01 passed | Suspend and resume the host, then request one DOM read | The read succeeds after bounded recovery, or returns the named recovery timeout without duplicate dispatch | Client JSON and timestamps; no host setting change | blocked: host suspension would terminate the only WSL driver | not run: remote host | not run: remote host | not run: remote host |
| A03 | Extension installed, then disabled | Request status and one read | The result says the extension is disabled and gives the matching remedy | Client JSON; re-enable the extension | pass: final bundle returned `extension_disabled` | not run: remote host | not run: remote host | not run: remote host |
| A04 | Isolated native-host registration removed | Request status and one read | The result says the host is not installed and does not call it an idle worker | Client JSON and isolated registration listing; restore registration | pass: final bundle returned `not_set_up`; registration restored | not run: remote host | not run: remote host | not run: remote host |

## Part B: shared broker and target ownership

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| B01 | One profile; two independent MCP clients | Attach both clients and list profiles, windows, and tabs | Both remain connected through one broker and see one complete registry | Both JSON streams and broker identity | pass | not run: remote host | not run: remote host | not run: remote host |
| B02a | NAT host; WSL client starts before native Windows | Start both against the same Windows browser, then interleave separate owned-window mutations and reads | One Windows PID, process start, epoch, bundle hash, profile and registry; both read-backs are exact | Both streams, Windows listener and broker identity | blocked: this host is mirrored and network changes are prohibited | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02b | NAT host; native Windows client starts before WSL | Repeat B02a in the opposite startup order | Same B02a identity and routing oracle | Both streams, Windows listener and broker identity | blocked: this host is mirrored and network changes are prohibited | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02c | NAT host; neither client started | Start native Windows and WSL clients simultaneously, then repeat the B02a operations | The atomic Windows lock elects one winner and both clients converge on it | Both streams, winner identity and listener | blocked: this host is mirrored and network changes are prohibited | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02d | Mirrored host; WSL client starts before native Windows | Repeat B02a | Same B02a identity and routing oracle; WSL uses the stdio proxy, not shared localhost | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B02e | Mirrored host; native Windows client starts before WSL | Repeat B02b | Same B02b identity and routing oracle; WSL uses the stdio proxy | Both streams, Windows listener and broker identity | pass | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B02f | Mirrored host; neither client started | Repeat B02c | Same B02c winner and routing oracle; WSL uses the stdio proxy | Both streams, winner identity and listener | pass | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B03 | Two clients in one profile | Each creates an owned window and two tabs, then interleaves reads and mutations | Responses return only to the caller; each sees foreign targets as owned by another client | Both streams and page event records; close test windows | pass | not run: remote host | not run: remote host | not run: remote host |
| B04 | B03 windows remain | Select a different current tab per client and interleave operations | Every request reaches its exact profile, window, and tab without cross-routing | Target ids and structured page records | pass | not run: remote host | not run: remote host | not run: remote host |
| B05 | One unowned tab in a shared user window | Client one claims the tab; client two reads it and attempts a window action | Client one can use tab-scoped DOM ops; client two receives `target_owned_by_another_client`; neither client changes window focus | Both streams and page record; release the tab | pass | not run: remote host | not run: remote host | not run: remote host |
| B06 | Unowned tab and window targets | Race two clients for the tab, then race a window claim against a foreign child lease | One atomic winner exists; every loser gets the named conflict before dispatch | Both streams and lease revision record; release winner | pass | not run: remote host | not run: remote host | not run: remote host |
| B07 | Owned window, child tabs, popup, and shared window | Open tabs with and without opener, a popup, and an unattributable shared-window child | Owned descendants inherit the correct lease; the unattributable shared child stays unowned | Registry snapshots; close created targets | pass | not run: remote host | not run: remote host | not run: remote host |
| B08 | Client owns one tab and one multi-tab window | Release each, then dispatch with the old revision | Browser state stays open, leases clear, and stale revisions fail | Registry and page records; close created state | pass: rerun after repair | not run: remote host | not run: remote host | not run: remote host |
| B09 | Client owns targets; second client stays connected | Break the first socket, reconnect inside 30 seconds, then repeat after heartbeat and grace expiry | Timely reconnect restores state; expired leases become orphaned and are explicitly reclaimable | Streams and monotonic timing; release reclaimed state | pass | not run: remote host | not run: remote host | not run: remote host |
| B10 | Browser resources remain open | Restart only the broker | New epoch marks rediscovered targets orphaned; old secrets and revisions fail; URL and title do not restore identity | Before and after registry plus epoch; reclaim or close test state | pass | not run: remote host | not run: remote host | not run: remote host |
| B11 | Windows and WSL clients share one broker | Exit only the WSL client, then operate from Windows | Windows continues through the same PID and epoch | Windows stream and broker identity | pass | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B12 | Windows and WSL clients share one broker | Exit only the Windows client, then operate from WSL | WSL continues through the proxy and the same Windows PID and epoch | WSL stream and broker identity | pass | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B13 | WSL client disconnected; Windows broker has a live Windows client or extension | Terminate only the test WSL distribution session | The Windows broker remains alive and usable | Windows process and operation read-back | pass: disposable distro stopped; native client kept the same broker | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B14 | Fresh verified bundle and endpoint | Corrupt isolated copies of the endpoint token and bundle | Bad authentication is refused and altered payload fails before execution | Named errors and unchanged live bundle hash; delete isolated copies | pass | Not-Needed: Windows-only packaging seam | not run: paired WSL client required | Not-Needed: Windows-only packaging seam |
| B15 | Broker running with owned resources | Terminate only that broker process and reconnect both clients | One new Windows PID and epoch appear; rediscovered leases are orphaned | Before/after identity and registry | pass | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B16 | Isolated stale and corrupt endpoint copies | Start both clients through the normal launcher | Startup rejects corrupt identity and safely recovers stale state without trusting its token | Named result, one Windows process and clean identity | pass | Not-Needed: Windows-only packaging seam | not run: paired WSL client required | Not-Needed: Windows-only packaging seam |
| B17 | Isolated WSL environment with Windows interop unavailable | Request browser status | A named interop remedy returns and no Linux/WSL broker starts | Error stream and process listing | pass: rerun after repair | Not-Needed: WSL-only negative seam | Not-Needed: proved by paired WSL row | Not-Needed: WSL-only negative seam |

## Part C: composed-tree actionability and browser typing

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| C01 | Owned target on the harness page | Click and type through one and nested open shadow roots | Each mutation succeeds and the DOM event record confirms the exact target and value | Client JSON and redacted event metadata; clear fields | pass | not run: remote host | not run: remote host | not run: remote host |
| C02 | C01 targets covered by document and nested-shadow overlays | Repeat click and type | Each action fails as covered and no page state changes | Error results and unchanged DOM record; remove overlays | pass | not run: remote host | not run: remote host | not run: remote host |
| C03 | Instrumented plain field | Run `fill`, fast `type`, and `type(human=true)` | Fill and fast type keep bulk behavior; human type emits ordered page events with varied intervals and exact read-back; evidence makes no `isTrusted` claim | Event kinds, trust flags, intervals, counts, and hashes only; never field text | pass | not run: remote host | not run: remote host | not run: remote host |
| C04 | Debounce, typeahead, validation, counter, Unicode, timeout, cancellation, and mismatch controls | Drive each human-typing branch while a second client uses another window | Intermediate states occur; the other client stays responsive; invalid and deadline cases mutate nothing; fallback is counted; cancellation skips submit; mismatch never duplicates the whole string | Both streams and redacted event metadata; reset page | pass | not run: remote host | not run: remote host | not run: remote host |
| C05 | Owned unfocused window with one selected decoy tab and an exact leased harness tab where `focused=false`, `active=false`, and `is_current=true` | Without `tabs.switch` or `windows.focus`, run `wait_for`, `query`, `read_text`, `get_attribute`, DOM `click`, fast and human `type`, `fill`, `select`, `scroll`, `element_state`, `clear` and `get_value` against the leased tab | Each content operation reaches only the exact leased tab; paced typing has exact read-back; state remains false/false/true; the decoy is unchanged | Both tab states before and after, redacted event metadata and decoy hash; reset the harness and close only the owned window | pass | not run: remote host | not run: remote host | not run: remote host |
| C06 | C05 state plus state-bearing pointer, reveal, focus, file-input, dialog and semantic controls | Run trusted `click`, `hover`, `focus`, `blur`, `upload`, `snapshot`, `accessibility_tree`, `eval`, navigation, reload, back and forward; arm the dialog on the leased tab while a decoy target also emits one | Every operation reaches the leased tab, carries an independent state/read-back oracle, ignores the decoy dialog and preserves false/false/true; cookie operations are excluded because they are profile/origin scoped | Before/after target state, state-bearing results, temporary upload hash and decoy hash; remove the temporary file and close only the owned window | pass | not run: remote host | not run: remote host | not run: remote host |
| C07 | C05 state, then separate discarded, frozen, browser-internal, Web Store and denied-file targets. Launch pinned isolated Chrome for Testing with `--remote-debugging-port=0`, enable its internal debugging pages, and use `harness/lifecycle_control.py` to establish and verify the exact lifecycle rows. | Call trusted `press` on the inactive harness and one page operation on each unavailable target; do not activate any target | `press` returns `inactive_tab_trusted_keyboard_unsupported`; unavailable targets return `target_discarded`, `target_frozen` or `target_restricted`; no action reports success, mutates a decoy, switches a tab or focuses a window | Exact Chrome version, DevTools protocol support, helper output, error codes and target state before/after; close only owned test windows and the isolated Chrome root | pass | not run: remote host | not run: remote host | not run: remote host |

## Part D: pixel typing

On WSL, invoke the committed foreground helper through a process-only execution
policy override; it does not change the host policy:

```bash
FOCUS_SCRIPT=$(wslpath -w E2E/0.7.6/harness/focus_window.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$FOCUS_SCRIPT" \
  -ExactTitle "$TEST_TITLE"
```

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| D01 | Native event-recording field focused. On WSL, give the isolated Windows test window a unique title and use `harness/focus_window.ps1 -ExactTitle` to verify its exact non-minimized HWND is foreground. | Run fast `type_text` and named-profile human `type_text` | Fast mode stays compatible; human mode emits ordered varied input and exact final text | Native event record with text removed; clear field | pass | not run: remote host | not run: remote host | not run: remote host |
| D02 | D01 field focused | Run custom WPM plus IKI-CV, including zero variation | Planned and achieved metadata are valid; zero variation is constant control | Timing metadata only; clear field | pass | not run: remote host | not run: remote host | not run: remote host |
| D03 | D01 field focused | Try invalid option combinations and a deadline shorter than the plan | Each fails before input and leaves the field unchanged | Error results and independent field read-back | pass | not run: remote host | not run: remote host | not run: remote host |
| D04 | D01 field focused | Cancel during human input and exercise supported Unicode or fallback | Modifiers are released, progress count is truthful, exact text or named fallback is reported, and no whole-string retry occurs | Event record with text removed; release keys and clear field | pass: 33-unit exact prefix and one fallback unit | not run: remote host | not run: remote host | not run: remote host |
| D05 | Human pixel typing active in one client | Start a second pixel keyboard action | The product makes no parallel-safety claim; evidence records machine-global serialization or conflict behavior exactly | Both streams; stop both operations and release keys | pass: concurrent calls interleaved | not run: remote host | not run: remote host | not run: remote host |

## Part E: packaged and clean delivery

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| E01 | Fresh environment outside checkout | Install only the built wheel and start `vadgr-cua` through its entry point | Version is 0.7.6, readiness succeeds, and source checkout is absent from import paths | Install log, path, version, wheel hash; remove environment | pass: final wheel at `4401329` | not run: remote host | not run: remote host | not run: remote host |
| E02 | Matching store-equivalent extension and installed wheel. WSL uses D01's exact foreground-window setup before the pixel action. | Run one owned-window browser read, one human browser type, and one human pixel type | The installed package and matching extension execute the released behavior | MCP JSON with input text removed; close test state | pass | not run: remote host | not run: remote host | not run: remote host |

## Per-OS results

| part | WSL | Linux | Windows | macOS |
|---|---|---|---|---|
| A: recovery and setup diagnosis | blocked: A02 needs host suspend and resume | not run: remote host | not run: remote host | not run: remote host |
| B: shared broker and target ownership | blocked: NAT cells need a NAT WSL host | not run: remote host | not run: remote host | not run: remote host |
| C: actionability and browser typing | pass | not run: remote host | not run: remote host | not run: remote host |
| D: pixel typing | pass | not run: remote host | not run: remote host | not run: remote host |
| E: packaged and clean delivery | pass | not run: remote host | not run: remote host | not run: remote host |
| overall | blocked: A02 and B02a-B02c | not run: remote host | not run: remote host | not run: remote host |

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

- A01 first changed the selected client from its restarting profile to the one
  remaining profile. The resulting stale target failed as foreign ownership.
  The repaired broker keeps an explicit profile pinned during bounded MV3
  recovery. The final run used one DOM read on the same target.
- D05 observed two concurrent WSL pixel calls. Both finished in about 7.6
  seconds, and the field oracle recorded interleaved output. This release makes
  no parallel pixel-safety claim.
- A04 first returned `extension_disabled` after the real Windows registration
  was absent because the broker checked a separate manifest copy. The repaired
  broker reads the actual HKCU registration. The sealed rerun returned
  `not_set_up`, and both registry keys were restored.
- WSL human browser typing initially returned `typing_mismatch` for plain and
  nested-shadow inputs. A later strict inactive-tab diagnostic proved that CDP
  keyboard input could pass on a selected background-window tab yet be
  discarded when the exact target tab itself was inactive. The repaired path
  sends each planned unit through that tab's content channel and verifies every
  intermediate value. A preliminary live rerun passed with `focused=false`,
  `active=false`, and `is_current=true`; the sealed C05 cell remains required.
