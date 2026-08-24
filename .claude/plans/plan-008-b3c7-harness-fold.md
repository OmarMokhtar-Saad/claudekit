# Implementation Plan: task 008 batch 3, cluster 7 — `harness-optimizer` → `context-budget`

**Status:** EXECUTED 2026-08-24. 5 ops configs. 22 → 21 agents. **Final cluster of batch 3.**

## Scope

`harness-optimizer` folds into the existing `context-budget` skill: 211 → 412 lines.
Cross-namespace alias, `kind: skill`.

The skill **measured** where the context budget goes. The agent **acted** on the
measurement — by reading the same files and re-deriving the same numbers. `/context-budget`
already loaded the skill, so the split bought a second spawn to compute what the invoker
had in hand.

| # | Config | Effect |
| --- | --- | --- |
| 01 | `union` | audit workflow, common optimizations and constraints grafted in |
| 02 | `consumers` | `QUICK_START`, `model-policy.json`, `tests/test_model_policy.py` |
| 03 | `delete` | `.claude/agents/harness-optimizer.md` |
| 04 | `alias` | `harness-optimizer` → `context-budget`, `kind: skill` |
| 05 | `tests` | final-cluster acceptance **plus a batch-wide close** |

## Batch 3, closed

Nine agents removed across seven clusters, **29 → 21**:

| Removed | Became | Kind |
| --- | --- | --- |
| `code-simplifier` | `refactor-cleaner` | agent |
| `silent-failure-hunter` | `code-reviewer` (Dimension 6) | agent |
| `python-reviewer` | `python-review-checklist` | skill |
| `typescript-reviewer` | `typescript-review-checklist` | skill |
| `documenter` + `doc-updater` | `docs` (`mode: create\|update`) | agent |
| `tdd-guide` | `test-driven-development` | skill |
| `model-router` | `coordinator` § Model economy | agent |
| `harness-optimizer` | `context-budget` | skill |

The final test file asserts the batch as a whole rather than only this cluster: every one
of the nine names resolves, **every alias target exists on disk** (an alias pointing at
nothing is worse than no alias — it tells a consumer the rename succeeded), both kinds are
represented, and the uncovered-routing disclosure is still present in all seven cluster
plans.

## What the sign-off required, and what actually happened

The owner approved batch 3 **over a recommendation to hold**, with compensating controls
in place of the eval-suite gate. All were met: one cluster per plan and per commit, never
a bulk sweep; each merge kept the union, proven by token diff rather than headings; every
removed name serves for one release through `renamedAgents`, which had to be built first
because the mechanism did not exist.

**The accepted risk was never retired and is stated in every plan and every commit:
routing behaviour is not demonstrated unchanged, because the eval cassettes do not exist.**
Nine agents' worth of invocation paths changed. What is proven is that content survived,
names resolve, and consumers do not dangle — not that an invoker reaching a merged
destination gets an equivalent result.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost | Token diff: 19 derived fragments + 4 headings, zero missing. |
| 2 | The workflow is still reachable | `/context-budget` loads the skill — otherwise the fold deleted the audit rather than relocating it. |
| 3 | All nine names resolve | Parametrized over the full batch-3 removal table. |
| 4 | No alias points at nothing | Each target checked on disk, in the namespace its `kind` names. |
| 5 | The disclosure survived | ≥7 cluster plans contain "not demonstrated unchanged". |
