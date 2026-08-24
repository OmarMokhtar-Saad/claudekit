# Implementation Plan: task 008 batch 3, cluster 6 — `model-router` → coordinator + `/model-route`

**Status:** EXECUTED 2026-08-24. 5 ops configs. 23 → 22 agents.

## The merge had to translate, not transplant

`model-router.md` named **Haiku / Sonnet / Opus** throughout — its capability table, its
decision table, its task mappings, its overrides. CLAUDE.md's own Token & Model Policy
says the opposite:

> policy names **capability tiers** (`most-capable`/`balanced`/`fast`), never vendor model
> names. `.claude/model-policy.json` is the one table.

So folding it into `coordinator.md` verbatim would have imported exactly what that policy
exists to prevent — into the agent every pipeline reads. The rubric is carried in full and
**restated in tiers**.

One judgement call is recorded rather than made silently: the old decision table had an
8–10 band labelled "Sonnet (heavy)", naming the same model as the 4–7 row above it. That
is a distinction the tier vocabulary cannot express and the vendor vocabulary only
*appeared* to. The two bands collapse into `balanced`, and the reason sits next to it.

## `/model-route` was carrying a duplicate of the same table

In vendor names: both the duplication task 008 exists to remove and the forbidden
vocabulary, in one file. It now applies the coordinator's rubric and reports a **tier**.
62 → 52 lines, so the command diet advanced as a side effect of doing the merge properly.

| # | Config | Effect |
| --- | --- | --- |
| 01 | `inline` | rubric into `coordinator.md` § Model economy, translated; plus the Model Select routing row and the handoff-table row, both of which named the removed agent |
| 02 | `command` | `/model-route` thin and tier-only; `gan-harness`, `QUICK_START`, `model-policy.json`, `tests/test_model_policy.py` |
| 03 | `delete` | `.claude/agents/model-router.md` |
| 04 | `alias` | `model-router` → `coordinator`, `kind: agent` |
| 05 | `tests` | `tests/test_008_b3c6_model_router_fold.py` |

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | The rubric survived | All four dimensions, all three bands, all three tier names asserted present in the coordinator. |
| 2 | Every override survived | Overrides **beat the score**, so losing one silently changes routing for exactly the cases that matter most. All three asserted. |
| 3 | The vocabulary really is tiers | A regex gate over both files: only a `model:` frontmatter line may name a vendor model. Two seam lines that *explain* the translation are the only exemptions, named individually. |
| 4 | The table is not duplicated | `/model-route` asserted to say "not repeated here" and to contain no dimension table. |
| 5 | The collapsed band is disclosed | Asserted present, so a future reader sees a decision rather than an omission. |

## The risk this plan does NOT retire

**Routing is not demonstrated unchanged.** No cassettes. And beyond the usual gap: task
scores now map to three tiers where they previously mapped to four labels, so a task that
would have been called "Sonnet (heavy)" now reads `balanced` with no gradation. That is
intended, but it is a behaviour change, not a rename.
