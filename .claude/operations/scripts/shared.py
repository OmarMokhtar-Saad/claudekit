"""Shared constants and utilities for CodeManifest scripts."""

__version__ = "3.1.0"
__all__ = ["__version__", "PROTECTED_PATTERNS", "MAX_FILE_SIZE_BYTES", "is_protected_file"]

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

# Maximum file size the executor will process (2 MB)
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024


def is_protected_file(file_path: str) -> bool:
    """Check if file matches protected patterns.

    Protected files cannot be deleted via operations config.
    """
    file_name = os.path.basename(file_path)
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern):
            return True
    return False
