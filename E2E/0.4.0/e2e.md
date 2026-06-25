# Browser tier 0.4.0 - end to end test runbook

Per-OS end to end validation of the browser tier (MV3 extension + native
messaging), driven by a real agent. Unit tests prove functions in isolation;
they do not prove the native-messaging pipe, the extension, and real pages work
on each platform. Run this runbook on each target OS and record the result in
the table at the bottom.

Target OSes: Linux, macOS, Windows (native), WSL (cua in WSL driving Windows Chrome).

## The approach: a Claude subagent over `claude -p`

Real end to end is driven by a real agent, never a script. A `.py` script that
calls `bridge.send` directly is an acceptance test only, not the e2e.

The runner gives a headless Claude Code subagent the cua MCP server and a
goal-level task, then reads the result from the agent's tool stream:

1. The task prompt is goal-level only: the page and the outcome. It never names
   HTML elements and never says how or what to verify. Verifying is the tool's
   job (the `browser` tool instructions). Whether the agent verifies on its own
   is part of what this measures.
2. The verdict comes from the `tool_use` / `tool_result` stream (cua's real
   read-backs), not from the agent's written summary.
3. A self-reported success with no confirming read-back is a fail.

## Prerequisites (per OS)

1. Install cua from this repo into a venv: `pip install .`
2. Build the extension: `cd extension && npm run build`
3. Load `extension/dist` as an unpacked extension in Chrome or Edge. Reload it
   after any rebuild. Accept the `debugger` permission when prompted.
4. On WSL nothing else is needed: cua self-registers the native host and places
   the Windows relay shim automatically on startup. cua runs in WSL, Chrome runs
   on Windows.
5. Sanity check: the agent's first `browser(op="status")` returns
   `connected: true`.

## How the runner drives a test

Write an `.mcp.json` that launches cua from the venv:

```json
{
  "mcpServers": {
    "vadgr-computer-use": { "command": "<venv>/bin/vadgr-cua", "args": [] }
  }
}
```

(On Windows the command is `<venv>\\Scripts\\vadgr-cua.exe`.)

For each test, pipe the goal-level prompt to the subagent over stdin (not as a
command-line argument, which truncates long prompts):

```
<prompt-file> piped to:
  claude --dangerously-skip-permissions --max-turns 60 \
    --mcp-config .mcp.json --output-format stream-json --verbose -p
```

Run exactly one subagent at a time. Never run tests in parallel: the browser
tier drives a single focused Chrome window over one extension connection, so
concurrent agents would fight over the same window. Finish and judge one test
before starting the next. Run Part A first, then Part B. Run the YouTube test
last in Part B because it leaves a playing tab.

## Part A: acceptance pages (run first)

Deterministic sandbox: `the-internet.herokuapp.com` and `saucedemo.com`. Each is
a goal-level task; the expected outcome is judged from the stream.

- A1 Login: log into `the-internet.herokuapp.com/login` with `tomsmith` /
  `SuperSecretPassword!`. Expect the success banner.
- A2 Async load: on `/dynamic_loading/2`, start the load and read the revealed
  text. Expect "Hello World!".
- A3 Form controls: on `/dropdown` choose an option, on `/checkboxes` toggle the
  first box, on `/inputs` enter a number. Expect each value reflected.
- A4 Scroll: on `/infinite_scroll`, scroll down a few times. Expect the page to
  grow.
- A5 Extract: on `/tables`, count the data rows in the first table.
- A6 History: navigate two pages, then go back and forward. Expect the correct
  URLs at each step.
- A7 Dynamic DOM: on `/add_remove_elements/`, add three elements then delete
  one. Expect three then two.
- A8 Checkout: on `saucedemo.com`, log in, add the first item, open the cart,
  confirm the same item is in the cart.
- A9 Negative: act on a selector that cannot match anything. Expect a raised
  error, not a silent success.

Pass for Part A: every outcome is confirmed from the stream, the agent verifies
before moving on without being told to, and A9 raises.

## Part B: real sites (run after Part A)

Production sites on the user's real logged-in browser. A not-logged-in or
captcha situation is recorded as blocked, not a tier failure. Run B2 last.

- B1 Gmail: send a short email to the user's own address. Expect it sent with
  the intended body, not an empty or hollow body.
- B2 YouTube Music: play a named song. Expect it playing, with the player time
  advancing.
- B3 Google: search a query. Expect at least three real result titles.
- B4 Wikipedia: look up a person. Expect the correct fact.
- B5 Amazon: search a product, open one, add it to the cart. Expect the cart to
  reflect it.
- B6 Google Flights: starting from the bare page, search a one-way flight using
  the on-screen origin, destination, and date fields. Do not encode the route or
  dates in the URL. Expect a fare.
- B7 GitHub: find a repository. Expect the correct star count and main language.

Pass for Part B: the outcome is confirmed from the stream and the agent verifies
on its own. A self-reported success with no read-back is a fail.

## Per-OS results

Fill these in by running the runbook on each OS.

Legend: pass / fail / blocked (login or anti-bot) / not run

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part A (A1-A9) | not run | not run | not run | pass |
| Part B (B1-B7) | not run | not run | not run | pass |
| Overall | not run | not run | not run | pass |

Status notes:
- WSL was exercised during development of this branch: Part A nine of nine, and
  Part B seven of seven (including a live Gmail send and the actionability gate
  firing on the hidden form mirror).
- Windows native, Linux, and macOS: pending.
