# Plan: `/plan` writes plan + ops inline; `--deep` spawns the planner

Item 4 of `.claude/plans/plan-token-spend-remediation.md` section E.

## Overview

Every `/plan` invocation currently spawns the `planner` agent. Measured 2026-09-19 over two
days: 33 planner runs, 646 M input tokens (19 % of all spend), 98 turns average, worst case
572 turns / 895 K context — for output the parent session could have written from the
context it already held. The spawn pays a second full corpus load (CLAUDE.md + agent prompt
+ re-exploration of files the parent has already read) on every Tier 1/2 change.

Default becomes: the parent writes `.claude/plans/plan-<slug>.md` and
`.claude/plans/ops-<slug>.json` itself, then validates. `/plan --deep <task>` keeps both
existing spawn mechanisms verbatim for changes that genuinely need exploration.

## Scope — every path this ops config writes

- `.claude/commands/plan.md` — new default section, mode table, `--deep` flag; the two
  existing invocation sections become `--deep` mechanisms A and B, bodies unchanged.
- `.claude/agents/_shared/INVOCATION.md` — the planner's headless row and the two prose
  paragraphs that still describe a planner `Bash` grant removed on 2026-09-19; the row now
  also records that the planner is spawned only by `/plan --deep`.

Not touched: `.claude/agents/planner.md` (the agent prompt is unchanged — it is still the
right prompt when it *is* spawned), `README.md` (the `/plan` row still describes what the
command does), `docs/` (no counts change; no command added or removed).

## Implementation steps

1. `plan.md`: replace the frontmatter description/argument-hint and the "Spawns the local
   planner agent" lead with (a) the no-spawn default statement + measurement, (b) a two-row
   mode table, (c) `## Task` carrying the `--deep` flag rule, (d) `## Default — you write
   both files` giving the five-step inline procedure, (e) the `## \`--deep\`` heading that
   the existing "Two verified mechanisms" sentence now falls under.
2. `plan.md`: fold the old `## Task` block away and retitle `## Invocation — interactive
   (default)` to `### \`--deep\` mechanism A — interactive Task tool`.
3. `plan.md`: retitle `## Invocation — scripted (claude -p)` to `### \`--deep\` mechanism B
   — scripted (claude -p)`.
4. `INVOCATION.md`: rewrite the planner rationale cell in the scoped-tool-list table — no
   Bash since 2026-09-19, caller runs the validator, spawned only by `/plan --deep`.
5. `INVOCATION.md`: rewrite the "Never grant unrestricted Bash" paragraph so it stops
   claiming the planner has a scoped Bash grant.
6. `INVOCATION.md`: rewrite the known-drift paragraph — the planner row is no longer drift,
   both tables agree.

## Validation commands

```bash
python3 -m pytest tests/test_behavior_spec.py tests/test_agent_tool_grant_drift.py tests/test_lint.py tests/test_agent_prompt_size.py -q -p no:cacheprovider
python3 scripts/gen-docs.py --check
python3 scripts/check-plan-artifacts.py --check
```

## Rollback

`.claude/plans/.ops-backups/<timestamp>/` holds both files; restore them and re-run the
validation commands. Nothing else depends on the wording.

## Risk assessment

- **LOW — prompt-only change.** No code, no hook, no schema. The binding gates are
  `test_agent_tool_grant_drift` (frontmatter-grants table, 2-column rows — untouched here)
  and `test_behavior_spec.test_invocation_table_covers_spawned_roles` (`| planner` row must
  survive — it does).
- **MEDIUM — INVOCATION.md is modified by another session.** Named by the item, so the edit
  is sanctioned; the baseline is stamped immediately before execution so a concurrent write
  fails the dry run instead of being clobbered.
- **LOW — behavioural regression risk.** The `--deep` bodies are moved, not rewritten: the
  Task-tool spawn instructions and the `claude -p` script are byte-identical afterwards.

## Archived configs

- `.claude/plans/archive/ops-plan-inline/ops.json` (2 operations)
- `.claude/plans/archive/ops-plan-inline/ops-trim.json` (1 operation)

