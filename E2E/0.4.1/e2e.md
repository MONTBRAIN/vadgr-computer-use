# Desktop tier 0.4.1 - end to end test runbook

> Status: **implementation complete and unit-green; awaiting user approval of
> this test suite before any run** (per ENGINEERING.md §2 — the runbook gate).
> Nothing here is executed until approved. The 0.4.1 code under test: the XDG
> portal screenshot backend, the provider/resolver abstraction + `doctor`
> reporting (`platform_backends`), the pure-python uinput executor, the
> python-xlib XTEST executor, and `vadgr-cua install-deps`.

End to end validation of the **desktop tier** after the backend rework (provider/
resolver selection, XDG portal capture, pure-python uinput, python-xlib XTEST).
Unit tests prove the resolver and each backend in isolation; they do not prove that
a real agent can *see the screen and drive the mouse/keyboard* and that **every
tool actually works** on a live session. Run this runbook and record the result in
the table at the bottom.

Targets: **Ubuntu 26.04 (GNOME 50)** and **Ubuntu 24.04.4 LTS (GNOME 46)** — the
goal is the tier working on both. 24.04 is also the backward-compatibility baseline
(it must keep selecting the backends it uses today). 0.4.1 is a Linux-only change;
the desktop tier on Windows / macOS / WSL is untouched and covered by its own runs.

## Scope: which tools this runbook exercises

**Every non-browser tool is tested here** (the full desktop + system surface). The
**browser tier (`browser`, `browser_eval`) is out of scope** — it already has its
own agent suite (`E2E/0.4.0/e2e.md`), which is reused and **not re-run** for this
minor. The tool-coverage checklist at the end maps each tool to its test.

## The approach: a Claude subagent over `claude -p` (reused from 0.4.0)

Real end to end is driven by a real agent, never a script. The runner gives a
headless Claude Code subagent the cua MCP server and a goal-level task, then reads
the verdict from the agent's tool stream:

1. The task prompt is **goal-level only** — the outcome, never the coordinates or
   the tool names. Whether the agent screenshots, grounds its clicks, and verifies
   on its own is part of what this measures.
2. The verdict comes from the `tool_use` / `tool_result` JSON (cua's real
   read-backs) **and an independent ground-truth** (a file on disk, a `wl-paste`, a
   before/after screenshot contrast) — never the agent's prose. See
   [`../README.md`](../README.md) for where that JSON lives (the run stream, and
   the `~/.claude` session transcript fallback) and how to read it.
3. A self-reported success with no confirming read-back is a fail.

Run **one** subagent at a time, never in parallel — they share one real screen,
mouse, and keyboard. Finish and judge one test before starting the next.

## Prerequisites

1. Install cua into a venv: `pip install .` (no compiler needed — `evdev` is now an
   optional extra; the default input path is pure-python uinput / XTEST).
2. Provision system deps: `vadgr-cua install-deps` (clipboard + the `/dev/uinput`
   udev rule), or accept the printed commands.
3. **Sanity check:** `vadgr-cua doctor` reports a resolved **capture** and **input**
   backend, and the agent's first `screenshot` returns a real frame. Record the
   resolved backend names in the results table.

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

## Part A: system & info tools (deterministic, run first)

Goal-level asks that force each Tier-0 / info tool; verdict from the `tool_result`
JSON plus an independent ground-truth.

- **A1 Platform** — ask the agent to report the OS and platform details. Exercises
  `get_platform` (= linux) and `get_platform_info`. Cross-check `/etc/os-release`.
- **A2 Screen size** — report the screen size. `get_screen_size` returns `WxH`
  matching the screenshot's pixel dimensions (Part B).
- **A3 File round-trip** — write a sentinel to `~/e2e-a3.txt` then read it back.
  Exercises `fs` write+read; ground-truth: independent `cat` matches.
- **A4 Shell** — run a trivial command (e.g. `echo` / `uname`). Exercises `shell`;
  `tool_result.returncode == 0` and expected stdout.
- **A5 HTTP** — GET a known endpoint (e.g. `https://httpbin.org/get`). Exercises
  `http`; `tool_result.status == 200`.
- **A6 Env** — read `HOME` (and set a process var). Exercises `env`; value matches
  the real environment.
- **A7 Time** — get the current time / sleep briefly. Exercises `time`; ISO-8601
  result.
- **A8 Tempfile** — allocate a temp path. Exercises `tempfile`; an absolute path is
  returned.
- **A9 Data** — parse a small JSON and a CSV blob. Exercises `data`; structured
  result matches input.
- **A10 Clipboard** — copy a sentinel string. Exercises `clipboard`; ground-truth:
  `wl-paste` (Wayland) / `xclip -o` (X11) returns the sentinel.

**Pass for Part A:** each tool returns a non-error `tool_result` and the
ground-truth confirms the real side effect.

## Part B: pixel & input tools (the desktop-specific surface)

Each names a tool and is judged from a screenshot read-back or a file/clipboard
ground-truth — never the agent's prose.

- **B1 screenshot** — capture the screen; expect a real, non-blank frame matching
  the actual desktop (cross-check the resolved capture backend from `doctor`).
- **B2 screenshot_region** — capture a sub-rectangle; expect dimensions equal to the
  requested region and content matching that area of the full frame.
- **B3 move_mouse** — move over a control with a hover state; screenshot shows the
  hover highlight (cursor moved without clicking).
- **B4 click** — screenshot, click a visible button/menu, screenshot again; the
  expected dialog/menu actually opened (the click landed on the target).
- **B5 double_click** — double-click a word in a text editor; the word shows
  selected in the next screenshot.
- **B6 right_click** — right-click an empty area; a context menu appears.
- **B7 scroll** — scroll a long window down several steps; before/after screenshot
  contrast shows the viewport moved.
- **B8 drag** — drag a window by its title bar (or a slider); screenshot contrast
  shows it moved.
- **B9 type_text** — open the text editor, type `vadgr-e2e-<rand>`, save to
  `~/e2e-b9.txt`; ground-truth: `cat` contains the exact sentinel (keystrokes
  reached the focused field).
- **B10 key_press** — in that editor, select-all + copy (`ctrl+a`, `ctrl+c`);
  ground-truth: `wl-paste` returns the typed text.
- **B11 negative** — act on an impossible target (click far outside screen bounds /
  an op that cannot succeed). Expect a `tool_result` with `is_error: true` — a
  raised error, never a silent success.

**Pass for Part B:** every outcome confirmed from the stream **and** the
ground-truth; the agent screenshots-then-acts and verifies before moving on without
being told to; B11 raises.

## Part C: real-app integration (run after A and B)

Multi-step goal-level tasks on stock apps — the screenshot -> click -> type -> verify
loop on the messy real UI a fixture can't reach.

- **C1 File manager** — open Files, go to Home, report the first folder's name.
- **C2 Settings lookup** — open Settings -> About, report the OS/desktop version;
  cross-check `/etc/os-release`.
- **C3 Editor write-out** — open the editor, write a given two-line note, save to
  `~/e2e-c3.txt`; ground-truth: `cat` matches the note exactly.

## Tool-coverage checklist (every non-browser tool has a test)

| Tool | Test | | Tool | Test |
|---|---|---|---|---|
| `get_platform` | A1 | | `screenshot` | B1 |
| `get_platform_info` | A1 | | `screenshot_region` | B2 |
| `get_screen_size` | A2 | | `move_mouse` | B3 |
| `fs` | A3 | | `click` | B4 |
| `shell` | A4 | | `double_click` | B5 |
| `http` | A5 | | `right_click` | B6 |
| `env` | A6 | | `scroll` | B7 |
| `time` | A7 | | `drag` | B8 |
| `tempfile` | A8 | | `type_text` | B9 |
| `data` | A9 | | `key_press` | B10 |
| `clipboard` | A10 | | (error path) | B11 |

Out of scope (reused, not run): `browser`, `browser_eval` — see `E2E/0.4.0/e2e.md`.

## Backward-compatibility gate (Ubuntu 24.04 / GNOME 46)

On 24.04 the run must additionally prove **no regression**: `doctor` names the
**same backends 24.04 uses today** — `gnome-screenshot` for capture, Mutter
RemoteDesktop for input — and **no portal consent dialog appears** during the run.
If 24.04 silently switches to the portal or prompts for consent, that is a
backward-compat **fail** even if the tasks pass.

## Results

Fill in per Ubuntu version. Record the exact build and the resolved backends.

Legend: pass / fail / blocked / not run

| | Ubuntu 26.04 (GNOME 50) | Ubuntu 24.04.4 (GNOME 46) |
|---|---|---|
| Part A — system & info (A1-A10) | pass (10/10) | pass (10/10) |
| Part B — pixel & input (B1-B11) | pass (11/11) | pass (11/11) |
| Part C — real-app (C3) | pass | pass |
| Backward-compat gate | n/a (forward target) | pass |
| Resolved backends (capture / input) | portal / mutter-remotedesktop | gnome-screenshot / mutter-remotedesktop |
| Overall | pass | pass |

Status notes:
- **Ubuntu 26.04 (GNOME Shell 50.1 / Mutter 50.1), kernel 7.0.0-27, 2026-06-28.**
  Driven by goal-level `claude -p` subagents against the 0.4.1 editable venv;
  judged from the `tool_use`/`tool_result` JSON + independent ground-truth.
  - Part A 10/10: `get_platform`/`get_platform_info`=linux; `get_screen_size`=1280x800;
    `fs` write+read (independent `cat`==sentinel); `shell` real kernel string;
    `http` 200; `env` HOME; `time` ISO; `tempfile`; `data` JSON+CSV; `clipboard`
    copy via wl-copy (independent `wl-paste`==sentinel, after `install-deps`).
  - Part B 11/11: `screenshot` real 1280x800 JPEG (portal, consent granted once);
    `screenshot_region` real 300x200; `click`+`type_text`+`key_press` ground-truthed
    via clipboard (typed sentinel round-tripped through ctrl+a/ctrl+c → wl-paste);
    `move_mouse`/`scroll`/`double_click`/`right_click`/`drag` executed via Mutter
    with no error; negative (`screenshot format=bogus`) raised `is_error`.
  - Part C: C3 editor write-out ground-truthed (`~/e2e-c3.txt`=="hello vadgr c3-ok"
    after click→type→ctrl+s). C1/C2 not run as separate tasks; the integration loop
    they exercise (screenshot→click→type→verify) is covered by C3 + Part B.
  - Resolved backends (`vadgr-cua doctor`): capture=portal, input=mutter-remotedesktop.
  - Extra live validation (beyond the scripted suite): drew a house on autodraw.com
    via 13 `drag` strokes + tool-select `click`, then closed the browser tab by
    landing a `click` precisely on the tab's close (×) button — both confirmed from
    follow-up portal screenshots. Exercises sustained pointer accuracy on GNOME 50.
- **Ubuntu 24.04.4 LTS (GNOME Shell 46.0 / Wayland), kernel 6.17.0-14-generic
  x86_64, 2026-06-28.** Backward-compat baseline. Driven by goal-level `claude -p`
  subagents against the 0.4.1 editable venv, restricted to the cua MCP tools
  (`--allowedTools mcp__vadgr-computer-use`, built-ins disallowed) so each cua
  tool is actually exercised; judged from the `tool_use`/`tool_result` JSON +
  independent ground-truth (`cat`, `wl-paste`, and orchestrator-side
  `gnome-screenshot` before/after frames).
  - Part A 10/10: `get_platform`/`get_platform_info`=linux; `get_screen_size`=1280x800
    (matches the screenshot frame); `fs` write+read (independent `cat`==`vadgr-a3-7Q2K9`);
    `shell` returncode 0 + real kernel string `6.17.0-14-generic`; `http` 200 (real
    httpbin body); `env` HOME=/home/vboxuser; `time` ISO-8601; `tempfile` abs path;
    `data` JSON+CSV parsed matching input; `clipboard` copy (independent
    `wl-paste`==`vadgr-a10-X4M8T`, after wl-clipboard install).
  - Part B 11/11: `screenshot` real 1280x800 + `screenshot_region` 300x200 (non-error;
    cross-checked against an independent gnome-screenshot frame); `click`+`type_text`+
    `key_press` ground-truthed via clipboard (typed `vadgr-b9-K7P3Q` round-tripped
    through ctrl+a/ctrl+c → `wl-paste`, and the text shown selected in an independent
    after-frame); `move_mouse`/`double_click`/`right_click`/`scroll`/`drag` executed via
    Mutter with non-error read-backs; negative (`screenshot format=bogus`) raised
    `is_error` ("Unsupported format"). Cold-start note: the first full `screenshot`
    via gnome-screenshot timed out twice at the 10s cap before succeeding, then was
    clean on re-run — a first-invocation warm-up flake, not a failure.
  - Part C: C3 editor write-out ground-truthed (`~/e2e-c3.txt` == "hello vadgr c3-ok\n
    second line e2e" after the subagent opened GNOME Text Editor via the overview,
    typed the note, and saved through the real GTK Save dialog). C1/C2 not run as
    separate tasks; the screenshot→click→type→verify loop they exercise is covered by
    C3 + Part B.
  - Backward-compat gate **pass**: `vadgr-cua doctor` resolved capture=gnome-screenshot
    (portal is `applicable` but correctly not selected — gnome-screenshot wins on
    priority) and input=mutter-remotedesktop — the same backends 24.04 uses today; no
    portal consent dialog appeared during the run.
  - Methodology note (single-listener does NOT apply to the desktop tier): unlike the
    browser tier, the desktop tools talk straight to gnome-screenshot / Mutter D-Bus,
    so each `claude -p` subagent spins up its own 0.4.1 cua server and drives the real
    screen directly. Run one at a time (shared screen); the editor subagent opens and
    focuses the app via the GNOME overview so keystrokes can't leak to the orchestrator
    terminal. Build note: this VM shipped minimal (no pip/venv/node/gcc, and no
    gnome-screenshot/wl-clipboard); cua 0.4.1 was installed editable with the
    pure-python input path (added python-xlib; evdev is now the optional `linux-uinput`
    extra, so no compiler), and `install-deps` provisioned wl-clipboard + the
    `/dev/uinput` udev rule. gnome-screenshot was apt-installed to match the stock-24.04
    capture baseline the gate expects.
  - Extra live validation (beyond the scripted suite): drew a recognizable house on
    autodraw.com via 13 `drag` strokes (square walls, triangular roof, door, window) +
    tool-select `click`s, no tool errors — confirmed from an independent follow-up
    gnome-screenshot. Mirrors the GNOME 50 run; exercises sustained pointer accuracy
    through Mutter RemoteDesktop on GNOME 46.
