# &lt;version&gt; - &lt;what this minor made true&gt;: e2e runbook

> Copy this file to `E2E/<version>/e2e.md` and fill it in. Delete every
> quoted instruction block as you go: they are addressed to whoever writes the
> runbook, and nothing addressed to a writer belongs in the finished one.
>
> **This template is this repo's, not a shared one.** `vadgr` proves an API and
> a CLI, `vadgr-mobile` proves a screen in a person's hand, and this repo proves
> **a real agent driving a real desktop**. The shape below follows from that: the
> driver is a Claude subagent, the oracle is the JSON it emitted, and the axis
> that has to be repeated is the **operating system**.

## The approach: a Claude subagent over `claude -p`

> Say which model, which MCP config, and what the agent was told. The task is
> **goal-level** ("log in and confirm the banner"), never a script of tool calls:
> a runbook that dictates the calls tests the runbook, not the runtime.

## The oracle is the JSON, never the agent's prose

**`E2E/README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative test must show
`is_error: true`, and with neither stream nor transcript the result is
**not verified** rather than a pass.

> Name where this pass's JSON landed - the teed stream, or the `~/.claude`
> transcript path - so a reader can check your verdicts rather than trust them.

## Prerequisites (per OS)

> One block per operating system this pass covers. Display server, browser and
> extension state, profiles, and anything that must already be running. An
> unstated prerequisite becomes a mystery failure on the OS nobody had at hand.

## Setup

> Every command in full, from a stated working directory. The reader is setting
> up a machine they have never set up before.

## Automated gate (necessary, never sufficient)

> The unit and integration suites, with the command and the expected result.
> Green here proves the code paths, and proves **nothing** about a real desktop:
> that is the whole reason this document exists.

## Coverage

> What this pass claims, and against what. A table of the tools or surfaces
> exercised, each with the part that exercises it. A surface with no part is
> uncovered and is listed as such - silence reads as covered.

## Part &lt;X&gt;: &lt;what it proves&gt;

> Parts, not cells: this repo's unit of work is an agent task with a verdict,
> not a tap. Order them so a later part can rely on an earlier one, and say when
> it does.

**Task given to the agent:**

> The literal prompt. Goal-level.

**Verdict from the JSON:**

> Which `tool_use` calls had to appear, and which `tool_result` read-backs
> confirm the effect. Be concrete enough that two people reading the same
> transcript reach the same verdict.

**Expected result:**

> What a pass looks like, in terms a reader can check.

## When a part surfaces a bug: fix it, then re-run it

**A defect found during a pass is fixed during that pass**, with a test that
fails without it, and **the part is re-run from a clean state** before being
marked. Never logged and carried to the end: the diagnosis is never fresher
than the minute it was found, a later part may build on the broken behaviour
and hand you a second false result, and a pile of deferred findings is how a
runbook ends "green with notes", which is not green.

## Repeatability

> How many independent passes, and what makes them independent. For an
> agent-driven pass the interesting axis is **the OS and the display server**,
> not repetition on one box - a second run on the same machine mostly re-proves
> the machine.
>
> Compare structurally: the tool calls issued, their order where order matters,
> and the error codes. Expect the agent's prose to differ every time and the
> **tool calls not to**. Identical prose across runs is a warning, not a comfort.

## Per-OS results

| part | Linux | Windows | macOS | notes |
|---|---|---|---|---|
| &lt;X&gt; | | | | |

> `pass` / `fail` mean it ran. `blocked` means it could not run, and says what
> broke. `not run` means nobody ran it - honest, and visibly owed.
> `planned <version>` means committed and scheduled, and is checkable against
> that minor. Never `deferred`: it reads as abandoned when the commitment stands.
>
> **A cell is marked from observation, never expectation.** Unwatched is
> `not run`.

## Evidence

> Where the artifacts are, and what each one is. Filed **while the pass runs**,
> at each part's boundary - a bundle assembled afterwards is one whose artifacts
> were chosen once the answer was known. A part that captured nothing gets a
> note saying so, never a reconstruction, and failures are kept alongside both
> sides of any fix.

## Findings

### F1 (&lt;fixed | open&gt;): &lt;the defect in one line&gt;

> What was seen, what caused it, what was done, and **what proves the fix**.
> A fix whose only proof is an unrun part is unproven.

## What this runbook cannot prove

> The honest limits. Hardware not owned, an OS not covered, a permission dialog
> nothing automated can accept. A reader deciding whether a gap is a risk needs
> this section more than any other, and it is the one most often left out.
