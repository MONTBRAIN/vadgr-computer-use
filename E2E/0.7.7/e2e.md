# 0.7.7 - browser broker discovery recovery: e2e runbook

> **vadgr-computer-use 0.7.7 implementation:**
> `fix/0.7.7-browser-broker-recovery`; seal the exact product head before the
> first live cell.
> **vadgr-computer-use 0.7.7 evidence PR:**
> resolve the single private evidence PR before the first live cell.

Read this file and [`../README.md`](../README.md) completely before any live
cell. Build the exact branch-head wheel and install it without editable mode in
a fresh environment outside the checkout. The MCP configuration must call that
environment's `vadgr-cua` entry point.

> **Status: not run.** The runbook is complete before implementation. Product
> head, installed identity, evidence PR and results are sealed before execution.

## The rules

1. Run owner-dependent cells before unattended cells.
2. Continue each host pass until every cell has a verdict or named blocker.
3. Reproduce and fix a product failure, add a regression test, rebuild, then
   rerun every invalidated cell.
4. A held lock, process, file or successful proxy launch is not readiness.
   Readiness requires an authenticated independent connection.
5. Run one product command at a time and read its exit code before continuing.
6. File raw evidence while each group runs. Never reconstruct it afterward.
7. Never record endpoint tokens, credentials, typed values or owner paths.
8. Change no host DNS, firewall, route, proxy, VPN, adapter or network service.
9. Use only isolated browser, home, application-data and broker-state roots.
10. Do not kill an uncertain process or delete uncertain state. Stop only
    recorded test processes and remove only validated test roots.
11. Use versioned Chrome for Testing, a fresh profile and the matching unpacked
    development extension. Never use the owner's normal browser profile.
12. Drive live goals through the current session's authenticated CLI with its
    permission bypass. Do not use a provider API key solely for this E2E.
13. Use the current CUA driver-selection rule. Record the selected CLI, model,
    effort and allowance result before each agent group.
14. A browser mutation passes only with a structured result and independent DOM
    read-back from the instrumented fixture.
15. Confirm evidence and the runbook result are committed and pushed before
    cleanup.

## Owner and environment requirements

Tell the owner about all required actions before the affected group begins.

| Requirement | Cells | Owner action | Cost and cleanup |
|---|---|---|---|
| Native Windows interactive session | W1-W6, R1 | Keep the existing Windows host available | Stop only isolated test brokers and Chrome for Testing |
| WSL with Windows interop | S1-S4, R1 | Keep the existing WSL distribution available | Remove only isolated WSL and Windows test roots |
| Chrome for Testing and development extension | R1 | Approve the unpacked extension only if the isolated browser asks | No browser account or sync; remove its test profile |
| Authenticated Codex or Claude Code CLI | R1 | Keep the current subscription login available | No provider API key or paid-extra enablement |

No phone, elevation, host suspend, account login, privacy-setting change or
network change is required. The fault fixtures may mutate only paths below the
recorded isolated application-data root.

## Subscription driver model selection

Before R1, run `python scripts/select_cua_e2e_driver.py`. Use the CLI and model
that the current repository policy selects. Record its safe allowance result,
CLI version, model and effort. Do not silently substitute another model or use
API billing.

## Paired surfaces this pass depends on

| Repository | Released surface | Use in this pass |
|---|---|---|
| none | not applicable | The installed CUA entry point, packaged Windows broker and development extension form the whole tested surface |

## Browser isolation

R1 uses a pinned Chrome for Testing executable, a new profile directory and the
matching development extension from the candidate. Record executable version,
profile root and extension hash. The profile contains only local instrumented
fixtures. No cell attaches to a normal Chrome, Chromium or Edge process.

## Persistent helper lifecycle recovery

The helper is one state machine across process, startup lock, endpoint record,
bundle and client connection. The harness records safe metadata only: PID,
process start identity, epoch, bundle hash, lock state, endpoint state, public
status and error code. It never records the endpoint token.

Fault injection operates only below isolated home and application-data roots.
It cannot delete, replace, stop or inspect an owner broker. The harness validates
the root and recorded PID before every mutation.

## Setup and identity

Record OS versions, branch, exact commit, wheel SHA-256, installed distribution
version, resolved `vadgr-cua` path, packaged broker manifest and archive hashes,
proxy hash, extension hash, Chrome for Testing version, agent CLI and CLI version.

Create separate absolute build, install, browser-profile, Windows application
data, WSL home and evidence roots. Build one wheel. Install it without editable
mode. Build and verify the packaged Windows broker through the repository's
normal scripts. Point every test child at the isolated roots before startup.

Capture metadata for normal owner registrations before and after without reading
their contents. Stop if an isolated child changes them.

## Coverage

The lifecycle axis crosses process state (absent, live, dead), discovery state
(absent, valid, corrupt, stale), lock state (free, held), client origin (Windows,
WSL), bundle state (matching, mismatched) and result (attach, exact failure).
Impossible or redundant products collapse into the eleven named cells below.

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| W: Windows lifecycle | clean, concurrent, missing, corrupt, stale, mismatch | 6 | 0 | 6 |
| S: WSL proxy diagnosis | clean, missing, failed repair, failed interop | 4 | 0 | 4 |
| R: recovered browser isolation | Windows and WSL clients, separate inactive targets | 1 | 0 | 1 |
| | | **11** | **0** | **11** |

## Part W: native Windows broker lifecycle

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| W1 | No broker, lock or endpoint in isolated Windows application data | Start one installed client and request readiness | One broker owns the lock, atomically publishes a matching endpoint, and an independent authenticated probe confirms PID, start identity, epoch and bundle | Candidate identity, safe state transitions, probe result and exit codes | Keep the broker for W2 | not run: candidate not sealed |
| W2 | W1 broker is live; two clients start concurrently | Both clients request readiness | Both attach to the W1 PID and epoch; one held lock never becomes false success; one broker exists | Both client results, identities, timing and process count | Close the second client; keep the broker | not run: candidate not sealed |
| W3 | W1 broker and first client remain live; harness validates then removes only the isolated endpoint | A new client requests readiness | The same broker republishes atomically with the same PID, start identity and epoch; old and new clients remain usable | Before/after safe endpoint metadata, identities and client probes | Keep the repaired broker | not run: candidate not sealed |
| W4 | Live isolated broker; harness replaces only its endpoint with invalid JSON and safe permissions | A new client requests readiness | The owner replaces the corrupt record atomically and authenticates, or returns `browser_broker_discovery_invalid`; no temporary record remains | Corrupt fixture hash, transitions, result code and process identity | Restore through product recovery; keep only a healthy broker | not run: candidate not sealed |
| W5 | Stop only the recorded isolated broker; leave its endpoint record; prove PID exit and lock release | A new client requests readiness | One contender validates stale discovery, starts one new PID and epoch, publishes and authenticates; it changes no unrelated state | Old/new identities, lock transition, process count and metadata comparison | Keep the new broker for W6 | not run: candidate not sealed |
| W6 | Isolated discovery or helper reports a verified bundle different from the installed candidate | Request readiness | Product follows its bounded update rule or returns `browser_broker_bundle_mismatch` before attach; it never accepts the mismatch | Expected/observed hashes, public code and process list | Restore matching isolated bundle | not run: candidate not sealed |

## Part S: WSL to Windows proxy and diagnosis

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | Matching isolated Windows broker; WSL client invokes installed entry point through the packaged proxy | Request readiness from WSL | WSL authenticates to the Windows PID and epoch; no endpoint token or endpoint file appears in WSL storage | WSL stream, proxy exit, broker identity and absence scan | Keep broker and client for S2 | not run: candidate not sealed |
| S2 | S1 broker remains live; remove only its validated isolated Windows endpoint | A second WSL client requests readiness | Same PID, start identity and epoch republish; both WSL clients attach and remain usable | Before/after safe metadata and both probes | Keep repaired broker | not run: candidate not sealed |
| S3 | Child-only fixture prevents the isolated broker from repairing discovery while interop still launches Windows commands | Request readiness from WSL | Exact broker discovery or startup error appears; no Windows-interop, DNS, firewall or network remedy appears | Interop control exit, public error and negative remedy scan | Disarm fixture and prove recovery | not run: candidate not sealed |
| S4 | Child-only test shim makes proxy launch unavailable without changing host interop | Request readiness from WSL | Only `windows_interop_unavailable` and its matching remedy appear; no broker or browser action dispatch occurs | Shim identity, public result and dispatch count | Remove the shim and prove S1 path again | not run: candidate not sealed |

## Part R: post-recovery browser operation

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| R1 | S2 recovery completed; isolated Chrome for Testing has two client-owned windows with separate inactive fixture tabs | Two parallel agent clients each update and read its own target without focusing either window | Both structured streams name the expected client and target; DOM oracle shows one exact mutation per target; focus stays unchanged; no cross-route occurs | Driver selection, both streams, broker identity, target leases, DOM and focus read-backs | Release leases; stop test broker and Chrome; remove validated roots after filing | not run: candidate not sealed |

## Per-OS results

| Part | WSL | Linux | Windows native | macOS |
|---|---|---|---|---|
| W: Windows lifecycle | Not-Needed: native Windows owns the packaged broker state | Not-Needed: no Windows packaged helper | not run | Not-Needed: no Windows packaged helper |
| S: WSL proxy diagnosis | not run | Not-Needed: no WSL-to-Windows proxy | Not-Needed: WSL origin is required | Not-Needed: no WSL-to-Windows proxy |
| R: recovered browser isolation | not run | Not-Needed: the patch does not change the POSIX broker lifecycle | not run | Not-Needed: the patch does not change the POSIX broker lifecycle |
| **overall** | **not run** | **Not-Needed: Windows packaged-helper patch** | **not run** | **Not-Needed: Windows packaged-helper patch** |

If implementation changes the POSIX lifecycle path, Linux and macOS lose their
`Not-Needed` verdicts. Add and run their missing-discovery and stale-state cells
before opening the implementation PR.

## Evidence

Before the first live cell, create the one private branch
`evidence/vadgr-computer-use-0.7.7` from fresh docs `master` and open its pull
request. File each group under
`e2e_evidence/vadgr-computer-use-0.7.7/<date>-<host>/` while it runs.

Each boundary contains raw command output with exit codes, candidate hashes,
safe lifecycle metadata, structured agent streams and independent read-backs.
Redact endpoint tokens, credentials, typed values and owner paths. Run the docs
evidence checker and secret scan before every evidence commit.

## Cleanup

Confirm the runbook and evidence are committed and pushed. Stop only recorded
test clients, broker processes, proxy children and Chrome for Testing processes.
Prove their PIDs exited. Remove only validated isolated build, install, profile,
home, application-data and evidence staging roots. Preserve source, Git,
configuration, credentials, owner registrations and every uncommitted file.

Run the repository's post-E2E cleanup after every host finishes all its cells.
Report reclaimed space. Never change or compact a mounted WSL virtual disk.

## Findings

No execution has started. Record reproduced findings, the failing cell, root
cause, fix commit, regression test and every invalidated cell here as work runs.
