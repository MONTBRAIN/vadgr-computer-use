# 0.7.6 - browser reliability and human-paced typing: e2e runbook

> **vadgr-computer-use 0.7.6 implementation:**
> `feature/0.7.6-browser-reliability` at product commit
> `ae13f4b7f938ee44fa820a5516bfbc7a7618444b`.
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
| `vadgr` | `0.4.12` | No live dependency. Packaged delivery is proved later by `vadgr 0.5.0` |

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
| A01 | Extension connected; one owned target exists | Let or force the MV3 worker idle, then request a DOM read | One bounded recovery restores the bridge and the original read runs once | Client JSON, broker log without page data; restore normal worker state | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| A02 | A01 passed | Suspend and resume the host, then request one DOM read | The read succeeds after bounded recovery, or returns the named recovery timeout without duplicate dispatch | Client JSON and timestamps; no host setting change | not run: owner resume may be required | not run: remote host | not run: remote host | not run: remote host |
| A03 | Extension installed, then disabled | Request status and one read | The result says the extension is disabled and gives the matching remedy | Client JSON; re-enable the extension | not run: owner approval required | not run: remote host | not run: remote host | not run: remote host |
| A04 | Isolated native-host registration removed | Request status and one read | The result says the host is not installed and does not call it an idle worker | Client JSON and isolated registration listing; restore registration | not run: owner approval required | not run: remote host | not run: remote host | not run: remote host |

## Part B: shared broker and target ownership

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| B01 | One profile; two independent MCP clients | Attach both clients and list profiles, windows, and tabs | Both remain connected through one broker and see one complete registry | Both JSON streams and broker identity | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B02a | NAT host; WSL client starts before native Windows | Start both against the same Windows browser, then interleave separate owned-window mutations and reads | One Windows PID, process start, epoch, bundle hash, profile and registry; both read-backs are exact | Both streams, Windows listener and broker identity | not run: NAT paired host required | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02b | NAT host; native Windows client starts before WSL | Repeat B02a in the opposite startup order | Same B02a identity and routing oracle | Both streams, Windows listener and broker identity | not run: NAT paired host required | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02c | NAT host; neither client started | Start native Windows and WSL clients simultaneously, then repeat the B02a operations | The atomic Windows lock elects one winner and both clients converge on it | Both streams, winner identity and listener | not run: NAT paired host required | Not-Needed: no cross-OS seam | not run: NAT paired WSL client required | Not-Needed: no cross-OS seam |
| B02d | Mirrored host; WSL client starts before native Windows | Repeat B02a | Same B02a identity and routing oracle; WSL uses the stdio proxy, not shared localhost | Both streams, Windows listener and broker identity | not run: mirrored paired host required | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B02e | Mirrored host; native Windows client starts before WSL | Repeat B02b | Same B02b identity and routing oracle; WSL uses the stdio proxy | Both streams, Windows listener and broker identity | not run: mirrored paired host required | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B02f | Mirrored host; neither client started | Repeat B02c | Same B02c winner and routing oracle; WSL uses the stdio proxy | Both streams, winner identity and listener | not run: mirrored paired host required | Not-Needed: no cross-OS seam | not run: mirrored paired WSL client required | Not-Needed: no cross-OS seam |
| B03 | Two clients in one profile | Each creates an owned window and two tabs, then interleaves reads and mutations | Responses return only to the caller; each sees foreign targets as owned by another client | Both streams and page event records; close test windows | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B04 | B03 windows remain | Select a different current tab per client and interleave operations | Every request reaches its exact profile, window, and tab without cross-routing | Target ids and structured page records | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B05 | One unowned tab in a shared user window | Client one claims the tab; client two reads it and attempts a window action | Client one can use tab-scoped DOM ops; client two receives `target_owned_by_another_client`; neither client changes window focus | Both streams and page record; release the tab | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B06 | Unowned tab and window targets | Race two clients for the tab, then race a window claim against a foreign child lease | One atomic winner exists; every loser gets the named conflict before dispatch | Both streams and lease revision record; release winner | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B07 | Owned window, child tabs, popup, and shared window | Open tabs with and without opener, a popup, and an unattributable shared-window child | Owned descendants inherit the correct lease; the unattributable shared child stays unowned | Registry snapshots; close created targets | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B08 | Client owns one tab and one multi-tab window | Release each, then dispatch with the old revision | Browser state stays open, leases clear, and stale revisions fail | Registry and page records; close created state | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B09 | Client owns targets; second client stays connected | Break the first socket, reconnect inside 30 seconds, then repeat after heartbeat and grace expiry | Timely reconnect restores state; expired leases become orphaned and are explicitly reclaimable | Streams and monotonic timing; release reclaimed state | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B10 | Browser resources remain open | Restart only the broker | New epoch marks rediscovered targets orphaned; old secrets and revisions fail; URL and title do not restore identity | Before and after registry plus epoch; reclaim or close test state | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B11 | Windows and WSL clients share one broker | Exit only the WSL client, then operate from Windows | Windows continues through the same PID and epoch | Windows stream and broker identity | not run: paired host required | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B12 | Windows and WSL clients share one broker | Exit only the Windows client, then operate from WSL | WSL continues through the proxy and the same Windows PID and epoch | WSL stream and broker identity | not run: paired host required | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B13 | WSL client disconnected; Windows broker has a live Windows client or extension | Terminate only the test WSL distribution session | The Windows broker remains alive and usable | Windows process and operation read-back | not run: paired host required | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B14 | Fresh verified bundle and endpoint | Corrupt isolated copies of the endpoint token and bundle | Bad authentication is refused and altered payload fails before execution | Named errors and unchanged live bundle hash; delete isolated copies | not run: paired host required | Not-Needed: Windows-only packaging seam | not run: paired WSL client required | Not-Needed: Windows-only packaging seam |
| B15 | Broker running with owned resources | Terminate only that broker process and reconnect both clients | One new Windows PID and epoch appear; rediscovered leases are orphaned | Before/after identity and registry | not run: paired host required | Not-Needed: no cross-OS seam | not run: paired WSL client required | Not-Needed: no cross-OS seam |
| B16 | Isolated stale and corrupt endpoint copies | Start both clients through the normal launcher | Startup rejects corrupt identity and safely recovers stale state without trusting its token | Named result, one Windows process and clean identity | not run: paired host required | Not-Needed: Windows-only packaging seam | not run: paired WSL client required | Not-Needed: Windows-only packaging seam |
| B17 | Isolated WSL environment with Windows interop unavailable | Request browser status | A named interop remedy returns and no Linux/WSL broker starts | Error stream and process listing | not run: paired host required | Not-Needed: WSL-only negative seam | Not-Needed: proved by paired WSL row | Not-Needed: WSL-only negative seam |

## Part C: composed-tree actionability and browser typing

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| C01 | Owned target on the harness page | Click and type through one and nested open shadow roots | Each mutation succeeds and the DOM event record confirms the exact target and value | Client JSON and redacted event metadata; clear fields | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| C02 | C01 targets covered by document and nested-shadow overlays | Repeat click and type | Each action fails as covered and no page state changes | Error results and unchanged DOM record; remove overlays | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| C03 | Instrumented plain field | Run `fill`, fast `type`, and `type(human=true)` | Fill and fast type keep bulk behavior; human type emits ordered key events with varied intervals and exact read-back | Event kinds, intervals, counts, and hashes only; never field text | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| C04 | Debounce, typeahead, validation, counter, Unicode, timeout, cancellation, and mismatch controls | Drive each human-typing branch while a second client uses another window | Intermediate states occur; the other client stays responsive; invalid and deadline cases mutate nothing; fallback is counted; cancellation skips submit; mismatch never duplicates the whole string | Both streams and redacted event metadata; reset page | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |

## Part D: pixel typing

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| D01 | Native event-recording field focused | Run fast `type_text` and named-profile human `type_text` | Fast mode stays compatible; human mode emits ordered varied input and exact final text | Native event record with text removed; clear field | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| D02 | D01 field focused | Run custom WPM plus IKI-CV, including zero variation | Planned and achieved metadata are valid; zero variation is constant control | Timing metadata only; clear field | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| D03 | D01 field focused | Try invalid option combinations and a deadline shorter than the plan | Each fails before input and leaves the field unchanged | Error results and independent field read-back | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| D04 | D01 field focused | Cancel during human input and exercise supported Unicode or fallback | Modifiers are released, progress count is truthful, exact text or named fallback is reported, and no whole-string retry occurs | Event record with text removed; release keys and clear field | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| D05 | Human pixel typing active in one client | Start a second pixel keyboard action | The product makes no parallel-safety claim; evidence records machine-global serialization or conflict behavior exactly | Both streams; stop both operations and release keys | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |

## Part E: packaged and clean delivery

| id | precondition and setup | action or goal | expected observable and oracle | evidence and cleanup | WSL | Linux | Windows | macOS |
|---|---|---|---|---|---|---|---|---|
| E01 | Fresh environment outside checkout | Install only the built wheel and start `vadgr-cua` through its entry point | Version is 0.7.6, readiness succeeds, and source checkout is absent from import paths | Install log, path, version, wheel hash; remove environment | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| E02 | Matching store-equivalent extension and installed wheel | Run one owned-window browser read, one human browser type, and one human pixel type | The installed package and matching extension execute the released behavior | MCP JSON with input text removed; close test state | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| E03 | `vadgr 0.5.0` release vehicle exists | Install the vehicle and run its bundled CUA proof | The bundled runtime reports and executes CUA 0.7.6 without a separate CUA or system Python | Filed by the `vadgr 0.5.0` runbook | blocked: vadgr 0.5.0 is not built | blocked: vadgr 0.5.0 is not built | blocked: vadgr 0.5.0 is not built | blocked: vadgr 0.5.0 is not built |

## Per-OS results

| part | WSL | Linux | Windows | macOS |
|---|---|---|---|---|
| A: recovery and setup diagnosis | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| B: shared broker and target ownership | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| C: actionability and browser typing | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| D: pixel typing | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |
| E: packaged and clean delivery | blocked: E03 awaits vadgr 0.5.0 | blocked: E03 awaits vadgr 0.5.0 | blocked: E03 awaits vadgr 0.5.0 | blocked: E03 awaits vadgr 0.5.0 |
| overall | not run: awaits local execution | not run: remote host | not run: remote host | not run: remote host |

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

None recorded before execution.
