# Plan: readable backup/execution history (`restore-backup.py --list`)

**Ops config:** `.claude/plans/ops-backup-history/ops-backup-history.json`
**Tier:** 1 (single script + its new test; no security, schema, or public-API surface)
**Status:** ready to execute

## Why

The ask was a read-only view of execution history over `backups/*/manifest.json`, so the
queued-ops and archive gates can read data instead of hand-kept README rows.

Reading the code first changed the shape of the work twice:

1. **`--list` already exists** and already walks every manifest (`restore-backup.py:355`).
   The gap is what it prints, not that it is missing. So this is an enrichment of one
   command, not a new script — the repo is consolidating (task 008) and does not need a
   17th operations script for something `--list` is already 80% of.

2. **`--list` has a bug, in the exact function the feature depends on.** `list_backups`
   (`:294`) returns `sorted(backups, reverse=True)` — directory names — under a comment
   calling that "load-bearing" and chronological because the executor names backups
   `<plan>-<YYYYmmdd>-<HHMMSS>-<micros>`. A lexicographic sort over that form orders by
   **plan slug first**, and only then by time. It is chronological only within one plan.

   Measured on this repo's 101 backups:

   ```
   name order says newest:  reflection-receipt-self-describing-20260905-110635-383541
   actually newest:         claude-md-floor-trim3-20260905-175126-628683   (+6h45m)
   ```

   `--list` prints "Available backups... most recent first". Anyone reaching for the
   latest backup to restore was handed the alphabetically-last plan. Shipping a history
   view on top of that ordering would ship the bug in a second place, so it is fixed here.

## Changes

`.claude/operations/scripts/restore-backup.py` (5 edits):

- `load_backups()` — new. Returns `[(path, manifest_or_None)]` ordered by the `timestamp`
  **inside** each manifest, name order as tie-break. An unparseable manifest yields `None`
  rather than dropping the row, and sorts last (an undatable backup must never be offered
  as "the latest"). `list_backups()` keeps its signature and delegates — one caller.
- `--list` output gains: plan slug, `N modified, M created`, and `Complete: yes/no` from
  `post_state`. Absent `post_state` means the executor died mid-run, which is the backup
  someone scanning this list is usually hunting for.
- `--list --json` — new flag. The rows as JSON, emitted with no banner so it pipes.
  This is the machine-readable half the gates need.
- Module docstring + epilog updated to name the new usage.

`tests/test_backup_history.py` (new, 11 tests): ordering, the pairing, unreadable
manifests, a manifest-less directory, a missing tree, both `--list` renderings, `--json`
parseability and fields, and that `--backup` is still required without `--list`.

`CHANGELOG.md`: two `[Unreleased]` entries (the ordering fix, the reporting change).

## Proof

`test_newest_first_is_by_time_not_by_name` is the binding test: its two fixtures give the
**older** backup the alphabetically-later slug, so name order and time order disagree.
Restore `sorted(backups, reverse=True)` and it fails. It carries its own vacuity guard
asserting the fixtures actually disagree — a fixture where both orders agree cannot tell
the two implementations apart, which is how the original bug survived having a `--list`.

Mutation proof to run after execution: revert `list_backups` to the name sort and confirm
that test reds.

## Rollback

`python3 .claude/operations/scripts/restore-backup.py --backup backups/backup-history-<ts>`
— or `--list` to find it, which after this change actually names the right one.

## Not doing

No changes to the queued-ops or archive gates themselves. This makes the data readable;
rewiring those gates to consume it is a separate, larger change and stays owner-gated.
