---
name: rollback
description: "Roll the working tree back to a git checkpoint taken before the main session's edits"
argument-hint: "[checkpoint tag or latest]"
model: haiku
---

# Rollback Command

Restore tracked files to a checkpoint. `checkpoint-gate` tags a `git stash create` snapshot
as `ck-checkpoint/<epoch>` before the first edit of a work period (newest 20 kept); a manual
`/checkpoint save` works too. Rollback is git-based: no backup directory, no executor.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage

## Task

Rollback operation: $ARGUMENTS

## Workflow

### Phase 1: List checkpoints
- `git tag -l 'ck-checkpoint/*' --sort=-creatordate` (newest first), with each tag's
  message (`git tag -n1 -l 'ck-checkpoint/*'`). The tag message lists untracked files the
  snapshot could not contain.
- If none exist, say so and stop. Legacy `backups/<plan>-<timestamp>/` directories from the
  old operations engine can still be restored with
  `python3 .claude/operations/scripts/restore-backup.py --list` (same dry-run-first rule).

### Phase 2: Select
- Use the tag named in $ARGUMENTS, else the newest. Confirm the selection with the user.

### Phase 3: Dry-run preview (ALWAYS first)
- `git diff --stat <tag>` shows what restoring would change in tracked files.
- `git status --short` plus the tag message show files created after the checkpoint; those
  are NOT removed by a restore. List them for the user to decide on.

### Phase 4: Restore
- Only after the user confirms the preview:
  `git restore --source=<tag> --staged --worktree -- .`
- Do not delete untracked files yourself; name them and let the user remove them.
- Report what was restored.

## Safety Rules

- ALWAYS show the preview before restoring
- NEVER delete tags (`checkpoint-gate` prunes its own)
- NEVER restore without user confirmation
- NEVER use `git reset --hard` or `git clean` for a rollback
- Suggest `/verify` after a successful rollback

## Output Format

```
## Rollback Report

### Checkpoint Selected
- **Tag**: ck-checkpoint/<epoch>
- **Created**: [timestamp]

### Preview
- Tracked files that would change: [git diff --stat]
- Untracked files created since (not removed): [list]

### Result
- **Status**: COMPLETE / FAILED
- Files restored: N

### Next Steps
- Run `/verify` to validate project state
```

## Usage Examples

- `/rollback` -- List checkpoints and restore the newest
- `/rollback ck-checkpoint/1793000000` -- Restore a specific checkpoint
- `/rollback --list` -- Only list checkpoints
