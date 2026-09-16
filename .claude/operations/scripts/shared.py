"""Shared constants and utilities for CodeManifest scripts."""

__version__ = "3.1.0"
__all__ = [
    "__version__", "PROTECTED_PATTERNS", "protected_patterns", "is_protected_file",
    "ALLOWED_RUN_COMMANDS", "allowed_run_commands",
    "MAX_PAYLOAD_BYTES", "resolve_payload_refs",
]

import fnmatch
import hashlib
import os
import re
from typing import Any, Dict, List, Optional

# Protected file patterns (cannot be deleted via ops config), matched against the
# BASENAME and CASE-INSENSITIVELY, so a pattern applies at any depth and `readme.md`
# is as protected as `README.md`.
#
# The markdown entry was the glob `*.md` until 2026-08-23. That froze every paragraph
# of prose in the tree, and this kit's corpus -- agents, commands, skills, modes -- is
# entirely markdown, so no ops config could ever retire one. The engine is the only
# sanctioned path for implementation (the Iron Law), so a whole class of maintenance
# had no legal route at all. Measured: across 97 archived configs there are ZERO
# file_delete operations of any kind, and task 008 stalled with 16 of 19 configs
# REJECTED, every one of them on `*.md`.
#
# What the guard is FOR is a project's identity documents -- the files whose loss a
# user would experience as damage. Those are named below and still refused at any
# depth. Ordinary prose is deletable, and three controls remain in front of it:
# MAX_DELETIONS = 3 per config, the mandatory `reason` field, and the executor's
# pre-delete backup.
#
# The list is a DEFAULT, not a survey: it is the conventional OSS set, not a census of
# what any particular consumer keeps. A project with its own identity documents widens
# its own set with CLAUDEKIT_EXTRA_PROTECTED rather than forking this file -- the same
# shape ALLOWED_RUN_COMMANDS already uses below.
PROTECTED_PATTERNS = [
    ".gitignore",
    "README.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "LICENSE",
    "LICENSE.md",
    "NOTICE.md",
    "MAINTAINERS.md",
    "GOVERNANCE.md",
    "AUTHORS.md",
    "SUPPORT.md",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "tsconfig.json",
]

# run_command executable allowlist (fail closed). Deterministic generators and
# formatters only — tools whose output is a pure function of files already in the
# tree, so plans never hand-transcribe generated text (lockfiles, format churn).
# Guardrail against accident and prompt-drift, not a sandbox: the allowlisted
# tools themselves read config files from the tree.
ALLOWED_RUN_COMMANDS = frozenset([
    "pip-compile",
    "black",
    "isort",
    "ruff",
    "prettier",
    "gofmt",
    "goimports",
    "rustfmt",
])


def allowed_run_commands() -> frozenset:
    """Allowlist for run_command argv[0], extended per-project via the
    CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW env var (colon-separated basenames,
    typically set in .claude/settings.local.json env)."""
    extra = os.environ.get("CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW", "")
    names = {name.strip() for name in extra.split(":") if name.strip()}
    return ALLOWED_RUN_COMMANDS | frozenset(names)


def protected_patterns() -> list:
    """The effective protected set: the defaults above plus anything a project
    adds through CLAUDEKIT_EXTRA_PROTECTED (colon-separated basenames or globs,
    typically set in .claude/settings.local.json env).

    Extensible for the same reason ALLOWED_RUN_COMMANDS is: the default list is a
    convention, and a consumer that keeps an identity document this kit never
    heard of should be able to say so without editing a file the kit overwrites
    on upgrade. Widening only -- there is no mechanism to REMOVE a default.
    """
    extra = os.environ.get("CLAUDEKIT_EXTRA_PROTECTED", "")
    return PROTECTED_PATTERNS + [n.strip() for n in extra.split(":") if n.strip()]


def is_protected_file(file_path: str) -> bool:
    """Check if file matches protected patterns.

    Protected files cannot be deleted via operations config.

    Case-INSENSITIVE, and deliberately so. `fnmatch.fnmatch` normalises case only
    on Windows, so on Linux CI the guard used to refuse `README.md` and permit
    `readme.md` while on macOS both behaved the same -- a security control whose
    answer depended on the developer's filesystem. The old `*.md` glob hid half
    of that; naming the documents exposes it, so it is fixed here rather than
    inherited.
    """
    file_name = os.path.basename(file_path).lower()
    for pattern in protected_patterns():
        if fnmatch.fnmatchcase(file_name, pattern.lower()):
            return True
    return False


# Payload-by-reference: a large file_create body, or a large edit payload, may live in
# its own file instead of being inlined in ops.json, so a plan writes it ONCE. The
# reference is resolved HERE, in one place, and materialised into the very key it stands
# in for (`content_path` -> `content`), so every downstream guard, simulation, backup and
# rollback path sees exactly what an inline payload would have produced.
#
# `<key>_sha256` is MANDATORY, not optional. Review approval is stamped over the hash of
# ops.json alone; a payload referenced by path only could be rewritten after the verdict
# and the gate would still pass. Carrying the digest inside ops.json puts the payload back
# under the approval hash transitively -- no change to review-record.py, and the ad-hoc
# --no-approval path is covered too, which a baseline extension would not have been.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

PAYLOAD_KEYS = ("content", "replace", "add_after", "add_before")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _has_refs(entry: Dict[str, Any]) -> bool:
    """True if this operation/file entry carries any payload reference."""
    if any(k + "_path" in entry for k in PAYLOAD_KEYS):
        return True
    edits = entry.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and any(k + "_path" in edit for k in PAYLOAD_KEYS):
                return True
    return False


def _resolve_one(container: Dict[str, Any], key: str, label: str, root: str,
                 errors: List[str]) -> None:
    """Materialise container[key] from container[key + '_path']; append any errors.

    Fail closed: on any error the inline key is left ABSENT, so a caller that ignores
    the returned errors still cannot execute an unresolved reference.
    """
    ref_key, sha_key = key + "_path", key + "_sha256"
    ref = container.get(ref_key)
    if not isinstance(ref, str) or not ref or "\x00" in ref:
        errors.append(f"{label}: {ref_key} must be a non-empty path with no null bytes")
        return
    if key in container:
        errors.append(
            f"{label}: {key!r} and {ref_key!r} are mutually exclusive -- use exactly one")
        return
    digest = container.get(sha_key)
    if not isinstance(digest, str) or not _HEX64.match(digest):
        errors.append(
            f"{label}: {ref_key} requires {sha_key} (64 lowercase hex chars). Without it"
            " the payload would sit outside the hash the approval gate stamps.")
        return
    if os.path.isabs(ref):
        errors.append(f"{label}: {ref_key} must be relative to the project root: {ref}")
        return
    full = os.path.realpath(os.path.join(root, ref))
    if full != root and not full.startswith(root + os.sep):
        errors.append(f"{label}: {ref_key} resolves outside the project root: {ref}")
        return
    if not os.path.isfile(full):
        errors.append(f"{label}: {ref_key} is not an existing regular file: {ref}")
        return
    size = os.path.getsize(full)
    if size > MAX_PAYLOAD_BYTES:
        errors.append(
            f"{label}: payload {ref} is {size} bytes (maximum {MAX_PAYLOAD_BYTES})")
        return
    try:
        with open(full, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        errors.append(f"{label}: cannot read payload {ref} ({exc})")
        return
    actual = hashlib.sha256(raw).hexdigest()
    if actual != digest:
        errors.append(
            f"{label}: payload digest mismatch for {ref}"
            f" (declared {digest}, actual {actual})")
        return
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"{label}: payload {ref} is not valid UTF-8 ({exc})")
        return
    if "\x00" in text:
        errors.append(f"{label}: payload {ref} contains null bytes")
        return
    container[key] = text


def resolve_payload_refs(config: Dict[str, Any], root: Optional[str] = None) -> List[str]:
    """Resolve every `<key>_path` payload reference in `config`, in place.

    Returns a list of error strings; empty means the config now carries inline
    payloads indistinguishable from hand-inlined ones. Callers MUST abort on a
    non-empty list.
    """
    errors: List[str] = []
    if not isinstance(config, dict):
        return errors
    root = os.path.realpath(root or os.getcwd())

    legacy = config.get("files")
    if isinstance(legacy, list):
        for entry in legacy:
            if isinstance(entry, dict) and _has_refs(entry):
                errors.append(
                    "Legacy 'files' format does not support payload references;"
                    " use the modern 'operations' format")
                break

    operations = config.get("operations")
    if not isinstance(operations, list):
        return errors

    for i, op in enumerate(operations, 1):
        if not isinstance(op, dict):
            continue
        if op.get("type") == "file_create" and "content_path" in op:
            _resolve_one(op, "content", f"Operation {i} (file_create)", root, errors)
        edits = op.get("edits")
        if not isinstance(edits, list):
            continue
        for j, edit in enumerate(edits, 1):
            if not isinstance(edit, dict):
                continue
            refs = [k for k in ("replace", "add_after", "add_before") if k + "_path" in edit]
            if len(refs) > 1:
                errors.append(
                    f"Operation {i}, Edit {j}: more than one payload reference"
                    f" ({', '.join(sorted(refs))}) -- use exactly one")
                continue
            for key in refs:
                _resolve_one(edit, key, f"Operation {i}, Edit {j}", root, errors)
    return errors

