# Desktop tier 0.4.1 - cross-desktop end to end test runbook

> Status: **implementation complete and unit-green; awaiting user approval of
> this test suite before any run** (per ENGINEERING.md §2 — the runbook gate).
> Nothing here is executed until approved. The 0.4.1 code under test: the XDG
> portal screenshot backend, the provider/resolver abstraction + `doctor`
> reporting (`platform_backends`), the pure-python uinput executor, the
> python-xlib XTEST executor, and `vadgr-cua install-deps`.

Per-desktop end to end validation of the **desktop tier** (screenshot + input)
after the cross-desktop backend rework: the provider/resolver abstraction, the XDG
portal screenshot path, pure-python uinput, and python-xlib XTEST. Unit tests prove
the resolver and each backend in isolation; they do not prove that a real agent can
*see the screen and drive the mouse/keyboard* on each desktop. Run this runbook on
each target and record the result in the table at the bottom.

Target: **Ubuntu 24.04.4 LTS** — the project's Linux baseline. (0.4.1 is a
Linux-only change; the desktop tier on Windows / macOS / WSL is untouched and
covered by its own runs.)

## The approach: a Claude subagent over `claude -p` (reused from 0.4.0)

Real end to end is driven by a real agent, never a script. A `.py` that calls the
executor directly is an acceptance test, not the e2e. The runner gives a headless
Claude Code subagent the cua MCP server and a goal-level task, then reads the
verdict from the agent's tool stream:

1. The task prompt is **goal-level only** — the outcome, never the coordinates or
   the tool names. Whether the agent screenshots, grounds its clicks, and verifies
   the effect on its own is part of what this measures.
2. The verdict comes from the `tool_use` / `tool_result` stream (cua's real
   read-backs) **and an independent ground-truth** (a file written to disk, a
   `wl-paste`, a before/after screenshot contrast) — never the agent's prose.
3. A self-reported success with no confirming read-back is a fail.

Run **one** subagent at a time, never in parallel — they share one real screen,
mouse, and keyboard. Finish and judge one test before starting the next.

## Prerequisites (per desktop)

1. Install cua into a venv: `pip install .` (no compiler needed — `evdev` is now an
   optional extra; the default input path is pure-python uinput / XTEST).
2. Provision system deps: `vadgr-cua install-deps` (clipboard + the `/dev/uinput`
   udev rule), or accept the printed commands. wlroots targets also need `grim`.
3. **Sanity check:** `vadgr-cua doctor` reports a resolved **capture** and **input**
   backend for this desktop, and the agent's first `screenshot` returns a real
   frame. The resolved backend names are recorded in the results table.

## How the runner drives a test (reused from 0.4.0)

Write an `.mcp.json` that launches cua from the venv, carrying the session env the
backend needs (`WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `DISPLAY`):

```json
{
  "mcpServers": {
    "vadgr-computer-use": {
      "command": "<venv>/bin/vadgr-cua",
      "args": [],
      "env": { "WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": "/run/user/1000", "DISPLAY": ":0" }
    }
  }
}
```

Pipe the goal-level prompt to the subagent over **stdin** (not as a `-p "<arg>"`
string, which truncates long prompts):

```
<prompt-file> piped to:
  claude --dangerously-skip-permissions --max-turns 40 \
    --mcp-config .mcp.json --output-format stream-json --verbose -p
```

The portal screenshot path prompts for consent on first use — grant it once before
the run (or pre-seed the PermissionStore) so the agent sees a silent capture.

## Part A: deterministic primitives (run first)

Each is a goal-level task with an independent ground-truth, so the verdict does not
depend on a noisy desktop.

- **A1 Capture liveness.** Take a screenshot and describe what is on screen. Expect
  a real, non-blank frame whose content matches the actual desktop. Ground-truth:
  the resolver selected a working capture backend (cross-check `doctor`); the image
  decodes with non-trivial content.
- **A2 Screen size + platform.** Report the screen size and platform. Expect
  `get_screen_size` to match the screenshot's pixel dimensions and `get_platform` =
  linux.
- **A3 Doctor / backend resolution.** Ask which capture and input backends are
  active. Expect the resolved pair for this desktop (e.g. GNOME 50 -> portal +
  Mutter RD; GNOME 46 -> gnome-screenshot + Mutter RD; X11 -> mss + XTEST) plus the
  skip trail for higher-priority providers that did not apply.
- **A4 Type round-trip (input ground-truth).** Open the desktop's text editor, type
  the sentinel `vadgr-e2e-<rand>`, and save to `~/e2e-a4.txt`. Ground-truth:
  independently `cat ~/e2e-a4.txt` contains the exact sentinel — proves keystrokes
  reached the focused field, not just that the agent claimed so.
- **A5 Keyboard shortcut + clipboard.** In that editor, select-all and copy
  (ctrl+a, ctrl+c). Ground-truth: `wl-paste` (Wayland) / `xclip -o` (X11) returns
  the sentinel.
- **A6 Scroll.** In a long window, scroll down several steps. Expect a before/after
  screenshot contrast showing the viewport moved (new content visible).
- **A7 Click grounding.** Given a visible button/menu (e.g. the editor's menu),
  screenshot, click it, screenshot again. Expect the menu/dialog actually opened —
  the click landed where the screenshot showed the target.
- **A8 Drag.** Drag a window by its title bar (or a slider). Expect a screenshot
  contrast showing it moved.
- **A9 Negative.** Act on an impossible target (click far outside screen bounds /
  an op that cannot succeed). Expect a **raised error**, not a silent success.

**Pass for Part A:** every outcome confirmed from the stream **and** the independent
ground-truth; the agent screenshots-then-acts and verifies before moving on without
being told to; A9 raises.

## Part B: real-app tasks (run after Part A)

Goal-level multi-step tasks on stock desktop apps — the screenshot -> click -> type
-> verify loop on the messy real UI a fixture can't reach.

- **B1 File manager.** Open the file manager, go to Home, and report the first
  folder's name. Verdict from screenshot read-backs.
- **B2 Settings lookup.** Open Settings -> About and report the OS/desktop version.
  Cross-check against `/etc/os-release` independently.
- **B3 Editor write-out.** Open the text editor, write a given two-line note, save
  to `~/e2e-b3.txt`. Ground-truth: `cat ~/e2e-b3.txt` matches the note exactly.

**Pass for Part B:** the outcome is confirmed from the stream and the agent verifies
on its own; a self-reported success with no read-back is a fail.

## Backward-compatibility gate (Ubuntu 24.04 / GNOME 46)

On 24.04 the run must additionally prove **no regression**: `doctor` (A3) names the
**same backends 24.04 uses today** — `gnome-screenshot` for capture, Mutter
RemoteDesktop for input — and **no portal consent dialog appears** during Part A.
If 24.04 silently switches to the portal or prompts for consent, that is a
backward-compat **fail** even if the tasks pass.

## Per-desktop results

Fill in by running the runbook on each target. Record the exact OS/desktop version
and the resolved backends (capture / input) in the status note.

Legend: pass / fail / blocked / not run

| | Ubuntu 24.04.4 LTS |
|---|---|
| Part A (A1-A9) | not run |
| Part B (B1-B3) | not run |
| Backward-compat gate (same backends as today, no portal dialog) | not run |
| Resolved backends (capture / input) | |
| Overall | not run |

Status notes:
- (record per target: OS build, desktop/compositor version, resolved capture+input
  backends, and any task that was blocked + why)
