"""Shared constants and utilities for CodeManifest scripts."""

__version__ = "2.1.0"
__all__ = [
    "__version__", "PROTECTED_PATTERNS", "protected_patterns", "is_protected_file",
    "ALLOWED_RUN_COMMANDS", "allowed_run_commands",
]

import fnmatch
import os

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
