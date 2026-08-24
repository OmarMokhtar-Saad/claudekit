# Implementation Plan: task 008 batch 3, cluster 1 — `code-simplifier` → `refactor-cleaner`

**Status:** EXECUTED 2026-08-24. 6 ops configs. 29 → 28 agents.

## Why this is its own plan

The sign-off approved batch 3 **over a recommendation to hold**, because its designed
gate — the eval suite — is blocked on cassettes. The owner's compensating controls
replace that gate, and one of them is **one merge cluster per plan, one plan per PR,
never a bulk agent sweep**. This is cluster 1 of seven. Phase 0
(`plan-008-batch3-agent-merges.md`) landed the `renamedAgents` mechanism this plan is
the first consumer of.

## Scope

| # | Config | Effect |
| --- | --- | --- |
| 01 | `union` | `refactor-cleaner` absorbs the whole of `code-simplifier`; description widened |
| 02 | `consumers` | `QUICK_START.md`, `model-policy.json`, `tests/test_model_policy.py` |
| 03 | `delete` | `.claude/agents/code-simplifier.md` |
| 04 | `alias` | first `renamedAgents` entry: `code-simplifier` → `refactor-cleaner`, `kind: agent` |
| 05 | `tests` | `tests/test_008_b3c1_simplifier_merge.py` |
| 06 | `alias-test` | inverts phase 0's "the map is empty" assertion, which cluster 1 falsifies by design |

The two agents are complementary, not redundant: dead-code removal asks "does anything
reach this?", simplification asks "is this the simplest thing that still works?". A
cleanup that answers only the first leaves the mess it was called in to fix. So the
survivor **grows**, 215 → 442 lines.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost | Token diff — every backtick span, dotted identifier, bold span and ALL-CAPS imperative from the deleted file present in the survivor. **One justified absence**: `Code Simplifier`, the merged-away agent's display name, which the survivor must not advertise. |
| 2 | The core rule survived verbatim | `**Preserve all functionality.**` asserted as an exact bold span. It outranks every simplification target, and a paraphrase would have satisfied a headings check while losing the rule — the first draft did exactly that and the token diff caught it. |
| 3 | The removed name still resolves | `renamedAgents` entry asserted; `gen-registry.py --check` refuses an alias whose old name is still on disk, so config 04 must run after 03. |
| 4 | No live consumer dangles | Walk `.claude/agents|commands|skills`, `docs/`, `src/claudekit/`, `scripts/` — only the survivor's own seam may name it. |
| 5 | The gate binds | Deleting one grafted section (`### 7. Comments That Restate Code`) turns the union test red. Verified. |
| 6 | Counts are generator-derived | `gen-docs.py --check` → 28 agents; `gen-model-policy.py --check` → 28 roles. |

## The risk this plan does NOT retire

**Routing behaviour is not demonstrated unchanged.** The eval cassettes do not exist, so
nothing here proves an invoker that would have reached `code-simplifier` now reaches
`refactor-cleaner` with the same result. Cluster 1 is the lowest-risk of the seven —
neither agent is referenced by any command, and `usedBy` was empty — but the gap is
real and is stated rather than implied to be covered.

## Rollback

`git revert` of one commit, or `restore-backup.py` per shard. The alias map means a
consumer sees a rename, not a deletion, for one release.

## Definition of Done

    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/ · mypy
    python3 scripts/gen-docs.py --check · gen-registry.py --check · gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    ck lint · ck doctor --strict
