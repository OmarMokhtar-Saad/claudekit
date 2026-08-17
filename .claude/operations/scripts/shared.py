"""Shared constants and utilities for CodeManifest scripts."""

__version__ = "2.1.0"
__all__ = [
    "__version__", "PROTECTED_PATTERNS", "is_protected_file",
    "ALLOWED_RUN_COMMANDS", "allowed_run_commands",
]

import fnmatch
import os

# Protected file patterns (cannot be deleted via ops config).
# Add project-specific patterns as needed.
PROTECTED_PATTERNS = [
    ".gitignore",
    "*.md",
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


def is_protected_file(file_path: str) -> bool:
    """Check if file matches protected patterns.

    Protected files cannot be deleted via operations config.
    """
    file_name = os.path.basename(file_path)
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern):
            return True
    return False
