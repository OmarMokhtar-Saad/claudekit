# Implementation Plan: task 008 batch 3, cluster 2 — `silent-failure-hunter` → `code-reviewer`

**Status:** EXECUTED 2026-08-24. 5 ops configs. 28 → 27 agents.

## Scope

`silent-failure-hunter` becomes **Dimension 6 (Silent Failures, P1)** of `code-reviewer`,
alongside its existing five. Its five hunt categories, investigation workflow, severity
classification and reporting format are grafted in full: 304 → 580 lines.

| # | Config | Effect |
| --- | --- | --- |
| 01 | `union` | Dimension 6 inserted into the numbered list; detail section appended |
| 02 | `consumers` | `/audit` (4 sites), `INVOCATION.md` (2 tool-grant tables + 1 sentence), `QUICK_START`, `commands/coordinator.md` parallel-group roster, `model-policy.json`, 2 test files |
| 03 | `delete` | `.claude/agents/silent-failure-hunter.md` |
| 04 | `alias` | `renamedAgents`: `silent-failure-hunter` → `code-reviewer`, `kind: agent` |
| 05 | `tests` | `tests/test_008_b3c2_silent_failure_merge.py` |

## This cluster changes routing, and that is the accepted risk

**Routing is not demonstrated unchanged.**

`/audit` spawned `silent-failure-hunter` as one of **three parallel agents**. It now
spawns `code-reviewer` for Dimension 6. **The eval cassettes that were batch 3's designed
gate do not exist, so nothing proves the fan-out behaves equivalently.** What is proven is
narrower and stated as such: the content survived, the name resolves, and the fan-out
**width** is unchanged at three. The uncovered gap is written into
`code-reviewer.md` itself — not only into this plan, which a consumer never reads — and
`tests/…::test_the_uncovered_risk_is_stated_in_the_agent_itself` asserts it stays there.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost | Token diff: 38 derived fragments + 13 headings. One justified absence — the merged-away agent's display name. |
| 2 | Its core argument survived verbatim | `**A failure that is silent is worse than a failure that is loud.**` asserted as an exact bold span. |
| 3 | It became a DIMENSION, not an appendix | `### 6. Silent Failures (P1)` present **and positioned before `## Workflow`** — otherwise Phase 3 never applies it. Mutation-proven: retitling it "Appendix" reddens two tests. |
| 4 | No live consumer dangles | Walk the live roots. **This caught four sites config 02's first draft missed**: the hyphenated id was clean everywhere, but the display name "Silent Failure Hunter" survived in `/audit`'s `--errors` route, its agent roster and its coverage template. Grep for the id would have passed. |
| 5 | The scan does not pass on itself | The test file names the removed agent throughout by design and excludes itself — the same self-reference trap batch 2 hit. |
| 6 | Counts are generator-derived | 27 agents, 27 model-policy roles. |

## Rollback

`git revert` of one commit. The alias serves the removed name for one release.
