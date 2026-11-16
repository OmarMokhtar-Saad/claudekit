# Plan: review-panel covered-only CONTINUE wording + stop-rule docs

**Date**: 2026-11-11 | **Requested by**: Omar — "do" (item 2: the 3 design-critic Majors carried from PR #71).
**Tier**: 1 (one wording branch in advisory tooling, plus docs).
**Branch**: `fix/review-panel-covered-wording` off main 4f6cdd7.

## Goal

Close the 3 Majors carried in PR #71 (design critic, round 3 of `plan-review-panel-followups.md`).

## Design

1. **Covered-only CONTINUE** (r3-1): in `stop_line()`, when the result would be CONTINUE and the
   current round has no uncovered Blocker or Major (`not cur.get("blockers") and not cur.get("majors")`)
   but is not clean (covered findings exist), return
   `CONTINUE: only covered findings — fix the reviewer's ISSUES, then re-run /review`.
   Every other CONTINUE keeps `CONTINUE: fix uncovered Blockers, then re-run /review`.
2. **STOP with an open covered Blocker** (r3-2): document in `REVIEW_PANEL.md` that the no-new-Blocker
   STOP fires even when a repeated Blocker is still open. That is the EGM intent (re-reviewing does
   not converge it), and the open Blocker goes to the owner as a follow-up. Behaviour is unchanged.
3. **S2 bound** (r3-3): in the `critic-read-scope.py` docstring, state that a `.claude/plans` symlink
   makes every regular `plan-*.md` directly in its target dir readable. This is intended, because
   the symlink is owner-made.

## Files

Files:
  `.claude/operations/scripts/review-panel.py`
  `.claude/hooks/critic-read-scope.py`
  `.claude/agents/_shared/REVIEW_PANEL.md`
  `tests/test_review_panel_script.py`
  `CHANGELOG.md`

## Tests

- `test_covered_blocker_is_not_a_clean_round`: expected line becomes
  `PANEL: 0 blocker, 0 major (uncovered), 1 covered; round 2; CONTINUE: only covered findings — fix the reviewer's ISSUES, then re-run /review`
  (fails before the change).
- The existing CONTINUE tests (`:137`, `:217`) stay green: those rounds have uncovered Blockers.

## Validation commands

```
python3 -m pytest -q tests/test_review_panel_script.py tests/test_critic_read_scope.py tests/test_review_panel.py tests/test_panel_guard.py
python3 scripts/gen-plan-index.py --check
ruff check .claude/operations/scripts/review-panel.py .claude/hooks/critic-read-scope.py
```

## Rollback

`git revert` the commit. No state change.
