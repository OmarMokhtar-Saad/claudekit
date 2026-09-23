# Plan: headless flow -- /plan in -p mode, actionable gate messages, `ck flow`

**Source:** 2026-09-23 headless flow benchmark (vault `claude/sessions/2026-09-23-flow-benchmark.md`).
Tier 2 (several files, no security/schema surface); parent-written.

## Problems measured

1. `/plan` under `claude -p` ignores its own body: no plan file, no planner spawn, implements
   directly (7 turns, 36k avg ctx, 255k rebilled).
2. Two implementer refusals ("no ops.json", "no APPROVED review record") cost ~150k tokens
   because neither names the next command.
3. No single headless entry point chains planner -> review -> record -> implement -> verify
   with per-phase usage.

## Changes

Ops file 1: `.claude/plans/plan-headless-flow.ops.json` (3 operations)
- `.claude/commands/plan.md` -- headless rule: no Task tool => mechanism B always; if Bash is
  missing too, refuse with the exact `claude -p --agent planner` command.
- `.claude/agents/implementer.md` -- pre-flight prints the expected ops path and the
  generate/extract commands; APPROVAL GATE relayed with the `review-record.py write
  --from-review` command.
- `.claude/operations/scripts/execute-json-ops.py` -- `approval_plan_hint()`; the refusal
  prints steps 1-3 with real paths (plan.md, recorder, executor).

Ops file 2: `.claude/plans/plan-headless-flow-cli.ops.json`
- `src/claudekit/cli/flow.py` (new) -- `ck flow "<task>"`: planner (`claude -p --agent planner`)
  -> extract-json-from-plan.py -> validate --stamp-baseline -> reviewer -> review-record.py
  write --from-review --reviewer-role reviewer -> execute-json-ops.py (gate on) + the plan's
  validation commands -> verifier with the captured test output. Usage table from
  `--output-format json` (turns, avg ctx, rebilled, cost). `--python` defaults to the main
  checkout's `.venv` python when run in a worktree.
- `src/claudekit/cli/main.py` -- `flow` sub-parser + dispatch.
- `tests/test_cli_flow.py` (new) -- fake `claude` on PATH; asserts plan/ops/record/execution
  and the table; refusal path when the reviewer rejects.
- `docs/cli.md`, `CHANGELOG.md`.

## Validation

```bash
python3 -m pytest tests/test_ops_approval_gate.py tests/test_review_record.py tests/test_cli_flow.py -q
ruff check src/ tests/ .claude/operations/scripts/
python3 scripts/gen-docs.py --check
```

## Not built (measure first, per request)

- reviewer on sonnet for tier-1 test-only plans: the kit's `reviewer.md` is already
  `model: sonnet`; the 19k/3-turn run must be checked against the installed copy.
- verifier at 10 turns for a one-file change: its 6-phase workflow mandates that many
  commands; a `--from-test-output` mode is what `ck flow` supplies.
