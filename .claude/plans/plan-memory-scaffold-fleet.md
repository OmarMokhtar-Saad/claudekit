# Implementation Plan: Per-project agent memory actually accumulates

Tier 3 (a distilled `MEMORY.md` is auto-injected into an agent's system prompt, so the
write path is a supply-chain surface). Branch: `feat/memory-scaffold-fleet`.
Ops configs, split along the phase boundary rather than one monolith:

- `.claude/plans/plan-memory-scaffold-fleet.ops.json` — Phases 1+2 (installer scaffold,
  doctor check). 2 ops. Validator: APPROVED. Both anchors verified unique and the
  post-apply Python compiles.
- `.claude/plans/plan-memory-scaffold-distill.ops.json` — Phase 3 (the `distill`
  subcommand) and its tests. Generated after Phases 1+2 land.

Split on purpose: Phases 1+2 touch existing, well-anchored code and are additive.
Phase 3 adds a new write path aimed at an auto-injected file and carries all of this
plan's security weight. Landing them together would put both under one verdict and let
the low-risk half carry the high-risk half through the gate.

## Overview

Seven agents ship `memory: project` in their frontmatter. Across the 15 kitted projects
in `~/IdeaProjects`, the total number of `MEMORY.md` files is **3**. The feature is
declared everywhere and functioning nowhere.

This is one product defect with three parts, all in claudekit. The fix ships from here
and then syncs to the fleet. No project's *lessons* travel — only the machinery.

### Measured baseline (2026-09-13)

```
project                 agents_declaring  memdirs  MEMORY.md
ai-agent-system                 7            1          0
ApiForge                        7            1          0
AppiumLens                      7            5          1
AutomationApp                   7            1          0
claudekit                       7            4          0
Eatizaz                         7            1          0
Lean                            7            1          0
LeanApis                        7            1          0
MobileUIAutomator               7            1          0
qa-agents                       7            3          2
qaforge-ai                      7            1          0
rest-framework                  7            1          0
SehhatyApp                      7            1          0
shsmartassistant-agent          7            1          0
shsmartassistant-qa             7            1          0
```

`memdirs=1` is the README alone — no agent directories at all.

## Revision 1 (reviewer round 1: 82 REVISE — 1 CRITICAL, 2 MAJOR, 2 MINOR)

- **CRITICAL, no Rollback section.** Added below.
- **MAJOR, sanitization declared but untested.** Phase 3 now names the exact existing
  helpers it reuses and Phase 4 tests them. Correction to the reviewer's suggestion: the
  right fix is NOT a new detection rule. `.claude/hooks/reflection.py` already ships
  `_ABSOLUTE_PATH` (:112), `_SECRET` (:116), `looks_like_credential()` (:165),
  `_VENDOR_SECRET` (:601) and `redact_secrets()` (:615). A second set of regexes would
  drift from those the moment either changed. `distill` imports and reuses them.
- **MAJOR, grouping undefined.** Pinned to exact match, v1. See Phase 3.
- **MINOR, path-escape threat model.** Stated as defense-in-depth, with the one
  genuinely untrusted component named.
- **MINOR, wrong symbol.** Confirmed: `knowledge-ledger.py:73` defines `project_root()`;
  `_project_root(start=None)` is a different function in `review-record.py:286`. Phase 3
  is implemented in knowledge-ledger.py, so it uses `project_root()`.

## Phase 0: Design precheck

**The three defects.**

1. **`install.sh` never ships `agent-memory/`.** It creates `knowledge/issues/` and
   copies that README (install.sh:272-277) but has no equivalent block for agent
   memory. Every install therefore points 7 agents at directories that do not exist.
   Claude Code reads `.claude/agent-memory/<agent>/MEMORY.md`; a missing file is not an
   error, it is silence. This is the root cause of the 13 empty projects.

2. **`ck doctor` has no memory check.** `grep -rn "agent-memory\|MEMORY.md"
   src/claudekit/cli/*.py` returns nothing. There is no check that an agent declaring
   `memory: project` has a readable, non-truncated memory file. This is why defect 1
   survived across 15 repos without anyone noticing.

3. **No distillation path.** `knowledge-ledger.py` has `open`, `close`, `record`,
   `propose`, `search`, `list`, `prune` — nothing that turns accumulated receipts into
   a memory entry. AppiumLens has 14 open receipts, every one with an empty `fix:`
   field, 12 of which are three lessons re-learned. Capture works; learning was never
   built.

**Isolation constraint (owner directive, 2026-09-13).** Memory is dedicated per project.
Nothing is written to `~/.claude/agent-memory/` (which does not currently exist on this
machine — keep it that way). Every path this plan writes is inside the target repo's own
`.claude/`. Duplication of a similar lesson across two projects is the accepted cost.

**What does NOT travel.** AppiumLens's 14 receipts are facts about AppiumLens (zsh
command-guard refusals, trailing spaces in its Java sources, its emulator binary). They
are distilled into AppiumLens only. Propagating them would be a correctness bug, not a
feature.

**Explicitly out of scope.** Two AppiumLens clusters look like genuine ClaudeKit product
bugs rather than project quirks: ops-anchor literalism, and the implementer stamping an
ops baseline after a verdict is recorded (hash deadlock). Both are real; both get their
own diff. Bundling them here would put three unrelated risk surfaces in one review.

## Phase 1: `install.sh` ships the scaffold

Add a block beside the issue-ledger one. For each agent whose frontmatter declares
`memory: project`, create `$DEST/agent-memory/<agent>/` and, if absent, write a
header-only `MEMORY.md` stub. Copy `agent-memory/README.md`.

- **Derive the agent list from the installed agent files**, never from a hardcoded array
  — a hardcoded list is exactly how the hook allowlist went stale (install.sh:283-287).
  Parse `^memory: project` out of `$DEST/agents/*.md` after agents are installed, so
  ordering matters: this block runs after the agent install step.
- **Idempotent.** An existing `MEMORY.md` is never overwritten, never truncated,
  never reordered. Re-running the installer over AppiumLens must leave its one real
  memory file byte-identical.
- bash 3.2 / macOS safe: no associative arrays, no `mapfile`, no `readarray`.

The stub is header-only (a title line and the one-line-per-entry index format from
`agent-memory/README.md`). A fresh install is *unpopulated*, not *broken*.

### Revision 5 (DATA LOSS, found by the Phase 4 tests)

Phase 1 as shipped **destroyed accumulated memory on every reinstall.** Measured, not
theorised: a project with a real `MEMORY.md` reinstalled, and the file came back as the
empty stub.

**Mechanism.** `install.sh` backs up and replaces `.claude/` wholesale, then
`preserve_assets.py` carries back any backup file the new tree **lacks**. The scaffold
block ran *before* preservation and wrote a stub at exactly that path, so preservation
saw the path occupied and skipped the real file. Before this plan, no file existed there
and preservation worked. My change created the hole.

**Why the idempotence proof missed it.** My manual probe re-ran `install.sh` without
`--yes`; the second run exited non-zero and never installed, so the file survived for a
reason that had nothing to do with the code. A green check measuring nothing. The Phase 4
test caught it only because it passed `--yes` and actually reinstalled.

**The fix.** Move the scaffold block to run *after* `preserve_assets.py`. Preservation
restores the real file first; the stub block then finds it present and leaves it alone.
Fresh installs are unaffected — nothing to preserve, so the stub is written as before.

Measured after the fix: reinstall leaves the real file byte-identical (sha256 unchanged),
and a fresh install still creates all 7 directories with stubs.

**This blocked the fleet rollout.** Phase 5 run against the 15 projects before this fix
would have destroyed AppiumLens's one real memory file and qa-agents' two — the only
three in the fleet.

### Revision 6 (reviewer REJECTED revision 5 at 65/100 — the reorder was not enough)

**The finding.** Moving the block after preservation only protects a fixed→fixed
reinstall. `preserve_assets.py` decides kit-vs-project ownership from the OLD manifest,
and the buggy build wrote its stub *before* manifest generation — so that manifest lists
`agent-memory/<agent>/MEMORY.md` as kit-owned. On the next reinstall preservation then
declines to restore the real file, and the relocated stub block fills the gap. Same loss,
one phase removed.

**Correction to the review, with evidence.** It named AppiumLens and qa-agents as the
exposed projects. They are not: both manifests carry 240 keys and **zero** `agent-memory`
entries, because they were installed with the original installer, which had no scaffold
at all. The exposed population is any project installed with the Phase 1 build — measured
at **8** agent-memory keys in its manifest. The mechanism was real; the named victims
were not.

**The fix, and the controls that prove it.** `preserve_assets.py` now treats
`agent-memory/<agent>/MEMORY.md` as **always custom**, keyed on the path rather than on
any manifest, so no manifest state can mark a project's memory as kit-owned:

| Configuration | Stale manifest (8 keys) | Result |
|---|---|---|
| Reorder alone | present | **LOST** — stub overwrote the real file |
| Reorder + always-custom | present | **PRESERVED**, byte-identical |

The negative control isolates the always-custom rule as the thing that saves the file —
the reorder alone demonstrably does not.

**Manifest ownership, now deliberate rather than accidental** (the review's MAJOR):

- `agent-memory/README.md` is copied in the asset phase and **stays manifest-managed**.
  It is the shipped entry-format contract: kit-owned, and it should track `ck update`
  and `ck uninstall` like any other kit asset.
- Per-agent directories and `MEMORY.md` stubs are created after preservation and are
  **deliberately absent from the manifest**. Accumulated memory is project data:
  `ck uninstall` must not delete it and `ck diff` must not report it as drift.

## Phase 2: `ck doctor` check

One new check in `cmd_doctor` (src/claudekit/cli/main.py:364), using the existing
`check(name, condition, fix_hint)` contract:

| State | Result | Rationale |
|---|---|---|
| No agents declare `memory: project` | `"skip"` | Minimal install; must not redden `--strict` |
| Directory + `MEMORY.md` exist, header-only | `True` | Fresh install is healthy |
| Directory + `MEMORY.md` exist, populated | `True` | Working as intended |
| **Zero** declaring agents have a `MEMORY.md` | `"skip"` | **Revision 3.** Not adopted. Covers all four shapes — directory absent, empty, README-only, or holding empty agent dirs — which are functionally identical: no agent is served by any of them. Reported exactly as a missing `.claude/profiles/` is (main.py:690) |
| Some but not all have one | `"warn"` | Defect 1's true signature: adopted, then drifted |
| `MEMORY.md` over 200 lines | `"warn"` | Claude Code silently truncates past 200 lines / 25 KB; the agent then reads half a memory it believes is whole (agent-memory/README.md) |

A header-only stub must pass, not warn. Otherwise every fresh install reddens
`--strict` until someone records a lesson, and the gate gets ignored — the failure mode
`_readiness_score`'s comment already warns about.

### Revision 2 (regression found by the suite, not by review)

v1 warned whenever a declaring agent lacked a `MEMORY.md`. That reddened `--strict` for
every install made before this feature existed — 5 tests failed
(`test_doctor_gate.py` ×4, `test_eject.py` ×1), including
`test_doctor_strict_exits_zero_on_this_repo`.

The plan's own Phase 2 rationale predicted this ("otherwise every fresh install reddens
`--strict` ... and the gate gets ignored") but the table only covered *fresh installs
carrying stubs*, never *old installs carrying none*. Absence of adoption is not a defect;
partial adoption is. Both reviewers missed it too — it took executing the code.

### Revision 3 (reviewer REJECTED revision 2 at 66/100)

Revision 2 keyed the skip on whether `.claude/agent-memory/` **exists**. That was wrong,
and the reviewer proved it against the filesystem: **this repo's own** `agent-memory/`
exists, holding `README.md` and three empty agent directories, with **zero** `MEMORY.md`
files. So `_mem_root.is_dir()` was True, the skip never fired, and
`test_doctor_strict_exits_zero_on_this_repo` — the very test the revision claimed to fix
— still failed. Verified by running it: still red.

The real predicate is **how many agents are served**, not whether a directory exists:

- 0 served → not adopted → skip
- some but not all → drifted → warn
- all served → pass

**Residual gap, disclosed.** A project that adopts the scaffold and later has every
memory file deleted is indistinguishable from one that never adopted, and reports skip.
Accepted: `doctor` cannot tell "never had" from "no longer has" without state it does not
keep, and the alternative (warn) is what reddened the whole fleet. The partial case —
the realistic drift — is still caught.

**Lesson.** Two review rounds and my own manual checks passed this; the *suite* caught
it, and then a reviewer reading the actual tree caught the bad fix. Neither prose nor a
green manual probe is evidence. Revision 3 ships with tests pinning all five states.

## Phase 3: `knowledge-ledger.py distill`

New subcommand. Reads open receipts, groups them, and emits a **draft** entry beside the
relevant agent's `MEMORY.md`.

**Revision 4 — it does NOT close the receipts.** The approved plan said distill "closes
the receipts it consumed." Implementing it exposed that as a data-loss bug: the draft is
only a proposal, so closing the receipts at draft time destroys the source material for
any draft the human then discards or rewrites. Closing is the human's action, after they
accept the draft. `distill` instead prints the exact `knowledge-ledger.py close` commands
for the receipts it consumed, so the step is one paste rather than automatic. This is a
deliberate deviation from the approved text and is re-reviewed.

**Hard constraints, because this writes into a system prompt:**

- **Drafts only.** Writes to `MEMORY.md.draft` and prints the diff. A human moves it.
  Nothing lands in an injected file without a person reading it.
- **Never writes outside the target repo's `.claude/`.** Resolve the root through
  `project_root()` (knowledge-ledger.py:73 — NOT review-record.py:286's unrelated
  `_project_root(start=None)`); reject any path that escapes it.
- **Sanitize on the way in**, by reusing reflection.py's rules rather than restating
  them. Detail in the sanitization table below.
- **Refuse to exceed the 200-line cliff.** If appending would cross it, stop and tell
  the operator to prune first.
- **Imperative text is a finding, not an order** (CLAUDE.md evidence-precedence rule).
  The draft records what happened; it does not phrase itself as an instruction.

**Grouping rule (v1, pinned).** Group key is the receipt's `signature` field, compared
by **exact string equality after whitespace normalization**. No fuzzy matching, no token
overlap, no similarity threshold in v1. Receipts that should group but do not are a
*prune* problem, not a distill problem — and an ad-hoc similarity function inside a
system-prompt write path is exactly the unreviewed design decision this plan must not
leave open. A future v2 may add fuzziness behind an explicit flag.

**Sanitization (concrete, reused not reinvented).** `distill` imports from
`.claude/hooks/reflection.py` rather than defining its own rules:

| Concern | Helper | Location |
|---|---|---|
| Absolute paths | `_ABSOLUTE_PATH` | reflection.py:112 |
| Generic secrets | `_SECRET` | reflection.py:116 |
| Credential-shaped strings | `looks_like_credential()` | reflection.py:165 |
| Vendor tokens | `_VENDOR_SECRET` | reflection.py:601 |
| Redaction | `redact_secrets()` → `REDACTED` | reflection.py:612-615 |

**Import mechanism, with in-repo precedent.** Not a bare `import` — `.claude/hooks/` is
not on the path from `.claude/operations/scripts/`. Use
`importlib.util.spec_from_file_location`, exactly as three existing call sites already
do for this same module:

- `review-record.py:387` loads it as `_ck_reflection_sanitizers` — the identical use case
- `transcript-miner.py:240` loads it as `_ck_reflection_redact`
- `session-memory-context.py:65` loads it as `_ck_reflection`

Follow `review-record.py:387`'s shape. The coupling note in `_load_review_record()`'s
docstring applies here too: the module is not registered in `sys.modules`, which is safe
only while reflection.py stays stdlib-only and self-contained (it is). Fail CLOSED — an
unloadable sanitizer module refuses the distill, never waves it through.

A receipt whose text still matches any of these after `redact_secrets()` is **refused**,
not redacted-and-shipped — a draft that quietly swallowed a secret is worse than a draft
that refused, because the human reviewing it cannot see what was removed. Importing is
what makes this testable: if reflection.py's rules tighten, distill tightens with them,
and the test below proves the import is live rather than a copy.

**Agent routing** is declared, not guessed: a receipt's `origin` maps to an agent via a
small explicit table, and an unmapped origin goes to a default with a warning.

**Path-escape check: defense-in-depth, stated honestly.** The reviewer is right that the
origin→agent table is closed, so the *directory* component is not attacker-influenced.
The genuinely untrusted component is the receipt content itself, which reaches a
**filename** (`MEMORY.md.draft` is fixed, but a per-receipt draft name derived from a
signature or slug would not be). v1 therefore uses a fixed draft filename and derives no
path component from receipt data at all. The `project_root()` containment check stays as
pure defense-in-depth against a future change reintroducing derived names — it is not
guarding a live hole today, and the plan does not claim it is.

## Phase 4: Tests

Artifact: `tests/test_agent_memory_scaffold.py` (new file — the installer, reinstall
data-loss and distill-refusal coverage below all live here).
Also written by this plan: `CHANGELOG.md` (`[Unreleased]` entry).


Behavioral, per CLAUDE.md — run the installer and the CLI, assert outcomes.

- Installer over an empty tree creates 7 directories and 7 stubs.
- Installer over a tree with a populated `MEMORY.md` leaves it byte-identical
  (hash before/after). This is the regression test for the idempotence requirement.
- Installer with a hand-edited agent list picks up a newly-declaring agent (proves the
  list is derived, not hardcoded).
- `doctor` returns skip / pass / warn for each row of the Phase 2 table.
- `doctor --strict` on a fresh install exits 0.
- `distill` writes a draft and does not modify `MEMORY.md`.
- `distill` refuses a path escaping the project root (defense-in-depth regression).
- `distill` refuses to cross 200 lines.
- `distill` refuses a receipt containing an absolute path (`/Users/...`).
- `distill` refuses a receipt containing a credential-shaped string.
- `distill` refuses a receipt containing a vendor token pattern. (Round 2 noted this
  overlaps the monkeypatch test below, which is strictly stronger. Kept deliberately:
  the monkeypatch proves the wiring is live, this one proves the *real* shipped pattern
  matches real vendor tokens. A live import of a rule that does not fire is still a hole.
  If Phase 4 runs long, this is the one to cut.)
- `distill` fails closed when the sanitizer module cannot be loaded.
- **The sanitizer import is live, not copied:** monkeypatch `reflection._SECRET` to match
  a benign sentinel, and assert `distill` then refuses a receipt containing it. This is
  the mutation proof that distill reuses reflection.py's rules rather than duplicating
  them — a copied regex passes every other test on this list.
- `distill` groups two receipts with identical signatures into one entry, and does NOT
  group two receipts whose signatures differ by one word (pins the v1 exact-match rule).
- `ECC_HOOK_PROFILE` forced explicitly in every test.

Generator gates: `gen-docs.py --check` (component counts are generator-owned),
`gen-registry.py --check`.

## Phase 5: Fleet rollout (separate, owner-gated)

Not part of this branch's merge. After claudekit ships:

- Run the updated installer against each of the 15 projects.
- Surgical: create missing directories and stubs only. The 3 existing `MEMORY.md`
  files (AppiumLens ×1, qa-agents ×2) are never touched — verified by hash.
- Downstream changes are left **uncommitted** for owner review (standing rule).
- Worktrees note: `~/.claude/projects/<path>/memory/` is keyed by path, so a worktree
  gets a separate store. The in-repo `.claude/agent-memory/` does not have this
  problem — it follows the checkout. Rollout targets the in-repo store.

## Rollback

Every phase is additive and idempotent, which is what makes the undo cheap. Stated
explicitly rather than left implied:

| Phase | Undo | Residue after undo |
|---|---|---|
| 1 — installer | Single `git revert` of the commit. Future installs stop creating the scaffold. | Directories and stubs already created in installed projects remain. They are inert: an empty `MEMORY.md` changes no agent behavior, and nothing reads the directory except Claude Code, which tolerates absence. Safe to leave or delete by hand. |
| 2 — doctor check | Same revert. | None. The check is read-only; it writes nothing. |
| 3 — distill | Same revert. | None in `MEMORY.md` **by construction** — distill only ever writes `MEMORY.md.draft`, so no revert is needed for the injected file. Orphan `.draft` files may remain; they are not read by anything and are deleted with `rm`. |
| 5 — fleet rollout | Not merged with this branch; per-project and uncommitted, so `git checkout -- .claude/agent-memory` in that project discards it. | The 3 pre-existing `MEMORY.md` files are never written, verified by hash before and after. |

**The one-way door check:** there is none. No migration, no schema change, no deletion,
no format change to an existing file. The highest-blast-radius change is Phase 1, and it
only ever *creates* files that do not exist.

## Risks

- **Writing into an injected file.** Mitigated by draft-only (Phase 3) and by the
  200-line refusal. The review rule in `agent-memory/README.md` stands: a `MEMORY.md`
  diff is reviewed exactly like code.
- **Installer regression.** The installer currently works; adding a block that runs for
  every install is the highest-blast-radius change here. Mitigated by the
  byte-identical idempotence test.
- **`--strict` reddening the fleet.** Mitigated by the fresh-install-passes rule.

## Definition of Done

`pytest` green · `ruff` · `mypy` · `gen-docs --check` · `gen-registry --check` ·
`check-context-floor --check` · `check-plan-artifacts --check` · `shellcheck install.sh` ·
`ck doctor --strict` · CHANGELOG `[Unreleased]` · conventional commit.
