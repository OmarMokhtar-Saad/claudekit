# Plan: contrib-governance P3 — write the procedure, not the workaround (C3)

Phase 3 of [plan-contrib-governance.md](plan-contrib-governance.md). Ops config:
`.claude/plans/ops-contrib-governance-p3.json` (6 operations, 0 deletions).

## The rule

A prompt step that cannot be justified without naming a model, a model version, or one
agent's private tool name is a defect: describe the **capability** instead. This is
CLAUDE.md's model-routing policy generalised from `model-policy.json` — where a model is
a one-line edit in one table — to every prompt in the corpus. A pinned model version in
prose goes stale silently, and the prompt then instructs a model that no longer exists.

## Measured ground truth (re-measured 2026-09-19 with the gate's own patterns)

20 files, 94 occurrences under `.claude/agents`, `.claude/commands`, `.claude/skills`
with frontmatter stripped and `.claude/worktrees/` excluded (agent **frontmatter**
legitimately carries `model:` — `gen-model-policy.py` gates that, so the gate must never
read it). Top: `QUICK_START.md` 31, `commands/refine.md` 10, `commands/santa.md` 8,
`santa-method/SKILL.md` 6, `_shared/INVOCATION.md` 5, `usage-monitoring/SKILL.md` 5,
`coordinator.md` 4.

Four are legitimate and stay: `usage-monitoring` (a price table needs real product
names), `coordinator.md` (prose explaining the migration *away* from names),
`_shared/INVOCATION.md` (measured per-model cost evidence), `eval-harness/SKILL.md`
("haiku" as the poem form, line 119). `commands/prp-commit.md` hardcodes a stale
`Co-Authored-By: Claude Sonnet 4.6` line twice — a separate, real bug, fixed here.

## Scope

In: the gate, its allowlist, its tests, and the prp-commit fix. **Out: the fix pass**
converting the ~90 remaining occurrences to tier language — deferred to
`plan-prompt-model-name-fixpass`, because each conversion needs an exact unique anchor
and 90 anchors across 19 files is several times one planning pass's anchor budget.
Phase 3 makes that debt explicit, counted and greppable instead of invisible.

## The hazard this design is built around

An allowlist placed above an early return exempts every branch below it (measured in
this repo; memory `allowlist-before-early-return`). Two structural answers:

1. **Order.** The gate scans everything first and collects every occurrence; only then
   does it filter. There is no `return` between the scan and the filter, and no allowlist
   lookup inside the scan loop.
2. **No true blanket.** A whole-file entry (`"match": "*"`) is legal only with a
   `"max"` — the occurrence count at the moment the decision was taken. The file may hold
   that many and no more; a new violation in an exempted file **reds the gate**. A
   whole-file entry also needs a reason beginning `PENDING-FIX(<plan-slug>)` (debt, must
   shrink) or `BY-DESIGN:` (permanent, ratcheted by `max`).

## Tasks

### T1 — the gate

- **File:** `scripts/check-prompt-model-names.py` (new)
- **Action:** `file_create`
- **Details:** stdlib only. `--check`, `--root`, `--allow`. Exit 0 clean / 1 on a
  violation or a malformed allowlist entry. Strips YAML frontmatter. Skips
  `.claude/worktrees/`. `--root` exists so the tests can run the real gate over a fixture
  tree.
- **Done when:** `python3 scripts/check-prompt-model-names.py --check` exits 0 and prints
  the outstanding debt count.

### T2 — the allowlist, one reason per entry

- **File:** `scripts/prompt-model-names.allow.json` (new)
- **Action:** `file_create`
- **Details:** 19 entries (every measured file except `prp-commit.md`, fixed in T4). Four
  `BY-DESIGN:`; fifteen `PENDING-FIX(plan-prompt-model-name-fixpass)`. Every entry
  carries its `max`.
- **Done when:** the gate accepts it and reports 15 files of debt.

### T3 — tests, including the two proofs

- **File:** `tests/test_prompt_model_names.py` (new)
- **Action:** `file_create`
- **Details:** fixture trees under `tmp_path`. Proofs: (a) an un-allowlisted violation
  reds the gate — the positive control, without which the gate is assumed inert; (b) an
  allowlisted file still reds on a **second, different** violation — the direct test of
  the early-return hazard. Also: frontmatter is not scanned; `.claude/worktrees/` is
  skipped; `"*"` without `max` is rejected; a short reason is rejected; a stale allowlist
  path is rejected; and the live repo run is clean.
- **Done when:** `python3 -m pytest tests/test_prompt_model_names.py -q` passes.

### T4 — fix the stale attribution in `prp-commit`

- **File:** `.claude/commands/prp-commit.md`
- **Action:** `code_edit`, 2 edits
- **Details:** both hardcoded `Co-Authored-By: Claude Sonnet 4.6` lines become a
  placeholder naming the session's own attribution line, plus one paragraph saying why a
  pinned version in a prompt mis-attributes every commit after it goes stale. This is the
  rule applied to itself.
- **Done when:** the file has no model name and the gate reports 0 occurrences for it.

### T5 — CLAUDE.md commands table

- **File:** `CLAUDE.md`
- **Action:** `code_edit` (`add_after`) — adds the Phase 2 and Phase 3 gates to the
  commands block, two lines.
- **Done when:** `python3 scripts/check-context-floor.py --check` still passes.

### T6 — CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** `code_edit` (`add_after` `## [Unreleased]`, leading newline in payload)

## Files touched

- `scripts/check-prompt-model-names.py`
- `scripts/prompt-model-names.allow.json`
- `tests/test_prompt_model_names.py`
- `.claude/commands/prp-commit.md`
- `CLAUDE.md`
- `CHANGELOG.md`

## Acceptance criteria

1. `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-contrib-governance-p3.json` → PASS.
2. `python3 scripts/check-prompt-model-names.py --check` → exit 0, printing
   `debt: 15 file(s)` (if a `max` is off, the gate says which file and by how much —
   correct the number, never widen the entry).
3. `python3 -m pytest tests/ -q` → zero failures.
4. Proven able to fail, by execution, recorded in the commit body:
   `echo 'Use Opus for this step.' >> .claude/commands/review.md` then run the gate →
   must exit 1 naming `review.md` **even though `review.md` is allowlisted** (its `max`
   is exceeded). Restore the file afterwards.
5. `ruff check scripts/ tests/`, `mypy`, `python3 scripts/check-context-floor.py --check`
   and `python3 scripts/gen-docs.py --check` clean.

## Rollback

`git revert` the phase commit. The gate is additive; nothing depends on it until it is in
CI, and the prp-commit edit is prose.
