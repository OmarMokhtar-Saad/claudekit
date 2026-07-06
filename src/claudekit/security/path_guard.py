"""Path validation for file operations.

Like the command validator, this is a **speed bump, not a sandbox**: it blocks
obvious escapes and writes to sensitive paths, but is not a substitute for OS
file-system permissions.
"""

import fnmatch
import os
from pathlib import Path, PurePath
from typing import Optional, Set, Tuple

# Maximum directory nesting depth allowed for creation.
MAX_DIRECTORY_DEPTH = 20

# Paths that should never be written to.
SYSTEM_PATHS = {
    "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "/boot", "/dev", "/proc", "/sys", "/var/run",
    "/System", "/Library",           # macOS
    "C:\\Windows", "C:\\Program Files",  # Windows
}

# File/path patterns that should never be modified. Matched at path-component
# granularity (not substring), so `my.envelope.txt` is NOT treated as `.env`.
#   - a bare name (".env")         -> fnmatch against each path component
#   - a name ending "/" (".ssh/")  -> that component appearing anywhere
#   - a path fragment (".git/config") -> that consecutive component sequence
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

    def validate_path(self, file_path: str) -> Tuple[bool, str]:
        """Validate a file path for safety.

        Returns:
            (is_safe, reason) tuple.
        """
        if not file_path:
            return False, "Empty path"

        # Null byte check.
        if '\x00' in file_path:
            return False, "Path contains null bytes"

        # Resolve the real path (follows symlinks, collapses `..`).
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError) as e:
            return False, f"Cannot resolve path: {e}"

        # Must resolve within the project root. Because resolve() follows
        # symlinks, an in-project symlink pointing at /etc/passwd is caught
        # here too.
        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            return False, f"Path escapes project root: {file_path} -> {resolved}"

        # Check against protected system directories (component-anchored).
        resolved_str = str(resolved)
        for sys_path in SYSTEM_PATHS:
            if resolved_str == sys_path or resolved_str.startswith(sys_path + os.sep):
                return False, f"Path is in protected system directory: {sys_path}"

        # Check against protected patterns at component granularity.
        rel_path = str(resolved.relative_to(self.project_root))
        for pattern in PROTECTED_PATTERNS | self.extra_protected:
            if self._matches_protected(pattern, rel_path):
                return False, f"Path matches protected pattern: {pattern}"

        # Explicit symlink check with correct relative-target resolution: a
        # relative symlink target is resolved against the *link's* directory,
        # not the process cwd.
        if os.path.islink(file_path):
            raw_target = os.readlink(file_path)
            if os.path.isabs(raw_target):
                link_target = Path(raw_target).resolve()
            else:
                link_target = (Path(file_path).parent / raw_target).resolve()
            try:
                link_target.relative_to(self.project_root)
            except ValueError:
                return False, f"Symlink target escapes project root: {file_path} -> {link_target}"

        return True, "OK"

    def validate_directory(self, dir_path: str) -> Tuple[bool, str]:
        """Validate a directory path for safety."""
        is_safe, reason = self.validate_path(dir_path)
        if not is_safe:
            return is_safe, reason

        # Bound directory nesting depth.
        try:
            rel = Path(dir_path).resolve().relative_to(self.project_root)
            if len(rel.parts) > MAX_DIRECTORY_DEPTH:
                return False, f"Directory nesting too deep ({len(rel.parts)} levels)"
        except ValueError:
            pass

        return True, "OK"

    @staticmethod
    def _matches_protected(pattern: str, rel_path: str) -> bool:
        """Component-level match of a protected pattern against a path.

        Substring matching (the old `pattern in rel_path`) blocked innocent
        names like `my.envelope.txt`; this matches whole components instead.
        """
        parts = PurePath(rel_path).parts

        if pattern.endswith("/"):
            # Directory component appearing anywhere (e.g. ".ssh/").
            comp = pattern.rstrip("/")
            return comp in parts

        if "/" in pattern:
            # Consecutive component sequence (e.g. ".git/config").
            pat_parts = PurePath(pattern).parts
            n = len(pat_parts)
            return any(parts[i:i + n] == pat_parts for i in range(len(parts) - n + 1))

        # Single component: fnmatch each path component (literal unless the
        # pattern itself contains wildcards).
        return any(fnmatch.fnmatch(part, pattern) for part in parts)
