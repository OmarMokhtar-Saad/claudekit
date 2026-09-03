#!/usr/bin/env python3
"""concurrency-guard.py - blocks tree-wide git commands while sessions share a working tree.

WHY THIS EXISTS
---------------
Several Claude sessions -- possibly two accounts -- work one repo at once. One working
tree means one `.git/index`: session B sees session A's half-written files and staged
paths. A tree-wide stage or a destructive checkout in B then commits or deletes A's
in-flight work, silently. It cost real work twice in `qa-agent` (2026-09-02, 2026-09-03).

The isolation that actually holds is one git worktree per session (`.ai/CONCURRENCY.md`).
This hook only catches the honest mistake -- which is the one that actually happened.

WHY PYTHON AND NOT A REGEX SHELL HOOK  ***DO NOT "SIMPLIFY" BACK TO grep -E***
------------------------------------------------------------------------------
The first implementation was regex-over-command-text. An adversarial review executed a
90-case battery against it and found 8 defects that were ALL tokenisation failures:

  * `git add .ai/x.md` was BLOCKED - an unanchored `\\.` alternative matched the first
    character of every dot-prefixed path, so the guard denied the very remediation its
    own message prescribed. In this repo family most staged paths start with `.claude/`.
  * `git stash pop|apply|drop` were BLOCKED - denying the operation that RESTORES work.
  * `git commit -m x -a` LEAKED - the flag scan assumed an unbroken run of dash-tokens.
  * `git checkout HEAD -- .`, `git restore --staged .` LEAKED - only a bare `--` was
    tolerated between subcommand and pathspec.
  * `git -C <dir> add -A` LEAKED - ordinary usage when the cwd is not the repo root.
  * `git add -u`, `checkout -f`, `reset --merge|--keep`, `git rm -r .` were absent.

Patching those alternations individually would have been eight more chances to get an
anchor wrong. `shlex` + per-subcommand argv inspection removes the whole class: flag
order stops mattering, `--` is honoured as end-of-options, clusters (`-am`, `-fd`)
decompose, and a pathspec is compared as a WHOLE token so `.ai/x` is never `.`.

BLOCKING CONTRACT (project hard rule 2)
---------------------------------------
`exit 2` with the reason on STDERR, nothing on stdout. Never exit 1.

FAIL DIRECTION
--------------
Fail CLOSED: a payload that cannot be parsed, or a git command that cannot be tokenised,
blocks. `command-guard.sh` sets that precedent on this same event. Unlike the shell
version this hook has NO `lib.sh` dependency, so there is no path where a missing helper
silently degrades it to exit 0.

PROFILE CONVENTION  ***DELIBERATE DIVERGENCE - DO NOT "FIX" THIS BACK***
------------------------------------------------------------------------
Under `ECC_HOOK_PROFILE=minimal` this hook does NOT short-circuit. This repo develops
with `minimal` set (CLAUDE.md "Session setup gotcha"), so a wholesale `exit 0` would give
ZERO dogfood signal in the very tree where the incident is recorded. Under `minimal` the
decision is still computed and logged as `WOULD-BLOCK`, then exit 0. Blocking is
suppressed; measurement is not. Same posture as `iron-law-gate.py` and `reflection-gate.py`.

LOGGING (project hard rule 6)
-----------------------------
Only the git subcommand and the rule id are logged - never the command text. A blocked
command line is exactly the text most likely to carry a credential or a host path, and a
guard that records the secrets it blocks is worse than the bypass it prevents.

HONEST FRAMING (project hard rule 6)
------------------------------------
A denylist speed bump, NOT a sandbox. It reads the command the model wrote, so residuals
are named rather than hidden: a git invocation constructed at runtime (`$VAR add -A`,
`xargs git`, `git submodule foreach git ...`, a script that runs git internally) is not
seen. `bash -c`, `sh -c`, `sudo`, `env` and `VAR=val` prefixes ARE unwrapped.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

HOOK_NAME = "concurrency-guard"
DEFAULT_PROFILE = "standard"
ESCAPE_ENV = "CK_ALLOW_BROAD_GIT"

#: Pathspecs that mean "the whole tree" (compared as WHOLE tokens, never as prefixes).
TREE_WIDE_PATHSPECS = frozenset({
    ".", "..", "*", "**", ":/", "./", "../", ":", ":!", "*.*", "**/*",
})

#: Pathspec MAGIC prefixes that re-root the match at the top of the tree. Matched as
#: prefix PLUS a tree-wide-or-empty remainder, never bare `startswith`: `:/src/a.py` is
#: a scoped single file (the ordinary form from a subdirectory) and blocking it repeats
#: round 1's defect of denying the remediation this hook prescribes.
TREE_WIDE_MAGIC = (":/", ":(top)", ":(glob)", ":(top,", ":(exclude)")

#: Shell operators that separate one command from the next. No `\n` member: newlines
#: are converted to `;` by `preprocess` before tokenising, because shlex cannot emit a
#: newline as a token. An earlier version listed `"\n"` here and it was DEAD, which is
#: how "every line after the first is discarded" survived a review round.
OPERATORS = frozenset({";", "&&", "||", "|", "&", "|&"})

#: Tokens that may precede the real command word and must be stepped over.
PREFIX_WORDS = frozenset({
    "sudo", "env", "command", "time", "nice", "nohup", "exec", "builtin",
    "then", "do", "else", "elif", "if", "while", "until", "!", "{", "(", "((",
    "case", "esac", "in", "for", "select", "function", "coproc", "source", ".",
})

#: Commands whose ARGUMENT is a shell script to be analysed recursively.
SCRIPT_WRAPPERS = frozenset({"bash", "sh", "zsh", "dash", "eval"})

#: git global options taking a separate value argument.
GIT_GLOBAL_WITH_VALUE = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
})

#: git global options taking no value.
GIT_GLOBAL_FLAGS = frozenset({
    "-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
    "--icase-pathspecs", "--no-optional-locks", "--html-path", "--info-path",
})


def blocking_enabled() -> bool:
    """True when this hook may actually block.

    Under `minimal` it returns False and the hook goes ADVISORY, not off: the decision
    is still computed and logged as WOULD-BLOCK. This repo develops with `minimal` set
    (CLAUDE.md "Session setup gotcha"), so a wholesale exit 0 would give zero dogfood
    signal in the very tree where the incident is recorded. Same posture as
    `iron-law-gate.py` and `reflection-gate.py`.
    """
    return os.environ.get("ECC_HOOK_PROFILE", DEFAULT_PROFILE) != "minimal"


def hlog(level: str, message: str) -> None:
    """Append one line to hooks.log. Never raises - a guard must not die logging."""
    try:
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        log = Path(os.environ.get("LOG_FILE") or root / ".claude" / "hooks" / "hooks.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log.open("a", encoding="utf-8") as fh:
            fh.write("[%s] [%s] %s: %s\n" % (stamp, level, HOOK_NAME, message))
    except OSError:  # silent-ok: a guard must block or allow correctly even when
        # hooks.log is unwritable (read-only FS, missing parent, full disk). The
        # verdict is on stderr and the exit code; the log line is a convenience.
        # Raising here would turn an unwritable log into a denied Bash tool call.
        pass  # pragma: no cover - logging must never be the failure


def deny(reason: str, subcommand: str = "?", rule: str = "?") -> int:
    # "verdict=deny", not "denied": a registry row may clamp this hook to advisory,
    # in which case the command still runs. The log records what THIS hook decided,
    # not what the dispatcher ultimately did.
    hlog("BLOCK", "git %s verdict=deny (%s)" % (subcommand, rule))
    sys.stderr.write(reason + "\n")
    return 2


# ---------------------------------------------------------------------------
# Tokenising
# ---------------------------------------------------------------------------

def preprocess(command: str) -> Tuple[str, bool]:
    """One quote-aware pass over the raw command. Returns (text, confident).

    Handles, in a single state machine because each of these needs the quote state
    that a separate pass would not have:

      * an unquoted newline becomes `;` so lines SEPARATE commands. shlex cannot
        emit a newline token (it lives in `whitespace`, and removing it there fuses
        it into the neighbouring word), so the substitution must happen here.
      * an escaped newline (line continuation) becomes a SPACE. Appending the
        backslash-newline verbatim made shlex fold it into the next word, so
        `git add \\<newline>-A` lost its flag.
      * an unquoted `#` at a token boundary starts a comment, dropped to the end of
        the line. shlex's own `commenters` runs AFTER newlines are gone, so a single
        `#` swallowed the entire rest of the script.
      * an unquoted `<<` starts a heredoc whose BODY is data, not commands, so the
        body is dropped. A `<<` inside quotes (`print(1 << 2)`) is NOT a heredoc --
        treating it as one invented a marker that never matched and deleted the rest
        of the command.

    `confident` is False when the text could not be fully understood -- an
    unterminated heredoc, or an unbalanced quote. The caller FAILS CLOSED on that
    rather than analysing a truncated command, which is the inversion that produced
    every CRITICAL in this layer.
    """
    out: List[str] = []
    quote = ""
    escaped = False
    confident = True
    i = 0
    n = len(command)
    pending_markers: List[str] = []

    def at_token_boundary() -> bool:
        # A `#` only starts a comment at the start of a word, so `file#1.txt` keeps
        # its hash. NOT behaviour-bound (mutation-checked): every realistic case is
        # either quoted, or the truncated path stays non-tree-wide and is allowed
        # either way. Kept for correctness of intent, not for a test.
        return not out or out[-1] in " \t;&|("

    while i < n:
        ch = command[i]

        if escaped:
            # A line continuation is whitespace in bash; anything else keeps its
            # backslash so shlex still sees the escape.
            out.append(" " if ch == "\n" else ch)
            escaped = False
            i += 1
            continue

        if ch == "\\" and quote != "'":
            if quote == '"' or not quote:
                escaped = True
                if not (i + 1 < n and command[i + 1] == "\n"):
                    out.append(ch)
                i += 1
                continue

        if quote:
            if ch == quote:
                quote = ""
            out.append(ch)
            i += 1
            continue

        if ch in "'\"":
            quote = ch
            out.append(ch)
            i += 1
            continue

        # --- unquoted from here ------------------------------------------------
        if ch == "#" and at_token_boundary():
            while i < n and command[i] != "\n":
                i += 1
            continue

        if command.startswith("<<<", i):          # here-STRING, not a heredoc
            out.append("<<<")
            i += 3
            continue

        if command.startswith("<<", i):
            j = i + 2
            while j < n and command[j] == "-":     # `<<-` strips leading tabs
                j += 1
            while j < n and command[j] in " \t":
                j += 1
            marker_chars: List[str] = []
            mquote = ""
            if j < n and command[j] in "'\"":
                mquote = command[j]
                j += 1
            while j < n and command[j] not in " \t\n;&|)":
                if mquote and command[j] == mquote:
                    j += 1
                    break
                marker_chars.append(command[j])
                j += 1
            marker = "".join(marker_chars).lstrip("\\").strip("'\"")
            if marker:
                pending_markers.append(marker)
            out.append("<<")
            i = j
            continue

        if ch == "\n":
            out.append(";")
            i += 1
            if pending_markers:
                # Consume heredoc BODIES that start on the next line.
                while pending_markers:
                    marker = pending_markers.pop(0)
                    found = False
                    while i < n:
                        line_end = command.find("\n", i)
                        if line_end == -1:
                            line_end = n
                        if command[i:line_end].strip() == marker:
                            i = line_end + 1 if line_end < n else n
                            found = True
                            break
                        i = line_end + 1 if line_end < n else n
                    if not found:
                        # The terminator never arrived: we do not know where the
                        # body ended, so we cannot claim to have read the command.
                        confident = False
            continue

        out.append(ch)
        i += 1

    if quote or escaped:
        confident = False
    return "".join(out), confident


#: Tokens that begin a shell REDIRECTION. The operator and its target are not
#: arguments -- leaving them in argv made `git add -A >/dev/null` look like a
#: scoped stage (">" and "/dev/null" read as pathspecs) and allowed it.
def classify_operator(token: str) -> str:
    """Classify an operator token: "separator", "redirection" or "" (not an operator).

    `shlex(punctuation_chars=True)` fuses a RUN of operator characters into one token,
    so `<<;` is both a heredoc operator and a command separator. A token carrying any
    separator character is treated as a separator FIRST -- losing the separator merges
    two commands, which is the fail-open direction.
    """
    if not token:
        return ""
    body = token.lstrip("0123456789")
    if not body or not all(ch in "<>&|;" for ch in body):
        return ""
    if any(ch in ";|" for ch in body) or "&&" in body:
        return "separator"
    if "<" in body or ">" in body:
        return "redirection"
    if body == "&":
        return "separator"
    return ""


def is_redirection(token: str) -> bool:
    return classify_operator(token) == "redirection"


def split_segments(tokens: Sequence[str]) -> List[List[str]]:
    """Split a token stream into individual commands on shell operators."""
    segments: List[List[str]] = [[]]
    skip_next = False
    for tok in tokens:
        # `punctuation_chars` collapses a RUN of operator characters into one token, so
        # a blank line between commands arrives as `;;` and an `||` as a single token.
        # Anything made only of operator characters is a separator.
        kind = classify_operator(tok)
        if skip_next:
            skip_next = False
            # A redirection TARGET is never a separator, but a fused run still is.
            if kind != "separator":
                continue
        if kind == "redirection":
            # `>` / `2>` / `<` and whatever they point at are not arguments. A bare
            # file-descriptor digit arrives as its OWN token just before the operator,
            # so drop that too -- left in place it read as a scoping pathspec and
            # `git add -A 2>/dev/null` was allowed.
            if segments[-1] and segments[-1][-1].isdigit():
                segments[-1].pop()
            # The target follows unless the operator token already carries it
            # (`>&1` fused). `>&` + `1` arrives as TWO tokens, and leaving the `1`
            # behind made `git add -A >/dev/null 2>&1` look scoped.
            skip_next = not tok[-1:].isdigit()
            continue
        if kind == "separator" or tok in OPERATORS:
            segments.append([])
        elif tok in (")", "}", "(", "{"):
            # Grouping punctuation is not an argument. A trailing `)` left in argv was
            # read as a PATHSPEC, which made `(git add -A)` look scoped and allowed it.
            continue
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def strip_prefixes(segment: Sequence[str]) -> List[str]:
    """Step over `sudo`, `env`, `VAR=val`, shell keywords and grouping tokens."""
    out = list(segment)
    while out:
        head = out[0]
        if head in PREFIX_WORDS:
            out = out[1:]
            continue
        # A leading VAR=value assignment (GIT_DIR=x git add -A).
        if "=" in head and not head.startswith("-") and head.split("=", 1)[0].isidentifier():
            out = out[1:]
            continue
        # A grouping token fused to the word, e.g. "{git".
        if len(head) > 1 and head[0] in "{(":
            out = [head[1:]] + list(out[1:])
            continue
        break
    return out


def is_git(word: str) -> bool:
    """True for `git`, `/usr/bin/git`, `git.exe` - the command word, however spelled."""
    return os.path.basename(word).split(".")[0] == "git" if word else False


def strip_git_globals(args: Sequence[str]) -> List[str]:
    """Drop git's pre-subcommand global options (`-C dir`, `--git-dir=...`, `-c k=v`)."""
    out = list(args)
    while out:
        head = out[0]
        if head in GIT_GLOBAL_FLAGS:
            out = out[1:]
            continue
        if head in GIT_GLOBAL_WITH_VALUE:
            out = out[2:] if len(out) > 1 else []
            continue
        if head.startswith("--") and "=" in head and head.split("=", 1)[0] in GIT_GLOBAL_WITH_VALUE:
            out = out[1:]
            continue
        # Fused short form: -C/tmp/x or -cuser.name=x
        if len(head) > 2 and head[:2] in ("-C", "-c"):
            out = out[1:]
            continue
        break
    return out


def split_args(args: Sequence[str]) -> Tuple[List[str], List[str], List[str]]:
    """Return (flags, operands, pathspecs_after_dashdash).

    `--` is honoured as end-of-options, so `git add -- -A` treats `-A` as a FILENAME.
    """
    flags: List[str] = []
    operands: List[str] = []
    after: List[str] = []
    seen_dashdash = False
    for tok in args:
        if seen_dashdash:
            after.append(tok)
        elif tok == "--":
            seen_dashdash = True
        elif tok.startswith("-") and tok != "-":
            flags.append(tok)
        else:
            operands.append(tok)
    return flags, operands, after


def has_flag(flags: Sequence[str], long_names: Sequence[str], short_letters: str = "") -> bool:
    """True if any long flag matches, or any short CLUSTER contains a listed letter."""
    for flag in flags:
        base = flag.split("=", 1)[0]
        if base in long_names:
            return True
        if short_letters and not flag.startswith("--") and flag.startswith("-"):
            if any(letter in flag[1:] for letter in short_letters):
                return True
    return False


def tree_wide(pathspecs: Sequence[str]) -> bool:
    """True if any pathspec means the whole tree. Whole-token compare: `.ai/x` is not `.`."""
    for p in pathspecs:
        if p in TREE_WIDE_PATHSPECS:
            return True
        if p.rstrip("/") in (".", "..", "*", "**", ":"):
            return True
        for magic in TREE_WIDE_MAGIC:
            if p == magic.rstrip(","):
                return True
            if p.startswith(magic):
                remainder = p[len(magic):]
                # A concrete path after the magic prefix SCOPES it.
                if remainder == "" or remainder.rstrip("/") in (
                        "", ".", "..", "*", "**", ":"):
                    return True
    return False


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

FIXES = {
    "add-tree-wide": "stage explicit paths: git add path/to/file",
    "commit-all": "git add <paths>, then git commit",
    "reset-destructive": "git restore --source=HEAD -- path/to/file",
    "reset-unstages-all": "unstage your own paths: git reset -- path/to/file",
    "checkout-tree-wide": "name the paths: git restore -- path/to/file",
    "checkout-force": "switch branches without -f, or commit your work first",
    "clean-force": "delete the specific files you created",
    "stash-mutating": "commit to your own branch instead",
    "rm-tree-wide": "name the paths: git rm path/to/file",
    "worktree-force-remove": "let the owning session close its own worktree",
}


def decide_git(argv: Sequence[str]) -> Optional[Tuple[str, str]]:
    """Return (subcommand, rule_id) if this git invocation is tree-wide, else None."""
    args = strip_git_globals(argv[1:])
    if not args:
        return None
    sub = args[0]
    flags, operands, after = split_args(args[1:])
    # Pathspecs are operands plus anything after `--`. For subcommands whose first
    # operand is a revision (checkout/restore/reset), the `--`-separated list is the
    # authoritative pathspec set; operands are only pathspecs when no `--` was used.
    pathspecs = after if after else operands
    if sub in ("commit", "reset"):
        # A bare operand here is a MESSAGE or a REVISION, never a pathspec (`git commit -am wip` ->
        # "wip" is -m's value), so only a `--`-separated list counts.
        pathspecs = after
    elif sub == "stash":
        # `git stash push src/a.py` (no `--`) is the ordinary SCOPED form and stashes
        # only that path, so ITS operands are pathspecs. `git stash save wip` takes a
        # MESSAGE, not a pathspec, so its operands must not be read as scoping.
        if operands[:1] == ["push"]:
            # `-m/--message` consumes the NEXT operand. Reading that message as a
            # pathspec made `git stash push -m wip` look scoped -- and it stashes the
            # whole shared tree, which is the loss this hook exists to prevent.
            rest = operands[1:]
            if has_flag(flags, ("--message",), "m") and not any(
                    f.startswith(("--message=", "-m=")) for f in flags):
                rest = rest[1:]
            pathspecs = rest + after
        else:
            pathspecs = after

    if sub in ("add", "stage"):
        # -A/-u with an explicit non-tree-wide pathspec is SCOPED, and allowed.
        if pathspecs and not tree_wide(pathspecs):
            return None
        if has_flag(flags, ("--all", "--no-ignore-removal", "--update"), "Au"):
            return sub, "add-tree-wide"
        if tree_wide(pathspecs):
            return sub, "add-tree-wide"
        return None

    if sub == "commit":
        if pathspecs and not tree_wide(pathspecs):
            return None
        if has_flag(flags, ("--all",), "a"):
            return "commit", "commit-all"
        return None

    if sub == "reset":
        if has_flag(flags, ("--patch",), "p"):
            return None                      # interactive: the human scopes it
        if has_flag(flags, ("--hard", "--merge", "--keep")):
            return "reset", "reset-destructive"
        # A bare / `--mixed` reset with no pathspec unstages every path ANOTHER session
        # staged in the shared index. Recoverable, but still a tree-wide mutation of the
        # shared object. `--soft` touches no index entry; a pathspec scopes it.
        if not pathspecs and not has_flag(flags, ("--soft",)):
            return "reset", "reset-unstages-all"
        return None

    if sub in ("checkout", "restore", "switch"):
        # `git switch -f` and `--discard-changes` throw away local modifications exactly
        # as `checkout -f` does, so the force rule must NOT be gated to `checkout`.
        if has_flag(flags, ("--force", "--discard-changes"), "f"):
            return sub, "checkout-force"
        if tree_wide(pathspecs):
            return sub, "checkout-tree-wide"
        return None

    if sub == "clean":
        # Without -f/--force git clean refuses to delete anything, so -d/-x alone is
        # not destructive and must not be swept up.
        if has_flag(flags, ("--dry-run",), "n"):
            return None
        if has_flag(flags, ("--force",), "f"):
            return "clean", "clean-force"
        return None

    if sub == "stash":
        if has_flag(flags, ("--patch",), "p"):
            return None                      # interactive: the human scopes it
        # Restorative and read-only forms stay allowed: they can only give work BACK.
        if operands and operands[0] in ("list", "show", "apply", "pop", "drop", "branch", "create", "store"):
            return None
        if pathspecs and not tree_wide(pathspecs):
            return None
        if not operands or operands[0] in ("push", "save", "clear"):
            return "stash", "stash-mutating"
        return None

    if sub == "rm":
        if tree_wide(pathspecs):
            return "rm", "rm-tree-wide"
        return None

    if sub == "worktree":
        if operands[:1] == ["remove"] and has_flag(flags, ("--force",), "f"):
            return "worktree", "worktree-force-remove"
        return None

    return None


def analyse(command: str) -> Optional[Tuple[str, str]]:
    """Tokenise a shell command and return the first tree-wide git finding, if any.

    Raises ValueError if the text cannot be tokenised (caller fails closed).
    """
    text, confident = preprocess(command)
    if not confident:
        raise ValueError("command could not be read with confidence")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    # Comments are already removed by `preprocess`, which still had real newlines to
    # bound them. shlex's own commenter would run after they are gone and would eat
    # the rest of the script -- that exact interaction was a CRITICAL review finding.
    # REDUNDANT-BY-DESIGN: mutation testing confirms the suite stays green if this
    # line is reverted, because `preprocess` already stripped every comment. It stays
    # as a second barrier against precisely the bug that got here once. Do not delete
    # it on the grounds that tests still pass.
    lexer.commenters = ""
    tokens = list(lexer)
    for segment in split_segments(tokens):
        segment = strip_prefixes(segment)
        if not segment:
            continue
        # Unwrap `bash -c '<script>'` / `sh -c '...'` and analyse the inner text.
        if os.path.basename(segment[0]) == "eval":
            # `eval 'git add -A'` -- the whole remaining argv is one script.
            for tok in segment[1:]:
                inner = analyse(tok)
                if inner:
                    return inner
            continue
        if os.path.basename(segment[0]) in SCRIPT_WRAPPERS:
            for i, tok in enumerate(segment[1:], start=1):
                is_c = tok == "-c" or (
                    tok.startswith("-") and not tok.startswith("--") and "c" in tok[1:])
                if is_c and i + 1 < len(segment):
                    # No try/except: an untokenisable inner script must fail CLOSED
                    # exactly as the same text does at the top level.
                    inner = analyse(segment[i + 1])
                    if inner:
                        return inner
                    break
            continue
        if not is_git(segment[0]):
            continue
        found = decide_git(segment)
        if found:
            return found
    return None


def denial_message(subcommand: str, rule: str) -> str:
    """The reason text. Deliberately does NOT say "blocked".

    A registry row may carry `tier: advisory`, in which case dispatch.sh CLAMPS this
    hook's exit 2 and the command runs anyway (that is how the fleet ships it in
    record-only mode). The hook cannot see its own tier, so asserting "blocked" would
    be false half the time. The exit code carries the verdict; this text carries the
    reason.
    """
    return (
        "%s: tree-wide `git %s` - it acts on files another concurrent session "
        "may own, which is how one session's work gets committed or deleted by another. "
        "Instead: %s. The isolation that actually holds is one git worktree per session "
        "(.ai/CONCURRENCY.md). Deliberate solo session? re-run with %s=1."
        % (HOOK_NAME, subcommand, FIXES.get(rule, "scope the command to your own paths"), ESCAPE_ENV)
    )


def read_command() -> Tuple[bool, Optional[str]]:
    """Return (payload_ok, command_text)."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        return False, None
    if not isinstance(payload, dict):
        return False, None
    command = payload.get("tool_input", {}).get("command") if isinstance(
        payload.get("tool_input"), dict) else None
    if command is None:
        command = payload.get("command")
    if command is None:
        return True, None
    return True, command if isinstance(command, str) else None


def main() -> int:
    may_block = blocking_enabled()

    payload_ok, command = read_command()
    if not payload_ok:
        if not may_block:
            hlog("WOULD-BLOCK", "unparseable tool payload")
            return 0
        return deny("%s: unparseable tool payload (fail-closed)" % HOOK_NAME,
                    "?", "payload")
    if not command:
        return 0
    if "git" not in command:
        return 0

    try:
        found = analyse(command)
    except ValueError:
        if not may_block:
            hlog("WOULD-BLOCK", "untokenisable command containing git")
            return 0
        return deny("%s: command contains `git` but cannot be tokenised (fail-closed)"
                    % HOOK_NAME, "?", "untokenisable")

    if not found:
        return 0
    subcommand, rule = found

    if not may_block:
        # DELIBERATE: no wholesale exit 0 - this repo develops under `minimal`, so the
        # decision is still computed and recorded to keep the dogfood signal alive.
        hlog("WOULD-BLOCK", "git %s (%s) - suppressed under minimal" % (subcommand, rule))
        return 0

    if os.environ.get(ESCAPE_ENV) == "1":
        hlog("WARN", "git %s (%s) allowed by %s" % (subcommand, rule, ESCAPE_ENV))
        sys.stderr.write("%s: tree-wide git allowed by %s (logged).\n" % (HOOK_NAME, ESCAPE_ENV))
        return 0

    return deny(denial_message(subcommand, rule), subcommand, rule)


if __name__ == "__main__":
    sys.exit(main())
