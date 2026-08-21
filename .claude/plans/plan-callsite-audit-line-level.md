# Plan: the override registry excuses one literal per entry, not one file

Slug: `callsite-audit-line-level`. **Tier 1** — single file (`tests/test_model_policy.py`), no
public API, security, schema, or architecture surface. Closes the one non-blocking note left open
by the `capability-tiers-audit` review (93.9/100, APPROVED).

## Problem

`EveryHandWrittenModelNameIsAccountedFor` built `recorded` as a **set of paths**. Any file with at
least one registered override became a permanent allowlist: a second, unrelated `--model` literal
added to `santa.md` later would pass the audit silently. The registry was supposed to make every
hand-written model name accountable; at path granularity it made every *file* accountable once.

Line numbers are the obvious key and the wrong one — they drift with every edit above them, so the
registry would rot within a few commits.

## Approach

Key on `(path, model)` and **count**. Each registry entry buys exactly one literal of that shape;
the audit spends an excuse per match and reports anything left unpaid. A second `--model opus` in
an already-registered file now has no unspent entry and fails.

`test_registry_excuses_are_spent_not_reusable` asserts the converse too — the registry must hold
*exactly* one entry per unresolvable literal, so it can carry neither missing entries nor spares.
Together they pin the registry from both sides.

## Operations (1)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `tests/test_model_policy.py` | counted excuses replace set-membership; one new test |

## Tests

The changed file is the test. Binding proven by mutation before this is considered done: append a
second `--model opus` line to a registered file and confirm the audit fails; remove it and confirm
it passes. Executed and pasted, not asserted.

## Risks

- **Two literals of the same shape in one file are indistinguishable**, so the audit cannot say
  *which* is unaccounted, only that one is. Accepted: line-level keying trades that precision for a
  registry that rots on unrelated edits, which is worse.
- Whole-file replacement (`find` = current content): fails closed on drift, cannot corrupt.

## Rollback

`git revert`, or `/rollback` against the engine backup. Test-only change; no runtime, product, or
policy behaviour is affected, so reverting restores the weaker audit and nothing else.
