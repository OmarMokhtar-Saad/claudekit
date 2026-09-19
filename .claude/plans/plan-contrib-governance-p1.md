# Plan: contrib-governance P1 — the skill-edit rejection axis (C1)

Phase 1 of [plan-contrib-governance.md](plan-contrib-governance.md). Ops config:
`.claude/plans/ops-contrib-governance-p1.json` (4 operations, 0 deletions).

## Problem

`.claude/knowledge/rejections/` records rejected **plans** only: one `<ops-slug>.md`
brief per slug plus an append-only `INDEX.jsonl`, single writer `review-record.py`,
trigger = the 2nd non-approving round for an ops slug. A rejected **skill or prompt
edit** has no record anywhere, so an edit that evals or review already killed can be
re-proposed forever, at full cost, with nothing to retrieve.

## Approach

A second `row_type` in the **same** index — not a second store (task 008, and one
Phase-0 search habit rather than two). `_folded_rows` is the fold every reader goes
through, so excluding the new rows there keeps `briefs=` (the `/flow-retro` sample-size
gate) counting plans only, while `stats` gains an explicit `skill_edits=` line and
`search` gains a `SKILL-EDIT REJECTIONS:` section.

## Scope

In: the writer subcommand, the two readers, the store README, one test file, CHANGELOG.
Out: any change to the plan-rejection trigger, schema or brief format; any new directory.

## Tasks

### T1 — extend `review-record.py` with the skill-edit axis

- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** `code_edit`, 5 edits, one op (they must land together — see below)
- **Details:**
  1. `_folded_rows` drops `row_type == "skill-edit"` alongside `"classification"`.
     This edit and the writer are in the **same operation** deliberately: if the writer
     landed first, every skill-edit row would be counted as a brief and inflate the
     retro's sample-size gate.
  2. `_stats_core` prints `skill_edits=N skills=M` as its own line.
  3. `cmd_rejections_search` scans the skill-edit rows separately (they are no longer in
     `_folded_rows`) and prints them before the plan hits; `no match` now returns 3 only
     when **both** axes are empty.
  4. New `SKILL_EDIT_ROW` / `SKILL_EDIT_OUTCOMES` constants and three functions:
     `_skill_edit_rows`, `_skill_brief_name`, `cmd_rejections_skill_edit`. The writer
     fails closed when `reflection.py`'s `redact_secrets` is unavailable and refuses to
     write through a symlink — the same discipline the brief writer already uses,
     because these are tracked files.
  5. argparse wiring: `rejections skill-edit --skill --change --before --after
     --outcome {rejected,reverted,superseded} --evidence`.
- **Done when:** `review-record.py rejections skill-edit --skill X ...` writes both the
  brief section and the index row; `rejections search X` prints it; `rejections stats`
  shows `skill_edits=1` while `briefs=` is unchanged.

### T2 — behavioural tests, including the axis-isolation regression

- **File:** `tests/test_skill_edit_rejections.py` (new)
- **Action:** `file_create`
- **Details:** every test drives the real script through subprocess in a temp tree
  holding a `.claude/` directory (that is how the script locates its store). Covers:
  the round trip; retrieval by skill name; `skill_edits=` counted **and** `briefs=`
  **not** inflated (the regression that motivates the single-op design); a second
  attempt on the same skill appends rather than overwrites; an invalid `--outcome` is
  refused; and the mutation proof — a row written with a `row_type` the readers do not
  know must not silently become a brief.
- **Done when:** `python3 -m pytest tests/test_skill_edit_rejections.py -q` passes and
  the axis-isolation test fails if edit 1 is reverted.

### T3 — the rule the machinery cannot enforce

- **File:** `.claude/knowledge/rejections/README.md`
- **Action:** `code_edit` (`add_after`, payload carries its own leading newline)
- **Details:** a `## The skill-edit axis` section documenting the subcommand, the row
  shape, and the non-obvious survival rule: **the row must land on the default branch in
  a commit separate from the rejected change.** A row that rides the rejected branch is
  discarded when that branch is force-pushed or closed, and the store then silently
  under-counts exactly the edits it exists to remember.
- **Done when:** the section names the subcommand, the separate-commit rule and the
  reason for it.

### T4 — CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** `code_edit` (`add_after` `## [Unreleased]`, leading newline in payload)
- **Done when:** the entry describes the user-visible surface (a new subcommand and two
  changed read paths) without a component count.

## Files touched

- `.claude/operations/scripts/review-record.py`
- `tests/test_skill_edit_rejections.py`
- `.claude/knowledge/rejections/README.md`
- `CHANGELOG.md`

## Acceptance criteria

1. `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-contrib-governance-p1.json` → PASS.
2. `python3 -m pytest tests/ -q` → zero failures (the whole suite, not just the new file:
   `test_rejection_briefs.py` and `test_review_record.py` exercise the same readers).
3. `python3 .claude/operations/scripts/review-record.py rejections stats` on the live
   store prints the same `briefs=` it printed before the change, plus `skill_edits=0`.
4. `ruff check .claude/operations/scripts/ tests/` and `mypy` clean.
5. The axis-isolation test is demonstrably able to fail: revert edit 1 by hand, re-run
   the test, observe red, restore. Record the observation in the commit body.

## Rollback

`git revert` the phase commit. Any skill-edit rows already written stay in the
append-only index; after the revert they are counted as briefs again, so the revert must
be paired with removing those rows from `INDEX.jsonl` if any were written.
