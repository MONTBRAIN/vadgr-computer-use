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
python3 ../docs/scripts/check_iteration.py <phase> <iteration>
```

(`../docs/` on the working machine, `../vadgr-docs/` where the docs repo was
cloned under its own name.) Exit `0` or do not start.

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
