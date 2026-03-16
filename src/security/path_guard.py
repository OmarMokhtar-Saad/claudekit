"""Path validation and sandboxing for file operations."""

import os
from pathlib import Path, PurePath
from typing import Optional, Set

# Paths that should never be written to
SYSTEM_PATHS = {
    "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "/boot", "/dev", "/proc", "/sys", "/var/run",
    "/System", "/Library",  # macOS
    "C:\\Windows", "C:\\Program Files",  # Windows
}

# File patterns that should never be modified
PROTECTED_PATTERNS = {
    ".git/config", ".git/HEAD", ".git/index",
    ".ssh/", ".gnupg/", ".aws/credentials",
    ".env", ".env.local", ".env.production",
}


class PathGuard:
    """Guards against unsafe file system operations."""

    def __init__(self, project_root: Optional[str] = None,
                 extra_protected: Optional[Set[str]] = None):
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.extra_protected = extra_protected or set()

    def validate_path(self, file_path: str) -> tuple:
        """Validate a file path for safety.

        Returns:
            (is_safe, reason) tuple
        """
        if not file_path:
            return False, "Empty path"

        # Null byte check
        if '\x00' in file_path:
            return False, "Path contains null bytes"

        # Resolve the real path
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError) as e:
            return False, f"Cannot resolve path: {e}"

        # Must be within project root
        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            return False, f"Path escapes project root: {file_path} -> {resolved}"

        # Check against system paths
        resolved_str = str(resolved)
        for sys_path in SYSTEM_PATHS:
            if resolved_str.startswith(sys_path):
                return False, f"Path is in protected system directory: {sys_path}"

        # Check against protected patterns
        rel_path = str(resolved.relative_to(self.project_root))
        for pattern in PROTECTED_PATTERNS | self.extra_protected:
            if pattern in rel_path:
                return False, f"Path matches protected pattern: {pattern}"

        # Check for symlink attacks
        if os.path.islink(file_path):
            link_target = Path(os.readlink(file_path)).resolve()
            try:
                link_target.relative_to(self.project_root)
            except ValueError:
                return False, f"Symlink target escapes project root: {file_path} -> {link_target}"

        return True, "OK"

    def validate_directory(self, dir_path: str) -> tuple:
        """Validate a directory path for safety."""
        is_safe, reason = self.validate_path(dir_path)
        if not is_safe:
            return is_safe, reason

        # Check depth to prevent deeply nested directory creation
        try:
            rel = Path(dir_path).resolve().relative_to(self.project_root)
            if len(rel.parts) > 20:
                return False, f"Directory nesting too deep ({len(rel.parts)} levels)"
        except ValueError:
            pass

        return True, "OK"
