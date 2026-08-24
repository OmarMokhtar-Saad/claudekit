# Implementation Plan: task 008 batch 3, cluster 5 — `tdd-guide` → `test-driven-development`

**Status:** EXECUTED 2026-08-24. 5 ops configs. 24 → 23 agents.

## Scope

The `tdd-guide` agent folds into the **existing** `test-driven-development` skill:
181 → 395 lines. Cross-namespace alias, `kind: skill`.

The premise: **`tester` already loaded that skill as role-core** (`tester.md:20`). So the
agent was a second context holding rules the test-writer already had, plus a spawn to get
them there.

| # | Config | Effect |
| --- | --- | --- |
| 01 | `union` | the whole agent grafted into the skill |
| 02 | `routing` | TDD routes to `tester`; `QUICK_START`, `model-policy.json`, `tests/test_model_policy.py` |
| 03 | `delete` | `.claude/agents/tdd-guide.md` |
| 04 | `alias` | `tdd-guide` → `test-driven-development`, `kind: skill` |
| 05 | `tests` | `tests/test_008_b3c5_tdd_fold.py` |

## The ordering rule moves rather than dies

`coordinator.md:281` said **"TDD Guide MUST produce tests before Implementer writes
code"** — an ordering constraint attached to an agent that no longer exists. Deleting the
agent without relocating it would have quietly dropped the one rule that makes TDD TDD.

It now exists in two places, deliberately: rewritten in the coordinator to name the
surviving agents (`tester` MUST produce failing tests before `implementer` writes code),
and stated inside the skill itself, where the test-writer will actually read it. The
reason is recorded with it — **the RED step cannot be recovered afterwards; a test written
after the code passes for the wrong reason.**

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost | Token diff: 22 derived fragments + 8 headings, zero missing. One justified absence — the agent's display name. |
| 2 | The ordering rule survived both moves | Asserted in the skill *and* in the coordinator, by content not heading. |
| 3 | **`tester` really loads the skill** | The load-bearing one. If it did not, this fold would have deleted the discipline rather than relocating it — the entire premise of routing TDD to `tester`. |
| 4 | The route no longer names a dead agent | `TDD Guide` absent from the coordinator. |
| 5 | Counts are generator-derived | 23 agents, 23 model-policy roles. |

## The risk this plan does NOT retire

**Routing is not demonstrated unchanged.** No cassettes. A TDD request now reaches
`tester`, whose accountability is "test writing" rather than "test-first ordering", and
the ordering now depends on it loading and honouring the skill.
