# Plan: Phase 2c file-set check lists every untracked file

Tier: 2

Found by the owner-requested `/implement --delegate` dry run on 2026-11-27, in a fresh session on a clean
clone of main f022759. `git status --porcelain --ignored` folds a new untracked directory into one
entry (`?? toy/`), so a stray `toy/stray.txt` written next to the planned `toy/a.txt` did not show up
as its own path. `--untracked-files=all` lists each file.

Files:
- .claude/agents/_shared/implementer-reference.md
- tests/test_implement_subagent.py
- .ai/SESSION_STATE.md
- .ai/CHANGELOG_AI.md
- CHANGELOG.md

## Steps
1. implementer-reference.md Phase 2c step 2: the command becomes
   `git -C <wt> status --porcelain --ignored --untracked-files=all`, with the reason in one clause.
2. tests/test_implement_subagent.py: the needle becomes `status --porcelain --ignored --untracked-files=all`.
   Add a behavioural test: in a tmp repo with a new dir holding 2 files, that command lists both paths.
3. SESSION_STATE + CHANGELOG_AI: record the Step 4 probe = branch (a) (`git status` from plan-implementer
   BLOCKED by shell-write-gate) and the Step 9 dry run results. CHANGELOG `[Unreleased]`: Fixed line.

## Verify
`python3 -m pytest tests/test_implement_subagent.py -q`; `ruff check tests/test_implement_subagent.py`.
