#!/usr/bin/env python3
"""
validate-config-json.py - Validate JSON operations config (v2.0)

Purpose: Check JSON operations config for errors before execution
Usage: python3 scripts/validate-config-json.py path/to/ops.json

Supports Two Formats:
  - LEGACY: {"plan": "...", "files": [...]} - Code edits only
  - MODERN: {"plan": "...", "operations": [...]} - file_create, file_delete, code_edit

Validation Guards: 29 total
  - 11 guards for code editing
  - 7 guards for file operations (create/delete)
  - 6 guards for backup/restore compatibility
  - 5 guards for security (null bytes, file size, operation type)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

from shared import PROTECTED_PATTERNS, MAX_FILE_SIZE_BYTES, is_protected_file, __version__

try:
    import jsonschema
    from jsonschema import validate, ValidationError, SchemaError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


def detect_config_format(config: dict) -> str:
    """Detect which config format is being used."""
    if 'operations' in config:
        return "modern"
    elif 'files' in config:
        return "legacy"
    else:
        return "unknown"


def validate_file_operations(operations: List[dict]) -> Tuple[bool, List[str]]:
    """
    Validate file_create and file_delete operations.

    Guards (7 total):
    - GUARD 12: File exists (for delete)
    - GUARD 13: File not protected
    - GUARD 14: Deletion reason >= 10 chars
    - GUARD 15: Max 3 deletions per config
    - GUARD 16: Not a directory
    - GUARD 17: Parent directory exists (for create)
    - GUARD 18: File doesn't exist (for create)
    """
    errors = []
    deletion_count = 0

    for i, op in enumerate(operations, 1):
        op_type = op.get('type', '')

        if op_type == 'file_delete':
            deletion_count += 1
            file_path = op.get('path', '')
            reason = op.get('reason', '')

            # GUARD 25: Null byte check on path
            if file_path and '\x00' in file_path:
                errors.append(f"Operation {i} (file_delete): Path contains null bytes")
                continue

            # Path traversal check
            if file_path:
                rel = os.path.relpath(file_path)
                if rel.startswith('..'):
                    errors.append(f"Operation {i} (file_delete): Path traversal detected: {file_path}")
                    continue

            # GUARD 12: File exists before deletion
            if file_path and not os.path.exists(file_path):
                errors.append(f"Operation {i} (file_delete): Cannot delete non-existent file: {file_path}")

            # GUARD 13: File not protected
            if file_path and is_protected_file(file_path):
                errors.append(
                    f"Operation {i} (file_delete): BLOCKED - Cannot delete protected file: {file_path}\n"
                    f"                  Protected patterns: {', '.join(PROTECTED_PATTERNS)}"
                )

            # GUARD 14: Deletion reason >= 10 chars
            if len(reason) < 10:
                errors.append(
                    f"Operation {i} (file_delete): Deletion reason too short (minimum 10 characters)\n"
                    f"                  Current: \"{reason}\" ({len(reason)} chars)"
                )

            # GUARD 16: Not a directory
            if file_path and os.path.exists(file_path) and os.path.isdir(file_path):
                errors.append(f"Operation {i} (file_delete): Cannot delete directory: {file_path}")

        elif op_type == 'file_create':
            file_path = op.get('path', '')
            content = op.get('content', '')

            # GUARD 25: Null byte check on path
            if file_path and '\x00' in file_path:
                errors.append(f"Operation {i} (file_create): Path contains null bytes")
                continue

            # Path traversal check
            if file_path:
                rel = os.path.relpath(file_path)
                if rel.startswith('..'):
                    errors.append(f"Operation {i} (file_create): Path traversal detected: {file_path}")
                    continue

            # GUARD 26: Null byte check on content
            if content and '\x00' in content:
                errors.append(f"Operation {i} (file_create): Content contains null bytes")

            # GUARD 18: File doesn't already exist (overwrite protection)
            if file_path and os.path.exists(file_path):
                errors.append(
                    f"Operation {i} (file_create): File already exists: {file_path}\n"
                    f"                  Use code_edit to modify existing files"
                )

            # GUARD 17: Parent directory exists (warning only — executor creates dirs automatically)
            if file_path:
                parent = os.path.dirname(file_path)
                if parent and not os.path.exists(parent):
                    print(
                        f"  Warning: Operation {i} (file_create): Parent directory doesn't exist: {parent}\n"
                        f"           The executor will create it automatically."
                    )

            if not content:
                errors.append(f"Operation {i} (file_create): Content cannot be empty")

    # GUARD 15: Max 3 deletions per config
    if deletion_count > 3:
        errors.append(
            f"Too many file deletions ({deletion_count}) - maximum 3 per config\n"
            f"                  Split into multiple configs if needed"
        )

    return len(errors) == 0, errors


def _validate_edits(edits: list, file_content: str, label: str, errors: List[str]):
    """Validate edit entries against file content (GUARDs 8-11).

    Args:
        edits: List of edit dicts from the config.
        file_content: The current text content of the target file.
        label: Prefix for error messages (e.g. "File 1" or "Operation 2").
        errors: List to append error messages to.
    """
    for j, edit in enumerate(edits, 1):
        # GUARD 8: Check for action type
        action_types = ['add_after', 'add_before', 'replace', 'delete']
        has_action = any(act in edit for act in action_types)
        if not has_action:
            errors.append(
                f"{label}, Edit {j}: No action specified (need one of: {action_types})"
            )

        # GUARD 9: Check 'find' pattern exists
        if 'find' not in edit:
            errors.append(f"{label}, Edit {j}: Missing 'find' pattern")
            continue

        find_pattern = edit['find']

        # GUARD 26: Null byte check on find pattern and action content
        if '\x00' in find_pattern:
            errors.append(f"{label}, Edit {j}: Find pattern contains null bytes")
            continue
        for action_key in ('replace', 'add_after', 'add_before'):
            if action_key in edit and '\x00' in edit[action_key]:
                errors.append(f"{label}, Edit {j}: '{action_key}' content contains null bytes")

        # GUARD 10: Verify 'find' exists in file
        if find_pattern not in file_content:
            preview = find_pattern[:50].replace('\n', '\\n')
            if len(find_pattern) > 50:
                preview += "..."
            errors.append(
                f"{label}, Edit {j}: Pattern not found in file\n"
                f"                  Looking for: \"{preview}\"\n"
                f"                  FIX: Check for typos, extra spaces, or wrong line"
            )
            continue

        # GUARD 11: Check for multiple occurrences (ambiguous match)
        occurrence_count = file_content.count(find_pattern)
        if occurrence_count > 1:
            errors.append(
                f"{label}, Edit {j}: Pattern appears {occurrence_count} times in file\n"
                f"                  FIX: Make pattern more specific to match only once"
            )


def validate_against_schema(config: dict, schema_file: str) -> Tuple[bool, List[str]]:
    """Validate config against JSON schema."""
    if not JSONSCHEMA_AVAILABLE:
        return True, []

    errors = []
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except Exception as e:
        return False, [f"Error loading schema: {e}"]

    try:
        validate(instance=config, schema=schema)
        return True, []
    except ValidationError as e:
        msg = getattr(e, 'message', str(e))
        error_msg = f"Schema validation failed: {msg}"
        if e.absolute_path:
            path = ".".join(str(p) for p in e.absolute_path)
            error_msg += f" at path: {path}"
        errors.append(error_msg)
        if "Additional properties are not allowed" in msg:
            errors.append("REJECTED: Config contains non-standard fields!")
            errors.append("Allowed fields: plan, files, operations, path, edits, find, add_after, add_before, replace, delete")
        return False, errors
    except SchemaError as e:
        return False, [f"Invalid schema definition: {e}"]


def validate_json_config(config_file: str) -> Tuple[bool, List[str]]:
    """
    Validate JSON operations config.

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    # GUARD 1: Check file exists
    if not os.path.exists(config_file):
        return False, [f"Config file does not exist: {config_file}"]

    try:
        # GUARD 2: Load and validate JSON syntax
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # GUARD 2.5: Validate against JSON schema
        schema_file = Path(__file__).parent / "operations-schema.json"
        if schema_file.exists():
            schema_valid, schema_errors = validate_against_schema(config, str(schema_file))
            if not schema_valid:
                errors.extend(schema_errors)
                return False, errors

        config_format = detect_config_format(config)

        # GUARD 3: Check required top-level keys
        if 'plan' not in config:
            errors.append("Missing required key: 'plan'")

        if config_format == "unknown":
            errors.append("Missing required key: 'files' or 'operations'")
            return False, errors

        if config_format == "modern":
            return validate_modern_format(config, errors)
        else:
            return validate_legacy_format(config, errors)

    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON syntax: {e}"]
    except UnicodeDecodeError:
        return False, [f"File appears to be binary or non-UTF-8: {config_file}"]
    except (OSError, KeyError, TypeError) as e:
        return False, [f"Validation error: {e}"]


def validate_legacy_format(config: dict, errors: List[str]) -> Tuple[bool, List[str]]:
    """Validate legacy format (files array with code edits only)."""
    if 'files' not in config:
        errors.append("Missing required key: 'files'")
        return False, errors

    files = config.get('files', [])
    # GUARD 4: Validate files array is not empty
    if not files:
        errors.append("No files defined in config")

    # GUARD 28: Max operations limit
    if len(files) > 5:
        errors.append(
            f"Too many operations ({len(files)}) — maximum 5 per config\n"
            f"                  Split into multiple configs if needed"
        )

    for i, file_op in enumerate(files, 1):
        # GUARD 5: Validate required fields for each file
        if 'path' not in file_op:
            errors.append(f"File {i}: Missing 'path' field")
            continue

        file_path = file_op['path']

        # GUARD 25: Null byte check on path
        if '\x00' in file_path:
            errors.append(f"File {i}: Path contains null bytes")
            continue

        # GUARD 6: Check file exists
        if not os.path.exists(file_path):
            errors.append(f"File {i}: File does not exist: {file_path}")
            continue

        # GUARD 27: File size check
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            errors.append(
                f"File {i}: File too large ({file_size} bytes, max {MAX_FILE_SIZE_BYTES}): {file_path}"
            )
            continue

        # GUARD 7: Validate edits array exists
        if 'edits' not in file_op:
            errors.append(f"File {i}: Missing 'edits' array")
            continue

        edits = file_op['edits']
        if not edits:
            errors.append(f"File {i}: Empty 'edits' array")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                file_content = f.read()
        except UnicodeDecodeError:
            errors.append(f"File {i}: File appears to be binary or non-UTF-8: {file_path}")
            continue
        except OSError as e:
            errors.append(f"File {i}: Error reading file: {e}")
            continue

        _validate_edits(edits, file_content, f"File {i}", errors)

    return len(errors) == 0, errors


def validate_modern_format(config: dict, errors: List[str]) -> Tuple[bool, List[str]]:
    """Validate modern format (operations array with file_create, file_delete, code_edit)."""
    if 'operations' not in config:
        errors.append("Missing required key: 'operations'")
        return False, errors

    operations = config.get('operations', [])

    if not operations:
        errors.append("No operations defined in config")
        return False, errors

    # GUARD 28: Max operations limit
    if len(operations) > 5:
        errors.append(
            f"Too many operations ({len(operations)}) — maximum 5 per config\n"
            f"                  Split into multiple configs if needed"
        )

    # Validate file operations (GUARD 12-18)
    file_ops_valid, file_ops_errors = validate_file_operations(operations)
    if not file_ops_valid:
        errors.extend(file_ops_errors)

    # Validate all operations
    valid_types = ['file_create', 'file_delete', 'code_edit']
    for i, op in enumerate(operations, 1):
        op_type = op.get('type', '')

        # GUARD 29: Validate operation type
        if op_type not in valid_types:
            errors.append(
                f"Operation {i}: Unknown type '{op_type}' (must be one of: {valid_types})"
            )
            continue

        # GUARD 5: Validate path field exists
        if 'path' not in op:
            errors.append(f"Operation {i} ({op_type}): Missing 'path' field")
            continue

        if op_type != 'code_edit':
            continue

        file_path = op.get('path', '')

        # GUARD 25: Null byte check on path
        if '\x00' in file_path:
            errors.append(f"Operation {i} (code_edit): Path contains null bytes")
            continue

        # GUARD 6: Check file exists
        if not os.path.exists(file_path):
            errors.append(f"Operation {i} (code_edit): File does not exist: {file_path}")
            continue

        # GUARD 27: File size check
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            errors.append(
                f"Operation {i} (code_edit): File too large ({file_size} bytes, max {MAX_FILE_SIZE_BYTES}): {file_path}"
            )
            continue

        # GUARD 7: Validate edits array exists
        if 'edits' not in op:
            errors.append(f"Operation {i} (code_edit): Missing 'edits' array")
            continue

        edits = op['edits']
        if not edits:
            errors.append(f"Operation {i} (code_edit): Empty 'edits' array")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                file_content = f.read()
        except UnicodeDecodeError:
            errors.append(f"Operation {i} (code_edit): File appears to be binary or non-UTF-8: {file_path}")
            continue
        except OSError as e:
            errors.append(f"Operation {i} (code_edit): Error reading file: {e}")
            continue

        _validate_edits(edits, file_content, f"Operation {i}", errors)

    return len(errors) == 0, errors


def validate_backup_compatibility(config_file: str, config: dict = None) -> Tuple[bool, List[str]]:
    """
    Validate backup/restore compatibility (GUARDS 19-24).

    Guards:
    - GUARD 19: Backup path format consistency
    - GUARD 20: Manifest path reconstruction testability
    - GUARD 21: Plan name safe for filesystem paths
    - GUARD 22: Backup directory parent is writable
    - GUARD 23: File naming collision detection
    - GUARD 24: Nested directory path handling

    Args:
        config_file: Path to JSON config file (used only if config is None)
        config: Pre-parsed config dict (avoids re-reading the file)
    """
    errors = []

    if config is None:
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            return False, [f"Cannot load config for backup validation: {e}"]

    config_format = detect_config_format(config)

    if config_format == "modern":
        operations = config.get('operations', [])
    elif config_format == "legacy":
        operations = []
        for file_op in config.get('files', []):
            operations.append({'type': 'code_edit', 'path': file_op['path']})
    else:
        return False, ["Unknown config format - cannot validate backup compatibility"]

    file_paths = [op['path'] for op in operations if 'path' in op]

    # GUARD 19: Backup path format consistency (with symlink resolution)
    cwd = os.path.realpath(os.getcwd())
    for file_path in file_paths:
        try:
            rel_path = os.path.relpath(file_path)
            if rel_path.startswith('..'):
                errors.append(
                    f"GUARD 19 FAILED: File path outside project root: {file_path}\n"
                    f"                  All files must be within the working directory"
                )
                continue
            resolved = os.path.realpath(file_path)
            if resolved != cwd and not resolved.startswith(cwd + os.sep):
                errors.append(
                    f"GUARD 19 FAILED: Path resolves outside project root: {file_path}\n"
                    f"                  Resolved to: {resolved}"
                )
        except (OSError, ValueError) as e:
            errors.append(f"GUARD 19 FAILED: Cannot validate path: {file_path} ({e})")

    # GUARD 20: Manifest path reconstruction testability
    for file_path in file_paths:
        try:
            rel_path = os.path.relpath(file_path)
            reconstructed = os.path.realpath(rel_path)
            original = os.path.realpath(file_path)
            if reconstructed != original:
                errors.append(
                    f"GUARD 20 FAILED: Path reconstruction mismatch: {file_path}"
                )
        except Exception as e:
            errors.append(f"GUARD 20 FAILED: Path reconstruction failed: {file_path} ({e})")

    # GUARD 21: Plan name safe for filesystem paths (warning only — executor sanitizes)
    plan_name = config.get('plan', '')
    if plan_name:
        unsafe_chars = re.findall(r'[^a-zA-Z0-9_\-]', plan_name)
        if unsafe_chars:
            unique_chars = list(dict.fromkeys(unsafe_chars))
            print(
                f"  Warning: Plan name contains characters that will be sanitized: "
                f"{repr(plan_name)}\n"
                f"           Unsafe chars: {unique_chars}"
            )

    # GUARD 22: Backup directory parent is writable
    backup_parent = Path("backups")
    if backup_parent.exists():
        if not os.access(backup_parent, os.W_OK):
            errors.append(
                f"GUARD 22 FAILED: Backup directory is not writable: {backup_parent.resolve()}\n"
                f"                  FIX: chmod +w {backup_parent.resolve()}"
            )
    else:
        # Check that cwd is writable (backup dir will be created there)
        if not os.access('.', os.W_OK):
            errors.append(
                f"GUARD 22 FAILED: Current directory is not writable — cannot create backups/\n"
                f"                  FIX: Run from a writable directory"
            )

    # GUARD 23: File naming collision detection (warning only — backup uses nested dirs)
    filename_map = {}
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        if filename in filename_map and filename_map[filename] != file_path:
            print(
                f"  Warning: Duplicate filename across paths: {filename}\n"
                f"           Path 1: {filename_map[filename]}\n"
                f"           Path 2: {file_path}"
            )
        else:
            filename_map[filename] = file_path

    # GUARD 24: Nested directory path handling
    for file_path in file_paths:
        try:
            rel_path = os.path.relpath(file_path)
            parent = os.path.dirname(rel_path)
            if parent and os.sep in parent:
                components = parent.split(os.sep)
                for component in components:
                    if not component or component in ['.', '..']:
                        errors.append(
                            f"GUARD 24 FAILED: Invalid path component in: {file_path}"
                        )
        except Exception as e:
            errors.append(f"GUARD 24 FAILED: Nested path validation failed: {file_path} ({e})")

    return len(errors) == 0, errors


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Validate JSON operations config (v2.0)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/validate-config-json.py my-plan/ops.json

Supported Formats:
  - LEGACY: {"plan": "...", "files": [...]} - Code edits only
  - MODERN: {"plan": "...", "operations": [...]} - file_create, file_delete, code_edit

Safety Guards (29 total):
  Code Editing (11):
    GUARD 1:  Config file existence
    GUARD 2:  JSON syntax validation
    GUARD 3:  Required top-level keys
    GUARD 4:  Empty files/operations array check
    GUARD 5:  Required fields per file/operation
    GUARD 6:  Target file existence
    GUARD 7:  Edits array validation
    GUARD 8:  Action type validation
    GUARD 9:  Find pattern required
    GUARD 10: Pattern exists in file
    GUARD 11: Ambiguous match detection

  File Operations (7):
    GUARD 12: File exists before deletion
    GUARD 13: Protected file check
    GUARD 14: Deletion reason >= 10 characters
    GUARD 15: Max 3 deletions per config
    GUARD 16: Not a directory
    GUARD 17: Parent directory exists (for create)
    GUARD 18: File doesn't exist (for create - overwrite protection)

  Backup/Restore (6):
    GUARD 19: Backup path format consistency
    GUARD 20: Manifest path reconstruction testability
    GUARD 21: Plan name safe for filesystem paths
    GUARD 22: Backup directory parent is writable
    GUARD 23: File naming collision detection
    GUARD 24: Nested directory path handling

  Security (5):
    GUARD 25: Null byte rejection in file paths
    GUARD 26: Null byte rejection in content
    GUARD 27: File size limit (2MB)
    GUARD 28: Max operations limit (5 per config)
    GUARD 29: Operation type validation
        """
    )
    parser.add_argument('config', help='Path to JSON operations config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    if not JSONSCHEMA_AVAILABLE:
        print("Warning: jsonschema library not installed - schema validation skipped")
        print("Install with: pip install jsonschema\n")

    print(f"Validating: {os.path.basename(args.config)}\n")

    is_valid, errors = validate_json_config(args.config)

    if is_valid:
        # Pass pre-parsed config to avoid re-reading the file
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                parsed_config = json.load(f)
        except Exception:
            parsed_config = None
        backup_valid, backup_errors = validate_backup_compatibility(args.config, config=parsed_config)
        if not backup_valid:
            is_valid = False
            errors.extend(backup_errors)

    if is_valid:
        print("  JSON syntax valid")
        print("  All required fields present")
        print("  All file paths valid")
        print("  All find patterns exist in files")
        print("\n-> APPROVED\n")
        sys.exit(0)
    else:
        print("Validation failed!\n")
        print("Errors found:")
        for error in errors:
            print(f"  - {error}")
        print("\n-> REJECTED\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
