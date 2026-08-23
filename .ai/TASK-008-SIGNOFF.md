# Task 008 — consolidation sign-off sheet

Measured 2026-08-23 on `main`. Every row is evidence, not estimate. Owner marks
APPROVE / HOLD per batch. Nothing is deleted until a batch is approved.

**Current corpus: 31 agents · 76 skills · 42 commands.** The 008 spec was written
against 30 / 73 / 42 — the corpus has *grown* since, so no consolidation has occurred.

Registry referential integrity is now **clean**: every `agentMapping` key is a real
agent, every mapped skill exists. The spec's ghost-reference findings are already fixed.

---

## Batch 1 — `templates/` duplicate tree (P1, highest risk, smallest judgement)

`install.sh` copies both trees to the same destination, so **which version wins depends
on copy order**. 11 of 14 are byte-identical; three are not.

| Skill | State | Action |
| --- | --- | --- |
| `incident-response` | **DIVERGED** 350 vs 440 lines | three-way merge; keep union of operative rules |
| `token-optimization` | **DIVERGED** 147 vs 219 lines | three-way merge |
| `spec-driven-development` | **DIVERGED** same length, different content | three-way merge |
| `i18n-workflow` | **only in `templates/`** | decide: promote to `.claude/skills/` or drop |
| 10 others | byte-identical | delete the `templates/` copy, no review needed |

Then delete `templates/skills|commands|hooks|modes` (14/13/4/7 entries) and update
`install.sh` + the manifest.

**Risk:** low for the 10 identical; the 3 diverged need real content review.
**Sign-off:** APPROVED 2026-08-23 · **DONE 2026-08-23** (21 ops configs, 79 operations).

> **This section was wrong in two places, and the corrections are the lesson.**
> `templates/commands|hooks|modes` are described above as part of a duplicate tree.
> They were **24 unique components** with zero name overlap in `.claude/` — deleting
> them as written would have destroyed content, not de-duplicated it. They were
> promoted instead. And the three skills marked DIVERGED, slated for a three-way
> merge, differed by exactly **one line** each: the `description:` frontmatter, with
> `.claude/` already holding a strict superset of the body.
>
> Both errors were found by measuring the tree, not by reading this sheet. It was
> written in good faith with a table of measurements in it, and was still wrong.

## Batch 2 — near-duplicate skills (P1, active mis-routing hazard)

All still present, all measured today.

| Cluster | Survivor (recommended) | Merge away |
| --- | --- | --- |
| loop pair | `autonomous-loop` | `autonomous-loops` |
| verification pair | `verification-before-completion` | `verification-loop` |
| token/context quintet | `context-budget` + `token-optimization` | `token-budget-advisor`, `context-keeper`, `context-priming` |
| onboarding pair | `codebase-onboarding` | `codebase-mapping` |
| dependency pair | `supply-chain-audit` | `dependency-audit` |

76 → ~69 skills. Deleted names go into a registry `renamed` alias map for one release.

**Risk:** medium — merges can lose nuance. Diff both, keep the union.
**Sign-off:** APPROVED 2026-08-23

## Batch 3 — agent merges (P2)

All 10 still present.

| From | Into |
| --- | --- |
| `python-reviewer`, `typescript-reviewer` | per-language checklist **skills**, loaded by `code-reviewer` on matching extensions |
| `silent-failure-hunter` | a `code-reviewer` dimension |
| `documenter` + `doc-updater` | one `docs` agent with `mode: create\|update` |
| `code-simplifier` | `refactor-cleaner` |
| `tdd-guide` | the existing `test-driven-development` skill |
| `model-router` | inline table in `coordinator.md` + thin `/model-route` |
| `harness-optimizer` | `context-budget` skill/command |

31 → ~22 agents.

**Risk:** medium-high — this is the batch that changes routing behaviour.
**Blocker:** should run behind the eval suite (task 010), which needs cassettes —
currently blocked on API quota. **Recommend HOLD until cassettes exist.**
**Sign-off:** APPROVED 2026-08-23

## Batch 4 — command diet + lint rules (P2)

42 commands to frontmatter + arg parsing + invocation + artifact contract (≤40 lines);
one reviewer decision taxonomy in `HANDOFF_PROTOCOL.md`; unify the two coordinator
routing tables; add lint rules (command line budget, `allowed-tools: Agent` in a skill,
duplicate trigger phrases).

**Risk:** low. Mechanical, and `ck lint` can enforce it afterwards.
**Sign-off:** APPROVED 2026-08-23

---

## Recommendation (superseded by the decision below)

Approve **1, 2, 4**. **Hold 3** until the eval cassettes exist — batch 3 is the only
one that changes routing behaviour, and the spec's own rollback plan names the eval
suite as the gate. Without it there is no way to prove routing did not degrade.

## OWNER DECISION 2026-08-23 — all four batches APPROVED

Batches 1, 2 and 4: approved as recommended.

Batch 3: **approved over the recommendation to hold.** The eval-suite gate named in
the spec's rollback plan is unavailable (cassettes blocked on API quota), so the risk
that a routing regression ships undetected is **accepted, knowingly**. Compensating
controls required in its place, since the designed gate is absent:
- batch 3 lands **after** 1, 2 and 4, never alongside them;
- one merge cluster per plan, one plan per PR — never a bulk agent sweep;
- the registry `renamed` alias map must serve every removed agent name for one
  release, so consumers see a rename and not a deletion;
- each merge keeps the **union** of operative rules from both sources, proven by
  diffing both before deleting either;
- if routing behaviour cannot be demonstrated unchanged by other means, record that
  plainly in the PR rather than implying the eval suite covered it.

## Carried debt (already an owner decision, 2026-08-22)

Fleet-sync marker co-ownership: `ck adapt` owns the `CLAUDEKIT:` region in
`.claude/local/CLAUDE.project.md`; fleet-sync keeps the root `CLAUDE.md` region.
Two writers, two files. **Decision: carry it.** Not an oversight.

## Consumer impact

16 downstream repos. The registry alias map means consumers see a rename, not a
deletion, for one release. Every batch is one PR and one `git revert` away.
