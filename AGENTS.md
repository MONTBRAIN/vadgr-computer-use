# vadgr-computer-use - the hands

The MCP runtime that drives the local machine: Tier 0 system tools, Tier 1
browser (MV3 extension, DOM-first) and structured (AX/UIA/AT-SPI), Tier 2 pixel
fallback. **Policy-free by contract**: this repo drives the machine and emits
`tier` + `risk`; `vadgr`'s loop owns authorization, approval, the denylist,
redaction and channels. Never add a policy decision here.

**This file is loaded automatically. The rules live in the docs repo and are not
copied here** - a second copy drifts. What follows is what must not be looked
up, plus where to look for everything else.

## Where this repo stands

Shipped and store-published, in real daily use. **Frozen at `0.6.x`
demand-driven patches through phases 1 and 2**, rejoining with its own minors
from phase 3.

**Frozen is not finished.** Four roadmap items remain
(`vadgr-docs/general/ARCHITECTURE.md` §8): the structured tiers per OS
(`0.7.0` Linux AT-SPI, `0.8.0` Windows UIA, `0.9.0` macOS), the CLI-wrapper tier
(`0.10.0`), and **element memory** and **stealth levels**, which stay unnumbered
until demand decides their order.

**Everything here is demand-gated**: it ships when a real task blocks on it, not
on a schedule. A patch that unblocks real browser work today is the normal case
and needs no minor.

## Before you touch anything

```bash
gh repo clone MONTBRAIN/vadgr-docs        # if it is not already beside this repo
```

Read `vadgr-docs/general/ARCHITECTURE.md` §8 (this repo's architecture and
roadmap, including the tier ladder and §8.1's decided element-memory design),
then `vadgr-docs/PLANS.md` for where a minor is homed and what gates it.
`vadgr-docs/AGENTS.md` and `general/ENGINEERING.md` are the full conventions -
**not auto-loaded, which is why this file names them.**

## Things that must never be looked up

**1. This repo is public. The private docs are never named in it** - not
`ARCHITECTURE.md`, `PLANS.md`, `CONTRACT.md`, `ENGINEERING.md`, no `D-xx` id, no
`vadgr-docs/` path - in code, comments, the CHANGELOG or a PR body. State the
substance. Sweep before every push:

```bash
grep -rn "CONTRACT\.md\|PLANS\.md\|ARCHITECTURE\.md\|ENGINEERING\.md\|vadgr-docs\|D-[0-9]" \
  --include=*.py --include=*.js --include=*.md . | grep -v "node_modules\|AGENTS.md\|CLAUDE.md"
```

**The exception, stated so it is not guessed at: this file and `AGENTS.md` name
the private docs on purpose** - they are the entry point, and a pointer that
cannot name what it points at is useless. The ban is on everything a stranger
reads as the product: code, comments, docstrings, test names, the CHANGELOG and
PR bodies. Those cite the substance, never the document.

**2. No AI attribution, anywhere** - no `Co-Authored-By`, no "generated with",
in commits, PR bodies or files.

**3. The four-platform rule.** Linux, Windows, macOS and WSL are each first
class. A change that touches a path, a process, a socket or a native API is
**owed** on each, not excused - and `Not-Needed` is a real verdict only when
there is genuinely no OS-specific surface, always stated with its reason.

**4. The tier ladder is the performance argument.** Structured tiers return
small text; pixels are the fallback, never the default. A change that quietly
moves work down a tier makes every agent loop more expensive.

**5. Design comes before code** for anything carrying a minor:

```bash
python3 ../vadgr-docs/scripts/check_iteration.py <phase> <iteration>
```

(use whatever name the docs repo was cloned under beside this one.) Exit `0` or do not start.

## The practices every repo in this family follows

**This section is identical in every code repo, and identical in this repo's
`CLAUDE.md` and `AGENTS.md`.** An agent loads one or the other depending on the
tool it runs under, and it must not get a different standard depending on which.
The long form of every rule here is `vadgr-docs/general/ENGINEERING.md`; these
are the ones that cost the most when missed.

**Ask in this order, and asking is the last resort**: `PLANS.md` including the
decision register, then `CONTRACT.md`, then `ARCHITECTURE.md` and the minor's
design doc - **then** the owner, saying which you checked and what each did not
answer. **A decision marked `Ruled` is an answer, not an option.**

**Do not bring a problem without a decision.** Anything found is either fixed,
or written into `PLANS.md` under the minor that owns it, with the reason. A
defect reported with no disposition moves the work rather than doing it.

**Design comes before code.** No minor is implemented until its build spec
exists and every minor in its iteration has one. Exit `0` or do not start:

```bash
python3 ../vadgr-docs/scripts/check_iteration.py <phase> <iteration>
```

Exit `0` is necessary and never sufficient: it checks that specs exist and are
structurally complete, and it cannot review one.

**CI is not an e2e pass.** The automated gate builds an environment and runs the
unit suites. It drives no session, calls nothing over the wire and reaches no
glass, so a green CI row on an OS says the suites pass there and **nothing at
all** about whether the product works there. An OS whose only evidence is CI is
marked `not run`, never `pass`, and a runbook's `overall` row never inherits a
gate result: it is the weakest of the parts actually driven on that OS. This
shipped once and was caught in review, with two platforms marked `pass (CI)`
while their own live rows read `not run`. **A suite is not a session.**

**Close an e2e with three independent passes**, run concurrently, each with its
**own port, database and daemon** - three observations rather than one run
watched three times. Compare them structurally: every HTTP entry on method,
path, status and **error code**, every CLI entry on argv and exit code, and the
frame type counts per socket. Then read the token counts with the fixture
pinned first, because three identical output counts suggest one result reused
rather than three real calls. **Ask each pass what looked odd, not only whether
its steps passed**: one sweep was entirely green when an agent noticed a single
case taking 15.2s against 0.1-0.8s for every other, which no assertion could
have caught because nothing asserted on duration.

**Drive an e2e with the agent CLI the machine has, and name it in the runbook.**
Codex and Claude Code both run a headless session with their own MCP config, and
either satisfies the method: a **fresh** MCP server started from the session's
own config, the `tool_use` / `tool_result` stream as the verdict, and an isolated
working directory. **Detect the CLI, do not assume it.** Record which one ran and
its version beside the result, because two passes driven by two CLIs are still
two observations, and a reader cannot compare them if the runbook does not say.
A result with no CLI named is a result nobody can reproduce.

**Evidence is filed while the pass runs, never assembled after it.** The
evidence directory exists before the first cell, each group files what it
produced at its own boundary, and a group that captured nothing gets a note
rather than a reconstruction.

**Every test suite states what it starts from.** The precondition is the
guarantee, not the reset: every suite declares the state it needs, nothing
inherits silently, and setup happens at the **start** of a group rather than as
the previous group's teardown - a teardown that did not run leaves the next
group dirty, and its failure looks like a product defect. Resetting between
every case is ritual, not rigour.

**Every fix gets a test that fails without it.** Stash the fix, watch it go red,
restore. A test that passes either way tests nothing.

**Never report a result from a command whose exit code you did not read**
(`cmd | head` reports `head`'s), and **a pass with no output is not a pass** - a
sweep once exited `0` five times printing nothing, against a daemon it never
reached.

**Audit once, exhaustively.** Run everything, fix everything, report once.
Fixing, re-checking, finding one more and repeating reads as an endless stream
of problems and is really one incomplete sweep.

**A result you did not produce is not a result.** Never write a number, a
status, a timing, a token count or a table row that no command printed. Evidence
is the artifact - the log, the record, the exit code - and the prose is a reading
of it, never a substitute for it. **A coverage table is generated from a recorded
sweep, never typed.** The failure this stops is not laziness: it is an agent that
could not run a step and wrote what the step would plausibly have said, which is
unfalsifiable at review and makes every real result in the same document worth
nothing. **`not run`, `blocked` and `partial` are always available and always
acceptable**; a fabricated pass never is. If a step could not run, say which,
why, and what would let it run.

**Implementation is delegated and driven to a finished PR, not hand-held slice
by slice.** A minor's build runs the steps end to end and does not come back
until the PR is review-ready: every slice implemented, the unit suites green,
the README, CHANGELOG and version updated, and the e2e runbook drafted. Breaking
the work into internal increments is correct engineering; stopping after one to
ask "should I continue?" is not, because the increments are the builder's to
sequence rather than the owner's to approve one at a time. **Stop for exactly
two things**: a genuine decision only the owner can make - surfaced with the
options and a recommendation - or a defined approval gate, which is running the
e2e (its runbook is approved before it runs) and merge, tag and release.

**Write your replies to the owner in Simplified Technical English, ASD-STE100.**
In Claude Code, set the output style to it; a CLI with no such setting applies
the rules below directly. This applies on every machine and in every repo, so
it is written in each entry point and not in one person's local settings.

The rules:

- Use short sentences. Use 20 words or less for an instruction. Use 25 words or
  less for a description.
- Write one instruction in one sentence.
- Use the active voice. Write "the check found three defects", not "three
  defects were found".
- Use simple and common words. Do not use a technical word when a common word
  is correct.
- Do not use metaphors, idioms or jokes. They are the most frequent defect in
  this project's replies.
- Use the articles "a", "an" and "the".
- Do not use more than three nouns together.
- Use the same word for the same thing every time. Do not use synonyms for
  variety.
- Keep paragraphs short. Use a list when you give more than two items.

**What this applies to and what it does not.** It applies to what you write to
the owner: replies, status reports, and summaries. **It does not change the
documents this project ships.** Their voice is deliberate, and a rewrite of them
is a separate decision that nobody has made.

**No em dashes and no en dashes**, anywhere this project ships: markdown, code
comments, commit messages, PR bodies, and the words on the screen. A colon, a
full stop, brackets or a spaced hyphen does every job. It is checked rather than
remembered:

```bash
python3 ../vadgr-docs/scripts/check_style.py [path ...]
```

**No AI attribution, anywhere.** No `Co-Authored-By`, no "generated with", no
model names - in commits, PR bodies, or generated files.

**PR bodies carry code, tests, user-visible changes and caveats, and nothing
else.** No methodology narration, no design-doc citations. A reviewer must
understand the PR from the PR alone.

**How a minor ends**: `CHANGELOG.md` written in the PR and re-read against the
final diff, the version bumped with it, **`README.md` updated if the minor
changed what it says**, the tag `vX.Y.Z` with notes matching the changelog,
branches deleted local and remote, every repo back on its default branch, then
`PROGRESS.md` updated and the next item named - read from `PLANS.md`'s
iteration table, not decided.

**Paths in this document are relative to this repo's parent directory**, with
the docs repo cloned beside it. If you cloned it under a different name, use
that name. Nothing here assumes a particular machine, user or absolute path.

## How a change is proven here

- **Every fix gets a test that fails without it.** Stash it, watch it go red,
  restore.
- **Browser-tier work is proven against real Chrome**, not a mock DOM.
- **Never report a result from a command whose exit code you did not read** -
  `cmd | head` reports `head`'s status.
- After any mutating browser operation, confirm with a **structured read-back**,
  never a screenshot: web state changes faster than a screenshot can witness it.

## Conventions

- Comments explain **why**, not what.
- Branch, then PR. Never commit to `master`.
- `CHANGELOG.md` is updated **in the PR**; CD publishes the extension keylessly
  on tag.
- **`README.md` is updated in the same PR when the minor changed what it says**,
  and it is the file most people read. A deleted surface, a renamed command, a
  moved directory, a changed install path, a changed dependency floor, or a
  change in what the product **is** all change it. Read the release's own diff
  against it and either edit it or **say nothing in it changed** - the silence is
  the defect. A claim can also rot with no diff touching it, and the one-line
  description is the usual casualty. This repo's described the daemon as a
  "workflow engine" long after Workflows were deferred out of the product
  whole.
- A patch that ships gets a row in `vadgr-docs/general/PATCHES.md` naming the
  runbook that caught it.
