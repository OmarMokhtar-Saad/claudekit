#!/usr/bin/env python3
"""
execute-json-ops.py - Execute JSON operations config (v3.0)

Purpose: Execute file create, delete, and code edit operations
Usage: python3 scripts/execute-json-ops.py path/to/ops.json [--dry-run]

Supports Two Formats:
  - LEGACY: {"plan": "...", "files": [...]} - Code edits only
  - MODERN: {"plan": "...", "operations": [...]} - file_create, file_delete, code_edit

Features:
  - Auto-detects format and normalizes to modern format internally
  - Automatic backup before all operations (including deleted files)
  - Backup manifest generation (compatible with restore-backup.py)
  - Dry-run mode with diff preview for code edits (state threaded across operations)
  - Fail-closed edits: a missing or ambiguous anchor aborts before any write
  - First-write-wins backups so rollback always restores pristine content
  - Transactional execution with automatic rollback on failure
  - Machine-readable RESULT-JSON summary line on config load/normalize error, lock contention, manifest failure, operation failure, crash, and signal
  - Execution lock to prevent concurrent runs
"""

import argparse
import difflib
import json
import logging
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shared import PROTECTED_PATTERNS, is_protected_file, allowed_run_commands, __version__

# run_command execution bounds (validator enforces the same schema limits)
RUN_COMMAND_DEFAULT_TIMEOUT = 120
RUN_COMMAND_MAX_TIMEOUT = 600

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

LOCK_FILE = ".codemanifest.lock"

# Reserved by the backup manifest at the backup root. A project file with this
# name at the project root would map onto the same backup path, so it is
# refused rather than silently corrupting the recovery manifest.
MANIFEST_NAME = "manifest.json"

# Global transaction reference for signal handler rollback
_active_txn: Optional['OperationTransaction'] = None

# Run context for out-of-band result emission (signal handler)
_active_plan: str = "unknown"
_active_dry_run: bool = False
_active_backup_dir: Optional[str] = None

# The run summary is emitted exactly once; later handlers must not double-report
_result_emitted: bool = False


def _signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM: rollback active transaction and exit."""
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\n  Interrupted by {sig_name}")
    if _active_txn is not None:
        _active_txn.rollback()
    _emit_result(_active_plan, _active_dry_run, 'interrupted', [],
                 backup_dir=_active_backup_dir, reason=f"signal-{sig_name}")
    sys.exit(130 if signum == signal.SIGINT else 143)


def atomic_write(file_path: Path, content: str, encoding: str = 'utf-8'):
    """Write content to file atomically via temp file + rename."""
    dir_path = file_path.parent
    tmp_path = None
    fd = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix='.tmp')
        with os.fdopen(fd, 'w', encoding=encoding) as f:
            fd = None  # os.fdopen takes ownership of fd
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(file_path))
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


class ExecutionLock:
    """File-based lock to prevent concurrent executor runs.

    Uses fcntl.flock on Unix. On Windows (where fcntl is unavailable),
    falls back to a simple lock file with no blocking detection.
    """

    def __init__(self, lock_path: str = LOCK_FILE):
        self.lock_path = lock_path
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        try:
            self._fd = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            if _HAS_FCNTL:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(self._fd, f"{os.getpid()}\n".encode())
            return True
        except (OSError, IOError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            return False

    def release(self):
        if self._fd is not None:
            try:
                if _HAS_FCNTL:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except (OSError, IOError):
                pass
            self._fd = None
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(
                f"Another CodeManifest executor is running (lock: {self.lock_path}).\n"
                "Wait for it to finish or remove the lock file if stale."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class OperationTransaction:
    """Track executed operations for transactional rollback."""

    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self._modified_files: List[str] = []
        self._created_files: List[str] = []

    def record_modified(self, file_path: str):
        self._modified_files.append(file_path)

    def record_created(self, file_path: str):
        self._created_files.append(file_path)

    def rollback(self):
        print("\n  ROLLBACK: Restoring files from backup...")
        for fp in self._modified_files:
            rel = Path(os.path.relpath(fp))
            bp = self.backup_dir / rel
            if bp.exists():
                try:
                    shutil.copy2(str(bp), fp)
                    print(f"  Restored: {fp}")
                except Exception as e:
                    print(f"  Warning: Failed to restore {fp}: {e}")
        for fp in self._created_files:
            if os.path.exists(fp):
                try:
                    os.unlink(fp)
                    print(f"  Removed: {fp}")
                except Exception as e:
                    print(f"  Warning: Failed to remove {fp}: {e}")
        print("  ROLLBACK COMPLETE")

    @property
    def modified_files(self) -> List[str]:
        return list(self._modified_files)

    @property
    def created_files(self) -> List[str]:
        return list(self._created_files)


def validate_path(file_path: str) -> bool:
    """
    Validate file path for safety.
    Rejects path traversal, null bytes, and paths resolving outside project root.
    Always resolves the full path (including symlinked parent directories).

    NOTE: The canonical, richer implementation is
    ``claudekit.security.PathGuard`` (src/claudekit/security/path_guard.py).
    This inline copy is kept deliberately dependency-free so ops scripts run in
    target projects that installed via ``install.sh`` without ``pip install
    claudekit``. Keep the two in sync when changing path-safety semantics.
    """
    if '\x00' in file_path:
        print(f"  BLOCKED: Path contains null bytes: {file_path!r}")
        return False
    rel = os.path.relpath(file_path)
    if rel.startswith('..'):
        print(f"  BLOCKED: Path traversal detected: {file_path}")
        return False
    # Always resolve the full real path to catch symlinked parent directories
    resolved = os.path.realpath(file_path)
    cwd = os.path.realpath(os.getcwd())
    if resolved != cwd and not resolved.startswith(cwd + os.sep):
        print(f"  BLOCKED: Path resolves outside project: {file_path} -> {resolved}")
        return False
    return True


def normalize_config(config: dict) -> dict:
    """
    Convert legacy format to modern format for unified processing.

    Legacy: {"plan": "...", "files": [...]}
    Modern: {"plan": "...", "operations": [{"type": "code_edit", ...}]}

    Returns None if the config is malformed.
    """
    if 'operations' in config:
        return config

    operations = []
    for file_op in config.get('files', []):
        if not isinstance(file_op, dict):
            print(f"Error: Invalid file entry (expected object): {file_op!r}")
            return None
        if 'path' not in file_op or 'edits' not in file_op:
            print(f"Error: Legacy file entry missing 'path' or 'edits': {file_op!r}")
            return None
        operations.append({
            'type': 'code_edit',
            'path': file_op['path'],
            'edits': file_op['edits']
        })

    return {
        'plan': config.get('plan', 'unknown'),
        'operations': operations
    }


def _sha256_file(path: str) -> Optional[str]:
    """sha256 of a file's bytes, or None if unreadable."""
    import hashlib
    try:
        digest = hashlib.sha256()
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(65536), b''):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    except OSError:
        return None


def verify_baseline(baseline: dict) -> List[str]:
    """Compare each baseline-recorded file hash against disk.

    Returns a drift message per mismatched file. A file that changed since the
    plan was stamped means the plan was authored against a state that no longer
    exists (concurrent session, external git checkout/restore, manual edit) —
    applying edits on top of it risks compounding the damage.
    """
    drift: List[str] = []
    for rel, expected in sorted(baseline.items()):
        if not isinstance(rel, str) or not isinstance(expected, str):
            drift.append(f"baseline entry malformed: {rel!r}")
            continue
        actual = _sha256_file(rel)
        if actual is None:
            drift.append(f"{rel}: MISSING (was {expected[:19]}...) — file deleted or moved "
                         "since the plan was stamped")
        elif actual != expected:
            drift.append(f"{rel}: CHANGED since the plan was stamped "
                         f"(expected {expected[:19]}..., found {actual[:19]}...)")
    return drift


def snapshot_post_state(backup_dir: Path, rel_paths: List[str]) -> bool:
    """Snapshot the post-execution state of touched files under backup_dir/post/.

    The pre-execution backup enables rollback; this enables FORWARD recovery —
    if an external actor (concurrent session, stray git restore) later wipes a
    file, `restore-backup.py --post` restores the completed result instead of
    forcing a replay of every ops config that built it.
    """
    post_dir = backup_dir / "post"
    try:
        for rel in rel_paths:
            if not os.path.isfile(rel):
                continue  # deleted by the plan — nothing to checkpoint
            dest = post_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rel, str(dest))
        manifest_path = backup_dir / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['post_state'] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return True
    except (OSError, ValueError) as e:
        print(f"  Warning: post-state checkpoint failed ({e}) — rollback backups intact")
        return False


def create_manifest(backup_dir: Path, plan_name: str, files_to_backup: List[str], files_to_create: List[str]) -> bool:
    """Create manifest.json for backup compatibility with restore-backup.py.

    Returns:
        True if manifest was created successfully, False otherwise.
    """
    manifest = {
        'plan': plan_name,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'files': files_to_backup,
        'created_files': files_to_create
    }

    manifest_path = backup_dir / MANIFEST_NAME
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        print(f"  Manifest: {manifest_path}")
        return True
    except Exception as e:
        print(f"  Error: Could not create manifest: {e}")
        print("  Aborting execution — backup manifest is required for safe recovery.")
        return False


def show_diff(file_path: str, original: str, modified: str):
    """Show unified diff between original and modified content."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines, modified_lines,
        fromfile=f"a/{file_path}", tofile=f"b/{file_path}",
        lineterm=''
    )
    diff_lines = list(diff)
    if diff_lines:
        print("  --- Diff preview ---")
        for line in diff_lines[:50]:
            print(f"  {line.rstrip()}")
        if len(diff_lines) > 50:
            print(f"  ... ({len(diff_lines) - 50} more lines)")
        print("  --- End diff ---")


def _emit_result(plan_name: str, dry_run: bool, status: str, operations: list,
                 backup_dir: Optional[str] = None, reason: str = "") -> None:
    """Print the machine-readable run summary consumed by the Implementer.

    Emitted on config load/normalize errors, lock contention, manifest failure,
    operation failure, crashes and signals. Absence means the process never
    reached a reported exit path — killed outright (SIGKILL/OOM), or failed
    before execution began (e.g. bad CLI arguments) — so the working tree must
    be treated as unknown.

    Idempotent: only the FIRST call reports. A crash inside the operation loop
    emits there and then re-raises through outer handlers, which must not
    overwrite that verdict with a less specific one.
    """
    global _result_emitted
    if _result_emitted:
        return
    _result_emitted = True
    payload: Dict[str, object] = {
        'plan': plan_name,
        'mode': 'dry-run' if dry_run else 'execute',
        'status': status,
        'operations': operations,
        'backup_dir': backup_dir,
    }
    if reason:
        payload['reason'] = reason
    print("RESULT-JSON: " + json.dumps(payload))


def execute_run_command(operation: dict, dry_run: bool) -> Tuple[bool, str]:
    """Execute an allowlisted generator/formatter command.

    Security contract (mirrors validator GUARDs 30-34, re-checked here as
    defense in depth — the executor must be safe even on an unvalidated config):
    argv array with shell=False (no shell ever spawns), argv[0] must be an
    allowlisted bare basename, no absolute/'..' arguments, bounded timeout,
    cwd pinned to the project root. NOT rolled back by the transaction —
    the validator orders these after all file operations.
    """
    command = operation.get('command')
    reason = operation.get('reason', '')

    if not isinstance(command, list) or not command or \
            not all(isinstance(a, str) and a for a in command):
        print("  ERROR: 'command' must be a non-empty argv array of strings")
        return False, "invalid-argv"

    executable = command[0]
    if os.sep in executable or (os.altsep and os.altsep in executable):
        print(f"  BLOCKED: executable must be a bare basename, not a path: {executable!r}")
        return False, "executable-is-path"
    if executable not in allowed_run_commands():
        print(f"  BLOCKED: '{executable}' is not an allowlisted command")
        print(f"  Allowed: {', '.join(sorted(allowed_run_commands()))}")
        return False, "not-allowlisted"
    for arg in command[1:]:
        if os.path.isabs(arg) or '..' in arg.split(os.sep):
            print(f"  BLOCKED: argument escapes the project root: {arg!r}")
            return False, "argument-escapes-root"

    timeout = operation.get('timeout', RUN_COMMAND_DEFAULT_TIMEOUT)
    if not isinstance(timeout, int) or timeout < 1:
        timeout = RUN_COMMAND_DEFAULT_TIMEOUT
    timeout = min(timeout, RUN_COMMAND_MAX_TIMEOUT)

    print(f"  Command: {' '.join(command)}")
    print(f"  Reason: {reason}")

    if dry_run:
        print(f"  [DRY RUN] Would run (timeout {timeout}s) — not executed")
        return True, "dry-run"

    try:
        result = subprocess.run(
            command, shell=False, cwd=os.getcwd(),
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        print(f"  ERROR: executable not found on PATH: {executable}")
        return False, "executable-not-found"
    except subprocess.TimeoutExpired:
        print(f"  ERROR: command timed out after {timeout}s and was killed")
        return False, "timeout"

    tail = (result.stdout + result.stderr).strip().splitlines()[-10:]
    for line in tail:
        print(f"    {line}")
    if result.returncode != 0:
        print(f"  ERROR: command exited {result.returncode}")
        return False, f"exit-{result.returncode}"
    print(f"  Command succeeded (exit 0)")
    return True, "ran"


def execute_file_create(operation: dict, backup_dir: Path, dry_run: bool,
                        sim_state: Optional[Dict[str, Optional[str]]] = None) -> Tuple[bool, str]:
    """Create new file with specified content."""
    file_path = Path(operation['path'])
    content = operation['content']

    if not validate_path(str(file_path)):
        return False, "path-validation-failed"

    byte_size = len(content.encode('utf-8'))

    if dry_run:
        print(f"  [DRY RUN] Would create: {file_path}")
        print(f"            Size: {byte_size} bytes, Lines: {content.count(chr(10)) + 1}")
        if sim_state is not None:
            sim_state[os.path.relpath(str(file_path))] = content
        return True, "dry-run"

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(file_path, content)
        print(f"  Created: {file_path}")
        print(f"  Size: {byte_size} bytes, Lines: {content.count(chr(10)) + 1}")
        return True, "created"
    except Exception as e:
        print(f"  Error creating file: {e}")
        return False, str(e)


def execute_file_delete(operation: dict, backup_dir: Path, dry_run: bool,
                        sim_state: Optional[Dict[str, Optional[str]]] = None,
                        backed_up: Optional[set] = None) -> Tuple[bool, str]:
    """Back up then delete specified file."""
    file_path = Path(operation['path'])
    reason = operation.get('reason', '')

    if not validate_path(str(file_path)):
        return False, "path-validation-failed"

    # Check protected file patterns
    if is_protected_file(str(file_path)):
        print(f"  BLOCKED: Cannot delete protected file: {file_path}")
        return False, "protected-file"

    # Refused in BOTH modes, so dry-run cannot report a clean plan that execution
    # would then reject — see execute_code_edit for why the name is reserved.
    rel_key = os.path.relpath(str(file_path))
    if rel_key == MANIFEST_NAME:
        print(f"  BLOCKED: a project-root {MANIFEST_NAME} collides with the engine's"
              " backup manifest; back it up manually and run this op separately.")
        return False, "manifest-name-collision"

    if dry_run:
        print(f"  [DRY RUN] Would delete: {file_path}")
        print(f"            Reason: {reason}")
        if file_path.exists():
            print(f"            Size: {file_path.stat().st_size} bytes")
        if sim_state is not None:
            sim_state[os.path.relpath(str(file_path))] = None
        return True, "dry-run"

    if not file_path.exists():
        print(f"  File already deleted: {file_path}")
        return True, "already-deleted"

    # Backup before deletion. First write wins — see execute_code_edit.
    try:
        rel_path = Path(os.path.relpath(file_path))
        backup_path = backup_dir / rel_path
        if backed_up is not None and rel_key in backed_up:
            print(f"  Backup already captured this run: {backup_path}")
        else:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(file_path), str(backup_path))
            if backed_up is not None:
                backed_up.add(rel_key)
            print(f"  Backed up to: {backup_path}")
    except Exception as e:
        print(f"  Error backing up file before deletion: {e}")
        print("  Aborting delete — cannot proceed without backup.")
        return False, str(e)

    try:
        file_size = file_path.stat().st_size
        file_path.unlink()

        print(f"  Deleted: {file_path}")
        print(f"  Reason: {reason}")
        print(f"  Freed: {file_size} bytes")
        return True, "deleted"
    except Exception as e:
        print(f"  Error deleting file: {e}")
        return False, str(e)


def execute_code_edit(operation: dict, backup_dir: Path, dry_run: bool,
                      sim_state: Optional[Dict[str, Optional[str]]] = None,
                      backed_up: Optional[set] = None) -> Tuple[bool, str]:
    """Apply find-replace edits to existing file.

    Fails closed: a missing or ambiguous anchor aborts the operation before any
    write, so the caller can roll the whole batch back.

    In dry-run mode, sim_state threads each file's simulated content across
    operations so the preview matches real sequential execution.
    """
    file_path = Path(operation['path'])
    edits = operation.get('edits', [])

    if not validate_path(str(file_path)):
        return False, "path-validation-failed"

    rel_key = os.path.relpath(str(file_path))

    sim_content: Optional[str] = None
    if dry_run and sim_state is not None and rel_key in sim_state:
        sim_content = sim_state[rel_key]
        if sim_content is None:
            print(f"  File deleted by an earlier operation: {file_path}")
            return False, "file-not-found"

    if sim_content is None and not file_path.exists():
        print(f"  File not found: {file_path}")
        return False, "file-not-found"


    # A project-root manifest.json maps onto the engine's own backup manifest.
    # Refuse rather than corrupt the file restore-backup.py depends on.
    if rel_key == MANIFEST_NAME:
        print(f"  BLOCKED: a project-root {MANIFEST_NAME} collides with the engine's"
              " backup manifest; back it up manually and run this op separately.")
        return False, "manifest-name-collision"

    # Backup original (preserve directory structure).
    #
    # FIRST WRITE WINS: when a later operation touches a file an earlier
    # operation already modified, re-copying would overwrite the pristine
    # backup with mutated content — and a subsequent rollback would then
    # "restore" that intermediate state, silently losing the original.
    # Membership is tracked in a run-scoped set rather than probed on disk,
    # so nothing the engine itself writes into backup_dir can be mistaken
    # for an already-captured backup.
    if not dry_run:
        try:
            rel_path = Path(os.path.relpath(file_path))
            backup_path = backup_dir / rel_path
            if backed_up is not None and rel_key in backed_up:
                print(f"  Backup already captured this run: {backup_path}")
            else:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(file_path), str(backup_path))
                if backed_up is not None:
                    backed_up.add(rel_key)
                print(f"  Backed up to: {backup_path}")
        except Exception as e:
            print(f"  Error backing up file: {e}")
            print("  Aborting edit — cannot proceed without backup.")
            return False, str(e)

    try:
        if sim_content is not None:
            content = sim_content
        else:
            content = file_path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        print(f"  Error: File appears to be binary or non-UTF-8: {file_path}")
        return False, "binary-or-non-utf8"
    except OSError as e:
        print(f"  Error reading file: {e}")
        return False, str(e)

    modified_content = content
    edits_applied = 0

    for j, edit in enumerate(edits, 1):
        find_pattern = edit.get('find', '')

        if not find_pattern:
            print(f"  Edit {j}: FAILED - No 'find' pattern specified")
            logger.warning("Edit %d for %s has no find pattern", j, file_path)
            return False, "missing-find-pattern"

        occurrences = modified_content.count(find_pattern)
        if occurrences == 0:
            print(f"  Edit {j}: FAILED - Pattern not found "
                  "(may have been changed by a previous edit)")
            logger.warning("Anchor missing at edit %d for %s", j, file_path)
            return False, "pattern-not-found"
        if occurrences > 1:
            print(f"  Edit {j}: FAILED - Pattern appears {occurrences} times "
                  "in current content (ambiguous match)")
            logger.warning("Ambiguous anchor (%d matches) at edit %d for %s",
                           occurrences, j, file_path)
            return False, "ambiguous-pattern"

        if 'add_after' in edit:
            modified_content = modified_content.replace(
                find_pattern, find_pattern + edit['add_after'], 1
            )
            print(f"  Edit {j}: Added {len(edit['add_after'])} chars after pattern")
            edits_applied += 1

        elif 'add_before' in edit:
            modified_content = modified_content.replace(
                find_pattern, edit['add_before'] + find_pattern, 1
            )
            print(f"  Edit {j}: Added {len(edit['add_before'])} chars before pattern")
            edits_applied += 1

        elif 'replace' in edit:
            modified_content = modified_content.replace(
                find_pattern, edit['replace'], 1
            )
            print(f"  Edit {j}: Replaced pattern with {len(edit['replace'])} chars")
            edits_applied += 1

        elif edit.get('delete') is True:
            modified_content = modified_content.replace(find_pattern, '', 1)
            print(f"  Edit {j}: Deleted pattern")
            edits_applied += 1

        else:
            print(f"  Edit {j}: FAILED - No action specified "
                  "(add_after, add_before, replace, delete)")
            logger.warning("Edit %d for %s specifies no action", j, file_path)
            return False, "no-action-specified"

    byte_size = len(modified_content.encode('utf-8'))

    if dry_run:
        print(f"  [DRY RUN] Would write {byte_size} bytes to: {file_path}")
        if content != modified_content:
            show_diff(str(file_path), content, modified_content)
        if sim_state is not None:
            sim_state[rel_key] = modified_content
        return True, "dry-run"
    else:
        try:
            atomic_write(file_path, modified_content)
            print(f"  Written {byte_size} bytes, {edits_applied}/{len(edits)} edits applied")
            show_diff(str(file_path), content, modified_content)
            return True, "edited"
        except Exception as e:
            print(f"  Error writing file: {e}")
            return False, str(e)


APPROVAL_SCRIPT = Path(__file__).resolve().parent / "review-record.py"

# Directory name that marks an ops.json as a pipeline artifact (/plan writes
# .claude/plans/<name>.ops.json). Configs there always need a verdict.
PLANS_DIR_NAMES = ("plans",)

# Opt-in blanket enforcement: gate EVERY config, not just the pipeline-shaped
# ones. This is the fail-closed default we want; it is not yet the default only
# because ad-hoc callers (tooling, worktree runs, the executor's own test
# suites) execute configs that never went through /review. Set this in CI or
# settings once those callers are updated, then flip the default here.
GATE_ALL_ENV = "ECC_OPS_GATE_ALL"


def _project_plans_dirs() -> List[Path]:
    """Plans directories to probe for a sibling plan.md, nearest .claude first."""
    dirs: List[Path] = []
    cur = Path.cwd()
    for candidate in (cur, *cur.parents):
        if (candidate / ".claude").is_dir():
            dirs.append(candidate / ".claude" / "plans")
            break
    return dirs


def _approval_slugs(config_file: str, plan_name: str) -> List[str]:
    """Candidate review-record slugs for an ops.json.

    review-record.py resolves plan.md -> ops.json; the executor is handed the
    ops.json and must invert that. Every filename form resolve_ops() emits
    (plan-x.ops.json, ops-x.json, x.ops.json, x.json) is inverted here, and the
    config's own "plan" field is tried too so renaming or moving the file does not
    silently detach it from the verdict that approved it.
    """
    slugs: List[str] = []
    name = Path(config_file).name
    if name.endswith(".ops.json"):
        base = name[:-len(".ops.json")]
    elif name.endswith(".json"):
        base = name[:-len(".json")]
    else:
        base = name
    for candidate in (base, plan_name):
        text = (candidate or "").strip()
        for prefix in ("plan-", "ops-"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        if text and text not in slugs:
            slugs.append(text)
    return slugs


def _load_review_record():
    """Import review-record.py by path (its filename is not an importable name).

    Reusing its record_paths/cmd_check keeps ONE implementation of the drift and
    threshold rules; a second copy here would drift from the source of truth.

    Coupling worth stating: the module is intentionally NOT registered in
    sys.modules. That is safe only while review-record.py stays stdlib-only and
    self-contained (it is). Anything that resolves its own module by name (some
    decorators, dataclasses with string annotations, pickling) would raise here —
    and the gate then fails CLOSED on every pipeline config, which is loud, not
    silent, but would need this line revisited.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("review_record", str(APPROVAL_SCRIPT))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gate_applies(config_file: str, slugs: List[str]) -> Tuple[bool, str]:
    """Decide whether this config must carry a verdict, and say why.

    Populations gated: everything when ECC_OPS_GATE_ALL=1; configs sitting in a
    plans/ directory; configs whose slug already has a review record (a copy or
    rename cannot shed a verdict); and configs whose slug owns a plan.md, either
    beside the config or in the project's .claude/plans (so writing the config to
    /tmp does not detach it from the plan it implements).
    """
    if os.environ.get(GATE_ALL_ENV) == "1":
        return True, f"{GATE_ALL_ENV}=1"
    if Path(config_file).resolve().parent.name in PLANS_DIR_NAMES:
        return True, "config lives in a plans/ directory"
    search_dirs = [Path(config_file).resolve().parent, *_project_plans_dirs()]
    for slug in slugs:
        for directory in search_dirs:
            for candidate in (f"plan-{slug}.md", f"{slug}.md"):
                if (directory / candidate).is_file():
                    return True, f"a plan document exists for slug '{slug}'"
    return False, ""


def check_approval(config_file: str, plan_name: str) -> Tuple[bool, str]:
    """Refuse to mutate anything unless this exact ops.json carries an APPROVED verdict.

    Fails CLOSED: an unreadable, missing or unusable review-record.py refuses a
    gated config rather than waving it through.
    """
    slugs = _approval_slugs(config_file, plan_name)

    try:
        module = _load_review_record()
    except Exception as e:
        module = None
        print(f"  Could not load {APPROVAL_SCRIPT}: {e}")
    if module is None or not all(hasattr(module, attr)
                                 for attr in ("record_paths", "cmd_check")):
        gated, why = _gate_applies(config_file, slugs)
        if gated:
            return False, f"approval-gate: review-record.py unusable ({why})"
        return True, ""

    try:
        recorded = [s for s in slugs if module.record_paths(s)[0].exists()]
    except Exception as e:
        return False, f"approval-gate: record lookup failed: {e}"

    gated, why = _gate_applies(config_file, slugs)
    if not recorded and not gated:
        return True, ""
    if recorded:
        why = why or f"a review record exists for slug '{recorded[0]}'"

    slug = recorded[0] if recorded else (slugs[0] if slugs else "unknown")
    try:
        code = module.cmd_check(argparse.Namespace(plan=f"plan-{slug}.md", ops=config_file))
    except Exception as e:
        # Includes an argparse.Namespace shape mismatch if review-record.py's
        # cmd_check ever grows a required attribute: refuse, never assume.
        return False, f"approval-gate: check raised: {e}"
    if code != 0:
        return False, f"approval-gate: review-record check exit {code} (slug '{slug}'; {why})"
    return True, ""


def execute_json_config(config_file: str, dry_run: bool = False,
                        require_approval: bool = True) -> bool:
    """
    Execute JSON operations config.

    Args:
        config_file: Path to JSON config file
        dry_run: If True, preview changes without applying

    Returns:
        True if all operations succeeded
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        _emit_result('unknown', dry_run, 'failed', [], reason=f"config-load-error: {e}")
        return False

    config = normalize_config(raw_config)
    if config is None:
        _emit_result('unknown', dry_run, 'failed', [], reason="config-normalize-failed")
        return False
    plan_name = config.get('plan', 'unknown')
    operations = config.get('operations', [])
    config_format = "MODERN" if 'operations' in raw_config else "LEGACY"

    print(f"Plan: {plan_name}")
    print(f"Format: {config_format}")
    print(f"Operations: {len(operations)}")

    # Approval gate: a reviewer verdict that nothing consults is not a gate. The
    # check lives here, in the only code path that can mutate the tree, rather
    # than in prose an agent may skip. Dry-run is exempt: it writes nothing (no
    # backup dir, no manifest, no edits) and is the pre-review sanity check the
    # /plan and /implement workflows run before a record can exist.
    if not require_approval:
        print("Approval: BYPASSED (--no-approval)")
        print("!!! APPROVAL GATE BYPASSED (--no-approval): executing an ops.json that no "
              "reviewer verdict authorises.", file=sys.stderr)
    elif dry_run:
        print("Approval: not required for --dry-run (nothing is written)")
    else:
        approved, approval_reason = check_approval(config_file, plan_name)
        if not approved:
            print("\nAPPROVAL GATE: refusing to execute — this ops.json is not bound to an "
                  "APPROVED review record.")
            print(f"  {approval_reason}")
            print("  Run /review for this plan (or re-run it if the ops.json changed after")
            print("  approval), then retry. --no-approval bypasses this gate and exists only")
            print("  for bootstrap and repo-maintenance runs you are authorised to make.")
            _emit_result(plan_name, dry_run, 'failed', [], reason=approval_reason)
            return False
        print("Approval: reviewed verdict verified for this exact ops.json")

    # Baseline drift gate: refuse to apply a plan authored against file states
    # that no longer exist. Runs in dry-run too — a drifted dry-run preview is
    # equally misleading.
    baseline = raw_config.get('baseline')
    if isinstance(baseline, dict) and baseline:
        drift = verify_baseline(baseline)
        if drift:
            print(f"\nBASELINE DRIFT — {len(drift)} file(s) changed since this plan was stamped:")
            for message in drift:
                print(f"  {message}")
            print("\nRefusing to execute. Re-validate the plan against the current tree")
            print("(validate-config-json.py --stamp-baseline) or re-plan if the drift is real.")
            _emit_result(plan_name, dry_run, 'failed', [],
                         reason=f"baseline-drift: {len(drift)} file(s)")
            return False
        print(f"Baseline: verified ({len(baseline)} file(s) unchanged since stamping)")
    else:
        print("Baseline: none — drift since planning cannot be detected "
              "(stamp via validate-config-json.py --stamp-baseline)")

    if dry_run:
        print("DRY RUN MODE - No changes will be made\n")
    else:
        print()

    # Acquire execution lock (non-dry-run only)
    if not dry_run:
        try:
            with ExecutionLock():
                return _execute_operations(config, operations, plan_name, config_format, dry_run)
        except RuntimeError as e:
            print(f"Error: {e}")
            _emit_result(plan_name, dry_run, 'failed', [], reason=f"lock-contention: {e}")
            return False
    else:
        return _execute_operations(config, operations, plan_name, config_format, dry_run)


def _execute_operations(config: dict, operations: list, plan_name: str,
                        config_format: str, dry_run: bool) -> bool:
    """Internal execution logic, called with lock held."""
    # Publish run context first: a signal arriving during backup-dir or manifest
    # creation must still report the real plan name, not "unknown".
    global _active_plan, _active_dry_run, _active_backup_dir
    _active_plan = plan_name
    _active_dry_run = dry_run

    # Create backup directory (sanitize plan name for safe filesystem path)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    safe_plan_name = re.sub(r'[^a-zA-Z0-9_-]', '_', plan_name)
    backup_dir = Path("backups") / f"{safe_plan_name}-{timestamp}"

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        _active_backup_dir = str(backup_dir)
        print(f"Backup directory: {backup_dir}\n")

    # Collect file lists for manifest
    files_to_backup = []
    files_to_create = []

    for operation in operations:
        op_type = operation.get('type', '')
        file_path = operation.get('path', '')
        if op_type in ('code_edit', 'file_delete') and file_path:
            files_to_backup.append(os.path.relpath(file_path))
        elif op_type == 'file_create' and file_path:
            files_to_create.append(os.path.relpath(file_path))

    if not dry_run:
        if not create_manifest(backup_dir, plan_name, files_to_backup, files_to_create):
            _emit_result(plan_name, dry_run, 'failed', [],
                         reason="manifest-creation-failed")
            return False
        print()

    # Execute operations with transaction tracking
    global _active_txn
    txn = OperationTransaction(backup_dir)
    if not dry_run:
        _active_txn = txn
    success_count = 0
    error_count = 0
    stats = {'file_create': 0, 'file_delete': 0, 'code_edit': 0, 'run_command': 0}

    # Defense in depth (validator GUARD 33): run_command is not rollback-able,
    # so it must never run before a file operation that could later fail and
    # roll back around it.
    run_positions = [i for i, op in enumerate(operations) if op.get('type') == 'run_command']
    file_positions = [i for i, op in enumerate(operations)
                      if op.get('type') in ('file_create', 'file_delete', 'code_edit')]
    if run_positions and file_positions and min(run_positions) < max(file_positions):
        print("ERROR: run_command operations must come after all file operations")
        _emit_result(plan_name, dry_run, 'failed', [], reason="run-command-before-file-ops")
        return False
    sim_state: Dict[str, Optional[str]] = {}
    backed_up: set = set()
    op_results: List[Dict[str, object]] = []
    # Once the loop finishes, every operation is committed; a later failure
    # (e.g. BrokenPipeError while printing the summary) must NOT roll it back.
    loop_completed = False

    try:
        for i, operation in enumerate(operations, 1):
            op_type = operation.get('type', 'unknown')
            file_path = operation.get('path', 'unknown')

            print(f"[{i}/{len(operations)}] {op_type.upper()}: {file_path}")

            if op_type == 'file_create':
                success, status = execute_file_create(operation, backup_dir, dry_run, sim_state)
                if success:
                    stats['file_create'] += 1
                    if status == "created":
                        txn.record_created(str(file_path))
            elif op_type == 'file_delete':
                success, status = execute_file_delete(operation, backup_dir, dry_run,
                                                      sim_state, backed_up)
                if success:
                    stats['file_delete'] += 1
                    if status == "deleted":
                        txn.record_modified(str(file_path))
            elif op_type == 'code_edit':
                success, status = execute_code_edit(operation, backup_dir, dry_run,
                                                    sim_state, backed_up)
                if status == "edited":
                    txn.record_modified(str(file_path))
                if success:
                    stats['code_edit'] += 1
            elif op_type == 'run_command':
                success, status = execute_run_command(operation, dry_run)
                if success:
                    stats['run_command'] += 1
            else:
                print(f"  ERROR: Unknown operation type: {op_type!r}")
                print(f"  Valid types: file_create, file_delete, code_edit, run_command")
                print(f"  Hint: regenerate ops.json using the generate-operations-config skill")
                success, status = False, "unknown-type"

            op_results.append({
                'index': i, 'type': op_type, 'path': str(file_path),
                'success': success, 'status': status,
            })
            if success:
                success_count += 1
            else:
                error_count += 1
                if not dry_run:
                    txn.rollback()
                break

            print()

        # The batch is committed. Retire the transaction BEFORE printing anything:
        # _signal_handler rolls back whatever _active_txn still points at, so a SIGINT
        # arriving during the summary would otherwise revert a finished run — and
        # _result_emitted would then suppress the 'interrupted' verdict, leaving success
        # evidence over a reverted tree.
        _active_txn = None
        loop_completed = True

        # Forward-recovery checkpoint: snapshot the resulting state of every
        # touched file so an external wipe later is a restore, not a replay.
        if not dry_run and error_count == 0:
            if snapshot_post_state(backup_dir, files_to_backup + files_to_create):
                print(f"\nPost-state checkpoint: {backup_dir}/post/")

        # Summary
        print()
        print("-" * 50)
        print(f"{'DRY RUN COMPLETE' if dry_run else 'EXECUTION COMPLETE'}")
        print(f"Operations: {len(operations)} total")
        print(f"  file_create: {stats['file_create']}")
        print(f"  file_delete: {stats['file_delete']}")
        print(f"  code_edit:   {stats['code_edit']}")
        print(f"  run_command: {stats['run_command']}")
        if not dry_run:
            print(f"Successful: {success_count}")
            print(f"Errors:     {error_count}")
            print(f"Backups:    {backup_dir}")
        print("-" * 50)
        _emit_result(
            plan_name, dry_run,
            'success' if error_count == 0 else 'failed',
            op_results,
            backup_dir=None if dry_run else str(backup_dir),
        )

        return error_count == 0
    except Exception as e:
        # An unexpected crash must not leave partial writes on disk, and must
        # still report — the Implementer treats a missing RESULT-JSON as an
        # unknown working tree.
        #
        # Roll back ONLY if the operation loop was still running. Once it has
        # completed, every write is committed and intended; a failure while
        # printing the summary (BrokenPipeError under `| head`, for instance)
        # must not revert a successful run.
        if not dry_run and not loop_completed:
            txn.rollback()
        _emit_result(plan_name, dry_run, 'crashed', op_results,
                     backup_dir=None if dry_run else str(backup_dir),
                     reason=f"{type(e).__name__}: {e}")
        raise
    finally:
        _active_txn = None
        _active_plan = "unknown"
        _active_dry_run = False
        _active_backup_dir = None
        # NOT reset: _result_emitted must stay latched for the life of the
        # process. Clearing it here lets the outer `except RuntimeError` in
        # execute_json_config emit a second, less specific verdict over the
        # 'crashed' one — the exact double-report this flag exists to prevent.


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Execute JSON operations config (v3.0)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow (always validate first):
  1. Validate: python3 scripts/validate-config-json.py ops.json
  2. Dry run:  python3 scripts/execute-json-ops.py ops.json --dry-run
  3. Execute:  python3 scripts/execute-json-ops.py ops.json

Operation Types:
  file_create: Create new file with content
  file_delete: Delete file (backed up first, with reason required)
  code_edit:   Edit existing file (find-replace patterns)
  run_command: Run an allowlisted generator/formatter (argv array, no shell,
               reason required, ordered after all file ops, NOT rolled back)

Edit Actions:
  add_after:  Insert content after matching pattern
  add_before: Insert content before matching pattern
  replace:    Replace matching pattern with new content
  delete:     Remove matching pattern

Safety:
  - Every modified/deleted file is backed up before changes
  - Backup manifest generated for restore-backup.py compatibility
  - Dry run mode available (--dry-run)
        """
    )
    parser.add_argument('config', help='Path to JSON operations config file')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    parser.add_argument('--no-approval', action='store_true',
                        help='Bypass the review-record approval gate (loudly logged; '
                             'bootstrap and maintenance runs only)')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, force=True)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    success = execute_json_config(args.config, dry_run=args.dry_run,
                                  require_approval=not args.no_approval)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
