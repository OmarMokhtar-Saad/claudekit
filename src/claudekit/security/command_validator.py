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
    # Build/test/lint entry points with no non-mutating substitute: refusing them
    # ships a language template whose gate can never run. Same class as cargo /
    # dotnet / composer / bundle / npm above; none is a shell, generic exec wrapper
    # or network fetcher, and `./vendor/bin/phpunit` already passes, so "repo-local
    # script" is not a new property. `pip` is deliberately NOT here - needing it was
    # a config defect (a mutating install used as a build check), not a policy gap.
    "gradle", "gradlew", "mvn", "mvnw", "golangci-lint",
    "swift", "swiftlint", "php-cs-fixer",
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
    # eval/exec are NOT here: as whole-string regexes they fired on any bare word,
    # rejecting `bundle exec rspec`. They are shell builtins, dangerous only in
    # command position, so they are checked per segment in _validate_segment().
    # Cost of that precision, measured and accepted: `eval`/`exec` inside an
    # ARGUMENT no longer trip anything, so `python3 -c "...eval(payload)"` and
    # `git commit -m "then exec the thing"` now pass. Disclosed in CHANGELOG.
    (r'\bfind\b[^;&|]*\s-delete\b', "find -delete"),
    (r'\bfind\b[^;&|]*\s-exec\b', "find -exec"),
    (r'\bos\.system\s*\(', "python os.system()"),
    (r'\bsubprocess\.(?:Popen|call|run|check_output|check_call)\b', "python subprocess"),
    (r'\b__import__\s*\(', "python __import__()"),
    (r':\s*\(\s*\)\s*\{', "fork bomb"),
    # Destructive git: silently discards uncommitted work. Another session (or a
    # later round of the same task) may have unstaged accumulated changes; these
    # commands wipe them with no undo. Benign forms (branch checkout, -b,
    # restore --staged) deliberately do not match.
    (r'\bgit\b[^;&|]*\breset\b[^;&|]*--hard\b', "git reset --hard discards uncommitted work"),
    (r'\bgit\b[^;&|]*\bclean\b[^;&|]*(?:\s-[a-zA-Z]*f|\s--force\b)',
     "git clean -f deletes untracked files"),
    (r'\bgit\b[^;&|]*\bcheckout\b[^;&|]*\s--\s', "git checkout -- overwrites uncommitted work"),
    (r'\bgit\b[^;&|]*\bcheckout\b\s+\.(?:\s|$)', "git checkout . overwrites uncommitted work"),
    (r'\bgit\b[^;&|]*\bstash\b[^;&|]*\b(?:drop|clear)\b', "git stash drop/clear destroys stashes"),
]

# `git restore` needs its own check: worktree restore destroys uncommitted work,
# but pure `--staged` usage only unstages (worktree untouched) and stays allowed.
_GIT_RESTORE_RE = re.compile(r'\bgit\b[^;&|]*\brestore\b([^;&|]*)')


def _git_restore_violation(command: str) -> bool:
    match = _GIT_RESTORE_RE.search(command)
    if not match:
        return False
    args = match.group(1)
    # Safe only when --staged is present and no worktree flag pulls the
    # restore back into the working tree.
    return "--staged" not in args or "--worktree" in args or re.search(r'\s-[a-zA-Z]*W', args) is not None

# Shell builtins that smuggle a payload past base-command inspection. Checked in
# command position per segment, which still catches `exec rm -rf /` and
# `git status && eval x` without matching `exec` inside an argument list.
_SHELL_BUILTIN_DENY = {"eval", "exec"}

# `VAR=value cmd` is a standard shell prefix; without this the validator read
# `XDEBUG_MODE=coverage` as the base command and rejected it. This is an ALLOWLIST,
# not a denylist, and the polarity is the whole point: a denylist of dangerous
# names can never be complete, and the misses grant execution to commands this
# module allowlists (RUBYOPT+bundle, JAVA_TOOL_OPTIONS/GRADLE_OPTS/MAVEN_OPTS+
# gradlew/mvn, CLASSPATH+javac, GIT_CONFIG_COUNT/GIT_SSH_COMMAND+git,
# NODE_OPTIONS+node, GEM_HOME, PYTHONHOME, npm_config_*). Anything not listed is
# refused by name. LANG/LC_ALL/TZ grant no execution but do steer locale and
# output; they are kept because build gates legitimately set them. Extend this set
# only with an argument that the variable cannot influence which code runs.
_ENV_ASSIGN_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
_SAFE_ENV_ASSIGN_NAMES = {
    "CI", "COVERAGE", "XDEBUG_MODE", "NODE_ENV", "RAILS_ENV", "RACK_ENV",
    "RUST_BACKTRACE", "TZ", "LANG", "LC_ALL", "NO_COLOR", "FORCE_COLOR",
}

# Token strings shlex emits for command separators (with punctuation_chars).
# NOTE: "\n" is unreachable AFTER the per-line split in validate() - shlex only
# ever emitted it for an escaped newline, and those lines are now split first. It
# stays so that _split_segments() remains correct if called directly.
_SEPARATORS = {";", "&&", "||", "|", "&", "|&", "\n"}
# Redirect operators: skip the operator and its target token when segmenting.
_REDIRECTS = {">", ">>", "<", "<<", "<<<", "<>", ">&", "&>", "&>>"}

# Characters that can wrap or adjoin a command name without being part of it. An EMPTY
# expansion is removed by bash before the command is resolved, so `` `` ``, `$()`, `$''` and
# `$""` glued to a name were invisible to the shell and to the blocklist alike: ``rm -rf /`
# was ALLOW with safeMode off, and bash really did delete the file. A list of literal
# empty-expansion spellings is the same losing game as an env-name denylist - review added
# `$''` and `$""` to a set that started as backticks and `$()` - so this is a character class.
_EXPANSION_PUNCT = "`$()"


def _strip_adjacent_fds(command: str) -> str:
    """Remove file-descriptor numbers that are ADJACENT to a redirect, outside quotes.

    `2>/dev/null rm -rf /` segmented to base command `2`, so the blocklisted `rm` was never
    checked: ALLOW with safeMode off, confirmed against bash. Three constraints make removing
    the digit safe, and the first two were each a rejected design:

      * Adjacency. `2 > log` with a space runs a command NAMED `2` in bash. Dropping the digit
        there erased a real command name and let `2 > f; ls` through in the default mode.
      * Position, not value. Tracking "which digit strings appear adjacent somewhere" and then
        testing tokens by value let a quoted `'x 2>y'` elsewhere in the line poison the set and
        silently erase a genuine `2 > f` segment. Working on the raw string keeps each
        occurrence bound to its own position.
      * Quotes. `echo "a 2>b"` is an argument, not a redirect.

    Anything not matching all three is left exactly as it was, so a digit stays a base command
    whenever bash would treat it as one.
    """
    out: List[str] = []
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\" and not in_single and i + 1 < n:
            out.append(ch)
            out.append(command[i + 1])
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif (ch.isdigit() and not in_single and not in_double
              and (not out or out[-1].isspace())):
            end = i
            while end < n and command[end].isdigit():
                end += 1
            if end < n and command[end] in "<>":
                i = end
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _expansion_stripped_base(parts: List[str]) -> str:
    """The base command with expansion punctuation removed - for DENY checks only.

    Never feed this to the allowlist. Measured on the first attempt at this fix, which used it
    everywhere: 5,118 REJECT -> ALLOW transitions over a 168,400-payload fuzz, because `$ls`
    and `` `ls` `` normalise to the allowlisted `ls`. A command substitution in command
    position is not `ls`; it is "run whatever this prints". Normalisation may only ever ADD
    rejections.
    """
    for tok in parts:
        stripped = "".join(ch for ch in tok if ch not in _EXPANSION_PUNCT)
        if stripped:
            return stripped.split("/")[-1].strip("\\")
    return ""


def _split_unquoted_newlines(command: str) -> List[str]:
    """Split a command on newlines that are OUTSIDE quotes and not backslash-escaped.

    Three shapes this must get right, each verified by a case in
    tests/test_validator_segmentation.py:

      * `ls\nrm -rf /`            -> two commands. A bare newline IS a separator, and
                                      missing that allowed a blocklisted `rm`.
      * `git commit -m "a\n\nb"`   -> ONE command. The newlines are inside an argument;
                                      splitting here rejects every trailer-bearing commit.
      * `ls \\\n -la`               -> ONE line, untouched. A backslash-escaped newline is a
                                      line continuation, and shlex already segments it the
                                      way it always has.

    An unterminated quote means the newline is treated as quoted, the line stays whole, and
    shlex then reports the quoting error - rejecting, which is the intended fail-closed
    outcome rather than an accident.

    A backslash inside a `#` comment does NOT escape the newline, and getting that wrong was
    a live fail-open: bash gives a backslash no special meaning in a comment, so
    `echo #<backslash><newline>rm -rf /` runs `rm` - while this splitter, applying
    line-continuation semantics unconditionally, swallowed the newline and handed shlex one
    line in which the comment glued itself to the next word, leaving `rm` out of command
    position. ALLOW in BOTH modes, measured. `in_comment` suppresses the escape for the rest
    of the line, and so do the quote characters: the comment body is INERT, exactly as bash
    treats it.

    Making only the escape inert was tried first and was itself a fail-open, caught by
    adversarial review: with `'` still toggling, `echo # don<backslash>'t<newline>rm -rf /`
    lost its escape pair, the apostrophe opened a quote, the newline read as quoted and the
    blocklisted `rm` was ALLOWED in both modes - 21 exploitable regressions over a 48k-payload
    differential fuzz. Escape state and quote state are not independent: suppressing one
    changes the parity of the other. A balanced quote in a comment (`echo #'<newline>rm -rf
    /<newline>#'`) hid a command the same way. Both are closed by making the whole comment
    body inert here. shlex still SEES the comment (commenters is disabled there), so an
    unbalanced quote in it is still reported as malformed and still fails closed.

    Two known over-approximations, unchanged by this round and stated so the next reader does
    not have to re-derive them: `#` starts a comment here at ANY unquoted position, including
    mid-word (`a#b`) and inside a heredoc body, where bash would not. Both can only cause MORE
    splitting or a malformed report, never less, so they err closed. And the differential fuzz
    behind this state machine covered `#`, quotes, backslashes and newlines only - NOT `;`,
    `|`, `&&`, `$()`, backticks, ANSI-C `$'...'` or heredocs. Zero regressions there is
    evidence about this alphabet, not a proof about the parser.
    """
    lines: List[str] = []
    buf: List[str] = []
    in_single = in_double = in_comment = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\" and not in_single and not in_comment and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if ch == "'" and not in_double and not in_comment:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_comment:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            in_comment = True
        elif ch == "\n" and not in_single and not in_double:
            lines.append("".join(buf))
            buf = []
            in_comment = False
            i += 1
            continue
        buf.append(ch)
        i += 1
    lines.append("".join(buf))
    return lines


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
        if _git_restore_violation(command):
            return False, ("Dangerous pattern (git restore overwrites uncommitted work; "
                           "only pure --staged unstaging is allowed — commit/stash first, "
                           "or the user runs it manually)")

        # 2/3. Newlines separate commands, and shlex does not report a BARE one: with
        #      whitespace_split its default whitespace (" \t\r\n") swallows it, so
        #      `ls\nrm -rf /` collapsed into ONE segment with base `ls` and was ALLOWED -
        #      a blocklist bypass. (The "\n" entry in _SEPARATORS was NOT dead code: posix
        #      shlex does emit a literal "\n" token for an ESCAPED newline, which is how
        #      line-continued commands segmented. It is unreachable only after this change;
        #      see the note beside it.) Validate each line separately.
        #
        #      The split is QUOTE-AWARE: a newline inside quotes belongs to an ARGUMENT,
        #      not a new command. `git commit -m "subject\n\nCo-Authored-By: ..."` is the
        #      everyday case - a naive command.split("\n") rejects it, because line 2's
        #      base command is `Co-Authored-By:`. Quoted content was already treated as an
        #      argument before this change, so honouring quotes here hides nothing new.
        #
        #      This loop MUST stay below the whole-string checks above. Those patterns are
        #      whole-string by construction - `[^;&|]*` spans a newline - and they are the
        #      ONLY thing standing between `git reset\n--hard` and ALLOW when
        #      safe_mode=False, where the allowlist check is skipped entirely.
        for line in _split_unquoted_newlines(command):
            if not line.strip():
                continue
            ok, reason = self._validate_line(line)
            if not ok:
                return ok, reason

        return True, "OK"

    def _validate_line(self, command: str) -> Tuple[bool, str]:
        """Substitution scan + segmentation for a single newline-free line."""
        # Command-substitution payloads: blocklist only, so `$(date)` passes.
        for inner in self._command_substitutions(command):
            ok, reason = self._validate_segment(inner, blocklist_only=True)
            if not ok:
                return False, f"In command substitution: {reason}"

        try:
            segments = self._split_segments(command)
        except ValueError as exc:
            # Report the cause shlex actually gave. The old text always said "unmatched
            # quotes", which is wrong for a trailing backslash (`No escaped character`) -
            # a security control should not assert a cause it did not check.
            return False, f"Malformed command ({exc})"

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

        `commenters` is disabled deliberately. shlex defaults to treating `#` as a
        comment and DISCARDING the rest of the line - which made it disagree with
        _split_unquoted_newlines() about where quotes are, and the disagreement was
        FAIL-OPEN. In `make test # don't rebuild\nrm -rf /` the splitter sees the
        apostrophe, treats the newline as quoted and passes the whole string through as
        one line; shlex then throws away `# don't rebuild`, never sees that apostrophe,
        finds no separator token, and reports a single segment with base `make` - so the
        blocklisted `rm` was ALLOWED, in both modes. Two parsers that must agree about
        quoting is the bug; disabling comment-stripping removes the disagreement at its
        source, and the same input now raises ValueError -> "Malformed command", which is
        the direction a security control must fail. A `#` inside quotes is unaffected.
        """
        lex = shlex.shlex(_strip_adjacent_fds(command), posix=True,
                          punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
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

        while parts and _ENV_ASSIGN_RE.match(parts[0]):
            name = parts[0].split("=", 1)[0]
            if name not in _SAFE_ENV_ASSIGN_NAMES:
                return False, f"Dangerous pattern (environment override: {name})"
            parts = parts[1:]
        if not parts:
            # A bare assignment (`CI=1`) runs no command.
            return True, "OK"

        base = parts[0].split("/")[-1].strip("\\")
        # Versioned interpreters (`python3.12`, Homebrew's `python3.14`) are the
        # same tool as `python3` for allow/block purposes; multi-Python machines
        # otherwise get spurious "not in allowlist" rejections per interpreter.
        normalized = re.sub(r'^(python|pip)3\.\d+$', r'\g<1>3', base)

        # The expansion-stripped spelling is checked against the deny lists FIRST and
        # separately: `$()rm` and ``rm` are `rm` to bash, whatever the token looks like here.
        deny_base = _expansion_stripped_base(parts)
        if deny_base in _SHELL_BUILTIN_DENY:
            return False, f"Dangerous pattern ({deny_base})"
        if deny_base in self.blocklist:
            return False, f"Blocked command: {deny_base}"

        # Before the blocklist_only early return, so `$(eval ...)` is covered too.
        if base in _SHELL_BUILTIN_DENY:
            return False, f"Dangerous pattern ({base})"

        if base in self.blocklist or normalized in self.blocklist:
            return False, f"Blocked command: {base}"

        if blocklist_only:
            return True, "OK"

        if self.safe_mode and base not in self.allowlist and normalized not in self.allowlist:
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
