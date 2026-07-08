# Playbook — Step-by-Step Recipes

## Release v2.1.0 (or any version) — currently the top pending action

1. Confirm owner go-ahead (release + PyPI are user-gated).
2. Green tree: full DoD gate ([CHECKLISTS.md](CHECKLISTS.md) §DoD) on main.
3. CHANGELOG: move `[Unreleased]` → `## [X.Y.Z] - YYYY-MM-DD`; keep the versioning-correction note.
4. Verify the three version locations agree (pyproject, `src/claudekit/__init__.py` fallback, `operations/scripts/shared.py`); `pytest tests/test_packaging.py -q`.
5. Local dry-run: `python3 -m build && pip install dist/*.whl --force-reinstall && ck doctor` in a clean venv, plus `CLAUDEKIT_HOME`-less `ck init /tmp/x --full --yes`.
6. `git tag vX.Y.Z && git push origin vX.Y.Z` → release.yml → Trusted Publishing. **First run is unexercised** — watch the job; PyPI publisher config may need iteration.
7. Post-publish: `pip install claude-kit==X.Y.Z` from PyPI in a clean venv → `ck init && ck doctor`; GitHub Release notes from CHANGELOG; update [STATUS.md](STATUS.md)/[SESSION_STATE.md](SESSION_STATE.md).

## Fix a bug

Reproduce as a red behavioral test → root-cause (no symptom patches; [DEBUGGING_GUIDE.md](DEBUGGING_GUIDE.md)) → minimal fix → full DoD gate → CHANGELOG `Fixed` → `fix(scope): ...` commit referencing the test.

## Add a feature to the kit

Check `review/tasks/` first (it's probably specced) → for surface changes get owner sign-off → tests-first where practical → implement per [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) asset recipes → DoD gate → CHANGELOG `Added` → update affected docs + relevant `.ai/` files.

## Execute task 008 (corpus consolidation) — when approved

1. Produce the migration table: each merged asset → absorbing asset, registry updates, coordinator-routing updates, QUICK_START/INVOCATION rows, README/docs mentions.
2. Merge order: skills first (autonomous-loop→autonomous-loops, verification pair, token/context trio, onboarding pair, dependency pair), then agents (python/ts-reviewer + silent-failure-hunter → code-reviewer; documenter + doc-updater; code-simplifier → refactor-cleaner; tdd-guide + model-router → skills; harness-optimizer → /context-budget), then delete `templates/skills/`.
3. Per merge: port unique content, delete file, `gen-docs.py` (counts change!), grep old name repo-wide (zero hits), registry + routing updated, full DoD gate.
4. CHANGELOG `Changed` with a user-facing migration note; bump docs counts everywhere via gen-docs.

## Build the eval framework (task 010)

`evals/` with 2–3 fixture repos → golden ops.json snapshots for planner on fixed prompts → `ck eval` runner via `claude -p --output-format json` → reviewer/verifier output schemas (`review.json`) → hook gates `/implement` on `score ≥ threshold` → nightly CI job + trend report → benchmark the 85% token-reduction claim.

## Update documentation after any asset change

`python3 scripts/gen-docs.py` (regen counts) → `--check` green → grep docs for the old asset name → update README tables + docs/ page + `.ai/` catalog entry → CHANGELOG if user-visible.

## Recover from a bad ops execution (in any ClaudeKit-enabled project)

`/rollback` (or `python3 .claude/operations/scripts/restore-backup.py`) → verify working tree (`git status`, tests) → diagnose which guard should have caught it → if a guard gap: bypass-corpus test + guard fix in the kit.

## Hand over to the next AI

Update [SESSION_STATE.md](SESSION_STATE.md) + [CHANGELOG_AI.md](CHANGELOG_AI.md) + [STATUS.md](STATUS.md) (+ [DECISIONS.md](DECISIONS.md) for new decisions) → verify DoD gate → commit. Test: could a stranger resume from those four files alone?
