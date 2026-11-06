# Plan: close remaining Tier 3 delete-gate bypasses (retroactive record)

**Date**: 2026-11-06 | **Requested by**: Omar ("finish them all") — the reviewer-found gaps left open after PR #66.
**Note**: the edit to `shell-write-gate.py` was made before this plan existed (a scripted write that plan-gate did not catch). This plan records it for review; the PR stays unmerged until the owner accepts it.

Tier: 3 (security hook)

## Goal

`shell-write-gate.py` must not let a Tier 3 tracked file be deleted unmarked through: variable operands, `xargs rm`, `find -delete` / `-exec rm`, brace expansion, literal `[ ]` names, or a case-variant spelling.

## Design

- Unenumerable operands (`$var`, backticks, `{a..b}`, xargs, find) yield an UNBOUNDED sentinel; inside a git repo with `.claude/plans` the command is blocked (exit 2), elsewhere ignored.
- `{a,b}` expanded; a literal existing name is checked alongside its glob; operands resolved to on-disk case.
- Operand tokens keep braces (group punctuation stripped only when unbalanced).
- Speed bump, not a sandbox (hard rule 6).

Files:
- `.claude/hooks/shell-write-gate.py`
- `tests/test_plan_gate_hooks.py`
- `CHANGELOG.md`

## Verification

`pytest tests/test_plan_gate_hooks.py` (115 pass), ruff clean, gen-docs --check OK.
