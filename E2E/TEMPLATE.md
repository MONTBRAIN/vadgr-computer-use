# &lt;version&gt; - &lt;what this minor made true&gt;: e2e runbook

> **Read this whole file before you run anything, and read
> [`README.md`](README.md) beside it.** Not the rules that look relevant to the
> cell in front of you: the whole file. Every rule in it was written because a
> pass broke it, and a pass that starts at the first cell meets them one at a
> time, each at the cost of the thing it was protecting.
>
> **This instruction exists because a rule that was already written, already
> indexed and already in front of the driver was broken by three separate
> passes**: evidence for `vadgr 0.4.7`, `0.4.8` and `0.4.9` was pushed straight
> to the docs default branch instead of the minor's evidence branch, once per
> release, by a host that had the rule on its screen. Reading the document is
> the cheapest of every remedy available, and it is the one that was skipped.

> Copy this file to `E2E/<version>/e2e.md` and fill it in. Delete every
> quoted instruction block as you go: they are addressed to whoever writes the
> runbook, and nothing addressed to a writer belongs in the finished one.
>
> **This template is this repo's, not a shared one.** `vadgr` proves an API and
> a CLI, `vadgr-mobile` proves a screen in a person's hand, and this repo proves
> **a real agent driving a real desktop**. The shape below follows from that: the
> driver is a headless agent CLI session, the oracle is the JSON it emitted, and
> the axis that has to be repeated is the **operating system**.

## The rules

**Read this before the first cell.** Every rule here was learned by breaking it,
they hold on every supported operating system and for every driver of a runbook,
and none of them is negotiable against a deadline or a token budget.

**This list is an index, not the rules themselves.** Each entry is deliberately
short. A bracketed name is where the rule is stated in full, with the incident
that produced it: a section of this file, or `../README.md`. Read the entry
before you start and the section when it bites. Where a bracketed name is not
present in a given runbook, the entry is all there is.

1. **Whatever needs the owner runs first.** Read the whole matrix, list every
   cell that cannot proceed without a human, and run those cells before any
   unattended one. **Running them is the rule; announcing them is not.**
   [How a pass is run] [../README.md]

2. **Do not stop the pass to report.** The pass runs to completion for the
   operating system it is on, and what it finds is written down as it happens and
   reported at the end. [How a pass is run] [../README.md]

3. **A bug you find is a bug you fix, here and now, with a test that fails
   without the fix.** Re-run the failing cell until it passes and push to the
   pull request branch before carrying on. [How a pass is run] [../README.md]

4. **A fix invalidates the cells it touched on every operating system that passed
   them**, so name them, mark them `not run` and re-run them. **A rebuild is a
   new subject**: re-run the identity cell and record the new hashes before any
   further cell. [How a pass is run]

5. **The evidence is pushed, not left on the machine that produced it, and it is
   pushed to the private docs repository** under `e2e_evidence/<repo>-<minor>/`,
   never into this one. The pull request carrying it is opened there as part of
   the pass, not after somebody asks. [How a pass is run] [Evidence]

6. **A cell is `pass` only when the observation and the artifact both exist.** A
   cell that ran, was read correctly and left nothing on disk is `not run` with a
   note. [How a pass is run]

7. **Evidence is what the execution produced, never a summary somebody wrote**:
   captured stdout and stderr with the exit code, wire bodies as they arrived,
   hash lines, listings, log lines, socket frames, journals. A coverage table is
   generated from a recorded sweep, never typed. [How a pass is run] [Evidence]

8. **One branch per minor for evidence, in the docs repository, and every host
   pushes into that one branch.** `evidence/<repo>-<version>`, cut once from a
   freshly pulled default branch there: a later operating system adds its
   boundary beside the first rather than opening a second pull request, and
   nothing else travels in it. **The default branch is never the target**, on
   any host, for any reason, and a pass that cannot find the branch asks for it
   rather than pushing past it. Broken once per release for three releases
   running, always by the same host and always with the rule on screen, so it is
   now a check rather than a sentence. [How a pass is run]

9. **A fix is verified by re-running the cell that found it**, whole and from its
   stated precondition, against a rebuilt and reinstalled product. A unit test is
   necessary and never sufficient.
   [A fix is verified by the cell that found it] [../README.md]

10. **Never edit a cell so it matches the behaviour you shipped.** If an
    assertion is genuinely wrong, say so in the cell's status and leave the
    assertion where the next reader can argue with it.
    [A fix is verified by the cell that found it]

11. **One failure is not a finding: reproduce before you diagnose, and reproduce
    through the same path the user used.** Behaviour that worked earlier with
    nothing changing it, and a failure you cannot reproduce on demand, are both
    evidence for a transient.

12. **Account for what the pass leaves running and on disk.** List and stop every
    process the pass started and show the ports free, and name the directories a
    group created in that group's cleanup column.
    [Account for what the pass leaves running]
    [Account for what the pass leaves on disk]

13. **One command at a time, and read its output and exit code before choosing
    the next.** A result from a command whose exit code you did not read is not a
    result. [One command at a time, and read its output before the next]

14. **Before you file a finding, suspect your own harness**, and do not stop one
    question early: a harness can create the condition while the product's answer
    to that condition is still wrong.
    [Before you file a finding, suspect your own harness]

15. **Finish the matrix: every cell carries a verdict or a named blocker**, and a
    blocked cell is owed only after the blocker itself was investigated.
    `Not-Needed` is a verdict with a reason, never a synonym for "did not run".
    [Finish the matrix] [Per-OS results] [../README.md]

16. **The oracle is never the product's own report.** The verdict comes from what
    the machine wrote down, and a claimed success with no confirming read-back is
    a fail; with neither journal nor transcript the result is `not verified`
    rather than a pass. [The approach] [../README.md]

17. **The runbook is complete before the first live cell, and the surface is
    enumerated rather than sampled.** Name the axes, multiply them, write the
    count, and give every cell an id, precondition, setup, action, expected
    observable, oracle, evidence boundary, cleanup and result slot. A check that
    needs something not built yet belongs to the minor that builds it.
    [Coverage] [../README.md]

18. **Evidence is filed while the pass runs, never assembled after it.** A bundle
    assembled once the answer was known is a bundle whose artifacts were chosen,
    and a group that captured nothing gets a note rather than a reconstruction.
    [Evidence] [../README.md]

19. **Credentials never enter Git or evidence.** Read only what a cell needs from
    the workspace `../.env`, never echo or copy a value anywhere, and run the
    secret check before every commit and before evidence is sealed.
    [Owner and environment requirements]

20. **Passes are independent only when each has its own port, database and
    daemon.** Two drivers sharing one daemon read each other's work and neither
    verdict means anything. [Repeatability] [../README.md]

**A pass is finished, not paused, and reporting is not a stopping point.** A
checkpoint or a progress summary does not end your turn: write it and keep
driving in the same turn. A pass ends when every cell carries a verdict or a
named blocker. Only a cell that cannot proceed without the owner, or a decision
only the owner can make, ends one early. Stopping to report looks like progress
and is the opposite, because the cells that were never run stay never run.

## How a pass is run, before anything else in this file

**These six rules come first because every one of them was learned by breaking
it. They hold on every supported operating system, for every agent that drives a
runbook, and they are not negotiable against a deadline or a token budget.**

**1. Whatever needs the owner runs first.** Before a single automated cell,
read the whole matrix, list every cell that cannot proceed without a human, and
run those cells at the start of the pass. A browser approval, a physical
handset, a hardware key, an elevation prompt, a permission dialog, a paid
account that must be enabled: all of it is scheduled first, in one batch, with
the owner told exactly what to click and when. The owner is not a resource you
discover you needed after four hours of work. A pass that reaches its end and
then asks for a click has wasted the owner's day and produced a runbook that is
still `not run` where it matters most.

**2. Do not stop the pass to report.** The pass runs to completion for the
operating system it is on. Findings, blocked cells, corrections and questions
are written into the runbook and the evidence as they happen, and they are
reported when the pass ends. The only thing that stops a pass is a cell that
physically cannot proceed without the owner, and rule 1 exists so that never
happens after the start. Reporting a blocker mid-pass, and waiting, converts one
run into many and leaves every later cell unexecuted.

**3. A bug you find is a bug you fix, here, now.** The purpose of an e2e is not
to catalogue defects. It is to establish that the product works on the target
operating system. So when a cell fails, you fix the code, you add a test that
fails without the fix and passes with it, you re-run the failing cell until it
passes, you commit and push to the PR branch, and only then do you carry on with
the rest of the matrix. **A finding recorded without a fix is a moved problem,
not a found one.** The fix ships on the PR branch as it is made; the branch is
the working surface, and holding a fix back to ask permission is the mistake.

**4. A fix invalidates the cells it touched, on every operating system that
already passed them.** A shared-behaviour fix means the earlier passes were
observing different code. Name the affected cells in the finding, mark them
`not run` again on the operating systems that had passed them, and say in the
per-OS matrix which fix invalidated them. The host that made the fix re-runs
them itself. The other hosts re-run them from the PR branch before merge. **No
operating system inherits a result from a build that no longer exists.** And a
rebuild is a new subject: rebuild the wheel, reinstall it, and re-record its
hash **before any further part**. A sibling repo's pass filed a cell whose
output only a later commit could produce, under a host record naming the
earlier head; nothing tied any result to any build, and the whole pass was
invalidated.

**5. One command at a time, and read its output before the next.** Every
product command is invoked on its own, and its output and exit code are read
before the next command is chosen. A wrapper script that runs a whole group in
one shot is not an execution of that group, even when every command inside it is
the real public surface: it prints one wall of output that no line can be
attributed to, it reports one exit code so the ones inside it are never read, a
failure in the middle is carried past by the lines after it, and it fixes the
order in advance when what the previous command returned is what tells you
whether the next one is still the right one. A helper may build isolated state
**before** a group and capture or parse evidence **after** a command has run. It
may not sequence the product commands. The exception is a cell whose own
definition is a matrix, such as one fixture per isolated copy: there the
repetition is the cell, it is written that way in the table, and each iteration
still prints its own labelled result.

**6. The evidence is pushed, not left on the machine that produced it.** The
boundary directory is created before the first cell, each group files its output
at its own boundary, and **the whole boundary is committed on a branch and
opened as a pull request as part of the pass, not after somebody asks for it**.
A pass whose evidence sits in a temporary directory on the host that ran it is a
pass nobody can check: the numbers in the runbook have nothing behind them, the
next host cannot compare its own record against yours, and the directory is one
reboot from gone. Filing it is the last cell of every pass, and a report that
says the pass is complete while the artifacts are still local is wrong about
what complete means. This is written here because it happened: a full native
Linux pass was reported as done with its runbook results pushed and 51 evidence
files still in `/tmp`, and only the owner asking "evidence are pushed?" caught
it.

## The approach: a headless agent CLI session

> Say which CLI drove it (Codex or Claude Code, whichever the machine has) and
> its version, which model, which MCP config, and what the agent was told. The task is
> **goal-level** ("log in and confirm the banner"), never a script of tool calls:
> a runbook that dictates the calls tests the runbook, not the runtime.

## Paired surfaces this pass depends on

> **This runtime depends on no sibling repository, and that is worth stating
> rather than assuming.** It is an MCP server: a client launches it over stdio
> and calls its tools. The daemon is one such client and the agent CLI driving
> this pass is another, so the dependency runs towards this repository, never
> out of it. A part here needs a released tag from nowhere else.
>
> That independence is a property to protect, not a permanent fact. **If a part
> ever needs a surface a sibling repository serves**, it stops being true, and
> then the rule applies: read that repository's released tag and the source
> behind the route, name the version the part depends on in a table here, and
> write a part whose surface arrives later into that release's runbook instead,
> stating its absence rather than leaving it silent.
>
> | repository | released version | what this pass relies on |
> |---|---|---|
> | none | not applicable | this runtime is driven by its clients, and calls none of them |
>
> The rule exists because a sibling repository shipped a cell telling a tester
> to start a run from the phone. That is the mobile app's next release; the
> shipped app only reads. The owner found it holding the handset.

## The oracle is the JSON, never the agent's prose

**`E2E/README.md` governs this and is not restated here.** In one line: the
agent's summary is self-report, a mutating action counts only when a
`tool_result` read-back confirms it, the negative test must show
`is_error: true`, and with neither stream nor transcript the result is
**not verified** rather than a pass.

**An oracle must be able to detect the failure it names.** Before the pass,
ask each part's check what it returns when the runtime is wrong: if the answer
is "the same thing", it is decoration, not an oracle, and the part can never
fail. A sibling runbook once asserted a mint through a list the minted thing
never appears in.

> Name where this pass's JSON landed - the teed stream, or the driving CLI's
> transcript path - so a reader can check your verdicts rather than trust them.

## Owner and environment requirements

> Complete this table before the first live part and inform the owner before an
> affected group starts. Include each OS or desktop, application, account,
> credential, permission, destructive action and owner decision. Missing setup
> blocks the already-written ids; it never removes them or reduces coverage.

> Host networking is never e2e state. Do not change the host firewall, DNS,
> routing, proxy, VPN or network service. Model a network failure in isolated
> test state. A host network change is never an e2e cell.

> Read credentials only from the workspace `../.env`. Never echo or copy a
> value into commands, logs, screenshots, transcripts, process listings,
> GitHub text, documentation or evidence. Run
> `python3 scripts/check_no_secrets.py --env-file ../.env` before every commit
> and before sealing evidence.

| requirement | parts or cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| &lt;item&gt; | &lt;ids&gt; | &lt;check&gt; | &lt;boundary&gt; | &lt;action&gt; |

## Billed model selection

> Complete this table from current official provider pages and the
> authenticated account catalog on the execution date. Pick the least expensive
> model that supports the exact agent task and MCP/tool-use contract. Do not
> start a billed call with a blank ceiling or an unrecorded escalation path.

| parts or cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| &lt;ids&gt; | &lt;provider/method&gt; | &lt;tools, content, continuation&gt; | &lt;authenticated id or snapshot&gt; | &lt;URL, YYYY-MM-DD&gt; | &lt;USD per MTok or subscription limitation&gt; | &lt;all three ceilings&gt; | &lt;recorded capability failure or none&gt; |

> An automatic client-selected model is exercised once when that selection is
> part of the delivered user path. Repeated provider-neutral work names an
> explicit cost-effective model. Add another model only for a distinct protocol
> or capability class or a prewritten model-specific cell. Record actual usage
> and cost, and stop when any ceiling is reached. Pixel or screenshot CUA
> requires image input for the selected endpoint and image-bearing tool-result
> continuation into the next model turn; record both under required
> capabilities. A text-only model cannot close that visual group.

## Prerequisites (per OS)

> One block per operating system this pass covers. Display server, browser and
> extension state, profiles, and anything that must already be running. An
> unstated prerequisite becomes a mystery failure on the OS nobody had at hand.

## Setup

> Every command in full, from a stated working directory. The reader is setting
> up a machine they have never set up before.

## Remote-host handoff for Linux, macOS and Windows

> Complete this section before a native-platform part runs. A new Codex session
> must be able to execute the part without hidden context or access to the first
> test machine. Include all of these items:

1. Files to read first: `AGENTS.md`, `E2E/README.md`, this runbook and the public
   installation and platform instructions.
2. The exact PR head rule, wheel build command, wheel hash command and fresh
   virtual-environment install command. Drive the installed wheel and
   `vadgr-cua` entry point from outside the source tree. Never use an editable
   install as the product under test.
   The agent CLI's MCP config must invoke that `vadgr-cua` entry point. A Python
   driver, `python -m`, a product import or a private function is acceptance
   evidence and cannot close an e2e part. Helpers may prepare state, capture
   streams and parse evidence, but they cannot drive the goal.
3. Paste-ready native setup for every claimed OS. Include Linux
   `vadgr-cua install-deps --yes`, macOS Accessibility and Screen Recording for
   the installed environment's Python, and native Windows execution without
   routing through WSL.
4. The exact display, browser extension, profile, permission and application
   preconditions. Record `vadgr-cua doctor` before the first agent task.
5. The part ids and order, goal text, independent JSON or OS read-backs,
   evidence captured before cleanup and result rows that host updates.
6. Cleanup boundaries. Remove only the fresh environment and reversible test
   effects. Never stop unrelated processes, browsers or applications.
7. Credential handling. Read only required values from the owner-only
   workspace `../.env`; never print or persist them. Run the secret check before
   the group and before evidence is sealed.

> Use a separate evidence boundary for Linux, macOS and native Windows. A CI
> matrix, type check or WSL pass never substitutes for these native sessions.


**The harness travels with this runbook.** Every helper the pass uses - the
recorder, the generator that turns its record into a table, a decoder, a stand-in
server - is committed at `E2E/<version>/harness/` with a README saying what each
one is and that none of them drives the product. **A helper that exists only in a
temporary directory on the machine that wrote it cannot be run anywhere else**,
so every other host produces a record nobody can compare, and comparison is the
point of a recorded sweep. Run each helper from its committed path before the
runbook is offered.

**Name what a host cannot do, not only what worked.** List the prerequisites the
pass actually hit, each saying **which cells it blocks** and what a host without
it records. A handoff assembled from the happy path leaves the next operating
system discovering a blocker four groups in.

## Automated gate (necessary, never sufficient)

> The unit and integration suites, with the command and the expected result.
> Green here proves the code paths, and proves **nothing** about a real desktop:
> that is the whole reason this document exists.
>
> **And the gate is not green until the pull request's checks have finished.**
> The suites above ran on one machine, the one the pass was driven on. The pull
> request runs them across the interpreter and operating system matrix, and
> those are the machines nobody looked at. **A pass is not closed and a pull
> request is not offered for review while a check is still running.** Waiting
> costs minutes; a release announced green over a check still running is a claim
> about machines nobody read.
>
> The last step of a pass is to watch the checks to completion and record their
> result beside the local ones. A red check is a finding like any other: it is
> fixed and the parts it invalidates are run again, or it is written down with
> its reason. A sibling repository offered a release as finished while its
> Windows job was still running, and that job went red.

## Coverage

> What this pass claims, and against what. A table of the tools or surfaces
> exercised, each with the part that exercises it. A surface with no part is
> uncovered and is listed as such - silence reads as covered.

> Any part that starts an owned subprocess has a separate cancellation case.
> Cancel the live MCP request while that child is active. Prove the request has
> no later successful result and the entire owned process tree exits within the
> written bound. Test this on every OS the subprocess path supports.

## Part &lt;X&gt;: &lt;what it proves&gt;

> Parts, not cells: this repo's unit of work is an agent task with a verdict,
> not a tap. Order them so a later part can rely on an earlier one, and say when
> it does.

> Every counted edge case has its own stable id, precondition, setup, goal,
> expected observable, JSON oracle, evidence boundary, cleanup and result slot.
> Do not collapse cases into prose or a "remaining matrix" row.

> **Depth is required, not optional.** A part that opens an app and performs one
> action is a smoke test, not a part. Each part chains several steps and confirms
> the state structurally between each, and at least one part spans two apps: make
> a thing in one, act on it in another, and confirm across the boundary. A suite
> of open-and-do-one-thing parts passes without proving the tier survives a real
> task. Judge the suite on the deepest task it drives, not the count of apps.

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

**The rows are this runbook's own parts, and nothing else.** A row named for a
theme rather than a part cannot be read back to the cells that produced it, so a
reader cannot check it and a reviewer cannot audit it. A sibling runbook shipped
a matrix whose rows were `credential matrix`, `live providers` and `full engine`,
none of which named a part or a cell, and it was unreadable for that reason.

**Where a case runs on several platforms, put the platform in the cell id**, so
the row and the cells agree by construction, and name those ids in the notes.

**`overall` never inherits the automated gate.** A green CI row says the suites
pass on that OS and nothing about whether the product works there.

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
>
> The runbook's own header and tables are part of the deliverable: the status
> line, the coverage table and this matrix are re-read against the part results
> before the runbook is offered. A file whose header and cells disagree is
> wrong twice, and a reader cannot tell which half to believe.

## Evidence

> Where the artifacts are, and what each one is. Filed **while the pass runs**,
> at each part's boundary - a bundle assembled afterwards is one whose artifacts
> were chosen once the answer was known. A part that captured nothing gets a
> note saying so, never a reconstruction, and failures are kept alongside both
> sides of any fix.
>
> A boundary contains the artifact it names, never a sentence about it: named
> hashes are the hash lines themselves, a named transcript is the file.
> "Unchanged: yes" is the product's word taken for the state, which is exactly
> what the JSON-oracle rule exists to distrust.

## Findings

### F1 (&lt;fixed | open&gt;): &lt;the defect in one line&gt;

> What was seen, what caused it, what was done, and **what proves the fix**.
> A fix whose only proof is an unrun part is unproven.

## What this runbook cannot prove

> The honest limits. Hardware not owned, an OS not covered, a permission dialog
> nothing automated can accept. A reader deciding whether a gap is a risk needs
> this section more than any other, and it is the one most often left out.
