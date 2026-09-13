# 0.7.8 - released browser broker upgrade handoff: e2e runbook

> **vadgr-computer-use 0.7.8 implementation:** branch
> `feature/0.7.8-broker-upgrade-handoff`; tested product source head
> `20549f5ee03a02e9650e3f06e68d9d4904ed5694`. **vadgr-computer-use 0.7.8
> evidence:** `https://github.com/MONTBRAIN/vadgr-docs/pull/164`.

Read this file and [`../README.md`](../README.md) completely before any live
cell. Build the exact branch-head wheel and install it without editable mode in
a fresh environment outside the checkout. The MCP configuration must call that
environment's `vadgr-cua` entry point.

> **Status: not run.** Native Windows must run W1-W9 and R1. WSL must run
> S1-S3 and R1. Linux and macOS are Not-Needed for live cells because the new
> process handoff exists only in the packaged Windows broker. Their complete
> automated suites remain required.

## Rules

1. Run owner-dependent cells before unattended cells.
2. Continue each host pass until every cell has a verdict or a named blocker.
3. Reproduce a failure before diagnosis. Fix a confirmed defect, add a test
   that fails without the fix, rebuild, and rerun each invalidated cell.
4. Start every released predecessor from its immutable published wheel.
5. A held lock or launched process is not readiness. Prove an authenticated
   connection to the exact candidate identity.
6. Never dispatch the candidate browser action before the handoff completes.
7. Never toggle, reload, update, enable or disable the extension. Never restart
   Chrome as an upgrade remedy.
8. Never kill by process name or PID alone. Preserve an unknown process and its
   state.
9. Run one product command at a time and read its exit code.
10. File raw evidence while each group runs. Never reconstruct evidence.
11. Never record endpoint tokens, credentials, typed values, owner paths or
    full process command lines.
12. Change no host DNS, firewall, route, proxy, VPN, adapter or network service.
13. Use only isolated browser, home, application-data and broker-state roots.
14. Use versioned Chrome for Testing with a fresh profile and the matching
    unpacked development extension. Never use the owner's normal browser.
15. Drive R1 through the selected subscription-authenticated agent CLI. Do not
    use a provider API key solely for this E2E.
16. Confirm evidence and results are committed and pushed before cleanup.

## Owner and environment requirements

Tell the owner about all required actions before the affected group begins.

| Requirement | Cells | Owner action | Cost and cleanup |
|---|---|---|---|
| Native Windows interactive session | W1-W9, R1 | Keep the Windows host available | Stop only isolated test processes |
| WSL with Windows executable interop | S1-S3, R1 | Keep this WSL distribution available | Remove only isolated WSL and Windows roots |
| Chrome for Testing and development extension | R1 | Approve the unpacked extension only if the isolated browser asks | No account or sync; remove its test profile |
| Authenticated Codex or Claude Code CLI | R1 | Keep the existing subscription login available | No provider API key or paid-extra enablement |

No phone, elevation, host restart, account login, privacy-setting change or
network change is required. Each fault helper can mutate only a validated path
below the recorded isolated root.

## Subscription driver selection

Before R1, run `python scripts/select_cua_e2e_driver.py`. Use the CLI, model and
effort selected by the current repository policy. Record the safe allowance
result and CLI version. Do not silently substitute a model or use API billing.

## Paired surfaces

| Repository | Released surface | Use in this pass |
|---|---|---|
| none | not applicable | The installed CUA entry point, packaged Windows broker and development extension form the complete surface |

## Browser isolation

R1 uses a pinned Chrome for Testing executable, a new profile and the matching
candidate extension build. Record its version, download URL, archive hash,
executable, profile root and extension hash. The profile contains only local
fixtures. No cell attaches to an installed Chrome, Chromium or Edge profile.

On WSL, run the Windows Chrome for Testing build with the extension built in a
Windows checkout. Do not load a WSL path into Windows Chrome. Keep this pass's
profile, debugging endpoint, processes and extension state separate from all
other passes.

## Persistent helper lifecycle

The process, lock, discovery record, bundle, candidate guard and authenticated
client form one state machine. The harness records only safe metadata: release,
artifact hash, PID, Windows creation identity, epoch, bundle hash, proof flags,
lock state, public result and error code. It never records a token.

Fault injection operates only below isolated user and application-data roots.
The helper validates those roots and recorded processes before each action. It
cannot delete, replace, stop or inspect an owner broker.

## Setup and identity

Record the OS versions, branch, exact commit, wheel SHA-256, installed package
version, resolved `vadgr-cua` path, candidate broker manifest and archive hashes,
frozen predecessor catalog hash, proxy hash, extension hash, Chrome for Testing
version, agent CLI and CLI version.

Download the exact `0.7.6` and `0.7.7` wheels from their immutable GitHub
releases. Verify these SHA-256 values before use:

| Release | Wheel SHA-256 | Embedded Windows broker archive SHA-256 |
|---|---|---|
| `0.7.6` | `3b1d431ce2d287ab5c5c5c0cf2b0975e72d4072665b97e85a36cd88586d525b5` | `fd2c57b76f57d06d3df3d7c964fa544b798e8f32ec460470bf326a46140696df` |
| `0.7.7` | `e982062875efd5e3e12ca61e1de15d2f5b41c8349f9067330b75136e10172b82` | `1745cc86a52413d4802ffda0db07266aa8890e7be447e7b475bbbd4e60ee260c` |

Create separate absolute build, candidate-install, predecessor-install,
browser-profile, Windows application-data, WSL home and evidence roots. Build
one candidate wheel. Install every wheel without editable mode. Drive only the
installed `vadgr-cua` command from outside the source checkout.

Capture safe metadata for normal owner registrations before and after. Do not
read their contents. Stop if an isolated child changes them.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| W: native Windows released upgrades | two releases, three discovery states, race, unknown owner, active request | 9 | 0 | 9 |
| S: WSL released upgrades | two releases, missing or corrupt discovery, unknown owner | 3 | 0 | 3 |
| R: candidate browser operation | native Windows and WSL, two inactive owned targets | 1 | 0 | 1 |
| | | **13** | **0** | **13** |

## Part W: native Windows released broker upgrades

| # | Precondition and setup | Goal or action | Expected observable and machine oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| W1 | Exact released `0.7.6` broker is healthy in an isolated root with valid discovery | Start one installed candidate client and request readiness | Candidate proves and replaces that process, publishes one candidate epoch, and authenticates with no manual browser action | Both artifact hashes, proof flags, old and new identities, public result and exit codes | Keep candidate for post-check, then stop only recorded processes | not run: native Windows execution required |
| W2 | Exact released `0.7.6` broker owns the isolated lock; remove only its validated discovery | Request candidate readiness | Candidate proves the predecessor from protected lock and process identity, replaces it, and authenticates | Mutation record, proof flags, process delta, candidate identity and result | Stop only recorded processes; restore through a clean setup | not run: native Windows execution required |
| W3 | Exact released `0.7.6` broker owns the isolated lock; replace only its discovery with invalid JSON under safe permissions | Request candidate readiness | Candidate does not trust corrupt discovery, proves the predecessor independently, replaces it, and authenticates | Corrupt hash, proof flags, process delta and public result | Stop only recorded processes; remove the isolated corrupt record | not run: native Windows execution required |
| W4 | Exact released `0.7.7` broker is healthy in a fresh isolated root | Start one installed candidate client and request readiness | The same automatic handoff path replaces it and authenticates one candidate | Both artifact hashes, proof flags, identities and exit codes | Stop only recorded processes | not run: native Windows execution required |
| W5 | Exact released `0.7.7` broker owns the isolated lock; remove only its validated discovery | Request candidate readiness | Candidate proves the predecessor from the lock and Windows process handle, then authenticates | Mutation record, proof flags, process delta and result | Stop only recorded processes | not run: native Windows execution required |
| W6 | Exact released `0.7.7` broker owns the isolated lock; corrupt only its validated discovery | Request candidate readiness | Candidate rejects the record, proves the exact predecessor by other facts, replaces it, and authenticates | Corrupt hash, proof flags, identities and public result | Stop only recorded processes; remove isolated state | not run: native Windows execution required |
| W7 | Exact released predecessor is live; two installed candidate clients wait behind one isolated candidate guard | Start both candidate readiness requests together | One verified replacement and one candidate broker occur; both clients authenticate to one PID, creation identity and epoch | Both streams, guard timing, process count and exact shared identity | Close clients; stop only their broker | not run: native Windows execution required |
| W8 | A synthetic isolated process has the broker filename and path shape but an unknown payload hash | Request candidate readiness | `browser_broker_upgrade_unsafe`; the exact synthetic process, lock and files remain unchanged; no candidate action dispatches | Before and after handles, hashes, process state, public code and dispatch count | Stop the synthetic process through its harness owner | not run: native Windows execution required |
| W9 | Exact released predecessor runs one instrumented active operation; a candidate request waits | Start candidate handoff while the old operation is active | Old client gets the existing uncertain-result failure without replay; candidate dispatch count remains zero until replacement authenticates | Old and new streams, operation count, timing, identities and final read-back | Stop only recorded processes and fixture | not run: native Windows execution required |

## Part S: WSL to Windows released broker upgrades

| # | Precondition and setup | Goal or action | Expected observable and machine oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | Exact released `0.7.6` Windows broker owns isolated state; discovery is removed; Windows interop control succeeds | From WSL, run the installed candidate and request readiness | The candidate Windows helper proves and replaces the predecessor; WSL authenticates to the new identity; no WSL endpoint copy appears | Interop control, hashes, proof flags, old and new identities, public result and absence scan | Stop only recorded processes; remove isolated roots | not run: WSL live execution required |
| S2 | Exact released `0.7.7` Windows broker owns isolated state; discovery is corrupt; interop control succeeds | From WSL, run the installed candidate and request readiness | Automatic Windows handoff completes and WSL authenticates without an interop or network remedy | Interop control, corrupt hash, proof flags, identities and result | Stop only recorded processes; remove isolated roots | not run: WSL live execution required |
| S3 | Synthetic unknown Windows lock owner exists only in the isolated root; interop control succeeds | From WSL, request candidate readiness | `browser_broker_upgrade_unsafe`; process and state remain unchanged; no interop, DNS, firewall or network remedy appears | Public code and remedy, before and after state, process identity and dispatch count | Stop the synthetic process through its harness owner | not run: WSL live execution required |

## Part R: post-handoff browser isolation

| # | Precondition and setup | Goal or action | Expected observable and machine oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| R1 | Candidate is ready after a released handoff; isolated Chrome for Testing has two agent-owned inactive fixture tabs | Run one native Windows client and one WSL client in parallel; each mutates and reads only its owned target without activation | Both structured streams name the expected target and candidate identity; DOM reads show one exact mutation per target; focus and decoys do not change | Driver selection, streams, leases, broker identity, DOM and focus read-backs | Release leases; stop only test broker and Chrome for Testing | not run: native Windows and WSL live execution required |

## Remote-host handoff

Each host first reads `AGENTS.md`, `E2E/README.md`, this runbook, `README.md`
and the browser setup instructions. It fetches the named implementation branch,
checks the exact sealed head, builds `python -m build --wheel`, records the wheel
hash, and installs it into a new virtual environment outside the checkout.

Native Windows executes W1-W9 and its half of R1 without WSL. WSL executes
S1-S3 and its half of R1 through working Windows executable interop. Each host
uses the committed harness and installed public command. A helper can prepare
or observe state but cannot replace the product command or agent goal.

Each host records `vadgr-cua doctor` before its first agent task. R1 uses the
existing interactive CLI login with `codex --yolo` or Claude Code
`--dangerously-skip-permissions`, as selected by repository policy. It reads no
provider API key. Each host runs the secret check before commits and evidence
boundaries.

## Automated gate

Run the complete Python suite, scientific tests, script tests, type checks,
lint, extension tests, Windows bundle check, clean-install smoke and every
repository workflow command. Native Windows must also build the pinned broker
bundle and run its smoke and installer regression tests. Linux and macOS run
the full automated suite because shared client and protocol files change.

The pull request checks must finish before the pass closes. CI does not replace
a live cell.

## Repeatability

The released transition is independent by release, operating system and
injected state. Compare process identities, proof flags, error codes, dispatch
counts and target read-backs. Do not compare agent prose.

## Per-OS results

| Part | WSL | Linux | Windows native | macOS |
|---|---|---|---|---|
| W: native Windows released upgrades | Not-Needed: native Windows owns these process states | Not-Needed: no Windows broker | not run: W1-W9 require native Windows | Not-Needed: no Windows broker |
| S: WSL released upgrades | not run: S1-S3 require WSL live execution | Not-Needed: no WSL-to-Windows path | Not-Needed: WSL origin is required | Not-Needed: no WSL-to-Windows path |
| R: candidate browser operation | not run: WSL half of R1 requires live execution | Not-Needed: no POSIX broker lifecycle change | not run: native Windows half of R1 requires live execution | Not-Needed: no POSIX broker lifecycle change |
| **overall** | **not run: S1-S3 and R1 are open** | **Not-Needed: Windows packaged-broker patch** | **not run: W1-W9 and R1 are open** | **Not-Needed: Windows packaged-broker patch** |

If implementation changes the POSIX broker lifecycle, Linux and macOS lose
their Not-Needed verdicts. Add and run equivalent released-transition cells
before the implementation pull request opens.

## Evidence

Before the first live cell, create one private evidence branch from fresh docs
`master` and open one evidence pull request. File each group under
`e2e_evidence/vadgr-computer-use-0.7.8/<date>-<host>/` while it runs.

Each boundary contains raw command output with exit codes, candidate and
predecessor hashes, safe lifecycle metadata, structured agent streams and
independent read-backs. Redact endpoint tokens, credentials, typed values, owner
paths and command lines. Run the evidence checker and secret scan before each
evidence commit.

## Cleanup

Confirm the runbook and evidence are committed and pushed. Stop only recorded
test clients, broker processes, proxy children and Chrome for Testing processes.
Prove their PIDs exited. Remove only validated isolated build, install, profile,
home, application-data and evidence staging roots. Preserve source, Git,
configuration, credentials, owner registrations and every uncommitted file.

Run the repository's post-E2E cleanup after each host finishes its cells. Report
reclaimed space. Never change or compact a mounted WSL virtual disk.

## Findings

No implementation finding is recorded yet.

## What this runbook cannot prove

This runbook does not prove a future broker version that is absent from the
frozen catalog. It does not prove an incompatible extension protocol update.
It does not prove a POSIX broker transition because this patch does not change
that path.
