---
name: checkpoint
description: Create, restore, and list git-based checkpoints
usage: /checkpoint [save|restore|list|delete] [name] [--message=msg]
args:
  action:
    description: "Action: save, restore, list, delete"
    required: false
    default: save
  name:
    description: Checkpoint name or ID to restore/delete
    required: false
  message:
    description: Optional description for the checkpoint
    required: false
---

# /checkpoint - Git-Based Checkpoint System

Create, restore, and manage named checkpoints using git stash. Checkpoints are recorded in `.claude/checkpoints/registry.json` with metadata for easy retrieval.

## Actions

### `save` (default)

Create a new checkpoint from the current working state.

**Algorithm:**
1. Check for uncommitted changes (staged + unstaged + untracked).
2. If no changes exist, report "nothing to checkpoint" and exit.
3. Generate a checkpoint ID: `cp-<timestamp>-<short-hash>`.
4. Generate a default name if none provided: `checkpoint-<YYYY-MM-DD-HHmmss>`.
5. Run `git stash push --include-untracked -m "checkpoint: <name> | <message>"`.
6. Immediately run `git stash apply` to restore the working state (checkpoint is non-destructive).
7. Record the checkpoint in `.claude/checkpoints/registry.json`:
   ```json
   {
     "id": "cp-1710000000-abc1234",
     "name": "checkpoint-2026-03-17-143000",
     "message": "Before refactoring auth module",
     "stash_ref": "stash@{0}",
     "timestamp": "2026-03-17T14:30:00Z",
     "branch": "feature/auth",
     "commit": "abc1234",
     "files_changed": 5,
     "files_list": ["src/auth.ts", "src/middleware.ts", "..."]
   }
   ```
8. Enforce max 20 checkpoints. If limit reached, auto-prune the oldest checkpoint.
9. Report: checkpoint ID, name, files included, stash ref.

### `restore`

Restore a previously saved checkpoint.

**Algorithm:**
1. Look up the checkpoint by name or ID in the registry.
2. If not found, list available checkpoints and exit with error.
3. Warn the user that current uncommitted changes will be replaced.
4. Find the corresponding git stash entry by matching the checkpoint message.
5. Run `git stash apply <stash_ref>` to restore the checkpoint state.
6. Report: restored checkpoint name, files restored, original timestamp.
7. Do NOT remove the checkpoint from the registry (it can be restored again).

### `list`

List all saved checkpoints.

**Algorithm:**
1. Read `.claude/checkpoints/registry.json`.
2. Display checkpoints in reverse chronological order (newest first).
3. For each checkpoint show: ID, name, message, timestamp, branch, file count.
4. Indicate which stash refs are still valid (stash entries can be lost if manually cleared).
5. Format as a table:
   ```
   ID                      | Name                        | Message              | Branch       | Files | Age
   cp-1710000000-abc1234   | checkpoint-2026-03-17-1430  | Before auth refactor | feature/auth | 5     | 2h ago
   ```

### `delete`

Remove a checkpoint from the registry and optionally drop the stash.

**Algorithm:**
1. Look up the checkpoint by name or ID.
2. If found in git stash, run `git stash drop <stash_ref>`.
3. Remove the entry from `.claude/checkpoints/registry.json`.
4. Report: deleted checkpoint name, freed stash slot.

## Registry Format

The registry file `.claude/checkpoints/registry.json` contains:

```json
{
  "version": 1,
  "max_checkpoints": 20,
  "checkpoints": [
    {
      "id": "cp-<timestamp>-<short-hash>",
      "name": "<user-provided or auto-generated>",
      "message": "<description>",
      "stash_ref": "stash@{N}",
      "timestamp": "<ISO 8601>",
      "branch": "<branch name>",
      "commit": "<commit short hash>",
      "files_changed": 0,
      "files_list": []
    }
  ]
}
```

## Auto-Prune

When the checkpoint count exceeds 20:
1. Sort checkpoints by timestamp ascending (oldest first).
2. Delete the oldest checkpoint (drop stash + remove registry entry).
3. Repeat until count is at or below 20.
4. Report pruned checkpoints to the user.

## Behavior

1. Parse the action and arguments.
2. Ensure `.claude/checkpoints/` directory exists; create if needed.
3. Ensure `registry.json` exists; initialize with empty structure if needed.
4. Execute the requested action.
5. On any git error, report the error clearly and suggest manual recovery steps.
6. The `--checkpoint` universal flag triggers `save` automatically before command execution.
