# Implementer reference (`/implement`)

Read once before Phase 2a of `.claude/commands/implement.md`. It holds the mode rules, the subagent
brief template and the Phase 2c check list, kept out of the command file for the lint line ratchet.

## Mode rules

`/implement <plan> [--delegate | --inline]`:
- `--inline`: the main session edits (Phase 2b, the old behaviour).
- `--delegate`: always spawn `plan-implementer`.
- Neither flag = auto. A "file" is a `Files:` entry other than the plan file itself and
  `.claude/plans/INDEX.md`; a "step" is a `### Step N` heading under `## Implementation Steps`.
  Delegate when files >= 3 OR steps >= 3, else inline. Worked examples:
  - this plan = 44 files, 11 steps -> delegate (but implemented inline, the agent did not exist yet)
  - a 2-file 2-step plan -> inline
  - a 1-file 4-step plan -> delegate
- Never delegate (STOP, say why, offer `--inline`): the main session root is not the plan's worktree
  (`git rev-parse --show-toplevel` must equal the worktree path, because plan-gate resolves its root from
  the hook's cwd); STEP 0 failed; the `Agent` spawn is blocked by a hook (report the BLOCKED text, no
  retry loop); the live probe ended in branch (b) and `--delegate` was not given explicitly.
- Probe status (branch taken by the implementing session): the live probe of the role signal could not be
  run from a subagent (the new agent file is not loaded in a running session), so branch (b) applies until
  an owner-run probe recorded in `.ai/SESSION_STATE.md` says branch (a): the auto rule above is the
  intended default, but until then treat auto as inline and delegate only with `--delegate`.
- Large plans: batches of at most 5 steps or 10 files per spawn, run sequentially (edits never parallel);
  the main session verifies each batch (Phase 2c) before the next.

## Brief template

Headings follow the owner's brief guard (7 headings, each on its own line):

```
## Objective
Implement steps <S>-<T> of the approved plan <PLAN_ABS_PATH> in the worktree <WT_ABS_PATH> (branch <BRANCH>).
## Done when
Each step's "Done when" holds. These pass (the main session re-runs them): <TARGETED_TEST_COMMANDS>.
## Scope
Work only under <WT_ABS_PATH>, absolute paths. Read the plan's status block, then only lines <a>-<b> per step.
Edit only: <FILES_FOR_THESE_STEPS>. Never: any git command (commit, push, branch, stash, checkout, add),
--no-verify, `ck lint --update-baseline`, edits to .claude/reports/reviews/, settings files, the plan file,
plan-gate.globs, deleting a file not marked (delete). Anything outside the plan is a plan change: stop.
## Verify
Run only the commands above with quiet flags; quote exit code and counts verbatim. Never report COMPLETE
while a command is still running.
## Stop and ask
Ambiguous step, file not in Files:, a hook BLOCKED message, an edit that fails twice: stop, return BLOCKED
with the exact message and file:line. Do not work around a hook.
## Report
At most 300 words: COMPLETE/PARTIAL/BLOCKED; per file one line of what changed; command outputs
(exit code, counts); deviations. Do not paste diffs. Detail beyond 300 words goes to a scratch file; reply with its path.
## Original request
<the user's /implement message, whole and exact>
```

## Phase 2c: check the delegated diff (main session, small outputs only)

1. Snapshot BEFORE and AFTER the spawn, each run as `git -C <wt> rev-parse HEAD`,
   `git -C <wt> symbolic-ref --short HEAD`, `git -C <wt> stash list`, `git -C <wt> tag -l`,
   `git -C <wt> for-each-ref`. Any difference = deviation -> `/rollback`.
2. File set: the per-batch list = the `Files:` entries of the steps in this batch (not the whole
   `Files:`). Run `git -C <wt> status --porcelain --ignored`; every reported path must be in the batch
   list (or be the plan file, untouched). Tier 3: `python3 .claude/operations/scripts/review-record.py
   plan-check "$PLAN" --path "$p"` exit 0 per path. An extra path = deviation.
3. `git -C <wt> diff --stat` and `git -C <wt> diff --check`.
4. Read the diff in windows of <= 150 lines only for security- or hook-related files; never paste diffs
   into the reply.
5. One repair round: re-spawn with the findings; a second failure -> `/rollback` and report, or the user
   chooses `--inline`.
