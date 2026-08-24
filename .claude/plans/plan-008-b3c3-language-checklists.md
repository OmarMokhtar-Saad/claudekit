# Implementation Plan: task 008 batch 3, cluster 3 — the per-language reviewers become skills

**Status:** EXECUTED 2026-08-24. 6 ops configs. 27 → 25 agents, 71 → 73 skills.

## Scope

`python-reviewer` and `typescript-reviewer` stop being agents and become checklists that
`code-reviewer` loads on demand when the diff contains matching extensions. Content
carried whole: 228 → `python-review-checklist` (237 lines), 210 →
`typescript-review-checklist` (219 lines).

| # | Config | Effect |
| --- | --- | --- |
| 01 | `create-skills` | both `SKILL.md` files, full checklists |
| 02 | `wire-loader` | `code-reviewer`'s **on-demand** list gains both, keyed on extension |
| 03 | `consumers` | `QUICK_START`, `project-adaptation` step 5, `model-policy.json`, `tests/test_model_policy.py` |
| 04 | `delete` | both agent files |
| 05 | `alias` + registry rows | `renamedAgents` with `kind: skill`; explicit registry rows |
| 06 | `tests` | `tests/test_008_b3c3_language_checklists.py` |

Why skills rather than agents: a separate agent meant a separate spawn, a separate
context and a separate report to reconcile, for review criteria that belong to whichever
reviewer is already reading the diff. They load **on demand**, not mandatorily —
preloading both for a diff touching neither language burns context for nothing, which is
what that section of `code-reviewer` says.

## This is the first cross-namespace alias

`renamedAgents` takes `{"to": …, "kind": …}` rather than a bare name **for this cluster**.
`kind: skill` sends `gen-registry.py` to `.claude/skills/` instead of `.claude/agents/`.
Proven load-bearing, not decorative: flipping either entry to `kind: agent` is rejected —

    ERROR: renamedAgents: 'python-reviewer' -> 'python-review-checklist' (agent), which does not exist

Clusters 1–2 only exercised `kind: agent`, so a test now asserts **both** kinds are
represented — an unused kind is an untested kind.

## Two things simulation caught that validation could not

1. **`gen-registry.py`'s rewrite aborted.** Its agentMapping consistency check runs
   *before* its auto-add of unregistered skills, so `code-reviewer` loading two skills
   with no registry rows returned 1 — and every downstream count check cascaded into
   failure. Fixed by adding the rows explicitly in config 05 rather than relying on the
   auto-add. Measured, not guessed.
2. `project-adaptation` step 5 told adapted projects to note in their `CLAUDE.md` that
   "`/code-review` may use python-reviewer / typescript-reviewer". That instruction would
   have propagated two dead agent names into every downstream repo `ck adapt` touches.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | Content carried whole | Token diff per skill: 27 and 26 derived fragments plus headings. Zero missing. |
| 2 | Something actually loads them | `code-reviewer` declares both, and each is asserted to sit **after** the "On demand" marker — not merely present. |
| 3 | Each says what loads it | A checklist nobody loads is dead prose, so the trigger is stated in the skill itself, not only in the loader. |
| 4 | The registry records the dependency | `usedBy: ["code-reviewer"]` on both rows. |
| 5 | The cross-namespace `kind` binds | Mutation: flip to `agent` → validator rejects. |
| 6 | Counts are generator-derived | 25 agents, 73 skills, 25 model-policy roles. |

## The risk this plan does NOT retire

**Routing is not demonstrated unchanged.** The eval cassettes do not exist. An invoker
that would have spawned `python-reviewer` now reaches `code-reviewer`, which must itself
decide to load the checklist. That is a behavioural change in the review path and nothing
here proves equivalence.
