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
**Sign-off:** ______

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
**Sign-off:** ______

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
**Sign-off:** ______

## Batch 4 — command diet + lint rules (P2)

42 commands to frontmatter + arg parsing + invocation + artifact contract (≤40 lines);
one reviewer decision taxonomy in `HANDOFF_PROTOCOL.md`; unify the two coordinator
routing tables; add lint rules (command line budget, `allowed-tools: Agent` in a skill,
duplicate trigger phrases).

**Risk:** low. Mechanical, and `ck lint` can enforce it afterwards.
**Sign-off:** ______

---

## Recommendation

Approve **1, 2, 4**. **Hold 3** until the eval cassettes exist — batch 3 is the only
one that changes routing behaviour, and the spec's own rollback plan names the eval
suite as the gate. Without it there is no way to prove routing did not degrade.

## Carried debt (already an owner decision, 2026-08-22)

Fleet-sync marker co-ownership: `ck adapt` owns the `CLAUDEKIT:` region in
`.claude/local/CLAUDE.project.md`; fleet-sync keeps the root `CLAUDE.md` region.
Two writers, two files. **Decision: carry it.** Not an oversight.

## Consumer impact

16 downstream repos. The registry alias map means consumers see a rename, not a
deletion, for one release. Every batch is one PR and one `git revert` away.
