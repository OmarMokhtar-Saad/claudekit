# Plan: capability-tiers follow-up — the corpus surfaces the first plan left in vendor terms

Slug: `capability-tiers-followup`. Completes wave-2 Phase 1. Blast radius: **Tier 2** — two files,
no security/schema/API surface. Derived from the approved `plan-capability-tiers` (95/100).

## Problem

Landing `plan-capability-tiers` turned `tests/test_behavior_spec.py::TestModelRouting::
test_reviewer_opus_escalation_is_documented` red, and the failure is **correct**: it asserted
`"escalate to opus" in CLAUDE.md`, and CLAUDE.md no longer names vendors. Two real gaps behind it:

1. The reviewer's escalation path was documented **only** as English prose in CLAUDE.md. Removing
   the prose removed the documentation. It should be a structured field — it already is
   (`escalate_to` / `escalate_when` on the role), but nothing read it.
2. `TestModelRouting` and `coordinator.md:427,475-476` are still written entirely in vendor product
   names, so the hardcoding this phase removed from CLAUDE.md survives one directory over.

## Approach

Point the behaviour spec at `.claude/model-policy.json` — the source of truth — instead of at
frontmatter strings, and restate the coordinator's routing prose in tiers.

The rewritten tests are *stronger*, not merely green: a model rename can no longer break them,
while a **tier demotion still does** (e.g. moving `reviewer` to `fast` fails
`test_no_gate_agent_runs_on_the_fast_tier`). One new test,
`test_routing_policy_names_no_vendor_model`, pins the regression this phase exists to prevent.

## Deliberate non-change: command invocation sites

`.claude/commands/plan.md` and `refine.md` keep the literal `--agent planner --model opus`.
Measured reason, not an oversight: `install.sh:203` copies only
`.claude/operations/scripts/*.py` into a user project, so repo-root `scripts/` — and therefore any
tier resolver — **does not exist where those commands run**. Rather than leave the literal
unguarded, `test_plan_command_spawns_planner_on_the_planner_tier` now derives the expected string
from the planner's tier, so the command and the table cannot drift apart silently. Recorded in
`.ai/BACKLOG.md` as the remaining vendor-name surface.

## Operations (3)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `tests/test_behavior_spec.py` | `import json` — the rewritten class reads the policy table, and the module imports only `os`/`re`/`subprocess`/`sys` |
| 2 | code_edit | `tests/test_behavior_spec.py` | `TestModelRouting` rewritten against the policy table |
| 3 | code_edit | `.claude/agents/coordinator.md` | routing prose (lines 427, 475–476) stated in tiers |

## Tests

The changed file *is* the test. Binding is proven by mutation rather than by the suite going green:
demote `reviewer` to `fast` in the policy table → `test_no_gate_agent_runs_on_the_fast_tier` and
`test_reviewer_defaults_to_the_balanced_tier` must fail; put a vendor name back in the CLAUDE.md
routing line → `test_routing_policy_names_no_vendor_model` must fail. Both are executed and the
output pasted before this plan is considered done.

## Risks

- **A test that reads a JSON file can be unreachable as well as vacuous.** Review round 1 rejected
  this plan for exactly that: the rewritten class called `json.load` in a module that never
  imported `json`, so all six tests would have raised `NameError` rather than asserting anything —
  "not vacuous" and "runs at all" are different properties. Op 1 exists because of it, and the
  mutation checks below are only trusted after the class is observed running green first.
- **A test that only reads a JSON file can go vacuous.** Mitigated by the mutation checks above:
  each assertion is shown failing against a deliberately broken table before being trusted.
- `coordinator.md` is a shipped product artifact. The edit is prose-only, changes no tool grant or
  spawn mechanic, and `gen-registry.py --check` still passes (no Skill Loading section touched).

## Rollback

`git revert` of the commit, or `/rollback` against the backup directory the engine writes. Both
edits are find/replace pairs with anchors verified unique before execution; no files are created or
deleted, and **no agent frontmatter or tier assignment changes**, so reverting cannot alter which
model any agent runs on.
