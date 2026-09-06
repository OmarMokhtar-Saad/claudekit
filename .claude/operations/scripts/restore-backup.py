#!/usr/bin/env python3
"""
restore-backup.py - Restore files from backup

Purpose: Restore files from a previous backup (manual recovery)
Usage: python3 scripts/restore-backup.py --backup backups/<backup_dir> [--force] [--dry-run]
       python3 scripts/restore-backup.py --list [--json]

Safety Guards (12 total):
  GUARD 1:  Backup directory existence
  GUARD 2:  Backup directory is a directory
  GUARD 3:  Manifest file existence
  GUARD 4:  Manifest parsing validation
  GUARD 5:  User confirmation (interactive)
  GUARD 6:  Target file writability
  GUARD 7:  Backup file existence
  GUARD 8:  Restoration verification
  GUARD 9:  Partial restoration handling
  GUARD 10: Backup preservation (never deletes backups)
  GUARD 11: Path traversal protection on manifest entries
  GUARD 12: Backup source path confinement
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import PurePath
from typing import List

sys.path.insert(0, os.path.dirname(__file__))
from shared import __version__


def restore_from_backup(backup_dir, force=False, dry_run=False, post=False):
    """
    Restore all files from backup directory.

    Args:
        backup_dir: Path to backup directory
        force: Skip user confirmation if True
        dry_run: Preview what would be restored without touching files
        post: Restore the POST-execution checkpoint (forward recovery after an
              external wipe) instead of the pre-execution state (rollback)

    Returns:
        True if successful
    """
    restored_files: List[str] = []

    try:
        # GUARD 1: Backup directory exists
        if not os.path.exists(backup_dir):
            print(f"Error: Backup directory does not exist: {backup_dir}")
            return False

        # GUARD 2: Path is a directory
        if not os.path.isdir(backup_dir):
            print(f"Error: Backup path is not a directory: {backup_dir}")
            return False

        # GUARD 3: Manifest file exists
        manifest_path = os.path.join(backup_dir, 'manifest.json')
        if not os.path.exists(manifest_path):
            print(f"Error: Backup manifest missing: {manifest_path}")
            print("Valid backups contain a manifest.json file")
            return False

        # GUARD 4: Manifest is valid JSON
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid manifest JSON: {e}")
            return False
        except Exception as e:
            print(f"Error: Cannot read manifest file: {e}")
            return False

        if not isinstance(manifest, dict):
            print("Error: Invalid manifest format (expected dictionary)")
            return False

        files_to_restore = manifest.get('files', [])
        created_files = manifest.get('created_files', [])

        # Forward recovery: restore the checkpointed RESULT of the run, not its
        # pre-state. The post/ snapshot covers modified AND created files;
        # nothing gets removed (that's rollback's job).
        source_root = backup_dir
        if post:
            if not manifest.get('post_state'):
                print("Error: This backup has no post-execution checkpoint "
                      "(older run, or the checkpoint failed). Use plain restore for rollback.")
                return False
            source_root = os.path.join(backup_dir, 'post')
            files_to_restore = files_to_restore + created_files
            created_files = []

        # GUARD 11: Path traversal protection on manifest entries
        cwd = os.path.realpath(os.getcwd())
        for fp in files_to_restore + created_files:
            if not isinstance(fp, str):
                print(f"Error: Invalid entry in manifest (expected string): {fp!r}")
                return False
            if os.path.isabs(fp):
                print(f"Error: Absolute path in manifest: {fp}")
                return False
            if '\x00' in fp:
                print(f"Error: Path contains null bytes in manifest: {fp!r}")
                return False
            resolved = os.path.realpath(fp)
            try:
                PurePath(resolved).relative_to(cwd)
            except ValueError:
                print(f"Error: Path traversal detected in manifest: {fp}")
                print("Manifest may have been tampered with.")
                return False

        if not files_to_restore and not created_files:
            print("Warning: Backup contains no files to restore")
            return True

        print(f"{'[DRY RUN] ' if dry_run else ''}Restoring from: {backup_dir}")
        print(f"Timestamp: {manifest.get('timestamp', 'unknown')}\n")

        if dry_run:
            print("DRY RUN MODE - No files will be changed\n")
            if files_to_restore:
                print(f"Would restore ({len(files_to_restore)}):")
                for fp in files_to_restore:
                    rel_path = os.path.relpath(fp)
                    backup_path = os.path.join(source_root, rel_path)
                    exists = "exists" if os.path.exists(backup_path) else "MISSING in backup"
                    print(f"  - {fp}  [{exists}]")
                print()
            if created_files:
                print(f"Would remove ({len(created_files)}):")
                for fp in created_files:
                    status = "exists" if os.path.exists(fp) else "already gone"
                    print(f"  - {fp}  [{status}]")
                print()
            print("-" * 40)
            print("DRY RUN COMPLETE - no changes made")
            print("-" * 40)
            return True

        # GUARD 5: User confirmation
        if not force:
            print("WARNING: This will overwrite current files!")
            print("-" * 40)

            if files_to_restore:
                print(f"Files to restore ({len(files_to_restore)}):")
                for fp in files_to_restore:
                    print(f"  - {fp}")
                print()

            if created_files:
                print(f"Files to remove ({len(created_files)}):")
                for fp in created_files:
                    print(f"  - {fp}")
                print()

            try:
                response = input("Continue with restore? (yes/no): ")
                if response.lower() not in ['yes', 'y']:
                    print("Restore cancelled")
                    return False
                print()
            except (EOFError, KeyboardInterrupt):
                print("\nRestore cancelled")
                return False

        # GUARD 6: Target file writability
        unwritable_files = [
            fp for fp in files_to_restore
            if os.path.exists(fp) and not os.access(fp, os.W_OK)
        ]
        if unwritable_files:
            print("Error: Cannot overwrite read-only files:")
            for fp in unwritable_files:
                print(f"  - {fp}")
            print("\nFix with: chmod +w <file>")
            return False

        # Restore each file (GUARD 7, 8, 9)
        restored_count = 0
        real_backup_dir = os.path.realpath(source_root)
        for file_path in files_to_restore:
            rel_path = os.path.relpath(file_path)
            backup_path = os.path.join(source_root, rel_path)

            # GUARD 12: Verify backup source stays inside backup directory
            real_backup_path = os.path.realpath(backup_path)
            try:
                PurePath(real_backup_path).relative_to(real_backup_dir)
            except ValueError:
                print(f"Error: Backup source path escapes backup directory: {backup_path}")
                return False

            # GUARD 7: Backup file exists
            if post and not os.path.exists(backup_path):
                # A file the plan deleted has no post-state snapshot — its
                # correct post-execution state is "absent", so skip it.
                print(f"  Skipped (deleted by plan): {file_path}")
                continue
            if not os.path.exists(backup_path):
                print(f"Error: Backup file missing: {backup_path}")
                if restored_files:
                    print("\nFiles restored before error:")
                    for rf in restored_files:
                        print(f"  - {rf}")
                return False

            # Create parent directory if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except Exception as e:
                    print(f"Error: Cannot create parent directory: {parent_dir} ({e})")
                    if restored_files:
                        print("\nFiles restored before error:")
                        for rf in restored_files:
                            print(f"  - {rf}")
                    return False

            # Restore file
            try:
                backup_size = os.path.getsize(backup_path)
                shutil.copy2(backup_path, file_path)

                # GUARD 8: Verify restoration
                if not os.path.exists(file_path):
                    print(f"Error: Restoration failed for: {file_path}")
                    if restored_files:
                        print("\nFiles restored before error:")
                        for rf in restored_files:
                            print(f"  - {rf}")
                    return False

                restored_size = os.path.getsize(file_path)
                if restored_size != backup_size:
                    print(f"Warning: File size mismatch after restore: {file_path}")

                print(f"  Restored: {file_path}")
                restored_files.append(file_path)
                restored_count += 1

            except Exception as e:
                print(f"Error: Failed to restore: {file_path} ({e})")
                if restored_files:
                    print("\nFiles restored before error:")
                    for rf in restored_files:
                        print(f"  - {rf}")
                return False

        # Remove created files (reverse file_create operations)
        removed_count = 0
        for file_path in created_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"  Removed: {file_path}")
                    removed_count += 1
                except Exception as e:
                    print(f"Warning: Could not remove: {file_path} ({e})")

        print()
        print("-" * 40)
        print("Restore complete!")
        print(f"Files restored: {restored_count}")
        if removed_count > 0:
            print(f"Files removed:  {removed_count}")
        print()

        # GUARD 10: Never delete backup
        print(f"Backup preserved at: {backup_dir}")
        print("Safe to delete manually if no longer needed")
        print()

        return True

    except Exception as e:
        print(f"Error during restoration: {e}")
        if restored_files:
            print("\nFiles restored before error:")
            for rf in restored_files:
                print(f"  - {rf}")
        return False


def _backup_sort_key(manifest):
    """Sort key for one backup: its manifest `timestamp`, or '' when it has none.

    '' sorts LAST under reverse=True, which is the wanted behaviour -- a backup whose
    manifest cannot be dated is not a candidate for "the latest backup".
    """
    if isinstance(manifest, dict):
        timestamp = manifest.get('timestamp')
        if isinstance(timestamp, str):
            return timestamp
    return ''


def load_backups(backup_base_dir):
    """[(path, manifest_or_None)] for every backup, most recent FIRST.

    Ordering is by the `timestamp` INSIDE manifest.json, not by directory name. The old
    implementation sorted names, justified by a comment claiming that a lexicographic sort
    over `<plan>-<YYYYmmdd>-<HHMMSS>-<micros>` is a chronological one. It is not: that form
    orders by PLAN SLUG first and only then by time. Measured on this repo's 101 backups,
    name order called `reflection-receipt-...-110635` the newest when
    `claude-md-floor-trim3-...-175126` was more than six hours later -- while `--list`
    printed "most recent first" and anyone reaching for the latest backup to restore got
    the alphabetically-last plan. Name order survives only as the tie-break.

    A manifest that will not parse yields `None` rather than dropping the row: it is still
    a backup that exists, and hiding it would hide the one row someone needs in order to
    repair it.
    """
    if not os.path.exists(backup_base_dir):
        return []

    rows = []
    for entry in os.listdir(backup_base_dir):
        backup_path = os.path.join(backup_base_dir, entry)
        manifest_path = os.path.join(backup_path, 'manifest.json')
        if not os.path.isdir(backup_path) or not os.path.exists(manifest_path):
            continue
        try:
            with open(manifest_path, 'r', encoding='utf-8') as handle:
                manifest = json.load(handle)
            if not isinstance(manifest, dict):
                manifest = None
        except Exception:
            manifest = None
        rows.append((backup_path, manifest))

    rows.sort(key=lambda row: (_backup_sort_key(row[1]), row[0]), reverse=True)
    return rows


def list_backups(backup_base_dir):
    """Backup directory paths, most recent first. `load_backups` owns the ordering."""
    return [path for path, _ in load_backups(backup_base_dir)]


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Restore files from backup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available backups, most recent first
  python3 scripts/restore-backup.py --list

  # The same history as JSON, for a gate or a script
  python3 scripts/restore-backup.py --list --json

  # Preview what would be restored (no files touched)
  python3 scripts/restore-backup.py --backup backups/my-plan-20240101-120000 --dry-run

  # Restore from specific backup (with confirmation prompt)
  python3 scripts/restore-backup.py --backup backups/my-plan-20240101-120000

  # Restore without confirmation
  python3 scripts/restore-backup.py --backup backups/my-plan-20240101-120000 --force
        """
    )

    parser.add_argument('--backup', help='Path to backup directory to restore from')
    parser.add_argument('--post', action='store_true',
                        help='Restore the post-execution checkpoint (forward recovery after '
                             'an external wipe) instead of the pre-execution state (rollback)')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--dry-run', action='store_true', help='Preview what would be restored without touching files')
    parser.add_argument('--list', action='store_true', help='List available backups')
    parser.add_argument('--json', action='store_true',
                        help='With --list, emit the backup history as JSON (machine-readable)')
    parser.add_argument('--backup-dir', default='backups', help='Base backup directory (default: backups)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    if args.list:
        rows = load_backups(args.backup_dir)

        # --json exists so the execution history can be READ by something other than a
        # person: the queued-ops and archive gates currently rely on hand-kept README rows
        # for facts the manifests already hold. Emitted alone, with no banner, so it pipes.
        if args.json:
            print(json.dumps([
                {
                    "backup": os.path.basename(path),
                    "path": path,
                    "plan": (manifest or {}).get('plan'),
                    "timestamp": (manifest or {}).get('timestamp'),
                    "files": (manifest or {}).get('files', []),
                    "created_files": (manifest or {}).get('created_files', []),
                    "post_state": (manifest or {}).get('post_state'),
                    "readable": manifest is not None,
                }
                for path, manifest in rows
            ], indent=2))
            sys.exit(0)

        print(f"Available backups in: {args.backup_dir}\n")

        if not rows:
            print("No backups found\n")
            sys.exit(0)

        for path, manifest in rows:
            print(f"  {os.path.basename(path)}")
            if manifest is None:
                print("    Error: manifest missing, unparseable, or not an object")
                print()
                continue
            print(f"    Plan:      {manifest.get('plan', 'unknown')}")
            print(f"    Timestamp: {manifest.get('timestamp', 'unknown')}")
            print(f"    Files:     {len(manifest.get('files', []))} modified, "
                  f"{len(manifest.get('created_files', []))} created")
            # post_state is stamped only after the executor finishes. Its absence marks a
            # run that died mid-flight -- which is precisely the backup someone hunting
            # through this list is usually looking for.
            print(f"    Complete:  {'yes' if manifest.get('post_state') else 'no'}")
            print()

        sys.exit(0)

    if not args.backup:
        print("Error: --backup required (or use --list to see available backups)")
        parser.print_help()
        sys.exit(1)

    success = restore_from_backup(args.backup, force=args.force, dry_run=args.dry_run,
                                  post=args.post)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
