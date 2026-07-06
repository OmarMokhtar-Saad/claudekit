"""Command validation and sanitization for hook execution."""

import re
import shlex
from typing import List, Optional, Set

# Commands that are always allowed
DEFAULT_ALLOWLIST = {
    "python", "python3", "node", "npm", "npx", "yarn", "pnpm",
    "git", "make", "cargo", "go", "dotnet", "bundle", "composer",
    "pytest", "jest", "rspec", "phpunit",
    "ruff", "mypy", "eslint", "prettier", "rubocop", "phpstan",
    "tsc", "javac", "gcc", "rustc", "swiftc",
    "docker", "kubectl",
    "echo", "cat", "head", "tail", "wc", "grep", "find", "ls", "test",
    "bash", "sh",
}

# Commands that are NEVER allowed
BLOCKLIST = {
    "rm", "rmdir", "dd", "mkfs", "fdisk", "mount", "umount",
    "chmod", "chown", "chgrp",
    "curl", "wget",  # network access should be explicit
    "ssh", "scp", "rsync",
    "sudo", "su", "doas",
    "kill", "killall", "pkill",
    "reboot", "shutdown", "halt", "poweroff",
}

# Dangerous shell patterns
DANGEROUS_PATTERNS = [
    r';\s*rm\s',           # command chaining with rm
    r'\|.*rm\s',           # piping to rm
    r'>\s*/dev/',          # writing to devices
    r'>\s*/etc/',          # writing to system config
    r'>\s*/usr/',          # writing to system dirs
    r'\$\(',              # command substitution (potential injection)
    r'`[^`]+`',           # backtick command substitution
    r'eval\s',            # eval is always dangerous
    r'exec\s',            # exec replaces process
    r'source\s',          # sourcing untrusted files
    r'\.\s+/',            # dot-sourcing
]


class CommandValidator:
    """Validates shell commands against security policies."""

    def __init__(self, allowlist: Optional[Set[str]] = None,
                 blocklist: Optional[Set[str]] = None,
                 safe_mode: bool = True):
        self.allowlist = allowlist or DEFAULT_ALLOWLIST
        self.blocklist = blocklist or BLOCKLIST
        self.safe_mode = safe_mode

    def validate(self, command: str) -> tuple:
        """Validate a command string.

        Returns:
            (is_valid, reason) tuple
        """
        if not command or not command.strip():
            return False, "Empty command"

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"Dangerous pattern detected: {pattern}"

        # Extract the base command
        try:
            parts = shlex.split(command)
        except ValueError:
            return False, "Malformed command (unmatched quotes)"

        if not parts:
            return False, "Empty command after parsing"

        base_cmd = parts[0].split("/")[-1]  # handle full paths

        # Check blocklist first
        if base_cmd in self.blocklist:
            return False, f"Blocked command: {base_cmd}"

        # In safe mode, command must be in allowlist
        if self.safe_mode and base_cmd not in self.allowlist:
            return False, f"Command not in allowlist: {base_cmd}. Add to allowlist or disable safe_mode."

        return True, "OK"

    @classmethod
    def from_config(cls, config: dict) -> 'CommandValidator':
        """Create validator from config dict."""
        hooks_config = config.get("hooks", {})
        safe_mode = hooks_config.get("safeMode", True)
        allowed = set(hooks_config.get("allowedCommands", []))
        blocked = set(hooks_config.get("blockedCommands", []))

        return cls(
            allowlist=allowed | DEFAULT_ALLOWLIST if allowed else None,
            blocklist=blocked | BLOCKLIST if blocked else None,
            safe_mode=safe_mode,
        )
