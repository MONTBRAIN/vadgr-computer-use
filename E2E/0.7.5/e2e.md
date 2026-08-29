# 0.7.5 - platform identity without a desktop backend: patch cell

> **vadgr-computer-use 0.7.5 implementation:**
> `fix/0.7.5-platform-probe` at product commit `c80a0a4` before the first
> live cell.
> **vadgr-computer-use 0.7.5 evidence PR:** private evidence PR #129.

> Read this file and [`../README.md`](../README.md) completely before running
> the cell. Invoke the installed entry point over its MCP wire; never replace
> it with a Python import or the checkout.

`get_platform` reports the detected operating system even when the host has no
available capture/input backend. This patch changes no mutating tool, native
backend, path, socket, permission or machine configuration.

> **Status: not started.** Automated gate: 916 passed, 14 skipped; ruff green.
> The live WSL patch cell is owed. **One finding repaired:** released 0.7.4
> constructed the unavailable WSL desktop backend before answering the identity
> probe.

## The rules

1. Build the exact product commit as a wheel and install it without editable
   mode in a new virtual environment outside the checkout.
2. Point the detected agent CLI's isolated MCP configuration at that
   environment's `vadgr-cua` entry point and record the CLI/version, command
   path, wheel hash and Git head.
3. Give the agent a goal, not a prescribed tool call. The captured `tool_use`
   and `tool_result` stream is the verdict; prose is not evidence.
4. Run one command at a time, file raw output into private evidence PR #129 at
   the cell boundary, and run secret/attribution checks before commits.
5. Change no host firewall, DNS, route, proxy, VPN, service, backend or desktop
   permission. Clean up only the temporary build/install/config roots.

## Owner and environment requirements

| Requirement | Cell | Availability | Cost and cleanup |
|---|---|---|---|
| Real WSL2 host whose cua backend reports unavailable | P1 | `vadgr-cua doctor` records `platform: wsl2` and no usable backend | read-only; remove temporary roots |
| Codex or Claude Code already authenticated | P1 | record resolved CLI and version without credentials | one short model turn; no provider secret enters evidence |

No owner click, credential entry, device, elevation, application, destructive
machine action or permission grant is required.

## Setup

Create new absolute temporary build, install and working directories. From the
recorded checkout head, build a wheel with `python -m build --wheel`, hash it,
create a separate virtual environment, and install that wheel without editable
mode. From outside the checkout, record the installed `vadgr-cua` path/version
and run `vadgr-cua doctor`; the unavailable backend is the precondition, not a
failure.

Create an isolated agent configuration containing exactly one MCP server whose
command is the installed environment's absolute `vadgr-cua` path and whose
arguments select stdio transport. Run the detected agent CLI headlessly with
its structured event stream captured verbatim. The goal is:

```text
Determine which operating system this computer-use server detects. Use the
computer-use tools and report only the detected platform.
```

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| P: backend-independent platform probe | WSL2 x unavailable backend x MCP wire | 1 | 0 | 1 |
| | | **1** | **0** | **1** |

## Part P: backend-independent platform probe

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| P1 | Exact `c80a0a4` wheel installed outside checkout; `doctor` detects WSL2 and reports the desktop backend unavailable; agent MCP config invokes installed `vadgr-cua` | Give the headless agent the goal above | Event stream contains exactly one `computer-use__get_platform` `tool_use`; matching `tool_result` is not an error and contains `wsl2`. Server stderr has no backend construction or `PlatformNotSupportedError` | Git head, wheel hash, installed path/version, doctor JSON, CLI/version, full agent stream and server stderr | stop only that MCP child; remove temporary roots after evidence is filed | not run: repaired wheel has not been driven yet |

## Per-OS results

| Part | WSL | Linux | Windows native | macOS |
|---|---|---|---|---|
| P: backend-independent platform probe | not run: repaired wheel has not been driven | not run: patch cell first runs on the reproducing WSL host | not run: patch cell first runs on the reproducing WSL host | not run: patch cell first runs on the reproducing WSL host |
| **overall** | **not run: repaired wheel has not been driven** | **not run: patch cell is WSL-first** | **not run: patch cell is WSL-first** | **not run: patch cell is WSL-first** |

## Evidence

File the raw P1 boundary under
`e2e_evidence/vadgr-computer-use-0.7.5/<date>-wsl/` on the single private
evidence branch and PR #129 while the cell runs. A typed summary cannot replace
the event stream. Stop the MCP child, prove it exited, run the secret scan, then
commit and push both the runbook result and evidence boundary.
