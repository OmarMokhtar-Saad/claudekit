# Plan: review-panel follow-ups (critic Majors carried from PR #70)

**Date**: 2026-11-11 | **Requested by**: Omar — "finish them all in parallel", then "do" (triage the 4 Majors the V5 panel carried as follow-ups, review, implement).
**Tier**: 2 (two small behaviour changes in advisory tooling; no new hooks, no state migration).
**Branch**: `feat/review-panel-followups` off main eefb7c9.

## Goal

Fix the two critic findings from the V5 round 3 panel (`plan-review-panel-fixes.md`) that hold up against the code. Drop the two that do not.

## Triage

| Id | Finding | Verdict |
|---|---|---|
| design-r3-1 | `stop_line()` "clean" uses *uncovered* counts; a real Blocker wrongly deduped as covered can yield `STOP: 2 consecutive clean rounds` | **Fix (S1)**: confirmed, `review-panel.py:246` `clean()` reads `blockers`/`majors`, which `cmd_merge` fills from `uncovered` only (`:284-285`) |
| design-r3-2 | Plan read denied when `.claude/plans` is a symlink to a dir not named `.claude/plans` | **Fix (S2)**: confirmed edge, `critic-read-scope.py:36` realpaths the target, and the cross-repo allowance (`:41`) needs the *real* path to end in `/.claude/plans/plan-*.md` |
| readiness-r3-1 | D1/D6 spec gaps (ledger fields, dedup word source, REF disambiguation, same-sha stop line) | **Drop**: D1-D9 shipped in PR #70 and the tests pin the behaviour (`review-panel.py:139` REF rule; `test_same_sha_is_one_round`). A spec note would restate code that tests already fix. |
| readiness-r3-2 | V5 manual, no machine assertion | **Drop**: V5 re-run passed 2026-11-11 and is recorded in that plan's Risks; it is a one-time live check by design. |

## Design

### S1. The stop rule counts every critic finding (dedup is display-only)

In `cmd_merge` (`review-panel.py`), next to `uncovered`, keep `found = []`: every `(name, sev, text)` from `findings(reply)` of a **valid** critic, appended before the `covered()` filter.
- `raw_blockers = [_norm(t) for _, s, t in found if s == "Blocker"]` (list of str, stored as sorted unique like `blockers`); `raw_majors = sum(1 for _, s, _ in found if s == "Major")` (int).
- `record_round(plan, sha, blockers, majors, raw_blockers, raw_majors)`: the row gains `"raw_blockers": sorted(set(raw_blockers)), "raw_majors": raw_majors`.
- `stop_line()`: new helpers `_rb(r) = r.get("raw_blockers", r.get("blockers", []))`, `_rm(r) = r.get("raw_majors", r.get("majors", 0))` (old rows without `raw_*` fall back to the uncovered fields, i.e. they keep today's behaviour). `clean(r) = not _rb(r) and not _rm(r)`; the no-new-Blocker test becomes `set(_rb(cur)) <= set(_rb(rounds[-2]))`. Order is unchanged: 2-clean STOP, then no-new-Blocker STOP (only when `cur` is not clean), then CAP, then CONTINUE. So uncovered/covered no longer affects any stop line; it only decides which findings are printed.
- The PANEL summary line gains a covered count so a CONTINUE round with 0 uncovered findings is not a dead end: when `n = len(found) - len(uncovered) > 0`, `(uncovered)` becomes `(uncovered), <n> covered`; with n = 0 the line is byte-identical to today (existing `startswith("PANEL: 0 blocker, 0 major")` and `tests/test_review_panel_script.py:137` checks stay green). Printed finding lines are unchanged.
- Docs: `.claude/agents/_shared/REVIEW_PANEL.md` PANEL line format (`(uncovered)[, <n> covered]`) and the clean-round rule ("0 Blocker and 0 Major from valid critics, covered or not"); the `review-panel.py` module docstring stop-rule sentence says the same.

### S2. A plan reached through a symlinked plans dir is readable

`critic-read-scope.py` `blocked()` gains one allow rule, checked **first**; when it does not apply, every existing check runs unchanged:
- `lex = os.path.normpath(os.path.join(root, os.path.expanduser(target)))` (lexical, no symlink resolution); `name = os.path.basename(lex)`.
- Allow (return `""`) only when all hold: `real = os.path.realpath(lex)` is **outside** the project root (`real != root and not real.startswith(root + os.sep)`; when inside, fall through so `DENY_GLOBS`/handoffs/`DENY_NAMES` run on the realpath as today); `lex.replace(os.sep, "/")` matches `*/.claude/plans/plan-*.md`; `name` matches neither `*.review.md` nor `*.panel-*.md`; `not os.path.islink(lex)` (the leaf itself is not a symlink); `real` is a regular file (`os.path.isfile(real) and not os.path.islink(real)`); `os.path.basename(real) == name`.
- Security bound: the rule reads at most a regular file named `plan-*.md` whose lexical parent is a `.claude/plans` dir; only the parent directory may be a symlink, and only to a target outside the project (an in-project target such as `.claude/hooks/.state` or `.claude/reports` keeps the existing deny). A leaf symlink (`plan-x.md -> secret`) is never allowed by it and falls to the existing realpath checks (denied when its target is out of scope or a denied sibling).

## Steps

1. S1: edit `cmd_merge`, `record_round`, `stop_line` in `.claude/operations/scripts/review-panel.py`; add S1 tests to `tests/test_review_panel_script.py`; run them.
2. S2: edit `blocked()` in `.claude/hooks/critic-read-scope.py`; add S2 tests to `tests/test_critic_read_scope.py`; run them.
3. Update `.claude/agents/_shared/REVIEW_PANEL.md` (PANEL line, clean rule) and the `review-panel.py` docstring.
4. `CHANGELOG.md` `[Unreleased]`: "review-panel: the stop rule counts covered critic findings too (dedup is display-only) and the PANEL line shows the covered count; critic-read-scope: a plan behind a `.claude/plans` dir symlinked outside the project is readable, leaf symlinks are not."
5. Run the Validation commands; commit.

S1 and S2 are independent; each lands and tests on its own.

## Files

Files:
  `.claude/operations/scripts/review-panel.py`
  `.claude/hooks/critic-read-scope.py`
  `tests/test_review_panel_script.py`
  `tests/test_critic_read_scope.py`
  `CHANGELOG.md`
  `.claude/agents/_shared/REVIEW_PANEL.md`

## Tests

S1 (`tests/test_review_panel_script.py`, existing `merge`/`plan` helpers and `REVIEWER` fixture, whose ISSUES cover `[Blocker] src/cache.py eviction handler swallows exceptions`):
- `test_covered_blocker_is_not_a_clean_round`: round 1 `CLEAN`; plan v2; round 2 the covered Blocker → summary line is exactly `PANEL: 0 blocker, 0 major (uncovered), 1 covered; round 2; CONTINUE: fix uncovered Blockers, then re-run /review` (pre-change code prints `STOP: 2 consecutive clean rounds`, so this test binds).
- `test_merge_records_raw_counts`: after that merge, `.claude/hooks/.state/review-panel-rounds.json` row 2 has `"blockers": []`, `"raw_blockers": ["src cache py eviction handler swallows exceptions"]`, `"raw_majors": 0`.
- `test_repeated_covered_blocker_stops`: covered Blocker in rounds 1 and 2 → `; round 2; STOP: round 2 raised no new Blocker`.
- `test_old_rounds_rows_fall_back`: seed the rounds file with a row lacking `raw_*` (`blockers: [], majors: 0`), then merge `CLEAN` on new bytes → `; round 2; STOP: 2 consecutive clean rounds`.
- Existing round tests stay green unchanged.

S2 (`tests/test_critic_read_scope.py`, existing `root` fixture):
- `test_plan_behind_symlinked_plans_dir_allowed`: real dir `tmp_path_factory.mktemp("store") / "notes"` holding `plan-a.md`, `plan-a.review.md`; `root/.claude` dir with `plans -> <store>/notes`. Assert `blocked(".claude/plans/plan-a.md", root) == ""` (pre-change: `"outside the project"`, so it binds) and `blocked(".claude/plans/plan-a.review.md", root) == "outside the project"`.
- `test_leaf_plan_symlink_not_allowed`: in a real `root/.claude/plans`, `plan-evil.md -> <outside>/secret.txt` → `"outside the project"`; `plan-evil2.md -> root/.claude/hooks/.state/x.jsonl` → contains `.state`.
- `test_symlinked_plans_dir_into_denied_dir`: `root/.claude/plans -> root/.claude/hooks/.state/` holding `plan-x.md` → `blocked(".claude/plans/plan-x.md", root)` contains `.state` (the new rule does not apply to in-project targets).
- The `plan-a.review.md` assertion pins pre-existing behaviour (the old cross-repo rule already excluded siblings): a regression guard, not a binding test. The `.state` wording comes from `DENY_GLOBS` (`matches .claude/hooks/.state/*`).

## Validation commands

```
cd ~/.claude-kit
python3 -m pytest -q tests/test_review_panel_script.py tests/test_critic_read_scope.py tests/test_review_panel.py tests/test_panel_guard.py
python3 scripts/gen-plan-index.py --check
ruff check .claude/operations/scripts/review-panel.py .claude/hooks/critic-read-scope.py
```

## Rollback

`git revert` the implementation commit. No migration: rows written with `raw_*` keys are ignored by the old `stop_line()` (it reads `blockers`/`majors`, which are still written), and old rows are read by the new one through the fallback.

## Out of scope

- Calibrating the dedup thresholds on audit data (after S1 they no longer change a stop decision).
- Changing the CONTINUE wording ("fix uncovered Blockers"); tests and docs quote it.
- Rewriting `plan-review-panel-fixes.md` for the dropped spec gaps.
