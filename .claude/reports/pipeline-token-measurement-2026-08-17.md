# First measured pipeline under the token-efficiency prompts (2026-08-17)

**Task:** add `--json` to `scripts/check-context-floor.py` + tests + CHANGELOG entry
(3 files, Tier 2 — multi-file, no security/schema/architecture surface → planner only,
no reviewer, per the blast-radius tiering).

## Measured

| Metric | Value |
|---|---|
| Planner (opus) total tokens | **31,959** |
| Planner tool calls | 14 |
| Wall time | 137 s |
| CHANGELOG.md (46,979 B ≈ 11.7k tok) | **NEVER Read — grep-anchored only** |
| Full Reads by planner | check-context-floor.py (3.3 KB), 3 mandatory skills (~16.7 KB), partial test file |
| Ops produced | 4 code_edit, 6 edits, validated APPROVED first try |
| Execution | 4/4 success, dry-run first, backups + RESULT-JSON |
| Suite after | 847 tests pass (3 new), ruff/mypy clean |

## Interpretation

- The anchor-extraction discipline worked on its first real outing: the historically
  worst file (CHANGELOG.md, read in full by 6/6 archived plans) cost a grep instead of
  ~11.7k tokens. On this small plan that is a **~27% planner-token saving** (31.9k vs
  ~43.7k counterfactual); on plans touching several large files the effect compounds.
- Reviewer hop skipped legitimately under Tier 2 → the old pipeline's second full
  payload read (plan + ops re-read by sonnet) did not occur at all.
- Remaining fixed cost visible in the data: ~16.7 KB (~4.2k tok) of mandatory skill
  loads (using-superpowers, writing-plans, generate-operations-config). That is the
  next optimization surface if planner cost needs to drop further (candidate for
  task 009 context-budget work).

## Method

Single planner agent spawn (Task tool, interactive), instructed to self-report full
Reads; usage from the harness (`subagent_tokens`). Executed via execute-json-ops.py
(dry-run → execute). Spent ops archived per delivery-contract gate.
