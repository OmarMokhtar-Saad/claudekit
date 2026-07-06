"""Command validation for hook execution.

This is a **denylist speed bump, not a sandbox**. It raises the cost of an
accidental or low-effort destructive command; it does not contain a determined
adversary (obfuscation, novel interpreters, and env-dependent expansion can all
evade a static check). For real isolation use OS-level sandboxing.

The validator inspects *every* command in a chain (``a && b``, ``a | b``,
``a; b``) plus the contents of command substitutions (``$(...)``, backticks),
rather than only the first word of the string.
"""

import re
import shlex
from typing import List, Optional, Set, Tuple, Union

# Commands that are always allowed in safe mode.
DEFAULT_ALLOWLIST = {
    "python", "python3", "node", "npm", "npx", "yarn", "pnpm",
    "git", "make", "cargo", "go", "dotnet", "bundle", "composer",
    "pytest", "jest", "rspec", "phpunit",
    "ruff", "mypy", "eslint", "prettier", "rubocop", "phpstan",
    "tsc", "javac", "gcc", "rustc", "swiftc",
    "docker", "kubectl",
    "echo", "cat", "head", "tail", "wc", "grep", "find", "ls", "test",
}
# NOTE: bash/sh/env/xargs are deliberately NOT allowlisted. Each lets a caller
# smuggle an arbitrary payload past base-command inspection
# (``bash -c 'rm -rf /'``, ``xargs rm``, ``env rm``). In safe mode they fall
# through to the "not in allowlist" rejection.

# Commands that are NEVER allowed, even in unsafe mode.
BLOCKLIST = {
    "rm", "rmdir", "dd", "mkfs", "fdisk", "mount", "umount",
    "chmod", "chown", "chgrp",
    "curl", "wget",          # network access should be explicit
    "ssh", "scp", "rsync",
    "sudo", "su", "doas",
    "kill", "killall", "pkill",
    "reboot", "shutdown", "halt", "poweroff",
    "shred", "srm",
}

# Whole-command dangerous patterns. Anchored/scoped so they don't fire on prose
# or legitimate arguments. Command *chaining* is handled structurally by
# segmentation below, not here.
DANGEROUS_PATTERNS = [
    (r'>\s*/dev/(?!null\b|stdout\b|stderr\b)', "redirect to a device file"),
    (r'>\s*/etc/', "redirect into /etc"),
    (r'>\s*/usr/', "redirect into /usr"),
    (r'>\s*/sys/', "redirect into /sys"),
    (r'>\s*/proc/', "redirect into /proc"),
    (r'\$\{?IFS', "IFS whitespace-evasion"),
    (r'(?:^|[\s;&|(])eval\b', "eval"),
    (r'(?:^|[\s;&|(])exec\b', "exec"),
    (r'\bfind\b[^;&|]*\s-delete\b', "find -delete"),
    (r'\bfind\b[^;&|]*\s-exec\b', "find -exec"),
    (r'\bos\.system\s*\(', "python os.system()"),
    (r'\bsubprocess\.(?:Popen|call|run|check_output|check_call)\b', "python subprocess"),
    (r'\b__import__\s*\(', "python __import__()"),
    (r':\s*\(\s*\)\s*\{', "fork bomb"),
]

# Token strings shlex emits for command separators (with punctuation_chars).
_SEPARATORS = {";", "&&", "||", "|", "&", "|&", "\n"}
# Redirect operators: skip the operator and its target token when segmenting.
_REDIRECTS = {">", ">>", "<", "<<", "<<<", "<>", ">&", "&>", "&>>"}


class CommandValidator:
    """Validates shell commands against a denylist/allowlist policy."""

    def __init__(self, allowlist: Optional[Set[str]] = None,
                 blocklist: Optional[Set[str]] = None,
                 safe_mode: bool = True):
        self.allowlist = allowlist or DEFAULT_ALLOWLIST
        self.blocklist = blocklist or BLOCKLIST
        self.safe_mode = safe_mode

    def validate(self, command: str) -> Tuple[bool, str]:
        """Validate a command string.

        Returns:
            (is_valid, reason) tuple.
        """
        if not command or not command.strip():
            return False, "Empty command"

        # 1. Whole-command dangerous patterns (redirects, eval/exec, IFS
        #    evasion, interpreter smuggling, fork bombs).
        for pattern, label in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"Dangerous pattern ({label})"

        # 2. Validate every command-substitution payload against the blocklist
        #    only, so legitimate `$(date)` passes but `$(rm -rf /)` does not.
        for inner in self._command_substitutions(command):
            ok, reason = self._validate_segment(inner, blocklist_only=True)
            if not ok:
                return False, f"In command substitution: {reason}"

        # 3. Split the command into segments on shell separators and validate
        #    each segment's base command.
        try:
            segments = self._split_segments(command)
        except ValueError:
            return False, "Malformed command (unmatched quotes)"

        if not segments:
            return False, "Empty command after parsing"

        for seg in segments:
            ok, reason = self._validate_segment(seg)
            if not ok:
                return False, reason

        return True, "OK"

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _command_substitutions(command: str) -> List[str]:
        """Extract the payloads of `$(...)` and backtick substitutions."""
        subs = re.findall(r'\$\(([^()]*)\)', command)
        subs += re.findall(r'`([^`]*)`', command)
        return [s for s in subs if s.strip()]

    @staticmethod
    def _split_segments(command: str) -> List[List[str]]:
        """Tokenize and split into per-command segments on shell separators.

        Redirect operators and their targets are dropped so a redirect target
        is never mistaken for a command. Raises ValueError on unmatched quotes.
        """
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)

        segments: List[List[str]] = []
        current: List[str] = []
        skip_next = False
        for tok in tokens:
            if skip_next:
                skip_next = False
                continue
            if tok in _REDIRECTS:
                skip_next = True
                continue
            if tok in _SEPARATORS or (tok and set(tok) <= {"&", "|", ";"}):
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append(tok)
        if current:
            segments.append(current)
        return segments

    def _validate_segment(self, segment: Union[str, List[str]],
                          blocklist_only: bool = False) -> Tuple[bool, str]:
        """Validate a single command segment (a token list or raw string)."""
        if isinstance(segment, str):
            try:
                parts = shlex.split(segment)
            except ValueError:
                return False, "Malformed command (unmatched quotes)"
        else:
            parts = segment

        if not parts:
            return True, "OK"

        base = parts[0].split("/")[-1].strip("\\")

        if base in self.blocklist:
            return False, f"Blocked command: {base}"

        if blocklist_only:
            return True, "OK"

        if self.safe_mode and base not in self.allowlist:
            return False, (
                f"Command not in allowlist: {base}. "
                "Add it to security.allowedCommands or disable security.safeMode."
            )

        return True, "OK"

    @classmethod
    def from_config(cls, config: dict) -> 'CommandValidator':
        """Create a validator from a ClaudeKit config dict.

        Reads the ``security`` section (``safeMode`` / ``allowedCommands`` /
        ``blockedCommands``) — matching config.schema.json.
        """
        sec = config.get("security", {}) or {}
        safe_mode = sec.get("safeMode", True)
        allowed = set(sec.get("allowedCommands", []))
        blocked = set(sec.get("blockedCommands", []))

        return cls(
            allowlist=(allowed | DEFAULT_ALLOWLIST) if allowed else None,
            blocklist=(blocked | BLOCKLIST) if blocked else None,
            safe_mode=safe_mode,
        )
