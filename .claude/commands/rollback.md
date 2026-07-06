---
name: rollback
description: "Rollback the last applied operations config from backup"
argument-hint: "[backup-name or latest]"
model: haiku
---

# Rollback Command

Restore files from a previous backup created by the operations execution engine.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage

## Task

Rollback operation: $ARGUMENTS

## Script Reference

This command uses the restore-backup.py script located at:
`.claude/operations/scripts/restore-backup.py`

## Workflow

### Phase 1: List Available Backups
- Run `python3 .claude/operations/scripts/restore-backup.py --list` to show available backups
- Display each backup with its timestamp and file count
- If no backups exist, report this clearly and stop

### Phase 2: Select Backup
- If the user specifies a backup name in $ARGUMENTS, use that backup
- If no backup is specified, present the list and use the most recent backup
- Confirm the selected backup with the user before proceeding

### Phase 3: Dry Run Preview
- ALWAYS run a dry run first before executing the actual restore
- Execute: `python3 .claude/operations/scripts/restore-backup.py --backup <path> --dry-run`
- Display which files would be restored and which would be removed
- Ask for user confirmation to proceed

### Phase 4: Execute Restore
- Only after user confirms the dry run results
- Execute: `python3 .claude/operations/scripts/restore-backup.py --backup <path> --force`
- The `--force` flag skips the script's interactive prompt since the user already confirmed in Phase 3
- Report the results

## Safety Rules

- ALWAYS show the dry run before executing the actual restore
- NEVER delete backup directories (the script preserves them automatically)
- NEVER run the restore without user confirmation
- If the restore fails partway through, report which files were restored and which were not
- Suggest running `/verify` after a successful rollback to validate project state

## Output Format

```
## Rollback Report

### Backup Selected
- **Path**: [backup directory]
- **Timestamp**: [when the backup was created]
- **Files**: N files to restore, M files to remove

### Dry Run Results
- Files to restore: [list]
- Files to remove: [list]

### Execution Results
- **Status**: COMPLETE / PARTIAL / FAILED
- Files restored: N
- Files removed: N

### Next Steps
- Run `/verify` to validate project state
- The backup is preserved at: [path]
```

## Usage Examples

- `/rollback` -- List backups and restore the most recent one
- `/rollback my-plan-20240101-120000` -- Restore a specific backup
- `/rollback --list` -- Only list available backups without restoring
- `/rollback --dry-run` -- Preview the most recent rollback without executing

## Notes

- Backups are created automatically when operations are executed via ops.json
- The restore script has 12 safety guards including path traversal protection
- Backups are never deleted by the restore process
- If no backups exist, suggest checking the backups/ directory manually
