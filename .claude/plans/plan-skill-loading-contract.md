# Plan: a sentence in the entrypoint is not a load

Slug: `skill-loading-contract`. Wave-2 **Phase 2.2**. Blast radius: **Tier 2** — 17 files
(15 skill frontmatters, one measurement script, one new test), no security or schema surface.

## Problem

The corpus asserts a contract it cannot execute. Measured, not estimated:

**33 of 76 skills carry `disable-model-invocation: true`**, which removes them from the Skill
tool's listing entirely. **15 of those 33 are named in an agent's "Skill Loading" section** — 8 as
mandatory, 7 as on-demand:

| Skill | Declared as | By |
|---|---|---|
| `execute-operations-config` | mandatory | implementer |
| `generate-operations-config` | mandatory | planner |
| `writing-plans` | mandatory | planner |
| `validate-operations-config` | mandatory | reviewer |
| `git-workflow` | mandatory | gitOps |
| `systematic-debugging` | mandatory | build-error-resolver, debugger |
| `test-driven-development` | **mixed** — mandatory (tester), on-demand (debugger, verifier) | |
| `verification-before-completion` | **mixed** — mandatory (implementer, tester, verifier), on-demand (coordinator) | |
| `brainstorming` | on-demand | planner |
| `context-budget` | on-demand | coordinator |
| `dispatching-parallel-agents` | on-demand | coordinator |
| `search-first` | on-demand | coordinator |
| `subagent-driven-development` | on-demand | coordinator |
| `verification-loop` | on-demand | coordinator |
| `finishing-a-development-branch` | on-demand | gitOps |

> **Correction (review round 1).** The first revision of this plan claimed all 15 were mandatory.
> That was false, and the cause is worth recording: the classifier matched `On-demand` with a
> hyphen while the corpus writes `**On demand (load when the trigger fires …):**` with a space, so
> the subsection header never matched and every skill fell into the mandatory bucket. A parser that
> cannot fail loudly produces a confident wrong answer, and it went into a plan as fact. The gate
> shipped here now asserts that both classes are present, so the same silent-miss cannot recur.

The pipeline's entire mandatory-load contract is dead prose. The implementer is told to load
`execute-operations-config` — the Iron Law mechanism. The reviewer, `validate-operations-config`.
The planner, `writing-plans` and `generate-operations-config`. None can.

**The semantics are confirmed empirically, with a positive control.** In a live session's
available-skills listing, exactly the 43 unflagged skills appear and all 33 flagged ones are
absent (76 − 33 = 43, matching exactly). The control: `using-git-worktrees`, which
`.ai/BACKLOG.md` records as un-flagged on 2026-08-09, **is** present. Flag → absent, un-flag →
present, against a known history.

A second defect surfaced while measuring: `scripts/check-context-floor.py` charges the
"skill descriptions" budget for **all 76** skills, including the 33 no model can see — inflating
that category by **3,938 chars** against text that costs zero always-on context.

## Approach

Three moves, in dependency order.

**1. Un-flag all 15 — but by a per-skill decision, not one blanket rule.**

The handoff asks for a per-skill verdict between *un-flag* and *delete the loader instruction*.
Applying the same lens used below for the 18 untouched skills, the deletion arm needs one of two
things to be true: the skill's content is duplicated in the agent prompt, or it is genuinely
slash-command-only. Measured against all 15, neither holds:

- **Not duplicated.** Every one is a 155–279 line technique document. No agent prompt contains an
  equivalent; deleting the mention would discard content the agent is explicitly meant to consult.
- **Not slash-command-only.** Only 2 of 15 carry `argument-hint` (`brainstorming`, `writing-plans`)
  — and `writing-plans` is a *mandatory role-core load for the planner*, which settles it:
  `argument-hint` describes arguments when a human invokes a skill, it does not mark one as
  human-only. It is not evidence for deletion.

So the verdict is un-flag for all 15, reached per skill rather than assumed — with two **different**
justifications, because the mandatory argument does not apply to the on-demand seven:

- **The 8 mandatory/mixed** (`execute-operations-config`, `generate-operations-config`,
  `writing-plans`, `validate-operations-config`, `git-workflow`, `systematic-debugging`,
  `test-driven-development`, `verification-before-completion`): a declared contract that cannot
  execute. Deleting these instructions would silently downgrade the Iron Law, TDD, and
  verification contracts to nothing.
- **The 7 on-demand** (`brainstorming`, `context-budget`, `dispatching-parallel-agents`,
  `search-first`, `subagent-driven-development`, `verification-loop`,
  `finishing-a-development-branch`): **no Iron Law argument applies here, and none is claimed.**
  The honest rationale is different: a "load when the trigger fires" instruction that can never
  fire is arguably worse than an absent one, because the prompt reads as a capability the agent
  does not have. Five of these are the coordinator's, whose entire value is adaptive routing —
  un-flagging is what makes that routing real rather than described.

Cost measured before deciding: **+1,517 chars** of description, taking the real always-on skill
floor from 6,294 to **7,811**.

**2. Make the floor measure reality.** Skip model-invisible skills, and re-baseline the category
**14,000 → 9,000**. That is a *tightening*, not a raise: the old ceiling gated a number that
counted 3.9k chars of invisible descriptions. 7,811 of 9,000 leaves honest headroom.

**3. Make the rule mechanical.** `tests/test_skill_loading_contract.py` fails if any agent declares
a load of a model-invisible skill. This is ChaosEngine A6 — *if a behaviour is mandatory at a
lifecycle moment, the mechanism must register it; prose is not enforcement* — enforced instead of
restated, so the contradiction cannot silently return.

## Operations (18)

| # | Type | Path | Why |
|---|------|------|-----|
| 1–15 | code_edit | `.claude/skills/<name>/SKILL.md` | delete the `disable-model-invocation` line |
| 16 | code_edit | `scripts/check-context-floor.py` | **measurement fix only** — stop charging for invisible skills; budget untouched |
| 17 | code_edit | `scripts/check-context-floor.py` | **budget re-baseline only** — 14000 → 9000, owner-visible in isolation |
| 18 | file_create | `tests/test_skill_loading_contract.py` | the mechanical A6 gate |

Ops 16 and 17 are split so `git blame` on the budget line shows a change that is *only* the
budget, and the owner-gated decision is reviewable without reading the measurement diff.

## Tests

- **The gate itself**: no agent may declare a load it cannot execute; every declared load names a
  skill that exists; and an anti-vacuity guard asserting the corpus is non-empty and that something
  is still flagged — otherwise a regex that quietly stops matching turns the file green while
  enforcing nothing.
- **The floor fix**: the visible total must be strictly less than the all-skills total.

Binding proven by mutation before this is considered done: re-flag one of the 15 and the gate must
fail naming that agent → skill pair.

## Risks

- **Un-flagging changes on-demand behaviour, not just availability.** Seven skills become
  model-invocable that were not, so agents may now auto-load them when a trigger fires. That is the
  intent — an unreachable trigger is the defect — but it is a behavioural change, not merely a
  bookkeeping one, and it lands on the coordinator most. Watched via the context floor rather than
  assumed harmless.
- **Un-flagging widens the routing surface**, which task 009 wants to shrink. Accepted with numbers
  rather than by assertion: +1,517 chars against a re-baselined 9,000 ceiling. The alternative —
  deleting 15 mandatory-load instructions — trades a measurable context cost for an unmeasurable
  behavioural one.
- **Lowering a budget is normally owner-gated.** This lowers it, which can only make the gate
  stricter, and it accompanies a measurement fix that made the old number meaningless. Flagged for
  the owner rather than done quietly.
- **The 18 flagged skills nobody declares a load of are left alone.** They are genuinely
  slash-command-only and cost no context; no change is the correct call for them.

## Rollback

`git revert`, or `/rollback` against the engine backup. Ops 1–15 delete one frontmatter line each
and are independently revertible; op 16 is a whole-file replacement that fails closed on drift; op
17 is a new file with no importers. Reverting restores the flags and the old (inflated) budget
together — they must move as a pair, since the 9,000 ceiling assumes the corrected measurement.
