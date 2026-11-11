# Plan: review-panel follow-ups (critic Majors carried from PR #70)

**Date**: 2026-11-11 | **Requested by**: Omar — "finish them all in parallel" (triage the 4 Majors the V5 panel carried as follow-ups).
**Tier**: 2 (two small behaviour changes in advisory tooling; no new hooks).
**Branch**: `feat/review-panel-followups` off main eefb7c9.

## Goal

Fix the two critic findings from the V5 round 3 panel (`plan-review-panel-fixes.md`) that hold up against the code. Drop the two that do not.

## Triage

| Id | Finding | Verdict |
|---|---|---|
| design-r3-1 | `stop_line()` "clean" uses *uncovered* counts; a real Blocker wrongly deduped as covered can yield `STOP: 2 consecutive clean rounds` | **Fix (S1)**: confirmed, `review-panel.py:246` `clean()` reads `blockers`/`majors`, which `merge` fills from `uncovered` only (`:284-285`) |
| design-r3-2 | Plan read denied when `.claude/plans` is a symlink out of the project | **Fix (S2)**: confirmed edge, `critic-read-scope.py:36` realpaths the target, and the cross-repo allowance (`:41`) needs the *real* path to end in `/.claude/plans/plan-*.md` |
| readiness-r3-1 | D1/D6 spec gaps (ledger fields, dedup word source, REF disambiguation, same-sha stop line) | **Drop**: D1-D9 are implemented; the code is the spec (`review-panel.py:139` REF rule, rounds file sha dedup). Plan is historical. |
| readiness-r3-2 | V5 manual, no machine assertion | **Drop**: V5 re-run passed 2026-11-11 and is recorded; it is a one-time live check by design. |

## Design

### S1. Clean rounds count every critic finding

- `merge` records, per round, `raw_blockers` and `raw_majors` (all parsed critic findings, covered or not) beside the existing uncovered `blockers`/`majors`.
- `stop_line()` `clean(r)` = `not r.get("raw_blockers", r.get("blockers")) and not r.get("raw_majors", r.get("majors"))` (old rounds files fall back to the uncovered fields).
- The no-new-Blocker STOP and CONTINUE lines keep using uncovered blockers (dedup stays advisory, as D1 says).
- PANEL line unchanged; add `(<n> covered)` only when n > 0.

### S2. The exact plan from the prompt is always readable

- `critic-read-scope.py` `blocked()`: before the realpath scope check, if `os.path.abspath(target)` matches `*/.claude/plans/plan-*.md` (not `*.review.md`/`*.panel-*.md`) and is a file, allow. Keeps the sibling denies.

## Files

- `.claude/operations/scripts/review-panel.py`
- `.claude/hooks/critic-read-scope.py`
- `tests/test_review_panel_script.py`
- `tests/test_critic_read_scope.py`
- `CHANGELOG.md`

## Tests

- S1: two rounds whose only Blocker is marked covered → stop line is not `STOP: 2 consecutive clean rounds`; old rounds file without `raw_*` still works.
- S2: plan reached through a symlinked `.claude/plans` dir → allowed; a `*.review.md` sibling through the same symlink → denied.

## Validation commands

```
/usr/local/bin/python3 -m pytest -q tests/test_review_panel_script.py tests/test_critic_read_scope.py tests/test_review_panel.py
/usr/local/bin/python3 scripts/gen-plan-index.py --check
```

## Out of scope

- Calibrating the dedup thresholds on audit data (S1 makes them non-gating, so calibration no longer changes a stop decision).
- Rewriting `plan-review-panel-fixes.md` for the dropped spec gaps.
