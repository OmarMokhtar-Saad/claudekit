# Plan: the implementer never runs git

Item 5 of `.claude/plans/plan-token-spend-remediation.md` section E: *"iron-law-gate: parent
creates the branch; implementer never runs git."*

## Problem

`iron-law-gate.py` carried four tables (`_GIT_READ_ONLY`, `_GIT_SAFE`, `_GIT_LIST_ONLY`,
`_GIT_LIST_SAFE`) that let a spawned implementer run `git status`, `git diff --stat`,
`git log --oneline -5`, `git show HEAD --stat`, `git branch --list`, `git remote -v`.
Every one of those reports on state the implementer does not own — the parent session
creates the branch before the spawn and commits after the ops config has run — and each
one costs a full subagent turn (measured: 44 turns / 1.4 M tokens to run three scripts).
Three review rounds were spent tightening those flag lists (MAJOR 2, round 3, round 4);
the grant they were tightening should not exist at all.

## Scope

- `.claude/hooks/iron-law-gate.py` — delete the four git tables; `_decide_git` refuses
  unconditionally, naming the parent session.
- `tests/test_iron_law_hook.py` — move the nine git reporters from `ALLOWED` to `BLOCKED`;
  retarget the mutants whose source anchors disappear; stop using `git status` as the
  spare allowed command in two unrelated tests.

Not in scope (owned by another session, not named by item 5): `.claude/agents/implementer.md`
still lists `git status` as permitted read-only inspection at line 70 and "verify by
checking git status" at line 343. Reported for the owner, not edited here.

## Approach

1. Hook: replace the table block with a comment recording why the grant is gone, and
   reduce `_decide_git` to `return False, "<git belongs to the parent session>"`. The
   dispatch in `decide()` is unchanged, so the refusal is specific rather than a generic
   "not in allowlist".
2. Test: the nine reporters become `BLOCKED` entries under a MAJOR-2-style comment. The
   two git `TARGETED_MUTANTS` pinned source that no longer exists
   (`_GIT_LIST_SAFE = frozenset({`, the positional loop) and are replaced by ONE mutant
   that re-permits git wholesale; its declared collateral is every other git label, which
   is the honest blast radius of a single refusal.
3. `invented-flag-refused-by-default` loses `git-diff-output`, `git-branch-delete-flagonly`
   and `invented-git-flag` from its collateral: with git refused before any flag check,
   disabling the flag-denylist inversion no longer flips them.
4. `test_an_invalid_utf8_allowed_command_still_passes` and
   `test_prefix_match_does_not_satisfy_the_allowlist` swap `git status` / `git diff` for
   `cat README.md` / `ruff check src/`, which are still allowed.

## Risk

- MEDIUM, behavioural: this REMOVES a permission. A parent session that spawns an
  implementer expecting it to report `git status` gets a block with a message naming the
  owner of the action. That is the intent; the ALLOWED→BLOCKED moves make it asserted.
- LOW, coverage: `_check_argv`'s `numeric_ok` parameter loses its only caller. It is a
  generic helper argument and its branch stays covered by nothing; left in place to keep
  the diff minimal, noted here so it is not mistaken for an oversight.

## Validation commands

```bash
python3 -m pytest tests/test_iron_law_hook.py -q -p no:cacheprovider
ruff check .claude/hooks/iron-law-gate.py tests/test_iron_law_hook.py
```

## Archived configs

- `.claude/plans/archive/ops-implementer-no-git/ops.json` (2 operations)
- `.claude/plans/archive/ops-implementer-no-git/ops-chains.json` (1 operation)

