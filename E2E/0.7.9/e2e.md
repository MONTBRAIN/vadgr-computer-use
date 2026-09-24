# 0.7.9 - profile packaging and authenticated deployment: e2e runbook

> Status: not run: written before the first live cell.
> Implementation branch: `feature/0.7.9-profile-packaging`.
> Initial checkout: `575a1442f425fd2a1f97609ae0c52e5103acd80c`.
> Tested head: `8bc81e68cdbdb69524bb5d1738b2b764f6baf3dd`.
> Common evidence PR: `https://github.com/MONTBRAIN/vadgr-docs/pull/182`.
> No release, protected signing result or native pass is claimed.

Read this file, [E2E rules](../README.md), [template](../TEMPLATE.md), `AGENTS.md`,
`CLAUDE.md`, and the public README installation/platform instructions completely.

## The rules

Execute owner-dependent cells first. Drive the installed public entry point outside
the checkout. Agent JSON tool calls and independent read-backs determine verdicts.
A green suite is not a live pass. A negative tool call must return an error.
Keep each failed and fixed attempt at its own evidence boundary. Never invent
signatures, release IDs, usage counts, read-backs or results. Never change a cell
to match shipped behavior. A rebuild changes the subject: repeat identity checks
and all affected cells on each earlier passing host. One common evidence branch
serves every host. Missing prerequisites retain every written cell with its reason.
Never expose credentials, endpoint tokens or raw account responses. Do not change
host networking. Stop only proved test-owned processes and clean validated roots.
Finish the host's executable cells; do not stop merely to report progress.

## How a pass is run, before anything else in this file

Run P12 and P14 first, including their actual protected owner actions. Prepare
exact candidate identities, legal packet and quota preview before requesting approval.
Next complete protected platform permission setup for P03/P13. Then execute the
applicable P01 and P03-P13 cells. P02 is an external consumer handoff.
If authorization or signed fixtures are absent, record signing-dependent cells
blocked with the exact prerequisite. Continue every independent unsigned,
producer, profile and asset cell. Only an oracle that needs signed bytes remains
blocked. Address owner cells first; this does not globally stop independent work.
Do not retry an uncertain signing call: retain the spent claim and reconcile usage.

Run each product command separately, inspect its output and exit code, then choose
the next action. Helpers prepare fixtures, capture streams and parse artifacts;
they do not choose tool calls or replace a real agent. Create evidence directories
before action. Publish no implementation PR before the first native pass and green
branch checks. Resolve the tested commit and common evidence PR before any live
cell; replace the branch reference with the implementation PR URL before handoff.

## The approach: a headless agent CLI session

Use the CLI's existing subscription login. No provider API key is needed.
Before each live group run `python scripts/select_cua_e2e_driver.py`.
Read the ordinary machine-readable Codex 10,080-minute allowance, not a model quota.
At least 75 percent remaining selects Codex. Below 75 percent or a failed probe
selects Claude until a fresh post-reset probe qualifies Codex again. Record only
remaining percentage, reset/probe times, selected CLI/version, exact model and effort.
Recheck current official capability documentation and authenticated availability
on the execution date, including image-result continuation for visual cells.
An unavailable selected driver blocks the group; do not silently substitute.

Use the following command from the isolated working directory with the cell's
literal goal in `CUA_CELL_GOAL` and a per-pass MCP configuration:

```sh
codex --yolo exec --json --model gpt-6-luna -c 'model_reasoning_effort="medium"' --cd "$CUA_TEST_ROOT/work" "$CUA_CELL_GOAL"
claude --dangerously-skip-permissions --print --verbose --output-format stream-json --model claude-sonnet-5 --mcp-config "$CUA_TEST_ROOT/work/.mcp.json" "$CUA_CELL_GOAL"
```

The selected CLI's MCP entry invokes the absolute installed `vadgr-cua` with
`--transport stdio`. Keep the driver login environment separate from the product
child's isolated home/state. Capture the actual JSON stream and exit code into
the current cell boundary. Codex medium is the default; high needs a recorded reason.
Claude retains medium effort where supported. There are no billed API cells.

Generate the per-pass configuration before either driver command:

```sh
python E2E/0.7.9/harness/harness.py mcp-config --root "$CUA_TEST_ROOT" --entry "$CUA_INSTALLED_ENTRY"
```

Claude reads the resulting `.mcp.json`. Add the returned `codex_override_argv`
elements as distinct arguments to the Codex command above. They set the same
entry point, stdio arguments and isolated child environment without moving the
subscription login. Do not join the array into a shell command or use `eval`.
For WSL, review its explicit Windows-native state paths before startup.

## Paired surfaces this pass depends on

The MCP runtime calls no sibling product. P02 preserves the consuming application's
combined-install handoff IDs; its result never gates CUA source-only acceptance.
Signed helper fixtures are immutable approved inputs, not a requirement that
another minor release before this one. Their approval and identity remain mandatory.

| repository | released version | dependency |
|---|---|---|
| none | not applicable | installed CUA CLI and MCP are driven directly |

## The oracle is the JSON, never the agent's prose

Each cell boundary contains `agent.jsonl`, `exit.json`, `identity.json`,
`before.json`, `after.json`, and the exact machine artifacts its oracle names.
A mutation needs a structured result or independent machine read-back. An error
case needs a real error result. Missing stream and transcript means not verified.
A hash record does not prove a signature. A written expectation is not evidence.

## Owner and environment requirements

| requirement | cells | availability check | effect | cleanup |
|---|---|---|---|---|
| Protected signing and exact legal approval | P12, P14; signed prerequisites P03-P10/P13 | approved claim, quota and retained artifact IDs | vendor calls only after approval; no automatic retry | retain actual claims and reports |
| Two real signed held fixtures per architecture | P07, P05 reverse transitions | exact artifact/member identities and reviewed pair | no synthetic predecessor | retain immutable fixture identities |
| Native Windows x64 and ARM64 | windows cells, P09/P14 | actual native architecture and process headers | isolated processes only | stop proved owned processes |
| Matching WSL x64/ARM64 and Windows host | wsl cells, P09/P13 | Linux identity and successful Windows host proof | no host interop changes | isolated state only |
| Linux x64/ARM64; macOS Intel/ARM64 | P01/P02/P11 | native hardware and OS | independent native sessions | fresh environment only |
| Linux dependency elevation; macOS Accessibility/Screen Recording | Linux/macOS P01/P11 | installed entry point diagnosis | protected owner prompt first | preserve host dependencies |
| Chrome for Testing and matching extension | browser cells | exact version, download URL and archive hash | fresh profile, no sync | owned browser/profile only |
| Existing selected subscription login | agent cells | CLI version and authenticated availability | account usage; no invented API cost | never copy login files |
| Released 0.7.6/0.7.7/0.7.8 x64 wheels | P06 | exact retained hashes | test installation | prove process owner before stop |
| Clean tested head and common evidence branch | all cells | preflight | evidence writes only | preserve evidence |
| Fault injection and managed test uninstall | P04-P08/P10/P13 | marked contained test root | copied state only | restore each fixture at setup |
| Required signing values, if any, from owner-only ../.env | P12/P14 | named-variable presence and mode/DACL without values | never provider API keys for driver | never persist secrets |

## Billed model selection

| cells | auth | required capability | model | source/date | price | ceilings | escalation |
|---|---|---|---|---|---|---|---|
| agent cells | subscription login | MCP, multi-turn; image continuation for visuals | gpt-6-luna medium or claude-sonnet-5 medium | [OpenAI models](https://developers.openai.com/api/docs/models) and [Anthropic models](https://platform.claude.com/docs/en/models/overview), checked 2026-09-24; recheck before execution | not applicable: subscription driver | not applicable: subscription driver | selected driver unavailable blocks |

## Prerequisites (per OS)

Native Windows runs from PowerShell, not WSL. Record OS build, native architecture,
Python path, browser version and owner SID. WSL runs Linux Python and Windows
Chrome for Testing from a Windows path. Record both architecture proofs.
Linux records distro, desktop and display server. GNOME Wayland, GNOME X11,
KDE Plasma, minimal install, Sway and Hyprland each owe their own browser session.
macOS records native architecture and grants permissions to installed Python.

## Browser isolation

Use the native versioned archive from the
[official Chrome for Testing downloads](https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json).
Record exact version, URL and SHA-256. Unavailability blocks the cells.
Build `extension/` with `npm ci` then `npm run build`. Load only matching
`extension/dist`. WSL uses the Windows checkout extension, never a Linux path.
Never reuse owner cookies, profiles, settings, sync or extensions.

Each independent pass owns its browser PID/start identity, debugging endpoint and
fresh profile. Linux uses isolated home plus `.config/google-chrome`; macOS uses
isolated home plus `Library/Application Support/Google/Chrome`; Windows uses
`CUA_TEST_ROOT/browser-profile`. Run installed `vadgr-cua browser-setup` first.
Start Chrome for Testing with that exact `--user-data-dir`, `--no-first-run`
and matching `--load-extension` path. Require browser status `connected: true`.

## Persistent helper lifecycle recovery

P04 covers clean, concurrent, missing discovery, corrupt discovery, dead/stale and
disconnect/reconnect states separately on all four Windows-helper profiles.
P06 covers released mismatch, P07 signed mismatch, and P08 active work, unknown
owner, PID reuse and cancellation. Record process, lock, endpoint, registration
and bundle identity before and after. Generic error remedies fail exact-state cases.

## Setup

From the clean branch checkout, compare the supplied exact tested head:

```sh
git fetch origin feature/0.7.9-profile-packaging
git rev-parse HEAD
git status --short
python E2E/0.7.9/harness/harness.py init
python E2E/0.7.9/harness/harness.py status
```

Set `CUA_TEST_ROOT` to the returned absolute root. Keep evidence outside it.
Record free space on the physical backing volume and all build/output roots.
Capture metadata/hashes of normal host registrations and launcher wrappers before
startup; never copy credential-bearing contents.

The ordinary `python -m build` wheel is intentionally source-only. It contains no
native helper, verifier, adoption policy, PowerShell installer or helper archive,
and is a packaging gate rather than a live-cell subject. Never install it for P01
or relabel it as a profile wheel.

Linux/macOS install the exact retained, validated standalone profile wheel from
the trusted default-branch producer. Record its workflow run, artifact ID, archive
hash, wheel hash and catalog/attestation identities before extraction. With
`CUA_WHEEL` set to that verified wheel outside the checkout:

```sh
python3 -m venv "$CUA_TEST_ROOT/venv"
"$CUA_TEST_ROOT/venv/bin/python" -m pip install "$CUA_WHEEL"
shasum -a 256 "$CUA_WHEEL"
```

Native Windows normally uses that same retained, validated standalone profile
wheel. Before the implementation PR exists, P01-windows-x86_64 alone may instead
use the exact `unsigned-development-x86_64` artifact produced for the tested
feature-branch commit by `development-profile.yml`. Record the run and artifact
IDs, archive/wheel hashes and `development-receipt.json`; require its package trust
to say `development: true`, `publishable: false`, `signing: unsigned-input`, and
`adoption: disabled`. It is not valid for signing, publication, authenticated
adoption, or any oracle that requires signed bytes. Never build a substitute
locally. With `CUA_WHEEL` set to the verified retained wheel outside the checkout:

```powershell
py -m venv "$env:CUA_TEST_ROOT/venv"
& "$env:CUA_TEST_ROOT/venv/Scripts/python.exe" -m pip install "$env:CUA_WHEEL"
Get-FileHash -Algorithm SHA256 -LiteralPath "$env:CUA_WHEEL"
```

Missing native helpers, verifier or trust policy fail the build prerequisite;
do not relabel x64 assets. A development wheel intentionally lacks verifier and
adoption policy and must fail any adoption request explicitly. Profile cells
install the exact catalog-selected wheel with the same install command.
No editable install, product import or `python -m` product invocation is evidence.

Set the product child's HOME, USERPROFILE, APPDATA, LOCALAPPDATA, XDG_CONFIG_HOME
and XDG_STATE_HOME to appropriate subdirectories of the isolated root. Keep the
driver's normal login environment unchanged. Explicit browser/broker state paths
must also be isolated; WSL passes Windows-native appdata/discovery paths through
interop. Apply this environment even to doctor and setup. A venv alone is not isolation.

From the isolated working directory, execute the installed path once per command:

```sh
"$CUA_TEST_ROOT/venv/bin/vadgr-cua" --version
"$CUA_TEST_ROOT/venv/bin/vadgr-cua" install-deps --yes
"$CUA_TEST_ROOT/venv/bin/vadgr-cua" doctor
```

The middle command is native Linux only. Windows substitutes
`venv/Scripts/vadgr-cua.exe`. macOS completes protected permissions first.
Record normal-host registration metadata again; stop on unexpected changes.

```sh
python E2E/0.7.9/harness/harness.py preflight --root "$CUA_TEST_ROOT" --entry "$CUA_INSTALLED_ENTRY" --evidence "$CUA_EVIDENCE_ROOT" --head "$CUA_TESTED_HEAD" --evidence-pr "$CUA_EVIDENCE_PR"
python scripts/check_no_secrets.py --env-file ../.env
```

## Remote-host handoff for Linux, macOS and Windows

Read the five files at the top. Fetch the same branch and verify the exact tested
head. Build, hash and install with the native commands above. Use separate evidence
boundaries for OS, architecture, desktop and independent pass. Configure MCP with
the resolved installed entry point and isolated child environment, then run owner
cells first. Use the exact cell goals below and read the independent oracles.
Update each result with boundary, tested head, wheel hash, driver/version/model,
UTC time and observed verdict or precise blocker. Update only that host's matrix.

Missing ARM64 hardware blocks its native architecture cells. Missing signing
authorization blocks P12/P14 and signed fixtures. Missing a second real signed
fixture blocks P07. Missing interop blocks WSL positives; P10 observes the isolated
failure. Missing Chrome for Testing blocks browser cells. Missing authenticated
selected driver blocks agent cells. Record the actual probe behind each blocker.

## Automated gate (necessary, never sufficient)

```sh
python -m pytest scripts/tests/test_e2e_079_harness.py
python -m pytest computer_use/tests scripts/tests
python scripts/check_readme_touched.py --git-range HEAD
python scripts/check_no_ai_attribution.py E2E/0.7.9/e2e.md E2E/0.7.9/harness/harness.py README.md CHANGELOG.md
python E2E/0.7.9/harness/harness.py status
```

Read every command's output and exit code. Run clean-install checks outside the
checkout in a fresh environment. Wait for all final-head PR checks. Unit/CI success
never changes a live cell result.

## Coverage

P06: two execution profiles x three released predecessors x three discovery states
= 18 independent cells. P13: two architectures x two startup orders x four ordered
standalone/managed native-or-WSL pairs = 16 independent cells. P14 has two cells,
one per architecture. All 130 primary cells initially read not run.
P02 is an external combined-install handoff, excluded from CUA source acceptance.

## Part P12: signing transformation

### P12-windows-x86_64: signing transformation on windows-x86_64

**Precondition:** Exact legal approval, protected signing claim, native verifier and retained producer closure. No fabricated signed fixture.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Review the exact nested quota and preserved-member preview. After protected authorization consume real signed output. Rebuild ZIP twice from identical signed members. Deploy with authenticated final metadata; require old input metadata to fail. "

**Expected result:** Identical signed members give byte-identical ZIPs. Publisher signatures satisfy policy; preserved vendor bytes do not change. Only authenticated final hashes deploy.

**Verdict from the JSON:** Actual quota ledger, all independent native signature results, ZIP hashes, authenticated handshake and rejected old-manifest result; warning exit 2 fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P12-windows-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P12-windows-aarch64: signing transformation on windows-aarch64

**Precondition:** Exact legal approval, protected signing claim, native verifier and retained producer closure. No fabricated signed fixture.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Review the exact nested quota and preserved-member preview. After protected authorization consume real signed output. Rebuild ZIP twice from identical signed members. Deploy with authenticated final metadata; require old input metadata to fail. "

**Expected result:** Identical signed members give byte-identical ZIPs. Publisher signatures satisfy policy; preserved vendor bytes do not change. Only authenticated final hashes deploy.

**Verdict from the JSON:** Actual quota ledger, all independent native signature results, ZIP hashes, authenticated handshake and rejected old-manifest result; warning exit 2 fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P12-windows-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P12-wsl-x86_64: signing transformation on wsl-x86_64

**Precondition:** Exact legal approval, protected signing claim, native verifier and retained producer closure. No fabricated signed fixture.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Review the exact nested quota and preserved-member preview. After protected authorization consume real signed output. Rebuild ZIP twice from identical signed members. Deploy with authenticated final metadata; require old input metadata to fail. "

**Expected result:** Identical signed members give byte-identical ZIPs. Publisher signatures satisfy policy; preserved vendor bytes do not change. Only authenticated final hashes deploy.

**Verdict from the JSON:** Actual quota ledger, all independent native signature results, ZIP hashes, authenticated handshake and rejected old-manifest result; warning exit 2 fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P12-wsl-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P12-wsl-aarch64: signing transformation on wsl-aarch64

**Precondition:** Exact legal approval, protected signing claim, native verifier and retained producer closure. No fabricated signed fixture.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Review the exact nested quota and preserved-member preview. After protected authorization consume real signed output. Rebuild ZIP twice from identical signed members. Deploy with authenticated final metadata; require old input metadata to fail. "

**Expected result:** Identical signed members give byte-identical ZIPs. Publisher signatures satisfy policy; preserved vendor bytes do not change. Only authenticated final hashes deploy.

**Verdict from the JSON:** Actual quota ledger, all independent native signature results, ZIP hashes, authenticated handshake and rejected old-manifest result; warning exit 2 fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P12-wsl-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P14: shared helper authorization

### P14-x86_64: shared helper authorization on x86_64

**Precondition:** One approved architecture claim binds both consumer inputs; retained actual signed helper closure.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Consume one architecture-level protected signing output for both native Windows and WSL. Compare relay, ZIP and final manifest; verify separate receipts and quota ledger before qualification. Run all independent construction cases below. "

**Expected result:** One shared signing call set; byte-exact final equality; separate receipts bind the same manifest and authorization. Re-signed WSL output is rejected.

**Verdict from the JSON:** Immutable artifact IDs, SHA-256 lines, spent-claim ledger, verified receipt bodies and each construction rejection artifact.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P14-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P14-aarch64: shared helper authorization on aarch64

**Precondition:** One approved architecture claim binds both consumer inputs; retained actual signed helper closure.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Consume one architecture-level protected signing output for both native Windows and WSL. Compare relay, ZIP and final manifest; verify separate receipts and quota ledger before qualification. Run all independent construction cases below. "

**Expected result:** One shared signing call set; byte-exact final equality; separate receipts bind the same manifest and authorization. Re-signed WSL output is rejected.

**Verdict from the JSON:** Immutable artifact IDs, SHA-256 lines, spent-claim ledger, verified receipt bodies and each construction rejection artifact.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P14-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P01: standalone selection

For every P01 browser read-back, the agent creates the fixture through Tier 0
and the harness exposes that exact test-owned directory through a loopback-only
HTTP server. The agent opens the resulting `http://127.0.0.1:<port>/...` view.
Do not use `file://`: browser targets on the file scheme remain intentionally
restricted by the product, and browser file-access flags or permissions must
not weaken that security boundary for this cell.

### P01-windows-x86_64: standalone selection on windows-x86_64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open the harness-provided loopback browser view of that exact file, read its content, create another tab, edit its field and return to verify the first tab."

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-windows-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** pass on native Windows x86_64 at `b6a72a1a59d796dab4d2047838d4a3de8f5a31ac`. The exact unsigned development profile artifact from workflow run `35979374403` selected the Windows profile; Tier-0 file bytes and DOM read-backs agreed; the second-tab edit remained isolated; the first tab retained its original heading and value; and the installed entry point, Chrome for Testing, native host and browser broker were independently verified as AMD64. Attempts 1-10 and their failures/noise are retained; attempt 11 is the accepted zero-tool-error pass. Private evidence: vadgr-docs PR #182.

### P01-windows-aarch64: standalone selection on windows-aarch64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-windows-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-wsl-x86_64: standalone selection on wsl-x86_64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-wsl-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-wsl-aarch64: standalone selection on wsl-aarch64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-wsl-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-linux-x86_64: standalone selection on linux-x86_64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-linux-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-linux-aarch64: standalone selection on linux-aarch64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-linux-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-macos-x86_64: standalone selection on macos-x86_64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-macos-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P01-macos-aarch64: standalone selection on macos-aarch64

**Precondition:** Native host, exact installed standalone wheel, isolated Chrome for Testing and extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Identify the selected native profile. Create a text file using Tier 0; open it in a browser file view, read its content, create another tab, edit its field and return to verify the first tab. "

**Expected result:** Actual native OS/architecture selects the profile; independent file and DOM read-backs agree. Registration and process architecture match; Linux/macOS deploy no Windows helpers.

**Verdict from the JSON:** MCP file and browser results plus independent file hash, process executable architecture and registration hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P01-macos-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P02: managed clean install handoff

### P02-windows-x86_64: managed clean install handoff on windows-x86_64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-windows-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-windows-aarch64: managed clean install handoff on windows-aarch64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-windows-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-wsl-x86_64: managed clean install handoff on wsl-x86_64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-wsl-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-wsl-aarch64: managed clean install handoff on wsl-aarch64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-wsl-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-linux-x86_64: managed clean install handoff on linux-x86_64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-linux-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-linux-aarch64: managed clean install handoff on linux-aarch64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-linux-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-macos-x86_64: managed clean install handoff on macos-x86_64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-macos-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

### P02-macos-aarch64: managed clean install handoff on macos-aarch64

**Precondition:** External consuming-application qualification with exact held vehicle, compiled profile pins, closed lock and inventory.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact held vehicle on a clean native host without system Python. Launch CUA through its authenticated parent and complete browser creation, mutation and DOM read-back. "

**Expected result:** Private Python starts CUA; final catalog, lock and installed inventory match. This combined vehicle result does not gate CUA source acceptance.

**Verdict from the JSON:** Consumer CLI output/exit, private interpreter path, inventory hashes and MCP DOM results.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P02-macos-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: external consuming-vehicle qualification has not run.

## Part P03: nested signed deployment

### P03-windows-x86_64: nested signed deployment on windows-x86_64

**Precondition:** Approved signed fixture, final authorization, both receipts and native Windows signature tools.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Deploy the real signed closure into a fresh isolated destination. Edit an inactive browser target and inspect the extracted tree and endpoint. Repeat with the existing destination. "

**Expected result:** Fresh and existing deployment verify every member; relay and broker are native; endpoint binds final archive hash.

**Verdict from the JSON:** Independent member-set/hash/ACL checks, SignTool /pa /all /tw /v exit zero, Get-AuthenticodeSignature results, process architecture and authenticated handshake.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P03-windows-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P03-windows-aarch64: nested signed deployment on windows-aarch64

**Precondition:** Approved signed fixture, final authorization, both receipts and native Windows signature tools.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Deploy the real signed closure into a fresh isolated destination. Edit an inactive browser target and inspect the extracted tree and endpoint. Repeat with the existing destination. "

**Expected result:** Fresh and existing deployment verify every member; relay and broker are native; endpoint binds final archive hash.

**Verdict from the JSON:** Independent member-set/hash/ACL checks, SignTool /pa /all /tw /v exit zero, Get-AuthenticodeSignature results, process architecture and authenticated handshake.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P03-windows-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P03-wsl-x86_64: nested signed deployment on wsl-x86_64

**Precondition:** Approved signed fixture, final authorization, both receipts and native Windows signature tools.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Deploy the real signed closure into a fresh isolated destination. Edit an inactive browser target and inspect the extracted tree and endpoint. Repeat with the existing destination. "

**Expected result:** Fresh and existing deployment verify every member; relay and broker are native; endpoint binds final archive hash.

**Verdict from the JSON:** Independent member-set/hash/ACL checks, SignTool /pa /all /tw /v exit zero, Get-AuthenticodeSignature results, process architecture and authenticated handshake.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P03-wsl-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P03-wsl-aarch64: nested signed deployment on wsl-aarch64

**Precondition:** Approved signed fixture, final authorization, both receipts and native Windows signature tools.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Deploy the real signed closure into a fresh isolated destination. Edit an inactive browser target and inspect the extracted tree and endpoint. Repeat with the existing destination. "

**Expected result:** Fresh and existing deployment verify every member; relay and broker are native; endpoint binds final archive hash.

**Verdict from the JSON:** Independent member-set/hash/ACL checks, SignTool /pa /all /tw /v exit zero, Get-AuthenticodeSignature results, process architecture and authenticated handshake.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P03-wsl-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P04: restart and helper recovery

### P04-windows-x86_64-clean: restart and helper recovery on windows-x86_64-clean

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper normally; start a first client and independently connect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper normally; start a first client and independently connect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-clean/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-x86_64-concurrent: restart and helper recovery on windows-x86_64-concurrent

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Connect a second client while the first holds the startup lock.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Connect a second client while the first holds the startup lock."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-concurrent/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-x86_64-missing: restart and helper recovery on windows-x86_64-missing

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Remove only the live isolated discovery file.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Remove only the live isolated discovery file."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-x86_64-corrupt: restart and helper recovery on windows-x86_64-corrupt

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Replace only isolated discovery with invalid JSON.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Replace only isolated discovery with invalid JSON."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-x86_64-stale: restart and helper recovery on windows-x86_64-stale

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper but retain its stale lock/discovery.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper but retain its stale lock/discovery."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-stale/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-x86_64-disconnect: restart and helper recovery on windows-x86_64-disconnect

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Disconnect final client and extension; observe idle expiry and reconnect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Disconnect final client and extension; observe idle expiry and reconnect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-x86_64-disconnect/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-clean: restart and helper recovery on windows-aarch64-clean

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper normally; start a first client and independently connect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper normally; start a first client and independently connect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-clean/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-concurrent: restart and helper recovery on windows-aarch64-concurrent

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Connect a second client while the first holds the startup lock.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Connect a second client while the first holds the startup lock."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-concurrent/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-missing: restart and helper recovery on windows-aarch64-missing

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Remove only the live isolated discovery file.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Remove only the live isolated discovery file."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-corrupt: restart and helper recovery on windows-aarch64-corrupt

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Replace only isolated discovery with invalid JSON.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Replace only isolated discovery with invalid JSON."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-stale: restart and helper recovery on windows-aarch64-stale

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper but retain its stale lock/discovery.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper but retain its stale lock/discovery."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-stale/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-windows-aarch64-disconnect: restart and helper recovery on windows-aarch64-disconnect

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Disconnect final client and extension; observe idle expiry and reconnect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Disconnect final client and extension; observe idle expiry and reconnect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-windows-aarch64-disconnect/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-clean: restart and helper recovery on wsl-x86_64-clean

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper normally; start a first client and independently connect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper normally; start a first client and independently connect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-clean/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-concurrent: restart and helper recovery on wsl-x86_64-concurrent

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Connect a second client while the first holds the startup lock.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Connect a second client while the first holds the startup lock."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-concurrent/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-missing: restart and helper recovery on wsl-x86_64-missing

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Remove only the live isolated discovery file.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Remove only the live isolated discovery file."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-corrupt: restart and helper recovery on wsl-x86_64-corrupt

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Replace only isolated discovery with invalid JSON.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Replace only isolated discovery with invalid JSON."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-stale: restart and helper recovery on wsl-x86_64-stale

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper but retain its stale lock/discovery.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper but retain its stale lock/discovery."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-stale/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-x86_64-disconnect: restart and helper recovery on wsl-x86_64-disconnect

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Disconnect final client and extension; observe idle expiry and reconnect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Disconnect final client and extension; observe idle expiry and reconnect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-x86_64-disconnect/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-clean: restart and helper recovery on wsl-aarch64-clean

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper normally; start a first client and independently connect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper normally; start a first client and independently connect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-clean/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-concurrent: restart and helper recovery on wsl-aarch64-concurrent

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Connect a second client while the first holds the startup lock.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Connect a second client while the first holds the startup lock."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-concurrent/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-missing: restart and helper recovery on wsl-aarch64-missing

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Remove only the live isolated discovery file.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Remove only the live isolated discovery file."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-corrupt: restart and helper recovery on wsl-aarch64-corrupt

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Replace only isolated discovery with invalid JSON.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Replace only isolated discovery with invalid JSON."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-stale: restart and helper recovery on wsl-aarch64-stale

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Stop the proved helper but retain its stale lock/discovery.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Stop the proved helper but retain its stale lock/discovery."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-stale/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P04-wsl-aarch64-disconnect: restart and helper recovery on wsl-aarch64-disconnect

**Precondition:** P03 verified final generation; record process creation identity, lock, endpoint, registration and bundle hash before fault.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Disconnect final client and extension; observe idle expiry and reconnect.

**Task given to the agent:** "Complete the specified lifecycle fault, reconnect through the installed entry point and finish a browser mutation/read-back. Disconnect final client and extension; observe idle expiry and reconnect."

**Expected result:** Only verified final generation is reused; no input fallback, stale endpoint attachment or false readiness. Live discovery recovery preserves epoch or returns precise state error.

**Verdict from the JSON:** Before/after PID/start identity, lock owner, discovery identity, final digest, readiness connection and MCP result.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P04-wsl-aarch64-disconnect/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P05: repair and rollback

### P05-windows-x86_64-tamper-repair: repair and rollback on windows-x86_64-tamper-repair

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Alter one copied nested member; require refusal; repair from retained verified bytes.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Alter one copied nested member; require refusal; repair from retained verified bytes."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-x86_64-tamper-repair/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-windows-x86_64-approved-rollback: repair and rollback on windows-x86_64-approved-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request the exact approved signed-to-signed reverse transition.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request the exact approved signed-to-signed reverse transition."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-x86_64-approved-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-windows-x86_64-unknown-rollback: repair and rollback on windows-x86_64-unknown-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-x86_64-unknown-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-windows-aarch64-tamper-repair: repair and rollback on windows-aarch64-tamper-repair

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Alter one copied nested member; require refusal; repair from retained verified bytes.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Alter one copied nested member; require refusal; repair from retained verified bytes."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-aarch64-tamper-repair/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-windows-aarch64-approved-rollback: repair and rollback on windows-aarch64-approved-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request the exact approved signed-to-signed reverse transition.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request the exact approved signed-to-signed reverse transition."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-aarch64-approved-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-windows-aarch64-unknown-rollback: repair and rollback on windows-aarch64-unknown-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-windows-aarch64-unknown-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-x86_64-tamper-repair: repair and rollback on wsl-x86_64-tamper-repair

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Alter one copied nested member; require refusal; repair from retained verified bytes.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Alter one copied nested member; require refusal; repair from retained verified bytes."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-x86_64-tamper-repair/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-x86_64-approved-rollback: repair and rollback on wsl-x86_64-approved-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request the exact approved signed-to-signed reverse transition.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request the exact approved signed-to-signed reverse transition."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-x86_64-approved-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-x86_64-unknown-rollback: repair and rollback on wsl-x86_64-unknown-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-x86_64-unknown-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-aarch64-tamper-repair: repair and rollback on wsl-aarch64-tamper-repair

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Alter one copied nested member; require refusal; repair from retained verified bytes.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Alter one copied nested member; require refusal; repair from retained verified bytes."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-aarch64-tamper-repair/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-aarch64-approved-rollback: repair and rollback on wsl-aarch64-approved-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request the exact approved signed-to-signed reverse transition.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request the exact approved signed-to-signed reverse transition."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-aarch64-approved-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P05-wsl-aarch64-unknown-rollback: repair and rollback on wsl-aarch64-unknown-rollback

**Precondition:** Verified retained signed closures; approved exact transition pairs where the case permits rollback.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states.

**Task given to the agent:** "Complete the specified repair/rollback operation and independently verify the resulting process and browser state. Request an uncataloged reverse pair, then signed-to-unsigned rollback in separate copied states."

**Expected result:** Repair stages an exact retained tree atomically. Only cataloged signed transitions succeed. Adopted input closure never returns to unsigned bytes.

**Verdict from the JSON:** Independent tree/process hashes, precise refusal code, verified deployment receipt and browser DOM read-back.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P05-wsl-aarch64-unknown-rollback/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P06: released upgrade

### P06-windows-x86_64-from-076-healthy: released upgrade on windows-x86_64-from-076-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-076-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-076-missing: released upgrade on windows-x86_64-from-076-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-076-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-076-corrupt: released upgrade on windows-x86_64-from-076-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-076-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-077-healthy: released upgrade on windows-x86_64-from-077-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-077-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-077-missing: released upgrade on windows-x86_64-from-077-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-077-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-077-corrupt: released upgrade on windows-x86_64-from-077-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-077-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-078-healthy: released upgrade on windows-x86_64-from-078-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-078-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-078-missing: released upgrade on windows-x86_64-from-078-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-078-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-windows-x86_64-from-078-corrupt: released upgrade on windows-x86_64-from-078-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-windows-x86_64-from-078-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-076-healthy: released upgrade on wsl-x86_64-from-076-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-076-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-076-missing: released upgrade on wsl-x86_64-from-076-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-076-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-076-corrupt: released upgrade on wsl-x86_64-from-076-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.6; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.6; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-076-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-077-healthy: released upgrade on wsl-x86_64-from-077-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-077-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-077-missing: released upgrade on wsl-x86_64-from-077-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-077-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-077-corrupt: released upgrade on wsl-x86_64-from-077-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.7; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.7; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-077-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-078-healthy: released upgrade on wsl-x86_64-from-078-healthy

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery healthy.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery healthy."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-078-healthy/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-078-missing: released upgrade on wsl-x86_64-from-078-missing

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery missing.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery missing."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-078-missing/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P06-wsl-x86_64-from-078-corrupt: released upgrade on wsl-x86_64-from-078-corrupt

**Precondition:** Immutable released wheel with complete member hashes; isolated Chrome stays open across handoff.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Predecessor 0.7.8; discovery corrupt.

**Task given to the agent:** "Start the specified exact released predecessor, apply the stated discovery condition and launch the 0.7.9 client. Edit an isolated browser field and inspect predecessor and successor. Predecessor 0.7.8; discovery corrupt."

**Expected result:** Exact candidate transition or safe designed refusal; no browser restart, extension toggle or operation replay. The 0.7.8 predecessor drains cooperatively.

**Verdict from the JSON:** Old/new PID, creation identity, owner SID, held process-handle proof, complete payload hashes, discovery excluding tokens and single DOM mutation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P06-wsl-x86_64-from-078-corrupt/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P07: signed upgrade

### P07-windows-x86_64: signed upgrade on windows-x86_64

**Precondition:** Two separately authorized held signed fixtures per architecture and exact approved transition catalog; no synthetic signatures.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Start real signed fixture A, then concurrently attach clients requiring distinct signed fixture B. Verify one B broker and separate targets. Exercise approved and unknown reverse pairs. "

**Expected result:** Forward/reverse behavior follows exact catalog; concurrent clients elect one authenticated broker and unknown reverse pair preserves state.

**Verdict from the JSON:** Actual signed fixture/manifest hashes, two JSON streams, broker epoch/start identity, DOM values and refusal preservation hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P07-windows-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P07-windows-aarch64: signed upgrade on windows-aarch64

**Precondition:** Two separately authorized held signed fixtures per architecture and exact approved transition catalog; no synthetic signatures.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Start real signed fixture A, then concurrently attach clients requiring distinct signed fixture B. Verify one B broker and separate targets. Exercise approved and unknown reverse pairs. "

**Expected result:** Forward/reverse behavior follows exact catalog; concurrent clients elect one authenticated broker and unknown reverse pair preserves state.

**Verdict from the JSON:** Actual signed fixture/manifest hashes, two JSON streams, broker epoch/start identity, DOM values and refusal preservation hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P07-windows-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P07-wsl-x86_64: signed upgrade on wsl-x86_64

**Precondition:** Two separately authorized held signed fixtures per architecture and exact approved transition catalog; no synthetic signatures.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Start real signed fixture A, then concurrently attach clients requiring distinct signed fixture B. Verify one B broker and separate targets. Exercise approved and unknown reverse pairs. "

**Expected result:** Forward/reverse behavior follows exact catalog; concurrent clients elect one authenticated broker and unknown reverse pair preserves state.

**Verdict from the JSON:** Actual signed fixture/manifest hashes, two JSON streams, broker epoch/start identity, DOM values and refusal preservation hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P07-wsl-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P07-wsl-aarch64: signed upgrade on wsl-aarch64

**Precondition:** Two separately authorized held signed fixtures per architecture and exact approved transition catalog; no synthetic signatures.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Start real signed fixture A, then concurrently attach clients requiring distinct signed fixture B. Verify one B broker and separate targets. Exercise approved and unknown reverse pairs. "

**Expected result:** Forward/reverse behavior follows exact catalog; concurrent clients elect one authenticated broker and unknown reverse pair preserves state.

**Verdict from the JSON:** Actual signed fixture/manifest hashes, two JSON streams, broker epoch/start identity, DOM values and refusal preservation hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P07-wsl-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P08: active work and unknown owner

### P08-windows-x86_64-drain: active work and unknown owner on windows-x86_64-drain

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-x86_64-drain/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-x86_64-unknown-owner: active work and unknown owner on windows-x86_64-unknown-owner

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use an independently owned test process in copied discovery; require unchanged process/state.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use an independently owned test process in copied discovery; require unchanged process/state."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-x86_64-unknown-owner/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-x86_64-pid-reuse: active work and unknown owner on windows-x86_64-pid-reuse

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use a stale process record with matching PID and different creation identity; require refusal.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use a stale process record with matching PID and different creation identity; require refusal."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-x86_64-pid-reuse/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-x86_64-cancel: active work and unknown owner on windows-x86_64-cancel

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-x86_64-cancel/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-aarch64-drain: active work and unknown owner on windows-aarch64-drain

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-aarch64-drain/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-aarch64-unknown-owner: active work and unknown owner on windows-aarch64-unknown-owner

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use an independently owned test process in copied discovery; require unchanged process/state.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use an independently owned test process in copied discovery; require unchanged process/state."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-aarch64-unknown-owner/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-aarch64-pid-reuse: active work and unknown owner on windows-aarch64-pid-reuse

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use a stale process record with matching PID and different creation identity; require refusal.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use a stale process record with matching PID and different creation identity; require refusal."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-aarch64-pid-reuse/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-windows-aarch64-cancel: active work and unknown owner on windows-aarch64-cancel

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-windows-aarch64-cancel/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-x86_64-drain: active work and unknown owner on wsl-x86_64-drain

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-x86_64-drain/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-x86_64-unknown-owner: active work and unknown owner on wsl-x86_64-unknown-owner

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use an independently owned test process in copied discovery; require unchanged process/state.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use an independently owned test process in copied discovery; require unchanged process/state."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-x86_64-unknown-owner/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-x86_64-pid-reuse: active work and unknown owner on wsl-x86_64-pid-reuse

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use a stale process record with matching PID and different creation identity; require refusal.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use a stale process record with matching PID and different creation identity; require refusal."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-x86_64-pid-reuse/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-x86_64-cancel: active work and unknown owner on wsl-x86_64-cancel

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-x86_64-cancel/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-aarch64-drain: active work and unknown owner on wsl-aarch64-drain

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Begin an owned long request then request cataloged handoff; observe drain or bounded timeout."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-aarch64-drain/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-aarch64-unknown-owner: active work and unknown owner on wsl-aarch64-unknown-owner

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use an independently owned test process in copied discovery; require unchanged process/state.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use an independently owned test process in copied discovery; require unchanged process/state."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-aarch64-unknown-owner/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-aarch64-pid-reuse: active work and unknown owner on wsl-aarch64-pid-reuse

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Use a stale process record with matching PID and different creation identity; require refusal.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Use a stale process record with matching PID and different creation identity; require refusal."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-aarch64-pid-reuse/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P08-wsl-aarch64-cancel: active work and unknown owner on wsl-aarch64-cancel

**Precondition:** Only isolated test-owned process fixtures, recorded PID/start identity and before hashes.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds.

**Task given to the agent:** "Perform the specified process-state case through the installed public entry point. Independently inspect operation count and state afterward. Cancel a live MCP request with its child active; require full child-tree exit within 10 seconds."

**Expected result:** No uncertain operation replay, unproved termination or state corruption. Cancellation has no later successful result and child tree exits within 10 seconds.

**Verdict from the JSON:** Tool stream, independent DOM operation count, process creation identity, before/after file hashes and bounded child-tree exit observation.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P08-wsl-aarch64-cancel/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P09: shared native and WSL use

### P09-x86_64: shared native and WSL use on x86_64

**Precondition:** Matching native and WSL installations bind identical final helper bytes and one isolated extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Attach native and WSL clients concurrently. Each creates and changes an inactive target, lists both targets, and attempts the other client's target. "

**Expected result:** One broker with independent current targets; foreign target operations fail without activation or cross-routing.

**Verdict from the JSON:** Two agent streams, common PID/epoch/archive, independent DOM values and target_owned_by_another_client error.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P09-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P09-aarch64: shared native and WSL use on aarch64

**Precondition:** Matching native and WSL installations bind identical final helper bytes and one isolated extension.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Attach native and WSL clients concurrently. Each creates and changes an inactive target, lists both targets, and attempts the other client's target. "

**Expected result:** One broker with independent current targets; foreign target operations fail without activation or cross-routing.

**Verdict from the JSON:** Two agent streams, common PID/epoch/archive, independent DOM values and target_owned_by_another_client error.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P09-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P10: WSL boundary failure

### P10-wsl-x86_64-host-mismatch: WSL boundary failure on wsl-x86_64-host-mismatch

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Provide mismatched native Windows architecture via the isolated host-proof fixture.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Provide mismatched native Windows architecture via the isolated host-proof fixture."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-x86_64-host-mismatch/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-x86_64-wrong-signer: WSL boundary failure on wsl-x86_64-wrong-signer

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Copy a return authorization from an unapproved signer.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Copy a return authorization from an unapproved signer."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-x86_64-wrong-signer/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-x86_64-wrong-profile: WSL boundary failure on wsl-x86_64-wrong-profile

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Copy a return receipt for another consumer profile.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Copy a return receipt for another consumer profile."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-x86_64-wrong-profile/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-x86_64-disabled-interop: WSL boundary failure on wsl-x86_64-disabled-interop

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Make executable interop unavailable only to the isolated product child.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Make executable interop unavailable only to the isolated product child."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-x86_64-disabled-interop/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-aarch64-host-mismatch: WSL boundary failure on wsl-aarch64-host-mismatch

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Provide mismatched native Windows architecture via the isolated host-proof fixture.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Provide mismatched native Windows architecture via the isolated host-proof fixture."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-aarch64-host-mismatch/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-aarch64-wrong-signer: WSL boundary failure on wsl-aarch64-wrong-signer

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Copy a return authorization from an unapproved signer.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Copy a return authorization from an unapproved signer."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-aarch64-wrong-signer/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-aarch64-wrong-profile: WSL boundary failure on wsl-aarch64-wrong-profile

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Copy a return receipt for another consumer profile.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Copy a return receipt for another consumer profile."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-aarch64-wrong-profile/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P10-wsl-aarch64-disabled-interop: WSL boundary failure on wsl-aarch64-disabled-interop

**Precondition:** Known-good signed fixture copied into isolated fault state; no-dispatch baseline. Never change host networking or host interop settings.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Make executable interop unavailable only to the isolated product child.

**Task given to the agent:** "Apply the specified isolated boundary fault and request startup and a browser action through the installed entry point. Make executable interop unavailable only to the isolated product child."

**Expected result:** Distinct precise refusal before helper dispatch, matching remedy and unchanged trusted state.

**Verdict from the JSON:** Error JSON, independent process/dispatch counts and before/after state hashes; generic interop advice for signer/profile defects fails.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P10-wsl-aarch64-disabled-interop/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P11: asset exclusion

### P11-linux-x86_64: asset exclusion on linux-x86_64

**Precondition:** Native Linux/macOS host, authorized parent launch and exact profile artifact; isolated Chrome for Testing.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact managed profile with private Python. Inspect every wheel and nested member; register the isolated browser and create, edit and read two targets. "

**Expected result:** No Windows relay, broker or standalone verifier; native registration and real browser work succeed.

**Verdict from the JSON:** Complete ZIP/member inventory and native-header scan, private interpreter path, registration hashes and MCP DOM read-backs.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P11-linux-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P11-linux-aarch64: asset exclusion on linux-aarch64

**Precondition:** Native Linux/macOS host, authorized parent launch and exact profile artifact; isolated Chrome for Testing.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact managed profile with private Python. Inspect every wheel and nested member; register the isolated browser and create, edit and read two targets. "

**Expected result:** No Windows relay, broker or standalone verifier; native registration and real browser work succeed.

**Verdict from the JSON:** Complete ZIP/member inventory and native-header scan, private interpreter path, registration hashes and MCP DOM read-backs.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P11-linux-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P11-macos-x86_64: asset exclusion on macos-x86_64

**Precondition:** Native Linux/macOS host, authorized parent launch and exact profile artifact; isolated Chrome for Testing.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact managed profile with private Python. Inspect every wheel and nested member; register the isolated browser and create, edit and read two targets. "

**Expected result:** No Windows relay, broker or standalone verifier; native registration and real browser work succeed.

**Verdict from the JSON:** Complete ZIP/member inventory and native-header scan, private interpreter path, registration hashes and MCP DOM read-backs.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P11-macos-x86_64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P11-macos-aarch64: asset exclusion on macos-aarch64

**Precondition:** Native Linux/macOS host, authorized parent launch and exact profile artifact; isolated Chrome for Testing.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Begin with no state inherited from another cell.

**Task given to the agent:** "Install the exact managed profile with private Python. Inspect every wheel and nested member; register the isolated browser and create, edit and read two targets. "

**Expected result:** No Windows relay, broker or standalone verifier; native registration and real browser work succeed.

**Verdict from the JSON:** Complete ZIP/member inventory and native-header scan, private interpreter path, registration hashes and MCP DOM read-backs.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P11-macos-aarch64/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Part P13: standalone and managed coexistence

### P13-x86_64-standalone-first-native-native: standalone and managed coexistence on x86_64-standalone-first-native-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order standalone-first; standalone/managed execution pair native-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order standalone-first; standalone/managed execution pair native-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-standalone-first-native-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-standalone-first-native-wsl: standalone and managed coexistence on x86_64-standalone-first-native-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order standalone-first; standalone/managed execution pair native-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order standalone-first; standalone/managed execution pair native-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-standalone-first-native-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-standalone-first-wsl-native: standalone and managed coexistence on x86_64-standalone-first-wsl-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order standalone-first; standalone/managed execution pair wsl-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order standalone-first; standalone/managed execution pair wsl-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-standalone-first-wsl-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-standalone-first-wsl-wsl: standalone and managed coexistence on x86_64-standalone-first-wsl-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order standalone-first; standalone/managed execution pair wsl-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order standalone-first; standalone/managed execution pair wsl-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-standalone-first-wsl-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-managed-first-native-native: standalone and managed coexistence on x86_64-managed-first-native-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order managed-first; standalone/managed execution pair native-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order managed-first; standalone/managed execution pair native-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-managed-first-native-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-managed-first-native-wsl: standalone and managed coexistence on x86_64-managed-first-native-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order managed-first; standalone/managed execution pair native-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order managed-first; standalone/managed execution pair native-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-managed-first-native-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-managed-first-wsl-native: standalone and managed coexistence on x86_64-managed-first-wsl-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order managed-first; standalone/managed execution pair wsl-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order managed-first; standalone/managed execution pair wsl-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-managed-first-wsl-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-x86_64-managed-first-wsl-wsl: standalone and managed coexistence on x86_64-managed-first-wsl-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture x86_64; order managed-first; standalone/managed execution pair wsl-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture x86_64; order managed-first; standalone/managed execution pair wsl-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-x86_64-managed-first-wsl-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-standalone-first-native-native: standalone and managed coexistence on aarch64-standalone-first-native-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order standalone-first; standalone/managed execution pair native-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order standalone-first; standalone/managed execution pair native-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-standalone-first-native-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-standalone-first-native-wsl: standalone and managed coexistence on aarch64-standalone-first-native-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order standalone-first; standalone/managed execution pair native-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order standalone-first; standalone/managed execution pair native-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-standalone-first-native-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-standalone-first-wsl-native: standalone and managed coexistence on aarch64-standalone-first-wsl-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order standalone-first; standalone/managed execution pair wsl-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order standalone-first; standalone/managed execution pair wsl-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-standalone-first-wsl-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-standalone-first-wsl-wsl: standalone and managed coexistence on aarch64-standalone-first-wsl-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order standalone-first; standalone/managed execution pair wsl-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order standalone-first; standalone/managed execution pair wsl-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-standalone-first-wsl-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-managed-first-native-native: standalone and managed coexistence on aarch64-managed-first-native-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order managed-first; standalone/managed execution pair native-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order managed-first; standalone/managed execution pair native-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-managed-first-native-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-managed-first-native-wsl: standalone and managed coexistence on aarch64-managed-first-native-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order managed-first; standalone/managed execution pair native-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order managed-first; standalone/managed execution pair native-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-managed-first-native-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-managed-first-wsl-native: standalone and managed coexistence on aarch64-managed-first-wsl-native

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order managed-first; standalone/managed execution pair wsl-native.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order managed-first; standalone/managed execution pair wsl-native."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-managed-first-wsl-native/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

### P13-aarch64-managed-first-wsl-wsl: standalone and managed coexistence on aarch64-managed-first-wsl-wsl

**Precondition:** Real same-version signed fixture, exact cataloged unsigned-to-signed edge, packaged native offline verifier/policy and isolated verifier network denial.

**Setup:** Prepare a fresh marked root, install the exact catalog-selected wheel and native prerequisites, record head and wheel/manifest hashes, create this cell's evidence directory, and record driver selection plus installed doctor output. Architecture aarch64; order managed-first; standalone/managed execution pair wsl-wsl.

**Task given to the agent:** "Start the specified order and standalone/managed execution pair. Adopt with network unavailable to the isolated verifier. Attach native and WSL clients concurrently and edit separate inactive targets. Restart, remove the managed test installation and reconnect standalone. Remove retained signed bytes and request unsigned rollback in separate copies. Architecture aarch64; order managed-first; standalone/managed execution pair wsl-wsl."

**Expected result:** All pairs/orders converge on one signed broker with separate targets. Restart/uninstall uses retained signed bytes or precise repair refusal; never unsigned fallback.

**Verdict from the JSON:** Verified attestation, both receipts, mapping, member signatures, PID/epoch/archive, owner-only adoption state, no-network verification, independent DOM and no-downgrade hashes.

**Evidence boundary:** `<evidence-root>/<host>/<pass>/P13-aarch64-managed-first-wsl-wsl/`: agent.jsonl, exit.json, identity.json, before.json, after.json and each named oracle artifact, captured before cleanup.

**Cleanup:** Seal and scan evidence; stop only this cell's proved owned process tree, close owned targets and restore copied fixtures. Retain the marked root until evidence is pushed. Preserve unknown processes and shared signed fixtures.

**Result:** not run: native execution and prerequisites have not been verified.

## Data-only mutation cases before protected use

These admission checks supplement, never replace, the real P12/P14 live cells.
Each row is independently executed against a fresh copied valid input.
Precondition: exact approved retained input and expected schema. Setup: copy it
under the marked root and change only the named field/member. Action: submit the
copy to the same installed public loader or trusted validator used by the positive
cell. Expected: fail before protected vendor access or helper execution. Oracle:
actual nonzero exit/error code plus unchanged vendor-call/dispatch count and state
hashes. Evidence: one directory per ID containing changed-field description,
original/mutated hashes, command output and exit. Cleanup: discard only that copy
after evidence sealing. None authorizes synthetic signed acceptance.

| id | isolated mutation or construction condition | result |
|---|---|---|
| T01 | catalog issuer | not run: exact retained fixture and validator execution owed |
| T02 | certificate identity | not run: exact retained fixture and validator execution owed |
| T03 | repository ID | not run: exact retained fixture and validator execution owed |
| T04 | owner ID | not run: exact retained fixture and validator execution owed |
| T05 | workflow identity | not run: exact retained fixture and validator execution owed |
| T06 | source commit | not run: exact retained fixture and validator execution owed |
| T07 | artifact digest | not run: exact retained fixture and validator execution owed |
| T08 | job ID | not run: exact retained fixture and validator execution owed |
| T09 | run ID | not run: exact retained fixture and validator execution owed |
| T10 | attempt | not run: exact retained fixture and validator execution owed |
| T11 | publication binding | not run: exact retained fixture and validator execution owed |
| T12 | lock digest | not run: exact retained fixture and validator execution owed |
| T13 | managed package marker | not run: exact retained fixture and validator execution owed |
| T14 | managed authorization pipe | not run: exact retained fixture and validator execution owed |
| T15 | final manifest digest | not run: exact retained fixture and validator execution owed |
| T16 | replayed signing return | not run: exact retained fixture and validator execution owed |
| T17 | duplicate JSON key | not run: exact retained fixture and validator execution owed |
| T18 | unknown JSON field | not run: exact retained fixture and validator execution owed |
| T19 | missing held binding | not run: exact retained fixture and validator execution owed |
| T20 | missing released binding | not run: exact retained fixture and validator execution owed |
| T21 | extra nested executable | not run: exact retained fixture and validator execution owed |
| T22 | unknown role | not run: exact retained fixture and validator execution owed |
| T23 | wrong execution OS | not run: exact retained fixture and validator execution owed |
| T24 | wrong architecture | not run: exact retained fixture and validator execution owed |
| T25 | duplicate archive path | not run: exact retained fixture and validator execution owed |
| T26 | case-colliding archive path | not run: exact retained fixture and validator execution owed |
| T27 | path traversal | not run: exact retained fixture and validator execution owed |
| T28 | opaque nested payload | not run: exact retained fixture and validator execution owed |
| T29 | missing helper | not run: exact retained fixture and validator execution owed |
| T30 | altered member hash | not run: exact retained fixture and validator execution owed |
| T31 | missing legal rights | not run: exact retained fixture and validator execution owed |
| T32 | unknown trust class | not run: exact retained fixture and validator execution owed |
| T33 | changed vendor member | not run: exact retained fixture and validator execution owed |
| T34 | stripped vendor signature | not run: exact retained fixture and validator execution owed |
| T35 | appended vendor signature | not run: exact retained fixture and validator execution owed |
| T36 | wrong publisher | not run: exact retained fixture and validator execution owed |
| T37 | untrusted chain | not run: exact retained fixture and validator execution owed |
| T38 | expired signature without timestamp | not run: exact retained fixture and validator execution owed |
| T39 | invalid vendor timestamp | not run: exact retained fixture and validator execution owed |
| T40 | warning exit 2 | not run: exact retained fixture and validator execution owed |
| T41 | quota counts preserved member | not run: exact retained fixture and validator execution owed |
| T42 | wrong adoption root | not run: exact retained fixture and validator execution owed |
| T43 | wrong adoption workflow | not run: exact retained fixture and validator execution owed |
| T44 | wrong adoption source | not run: exact retained fixture and validator execution owed |
| T45 | wrong packaged verifier hash | not run: exact retained fixture and validator execution owed |
| T46 | invalid adoption bundle | not run: exact retained fixture and validator execution owed |
| T47 | changed input-to-final mapping | not run: exact retained fixture and validator execution owed |
| T48 | unknown same-version edge | not run: exact retained fixture and validator execution owed |
| T49 | signed-to-unsigned rollback | not run: exact retained fixture and validator execution owed |
| T50 | generic publisher/version match | not run: exact retained fixture and validator execution owed |
| T51 | corrupt persisted adoption state | not run: exact retained fixture and validator execution owed |
| T52 | changed installed adopted member | not run: exact retained fixture and validator execution owed |
| T53 | shared consumer set | not run: exact retained fixture and validator execution owed |
| T54 | shared architecture | not run: exact retained fixture and validator execution owed |
| T55 | swapped Windows receipt | not run: exact retained fixture and validator execution owed |
| T56 | swapped WSL receipt | not run: exact retained fixture and validator execution owed |
| T57 | separately re-signed WSL archive | not run: exact retained fixture and validator execution owed |
| T58 | inner authorization_sha256 field | not run: exact retained fixture and validator execution owed |
| T59 | inner final receipt hash | not run: exact retained fixture and validator execution owed |
| T60 | inner self-digest | not run: exact retained fixture and validator execution owed |
| T61 | final manifest inside its own ZIP | not run: exact retained fixture and validator execution owed |
| T62 | authorization inside referenced artifact | not run: exact retained fixture and validator execution owed |
| T63 | manifest/authorization mutual hash | not run: exact retained fixture and validator execution owed |
| T64 | claim mutation invalidates downstream | not run: exact retained fixture and validator execution owed |
| T65 | member mutation invalidates downstream | not run: exact retained fixture and validator execution owed |
| T66 | ZIP mutation invalidates downstream | not run: exact retained fixture and validator execution owed |
| T67 | inner manifest mutation invalidates downstream | not run: exact retained fixture and validator execution owed |
| T68 | frozen manifest rewrite after attestation | not run: exact retained fixture and validator execution owed |
| T69 | placeholder backfill | not run: exact retained fixture and validator execution owed |
| T70 | unrelated cross-workflow binary | not run: exact retained fixture and validator execution owed |
| T71 | executable script disguised as metadata | not run: exact retained fixture and validator execution owed |
| T72 | fault before ZIP rebuild | not run: exact retained fixture and validator execution owed |
| T73 | fault after ZIP rebuild | not run: exact retained fixture and validator execution owed |
| T74 | fault before atomic deployment | not run: exact retained fixture and validator execution owed |
| T75 | fault after atomic deployment | not run: exact retained fixture and validator execution owed |
| T76 | fault before WSL return | not run: exact retained fixture and validator execution owed |
| T77 | fault after WSL return | not run: exact retained fixture and validator execution owed |

P14's positive construction freezes each object's bytes once, in order:
members/ZIP, inner manifest containing only pre_signing_claim_sha256 as its claim
binding, attested closure authorization, separate receipts, then outer inventory.
Record each object's actual bytes/digest. Earlier-object mutations invalidate every
downstream receipt/inventory. No zero hash, second write, mutual hash or backfill
is permitted. P12 rebuilds a deterministic ZIP twice from the same verified signed
members; this does not claim timestamped signing itself is reproducible.

## When a part surfaces a bug: fix it, then re-run it

Repeat the failed public path before diagnosis. Add a regression, rebuild and
reinstall, record the new identity and rerun the entire affected cell.
Retain failed and fixed boundaries. Shared changes invalidate earlier host results.

## Repeatability

Run three independent passes per native platform, each with separate roots,
processes, profiles, endpoints and evidence. Compare tool-call order, error codes,
target ownership, process identities and hashes. Record unusual observations.
Concurrent clients sharing one broker inside P09/P13 are one concurrency case,
not independent passes. Emulation, CI and WSL do not prove native Windows.

## Per-OS results

Only applicable explicit IDs contribute to each host. P02 remains external.

| part | Linux | Windows | macOS | WSL | notes |
|---|---|---|---|---|---|
| Part P01 | not run: no native session | pass: P01-windows-x86_64 at b6a72a1; Windows ARM64 remains owed | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P02 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P03 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P04 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P05 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P06 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P07 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P08 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P09 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P10 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P11 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P12 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P13 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |
| Part P14 | not run: no native session | not run: no native session | not run: no native session | not run: no WSL session | Applicable explicit IDs above; P02 is external. |

Overall: not run: no live cell executed. No platform inherits CI results.

| Linux desktop | x86_64 | aarch64 |
|---|---|---|
| GNOME Wayland | not run: host owed | not run: host owed |
| GNOME X11 | not run: host owed | not run: host owed |
| KDE Plasma | not run: host owed | not run: host owed |
| Minimal install | not run: host owed | not run: host owed |
| Sway | not run: host owed | not run: host owed |
| Hyprland | not run: host owed | not run: host owed |

## Evidence

Resolve the common evidence PR before live startup. Each host contributes its own
boundary with actual non-secret command output, exit codes, hash lines, inventories,
signature verification and process identity. The helper only hashes already-captured
files; it cannot mark a pass.

```sh
python E2E/0.7.9/harness/harness.py evidence --evidence "$CUA_EVIDENCE_BOUNDARY" --cell "$CUA_CELL_ID" "$CUA_EVIDENCE_BOUNDARY/agent.jsonl" "$CUA_EVIDENCE_BOUNDARY/exit.json" "$CUA_EVIDENCE_BOUNDARY/identity.json"
python scripts/check_no_secrets.py --env-file ../.env
```

Keep tokens out of captured inputs. Inspect streams before sealing; redact secret
fields while preserving tool identity and read-backs. Never commit raw secret output.
The helper is not a redactor and never loads authentication files.

## Account for what the pass leaves running and on disk

Record every owned PID/start identity, executable hash and port at creation.
After evidence is committed and pushed, stop only those proved processes and confirm
their ports are free. Resolve any owner launcher that still references a test runtime.
Only after these checks write the following root-local cleanup clearance:

```json
{"owned_processes_stopped": true, "owner_references_checked": true, "root": "<exact resolved test root>"}
```

```sh
python E2E/0.7.9/harness/harness.py cleanup --root "$CUA_TEST_ROOT" --evidence "$CUA_EVIDENCE_CHECKOUT"
python E2E/0.7.9/harness/harness.py cleanup --root "$CUA_TEST_ROOT" --evidence "$CUA_EVIDENCE_CHECKOUT" --execute
```

The helper verifies a clean pushed evidence checkout and moves only the marked root
to an explicit recoverable sibling. It reports zero reclaimed bytes.
After review remove only that validated retired root with native filesystem tools,
run standard build cleanup, and record actual free-space delta. Preserve source,
evidence, credentials, configuration, shared caches and uncommitted work.
Use the same procedure after failed or interrupted passes.

## Findings

No live findings: execution has not begun. Exact fixtures, protected authorization,
native hosts, packaged verifier policy and evidence identity are prerequisites.
They are never fabricated failures or synthetic passes.

## What this runbook cannot prove

An unrun cell proves nothing about native hardware, legal rights or certificate trust.
Certificate-table presence is not signature verification. Unit fixtures cannot prove
protected signing, native ARM64 execution or offline adoption.
CUA source results do not close a consuming application's signed installer, console,
legal, rollback or full-release qualification.
