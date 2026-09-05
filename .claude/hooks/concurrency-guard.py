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

#: Marks a QUOTED word so `classify_operator` cannot mistake it for the operator it
#: spells. Stripped again in `split_segments`, before any rule reads argv.
QUOTED_WORD_SENTINEL = "\x01"

#: Characters that mean something to the SHELL and nothing to git when quoted. Rounds
#: 21 and 22 covered `<>&|;` and left the GROUPING characters out, so a quoted or
#: escaped `)` was still peeled as a real closer: `git commit -m ")" -a` committed both
#: sessions' files and `git add ")" .` staged both, rc 0 (round 24, verified with a
#: file named `)` present). One set, used by every branch that needs it.
SHELL_ONLY_CHARS = "<>&|;(){}"

#: Shell operators that separate one command from the next. No `\n` member: newlines
#: are converted to `;` by `preprocess` before tokenising, because shlex cannot emit a
#: newline as a token. An earlier version listed `"\n"` here and it was DEAD, which is
#: how "every line after the first is discarded" survived a review round.
OPERATORS = frozenset({";", "&&", "||", "|", "&", "|&"})

#: Tokens that may precede the real command word and must be stepped over.
PREFIX_WORDS = frozenset({
    "sudo", "env", "command", "time", "nice", "nohup", "exec", "builtin",
    # round 21: an unlisted wrapper word makes the segment's command word not `git`,
    # so `is_git` says no and the WHOLE segment is dropped -- `caffeinate git add -A`
    # staged both sessions' files at exit 0 (verified). macOS-native `caffeinate` was
    # the miss; the others are the same shape on Linux.
    "caffeinate", "timeout", "stdbuf", "setsid", "ionice", "chrt", "doas",
    "then", "do", "else", "elif", "if", "while", "until", "!", "{", "(", "((",
    "case", "esac", "in", "for", "select", "function", "coproc", "source", ".",
})

#: Commands whose ARGUMENT is a shell script to be analysed recursively.
SCRIPT_WRAPPERS = frozenset({"bash", "sh", "zsh", "dash", "eval"})

#: Shell-wrapper options that take a SEPARATE value, so the word after them is not a
#: script file (`bash -O extglob`, `bash --rcfile f`). Round 26.
WRAPPER_VALUE_OPTS = frozenset({"-O", "+O", "-o", "+o", "--rcfile", "--init-file"})

#: Subcommands with a real interactive `--patch`. The human confirms every hunk, so the
#: command cannot touch another session's file unattended -- the same reasoning the
#: `reset` and `stash` rules already used, applied to the siblings that lacked it and
#: therefore denied `git add -p .`, ordinary daily usage.
PATCH_SUBCOMMANDS = frozenset({
    "add", "stage", "checkout", "restore", "reset", "stash", "commit",
})

#: `git stash` operands that can only GIVE WORK BACK or read. The stash rule denies by
#: default and this set is what lifts the denial, so an unknown future stash verb fails
#: CLOSED rather than being waved through.
STASH_RESTORATIVE = frozenset({
    "list", "show", "apply", "pop", "drop", "branch", "create", "store",
})

#: git global options taking a separate value argument. Exact membership: git does not
#: abbreviate globals (`git --lit status` -> `unknown option: --lit`), and an
#: unrecognised one now fails CLOSED rather than becoming the "subcommand".
GIT_GLOBAL_WITH_VALUE = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env", "--attr-source", "--list-cmds",
})

#: git global options taking no value.
GIT_GLOBAL_FLAGS = frozenset({
    "-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
    "--icase-pathspecs", "--no-optional-locks", "--html-path", "--info-path",
    # round 19: absent, so each of these made the FLAG the subcommand and disarmed
    # every rule. `--no-literal-pathspecs` is the negation of a member that was
    # already here, which is the sibling-drift shape rounds 5-9, 11, 13 and 14 were.
    # `--no-glob-pathspecs` and `--no-icase-pathspecs` sat here for one execution and
    # do NOT belong: git rejects both (`unknown option`), so they were dead weight --
    # me inventing plausible negations of members that do exist. Caught by
    # `test_git_accepts_every_global_this_hook_lists`, which asks git rather than
    # trusting the author. The negation git really does accept is
    # `--no-literal-pathspecs`.
    "--no-advice", "--no-lazy-fetch", "--no-literal-pathspecs",
    # Round 20: the fail-closed inversion denied these, and the doc justified it with
    # "it is not a command git would run either" -- false, executed: all six run at
    # rc 0, `git --version` is in doctor and CI scripts everywhere, and a denial
    # anywhere in a compound kills the whole call. An over-block with a rationale
    # refuted by execution is the class this file keeps warning about.
    "--version", "-v", "--help", "-h", "--man-path",
})

#: Short options that take a VALUE, per subcommand. Whatever follows one of these
#: letters inside a token is that option's ARGUMENT, not more flags. Scanning it as a
#: flag cluster blocked `git commit -m"refactor"` as `commit -a` and
#: `git checkout -bfeature` as `checkout -f` -- an ordinary commit denied because of
#: the letters in its own message, which is round 1's defect shape (deny the benign
#: command, then prescribe a remediation that does not apply).
VALUE_SHORT_OPTS = {
    "add": "", "stage": "", "reset": "", "rm": "",
    "commit": "mFCctSu",
    "checkout": "bBt",
    "switch": "cCt",
    "restore": "s",
    "clean": "e",
    "stash": "m",
}

#: The subset of `VALUE_SHORT_OPTS` whose value is REQUIRED, and which may therefore
#: take the NEXT token as that value. `-S` (`--gpg-sign`) and `-u`
#: (`--untracked-files`) are deliberately ABSENT: their value is OPTIONAL, so git reads
#: a separate token after them as a PATHSPEC. Verified against git 2.50 -- `git commit
#: -u . -m x` commits every modified tracked file -- so consuming that token would open
#: the very leak this table closes.
REQUIRED_VALUE_SHORT_OPTS = {
    "add": "", "stage": "", "reset": "", "rm": "", "worktree": "",
    "commit": "mFCct",
    "checkout": "bB",
    "switch": "cC",
    "restore": "s",
    "clean": "e",
    "stash": "m",
}

#: Long options whose value is REQUIRED and arrives as the NEXT token, per subcommand.
#: A separate value read as an OPERAND becomes a scoping pathspec, and the scoped-pathspec
#: early return then fires before the flag rule is ever reached: `git commit -am wip
#: --author 'N <n@e.com>'` committed every modified tracked file in the shared tree and
#: exited 0 (round 15, verified against git), as did `git add -A --chmod +x`. The
#: `--opt=value` spelling carries its own value and consumes nothing. `--gpg-sign` and
#: `--untracked-files` are absent for the same reason as `-S`/`-u` above; every member
#: here was confirmed against git 2.50 with `git <sub> <opt>` reporting
#: "requires a value".
REQUIRED_VALUE_LONG_OPTS = {
    "add": frozenset({"--chmod", "--pathspec-from-file"}),
    "stage": frozenset({"--chmod", "--pathspec-from-file"}),
    "commit": frozenset({
        "--message", "--file", "--reuse-message", "--reedit-message", "--template",
        "--author", "--date", "--cleanup", "--trailer", "--squash", "--fixup",
        "--pathspec-from-file",
    }),
    "checkout": frozenset({"--orphan", "--conflict", "--pathspec-from-file"}),
    "switch": frozenset({"--orphan", "--conflict", "--create", "--force-create"}),
    "restore": frozenset({"--source", "--conflict", "--pathspec-from-file"}),
    "clean": frozenset({"--exclude"}),
    "reset": frozenset({"--pathspec-from-file"}),
    "rm": frozenset({"--pathspec-from-file"}),
    "stash": frozenset({"--message", "--pathspec-from-file"}),
    "worktree": frozenset({"--expire", "--reason"}),
}

#: The option that reads its pathspec list from a FILE. The hook cannot know whether
#: that file names one path or `.`, so it is treated as TREE-WIDE -- fail CLOSED.
#: `git rm -r --pathspec-from-file=list.txt` with `.` in the file deleted every tracked
#: file and exited 0 (round 15, verified against git).
PATHSPEC_FROM_FILE = "--pathspec-from-file"


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
    quote_content_at = 0
    # A `$(...)` inside DOUBLE quotes is a command, and it was copied verbatim as
    # quoted data, so shlex yielded one word and the inner command never became a
    # segment: `echo "$(git add -A)"` staged both sessions' paths at rc 0 (verified
    # against git 2.50), as did `x="$(git checkout -f)"` -- the commonest scripted
    # capture spelling there is. The UNQUOTED form was already caught, which is why
    # the doc claimed the whole class was. Inside the substitution the text is
    # processed UNQUOTED, bracketed by `;` so it is its own segment, and the quote is
    # restored at the matching paren.
    # The round-20 splice needed a quote stack and a nesting counter that the main
    # loop unwound; extraction reads the substitution's extent in one scan instead, so
    # both are gone. Leaving the two pushes behind with nothing to pop them made
    # `confident` False for EVERY quoted substitution -- an ordinary
    # `echo "$(git status)"` was denied until the probes caught it.
    #: Command-substitution bodies lifted out of double quotes, analysed as their own
    #: scripts after the outer text so that the outer token stream is never disturbed.
    extra_scripts: List[str] = []

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
            if ch in SHELL_ONLY_CHARS and quote == '"':
                # ALREADY inside double quotes: shlex keeps the character literal, and
                # the quote-close check below adds the sentinel if the whole body turns
                # out to be operator characters. Emitting the round-22 `"..."` wrapper
                # here CLOSED the live quote and severed the command line -- every
                # token after it landed in a segment whose command word was not `git`,
                # so the flag was silently dropped: `git commit -m "wip\;x" -a`
                # committed BOTH sessions' files and `git clean -e "a\;b" -fd` deleted
                # both sessions' untracked files, rc 0 (round 23, verified against git
                # 2.50) -- including the mandated attribution spelling
                # `git commit --author "Claude\;X <...>" -a`. Ninth instance of "a
                # pre-tokenisation transform silently deletes part of a command".
                out.append(ch)
                escaped = False
                i += 1
                continue
            if ch in SHELL_ONLY_CHARS:
                # An ESCAPED operator character is a WORD, exactly as a quoted one is,
                # and round 21's sentinel covered only the quoted branch: `git checkout
                # \> .` still had its `>` classified as a redirection whose target-skip
                # ate the `.`, which DESTROYED both sessions' in-flight edits at rc 0
                # (round 22, verified against git 2.50).
                #
                # It is re-emitted QUOTED, not merely sentinel-prefixed. Two attempts
                # failed first and both were caught by running the probe rather than
                # reading the diff: the backslash already emitted below ESCAPES the
                # sentinel instead of the operator, and even with that fixed, shlex
                # with `punctuation_chars` splits a punctuation character away from an
                # adjacent word character, so `<sentinel>>` still arrived as two
                # tokens. Quoting is what the quoted branch relies on too -- that is
                # the only reason its sentinel survives tokenisation.
                if out and out[-1] == "\\":
                    out.pop()
                out.append('"' + QUOTED_WORD_SENTINEL + ch + '"')
                escaped = False
                i += 1
                continue
            # A line continuation is DELETED by bash, joining the words on either
            # side. Emitting a space SPLIT them instead, so one bash word arrived as
            # two and the extra one read as a scoping pathspec or a second operand:
            # `git reset HEA\<newline>D` emptied the shared index and
            # `git stash push -m a\<newline>b` stashed the whole tree, both rc 0
            # (round 24, verified against git).
            out.append("" if ch == "\n" else ch)
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

        if quote != "'" and command.startswith("$((", i):
            # ARITHMETIC, not a command substitution, in EVERY quote state. This
            # branch was `quote == '"'` only, and once round 25 let the `$(`
            # extraction run unquoted too, the extraction matched `$((` first and
            # swallowed the newline behind it -- `echo $((1+2))` above `git add -A`
            # went from BLOCK to ALLOW, a regression the suite caught immediately.
            # It also replaces the unquoted-only arithmetic branch that used to sit
            # further down, which is now unreachable and deleted rather than left to
            # read as load-bearing.
            # This test has to come
            # BEFORE the `$(` lift below, which `startswith("$(")` also matches. The
            # lift fired first, skipped two characters, left `arith_depth` at 0, and
            # the `<<` inside was then read as a HEREDOC whose invented marker
            # swallowed every following line with `confident` still True:
            # `x="$((1<<2))"\ngit add -A\n2` staged both sessions' files at exit 0
            # (round 21, verified against git). That is the fail-OPEN shape this layer
            # was rewritten to eliminate, arriving inside round 20's own fix.
            #
            # Read to the matching `))` and replaced by a PLACEHOLDER word, the same
            # shape as `$(...)` and `${...}`. Emitting `$((` and letting the contents
            # flow through left `$`, `((`, `))` as separate tokens, and the grouping
            # branch in `split_segments` then started a new segment on the `((` --
            # `git commit -m $((1)) -a` lost its `-a` and exited 0. A placeholder also
            # makes the `<<`-inside-arithmetic suppression automatic, so `arith_depth`
            # has no remaining purpose and is gone: one mechanism for all three
            # expansions instead of three.
            depth = 1
            j = i + 3
            while j < n and depth:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                    if not depth and command[j:j + 2] == "))":
                        j += 1
                        break
                j += 1
            if depth:
                confident = False          # unclosed: the text was not understood
                break
            out.append('"' + QUOTED_WORD_SENTINEL + '"')
            i = j + 1
            continue

        if quote != "'" and command.startswith("$(", i):
            # In ANY quote state except single quotes. Round 23 gated this on
            # `quote == '"'`, so the UNQUOTED spelling still went out verbatim: shlex
            # made `(` and `)` their own tokens, `split_segments` treated them as
            # grouping, and the flag behind the expansion landed in a segment whose
            # command word was not `git`. `git commit -m $(cat VERSION) -a` and
            # `git commit -m $((1)) -a` committed BOTH sessions' files and
            # `git clean -e $(cat p) -fd` deleted both sessions' untracked files, all
            # rc 0 (round 24, verified against git) -- tenth instance of this class and
            # the third round running whose leak sat inside the previous round's fix.
            # EXTRACTED, not spliced. Round 20 bracketed the substitution with `;`
            # inside the outer text, which split the git invocation itself: every token
            # AFTER the substitution landed in a segment whose command word was not
            # `git`, so `git commit -m "release $(cat VERSION)" -a` lost its `-a` and
            # committed BOTH sessions' files at rc 0 (round 23, verified against git).
            # Only tokens after the substitution were affected, which is why every
            # existing test missed it -- they all put the substitution last or alone.
            # The body is analysed as its own script, appended after the outer text, so
            # the outer quoting survives untouched.
            depth = 1
            j = i + 2
            inner_quote = ""
            while j < n and depth:
                c = command[j]
                if inner_quote:
                    if c == inner_quote:
                        inner_quote = ""
                elif c in "'\"":
                    inner_quote = c
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if not depth:
                        break
                j += 1
            if depth:
                confident = False          # unbalanced: we did not read the text
                break
            extra_scripts.append(command[i + 2:j])
            # A PLACEHOLDER word takes the expansion's place, so the outer token stream
            # keeps the same shape whether the expansion was quoted or not: removing it
            # outright left `-m` with nothing to consume and the flag behind it became
            # the message instead.
            out.append('"' + QUOTED_WORD_SENTINEL + '"')
            i = j + 1
            continue

        if quote:
            if ch == quote:
                quote = ""
                # `shlex` discards quoting, so `classify_operator` cannot tell the
                # WORD `>` from the OPERATOR `>`. A quoted operator-only token was
                # classified as a redirection and its `skip_next` then swallowed the
                # argument behind it: `git add '>' .` dropped the `.` and staged both
                # sessions' files at exit 0 (round 21, verified against git with a
                # file named `>` present). A sentinel makes the token no longer
                # operator-only; `split_segments` strips it before argv is read.
                body = "".join(out[quote_content_at:])
                if body and all(c in SHELL_ONLY_CHARS for c in body):
                    out.insert(quote_content_at, QUOTED_WORD_SENTINEL)
            out.append(ch)
            i += 1
            continue

        if ch in "'\"":
            quote = ch
            quote_content_at = len(out) + 1
            out.append(ch)
            i += 1
            continue

        # --- unquoted from here ------------------------------------------------
        if ch == "#" and at_token_boundary():
            while i < n and command[i] != "\n":
                i += 1
            continue

        if not quote and command[i:i + 2] in ("<(", ">("):
            # In ANY position within a word, not only at a token boundary: bash
            # performs process substitution mid-word (`echo x<(echo y)` prints
            # `x/dev/fd/63`). Gated on the boundary, a GLUED `<(` went out verbatim,
            # `classify_operator` read it as a separator, and the flag behind it was
            # dropped -- `git commit -m x<(echo y) -a` committed both sessions' files
            # and `git clean -e p<(echo y) -fd` deleted both sessions' untracked work,
            # rc 0 (round 26, verified against bash + git).
            # PROCESS SUBSTITUTION is a word whose body is a command, exactly like
            # `$(...)`: the body is lifted out and read as its own script, and a
            # placeholder holds the word's place. Classifying `<(` as a separator in
            # `split_segments` had put the tokens AFTER the closing paren in a new
            # segment, so `git commit -m <(echo x) -a` lost its `-a` -- found by the
            # widened metamorphic ratchet on its first run, round 25.
            depth = 1
            j = i + 2
            inner_quote = ""
            while j < n and depth:
                c = command[j]
                if inner_quote:
                    if c == inner_quote:
                        inner_quote = ""
                elif c in "'\"":
                    inner_quote = c
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if not depth:
                        break
                j += 1
            if depth:
                confident = False
                break
            extra_scripts.append(command[i + 2:j])
            out.append('"' + QUOTED_WORD_SENTINEL + '"')
            i = j + 1
            continue

        if quote != "'" and command.startswith("${", i):
            # One opaque WORD, read to its matching brace. There was no `${` extent at
            # all, so a `;` inside an unquoted parameter expansion fell through to the
            # operator path and SEPARATED the command: `git commit -m ${x:-a;b} -a`
            # committed both sessions' files at rc 0, and bash keeps it one word
            # (`echo ${x:-a;b}` prints `a;b`) -- round 24, verified.
            depth = 1
            j = i + 2
            inner_quote = ""
            while j < n and depth:
                c = command[j]
                # Quote-aware like the `$(` scan: `${x:-"}"}` has a `}` INSIDE quotes,
                # and closing on it left an unbalanced quote behind that failed the
                # whole read-only command closed (`git commit -m ${x:-"}"} src/a.py`
                # exited 2 -- found probing this fix, round 25).
                if inner_quote:
                    if c == inner_quote:
                        inner_quote = ""
                elif c in "'\"":
                    inner_quote = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if not depth:
                        break
                j += 1
            if depth:
                confident = False
                break
            out.append('"' + QUOTED_WORD_SENTINEL + '"')
            i = j + 1
            continue

        if command.startswith("((", i) and at_token_boundary():
            # The bash arithmetic COMMAND `(( 1 << 2 ))` is not `$((`, so the guard
            # below never saw it and its `<<` became a heredoc marker too, swallowing
            # the commands after it (`(( 1 << 2 ))\ngit checkout -f\n2` exit 0,
            # verified). Only at a token boundary, so a subshell-in-subshell `((` from
            # `( (echo x) )` is untouched -- `split_segments` handles grouping.
            depth = 1
            j = i + 2
            while j < n and depth:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                    if not depth:
                        break
                j += 1
            if depth:
                confident = False
                break
            out.append('"' + QUOTED_WORD_SENTINEL + '"')
            i = j + 1
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
            # The marker is CONSUMED here, so the `<<` token that reaches
            # `split_segments` had no target left -- and the redirection's target-skip
            # ate the next REAL argument instead: `git commit -m x <<EOF -a` lost its
            # `-a` and committed BOTH sessions' files at rc 0 (round 26, found probing;
            # verified against bash + git, where `-a` after the marker is still git's
            # argument). A placeholder stands in for the marker so the skip lands on it.
            out.append('<< "' + QUOTED_WORD_SENTINEL + '"')
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

    for script in extra_scripts:
        # RECURSIVELY, so a substitution nested inside another one is read too:
        # appending the raw text left the inner `$(` as quoted data and
        # `echo "$(echo "$(git add -A)")"` exited 0. An inner text that cannot be read
        # makes the whole command unreadable, exactly as at the top level.
        inner_text, inner_confident = preprocess(script)
        out.append(";" + inner_text + ";")
        confident = confident and inner_confident
    if quote or escaped or pending_markers:
        # An arithmetic expansion that never closes means the `<<` suppression above may
        # have swallowed a real heredoc, so the text was NOT understood. Fail closed.
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
    if body[:1] in ("<", ">") and "(" in body:
        # Process substitution `<(cmd)` / `>(cmd)`. The paren opens a NEW command, so
        # this is a SEPARATOR: the inner text is still analysed as its own segment and
        # the operator never reaches argv. Left as an argument it read as a scoping
        # pathspec and `git add -A <(echo hi)` was allowed.
        return "separator"
    if not body or not all(ch in "<>&|;" for ch in body):
        return ""
    if body[:1] in ("<", ">") and ";" not in body and "&&" not in body:
        # A run that BEGINS with a redirection character and carries no separator is
        # one redirection operator -- `>|` (noclobber override), `>&`, `<>`, `>>`. The
        # separator-first rule below read the `|` in `>|` as a PIPE, which severed the
        # command at the redirection and dropped every flag behind it:
        # `git commit -m wip >| out -a` committed BOTH sessions' files and
        # `git clean -e p >| out -fd` deleted both sessions' untracked files, rc 0
        # (round 25, verified against bash + git). `<<;` -- a heredoc glued to the
        # separator behind it -- still carries a `;` and stays a separator.
        return "redirection"
    if any(ch in ";|" for ch in body) or "&&" in body:
        return "separator"
    if "<" in body or ">" in body:
        return "redirection"
    if body == "&":
        return "separator"
    return ""


def is_redirection(token: str) -> bool:
    return classify_operator(token) == "redirection"


def split_segments(tokens: Sequence[str]) -> List[Tuple[List[str], bool]]:
    """Split a token stream into commands, each with whether its STDIN is FED.

    "Fed" means the command line supplies stdin -- the right operand of a `|`, or a
    `<` / `<<<` redirection. That flag is what the `--patch` exemption needs: the
    exemption exists because a human confirms every hunk, and `yes | git commit -p -m
    wip .` committed BOTH sessions' files while `yes | git checkout -p .` destroyed
    another session's edit (round 18, verified against git 2.50). The hook was already
    LOOKING at the evidence and throwing it away -- `|` and `<` are classified here and
    dropped -- so the fix is to keep one bit of it rather than to add a new layer.

    Every new segment is started through `start_segment`, not by appending to the list
    directly, because two parallel lists that some branches update and others forget is
    exactly the shape of rounds 13, 14 and 15.
    """
    segments: List[List[str]] = [[]]
    fed: List[bool] = [False]
    # Index of the segment a just-CLOSED group began at. A redirection attached to the
    # group (`{ git checkout -p .; } < ans`) feeds every command INSIDE it, but the
    # closer has already started a new segment by the time the `<` is read, so marking
    # only `fed[-1]` marked an empty segment and the git command kept `fed=False`.
    # Verified against git 2.50: that spelling DESTROYED both sessions' in-flight edits
    # unattended at rc 0 -- round 19's leak in the redirection spelling, the third time
    # in five rounds that a fix carried the next leak.
    group_starts: List[int] = []
    closed_group_at: Optional[int] = None

    def start_segment(stdin_fed: bool = False) -> None:
        segments.append([])
        fed.append(stdin_fed)

    skip_next = False
    for raw in tokens:
        # `punctuation_chars` collapses a RUN of operator characters into one token, so
        # a blank line between commands arrives as `;;` and an `||` as a single token.
        # Anything made only of operator characters is a separator.
        #
        # A CLOSING group can arrive GLUED to the separator that follows it -- `);`,
        # `));`, `)&&`, `))` from an arithmetic expansion. Such a token is neither a
        # bare `)` nor a pure operator run, so classifying it whole returned "not an
        # operator": the separator was lost, the next command merged into the previous
        # segment, and its command word was no longer `git`. `(echo x); git add -A`,
        # `x=$(date); git add -A` and `echo $((1+2))` on the line above `git add -A`
        # were all ALLOWED. Peel the closing groups off FIRST, then classify what is
        # left -- losing a separator is the fail-open direction and the class that
        # produced the CRITICALs in rounds 1-3 and again in round 6.
        core = raw.lstrip(")}")
        if raw and all(ch in "{}" for ch in raw) and segments[-1]:
            # A brace is a reserved word ONLY in command-word position; anywhere else
            # `{`, `}` and `{}` are ordinary words (`bash -c 'echo A {} B'` prints them).
            # Round 24 fixed the bare `}` on that premise but gated it on `not
            # group_starts`, so `{ git commit -m } -a; }` -- the same command merely
            # WRAPPED -- lost its `-a` again; and it never covered the opener at all, so
            # `git commit -m { -a` and `git clean -e { -fd` reached the whole tree
            # (round 25, all verified against git). Deciding by POSITION -- is there a
            # command word in this segment already? -- covers opener, closer and
            # `{}` in one rule, grouped or not. `(`/`)` keep their handling: bash
            # rejects a bare paren as an argument, so it can only ever be grouping.
            segments[-1].append(raw)
            continue
        if core != raw:
            closed_group_at = group_starts.pop() if group_starts else len(segments) - 1
            start_segment(fed[-1])
            if not core:
                continue
        if not raw:
            # An EMPTY argument is an argument, not a separator. `all()` over an empty
            # string is True, so the grouping branch below swallowed `""` and STARTED A
            # NEW SEGMENT -- which split the command and dropped every flag after it.
            # Round 23's substitution extraction leaves exactly that token behind
            # (`git commit -m "" -a`), so `git commit -m "$(date)" -a` and
            # `git clean -e "$(cat p)" -fd` both exited 0 with their `-a`/`-fd` in a
            # segment of their own. Latent before, reachable now.
            #
            # It is KEPT, not skipped: git reads `-m ""` as an option with an empty
            # value, so the flag behind it is a FLAG. Dropping the token instead let
            # `-m` swallow the `-a` as its message and `git commit -m "" -a` exited 0 --
            # the same fail-open one step further along, caught by re-running the probe.
            segments[-1].append("")
            continue
        if all(ch in "(){}" for ch in core):
            # A run of grouping punctuation is never an argument. `()` from a FUNCTION
            # DEFINITION arrives as one token that the peel above cannot touch (it does
            # not START with a closer), so `stage() { git add -A; }` kept `()` in argv,
            # the command word became `stage`, `is_git` said no, and the whole segment
            # -- literal `git add -A` included -- was dropped.
            start_segment(fed[-1])
            if any(ch in "({" for ch in core):
                # Remember where this group's commands begin. The push HAS to happen
                # here: a bare `(` or `{` is consumed by THIS branch, so pushing it in
                # the later `elif` never ran, and `{ git checkout -p .; } < ans` still
                # marked the wrong segment -- the `;` before `}` had already started an
                # empty one. The `(` spelling only appeared fixed by luck, because with
                # no `;` the fallback index happened to be the git command's.
                group_starts.append(len(segments) - 1)
            continue
        tok = core
        kind = classify_operator(tok)
        # An INPUT redirection feeds the CURRENT segment's stdin, and that must be
        # recorded before the token is classified any further -- `punctuation_chars`
        # fuses a run of operator characters, so a heredoc arrives GLUED to the
        # separator that follows it (`git add -p . <<EOF` preprocesses to `... <<;`,
        # one token `<<;`). Classified whole it read as a SEPARATOR, the redirection
        # meaning was lost, and the `--patch` exemption came back: verified against
        # git 2.50, `git add -p . <<EOF\ny\ny\nEOF` staged BOTH sessions' files at
        # exit 0, while the identical `<<<` and `<` spellings blocked. Same class as
        # rounds 18 and 19, third spelling -- and the same fused-token trap that cost
        # rounds 1-3 and 6 their separators.
        if "<" in tok:
            fed[-1] = True
            # The redirection belongs to the group that just closed -- every command
            # inside it read from that file -- and when no group closed we cannot tell
            # WHICH commands it feeds: `while read x; do git add -p .; done < f` hangs
            # the redirection off `done`, and `do`/`done` are not grouping tokens, so
            # tracking them would mean a shell grammar. Every segment is marked
            # instead, which closes the CLASS rather than one more spelling -- the fix
            # for the fix for the fix, three rounds running, is the argument for taking
            # the whole class. The cost is an over-block: an input redirection anywhere
            # in the command text denies an interactive `-p` elsewhere in it
            # (`cat < f; git add -p .`), named in the doc's residuals next to the
            # `;`-sibling one. `fed` only ever gates the `--patch` exemption, so
            # nothing that does not carry `-p` changes verdict.
            start = closed_group_at if closed_group_at is not None else 0
            for idx in range(start, len(fed)):
                fed[idx] = True
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
            # The right operand of a PIPE reads its stdin from the left one; every
            # OTHER separator starts a sibling that INHERITS the stdin of the compound
            # it sits in. Resetting to False there -- and in the grouping branches
            # above -- discarded round 18's whole fix the moment the command was
            # wrapped: `yes | (git checkout -p .)` DESTROYED another session's
            # in-flight edit and `yes | { git commit -p -m wip .; }` committed both
            # sessions' files, exit 0, while the identical UNWRAPPED spellings blocked
            # (round 19, verified against git 2.50). A subshell does not give a human
            # back the keyboard: grouping never changes stdin.
            start_segment(True if "|" in tok else fed[-1])
        elif tok.strip("({") == "":
            # An OPENING group is not an argument -- the command word follows it. (A
            # CLOSING group already ended its command above: dropped silently it merged
            # two commands, so in `diff <(git add -A) b` the word `b` joined the inner
            # segment and read as a scoping pathspec, and in
            # `case $x in a) git add -A;; esac` the label `a` became the command word.)
            continue
        else:
            # REDUNDANT-BY-DESIGN, and named as such rather than left to read as
            # load-bearing: mutation testing (round 22) shows removing this strip
            # changes no verdict, because a sentinel is only inserted when the quoted
            # body is ENTIRELY operator characters, so such a token can only ever be a
            # pathspec -- and `\x01>` is non-tree-wide exactly as `>` is. It stays so
            # that a future rule which DOES read such a token gets the real word, the
            # same posture this file takes for `lexer.commenters`.
            segments[-1].append(tok.replace(QUOTED_WORD_SENTINEL, ""))
            # A real word ends any pending group-close: a redirection further along the
            # line belongs to that word's command, not to the group behind it.
            closed_group_at = None
    return [(s, f) for s, f in zip(segments, fed) if s]


def strip_prefixes(segment: Sequence[str]) -> List[str]:
    """Step over `sudo`, `env`, `VAR=val`, shell keywords and grouping tokens."""
    out = list(segment)
    saw_prefix = False
    while out:
        head = out[0]
        if head in PREFIX_WORDS:
            out = out[1:]
            saw_prefix = True
            continue
        if saw_prefix and head.startswith("-") and head != "-":
            # A wrapper's OWN option sits between it and the real command:
            # `sudo -u me git add -A`, `nice -n 10 ...`, `env -i ...`, `time -p ...`.
            # Left in place the option became the command word, `is_git` said no, and
            # the whole segment -- git call included -- was dropped.
            out = out[1:]
            continue
        if saw_prefix and len(out) > 1 and is_git(out[1]) and not is_git(head):
            # The VALUE of such an option (`-u me`, `-n 10`): a bare word directly in
            # front of the command word. Stepping over it can only over-block, and only
            # for `<wrapper> <word> git ...`, which is not a real invocation.
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


#: `-c` keys whose VALUE changes what a command means or whether it is destructive.
#: The hook already parses these tokens and used to throw them away, which is the very
#: argument this file makes about evidence it is holding.
#: `include.path` / `includeIf.*` pull in a whole config FILE, so an alias can arrive
#: one indirection further out: `git -c include.path=<file> st` with `[alias] st = add
#: -A` in that file staged both sessions' files at rc 0 (round 22, verified). git's
#: config sections are case-insensitive, which `_config_is_opaque` already handles.
#: `help.autocorrect` decides WHICH SUBCOMMAND git runs: with it set,
#: `git -c help.autocorrect=immediate addd -A` really executes `add -A` and staged both
#: sessions' files, and `... cleann -fd` deleted both sessions' untracked files, at
#: rc 0 (round 23, verified). `decide_git` read the typo as the subcommand, matched no
#: rule and returned None. A fourth key for the class round 21 opened.
OPAQUE_CONFIG_PREFIXES = (
    "alias.", "clean.requireforce", "include.", "includeif.", "help.autocorrect",
)


def _config_is_opaque(setting: str) -> bool:
    """True when a `-c key=value` decides something this hook cannot then model.

    `git -c alias.st='add -A' st` makes the command word an ALIAS whose expansion only
    git knows, and `git -c clean.requireForce=false clean -d` DELETED another session's
    untracked file and subdirectory at rc 0 (round 21, both verified) -- because the
    `clean` rule's premise, that git refuses to delete without `-f`, is config-dependent
    and the config was in the command text. Both fail CLOSED rather than being
    enumerated away, the same inversion round 19 chose for unknown globals.
    """
    key = setting.split("=", 1)[0].strip().lower()
    return any(key == p or key.startswith(p) for p in OPAQUE_CONFIG_PREFIXES)


class UnknownGitGlobal(ValueError):
    """An option before the subcommand that this hook does not model.

    Raised rather than tolerated. `strip_git_globals` used to `break` on the first
    token it did not recognise, so the OPTION became `sub`, matched no rule, and
    `decide_git` returned None -- one ordinary flag disarmed add, commit, reset,
    checkout, clean and stash at once. Round 19, verified against git 2.50:
    `git --no-lazy-fetch add -A` staged both sessions' files,
    `git --no-literal-pathspecs reset --hard` destroyed another session's edit, and
    `git --attr-source=HEAD clean -fd` deleted its untracked file. All are documented
    globals, not obfuscation.

    Enumerating the four missing members would have been the fifth hand-patch in this
    class (`:(top,glob)` r5, `--pathspec-from-file=` r15, long-option prefixes r16,
    `add -e`/`-i` r18, globals r19), so the FAIL DIRECTION is inverted instead: an
    unknown pre-subcommand option is now indistinguishable from text this hook cannot
    read, and takes the same fail-CLOSED path. The known members are still listed,
    because they must NOT block.
    """


def strip_git_globals(args: Sequence[str]) -> List[str]:
    """Drop git's pre-subcommand global options (`-C dir`, `--git-dir=...`, `-c k=v`).

    Raises `UnknownGitGlobal` for an unrecognised option before the subcommand.
    """
    out = list(args)
    while out:
        head = out[0]
        if head in GIT_GLOBAL_FLAGS:
            out = out[1:]
            continue
        if head in ("-c", "--config-env") and len(out) > 1 and _config_is_opaque(out[1]):
            # BEFORE the generic value-consuming branch below, which matched `-c`
            # first and threw the setting away before anything could read it.
            raise UnknownGitGlobal(out[1])
        if head in GIT_GLOBAL_WITH_VALUE:
            out = out[2:] if len(out) > 1 else []
            continue
        if head.startswith("--") and "=" in head and head.split("=", 1)[0] in GIT_GLOBAL_WITH_VALUE:
            # The FUSED spelling needs the same opacity test as the separate one, and
            # not having it restored round 21's two BLOCKING leaks in full for the cost
            # of one `=`: `git --config-env=alias.st=AL st` staged both sessions' files
            # and `--config-env=clean.requireForce=RF clean -d` deleted both untracked
            # files, rc 0, verified against git 2.50. Round 22, and the SEVENTH
            # "one site updated, its sibling missed" -- which is why the parity is now
            # asserted mechanically for every valued global instead of per spelling.
            if head.split("=", 1)[0] in ("-c", "--config-env"):
                if _config_is_opaque(head.split("=", 1)[1]):
                    raise UnknownGitGlobal(head)
            out = out[1:]
            continue
        # Fused short form: -C/tmp/x or -cuser.name=x
        if len(head) > 2 and head[:2] in ("-C", "-c"):
            if head[:2] == "-c" and _config_is_opaque(head[2:]):
                raise UnknownGitGlobal(head)
            out = out[1:]
            continue

        if head.startswith("-") and head != "-":
            # Not a subcommand and not a global we model: fail CLOSED. git does NOT
            # abbreviate globals (`git --lit status` -> `unknown option: --lit`), so
            # exact membership above is right and this branch cannot be reached by an
            # abbreviation of a known one.
            raise UnknownGitGlobal(head)
        break
    return out


def split_args(
    args: Sequence[str],
    value_letters: str = "",
    required_letters: str = "",
    long_value_opts: frozenset = frozenset(),
) -> Tuple[List[str], List[str], List[str]]:
    """Return (flags, operands, pathspecs_after_dashdash).

    `--` is honoured as end-of-options, so `git add -- -A` treats `-A` as a FILENAME.

    An option's SEPARATE value is consumed here and lands in NEITHER list -- not in
    `operands`, where it became a scoping pathspec (`git commit -am wip --author
    'N <n@e.com>'`, `git add -A --chmod +x`, round 15), and not in `flags`, where it
    impersonated an EXEMPTION (`git commit -a -m --dry-run`, `git clean -f -e -n`,
    `git stash push -m --patch`, round 17). Both spellings reached the whole shared tree
    and exited 0. NEITHER list is the whole rule, and the two halves were found two
    rounds apart because round 15 shipped the sentence "keeping it in `flags` can only
    ADD a denial, never lift one" -- which is false, since `flags` is where the
    exemptions are read from.
    """
    flags: List[str] = []
    operands: List[str] = []
    after: List[str] = []
    seen_dashdash = False
    skip_next = False
    for tok in args:
        if seen_dashdash:
            after.append(tok)
            continue
        consume, skip_next = skip_next, False
        # A consumed value is dropped UNCONDITIONALLY -- it is neither a flag nor a
        # pathspec. Round 16 kept an option-LOOKING value in `flags` on the reasoning
        # that this "can only ADD a denial, never lift one". That reasoning was wrong,
        # and round 17 refuted it by executing: `flags` is the SAME list the EXEMPTIONS
        # are read from, so a value beginning with `-` injects one. `git commit -a -m
        # --dry-run` committed BOTH sessions' files, `git clean -f -e -n` deleted both
        # sessions' untracked files, and `git stash push -m --patch` stashed the whole
        # shared tree -- every one exit 0, every one verified against git 2.50.
        # Dropping instead cannot lift a denial, and its own cost is bounded: the
        # command git would actually RUN is either refused by git (`--chmod param '-A'
        # must be either -x or +x`, `invalid date format: -a`, `ambiguous option: d`)
        # or genuinely scoped (`git commit -m -a` commits only what was staged --
        # verified, the second file stayed dirty). A tree-wide PATHSPEC is unaffected,
        # because a pathspec is not the token directly behind the option.
        if consume:
            continue
        if tok == "--":
            seen_dashdash = True
        elif tok.startswith("-") and tok != "-":
            flags.append(tok)
            skip_next = option_needs_next_token(
                tok, value_letters, required_letters, long_value_opts)
        else:
            operands.append(tok)
    return flags, operands, after


def is_short_cluster(flag: str) -> bool:
    """True for `-am`, `-fd`, `-A` - a single-dash token that is not a bare `-`."""
    return flag.startswith("-") and not flag.startswith("--") and flag != "-"


def strip_fused_value(flag: str, value_letters: str) -> str:
    """Drop the ARGUMENT fused to a value-taking short option.

    `-m"refactor"` arrives from shlex as `-mrefactor` and means `-m` with the message
    `refactor`, NOT the cluster `-m -e -f -a -c -t -o -r`. Everything from the first
    value-taking letter onward is that option's value, so it is cut before any cluster
    scan. `-fd` (no value letter) is untouched.
    """
    if not value_letters or not is_short_cluster(flag):
        return flag
    for idx, ch in enumerate(flag[1:], start=1):
        if ch in value_letters:
            return flag[:idx + 1]
    return flag


def fused_short_value(flag: str, value_letters: str, letter: str) -> Optional[bool]:
    """Whether `letter`'s value is FUSED to this token.

    Returns None when the token does not carry `letter` as its value-taking option,
    True when the value is fused (`-mwip`), False when it still needs the NEXT operand
    (`-m wip`). The difference decides whether an operand is a message or a pathspec.
    """
    if not is_short_cluster(flag):
        return None
    for idx, ch in enumerate(flag[1:], start=1):
        if ch in value_letters:
            if ch != letter:
                return None
            return idx + 1 < len(flag)
    return None


def option_needs_next_token(
    flag: str,
    value_letters: str,
    required_letters: str,
    long_value_opts: frozenset,
) -> bool:
    """True when this option's value is the NEXT token, so that token is not a pathspec.

    ONE consumption model for every subcommand and every option. It replaced
    `message_needs_operand`, which modelled `-m` alone: every OTHER value-taking option's
    separate value stayed an operand, became a scoping pathspec, and disarmed the flag
    rule above it (`git commit -am wip --author 'N <n@e.com>'`, `git add -A --chmod +x`
    -- both verified tree-wide against git, both exit 0 before round 15). Rounds 13 and
    14 were each a code path carrying its own copy of a shared rule, so this one is
    shared rather than repeated per branch.

    A LONG option consumes the next token only in its separate spelling: `--message=wip`
    carries its own value. A SHORT cluster is scanned for the FIRST value-taking letter,
    exactly as `strip_fused_value` cuts it -- scanning for a required letter directly
    would misread `-Sm` (where `-S` already swallowed the `m`) as a separated `-m`. That
    letter consumes the next token only when its value is REQUIRED and not already
    fused: `-mwip` carries its message, `-m wip` does not, and `-u`/`-S` never consume
    because git's own value for them is optional.
    """
    if flag.startswith("--"):
        # By PREFIX, through the same matcher the denials use. Leaving this one exact
        # while round 16 made the denials prefix-matched put round 15's defect back
        # inside round 16's dimension: `git add -A --chm +x` staged both sessions'
        # files and `git stash push --mes wip` stashed the whole tree, both exit 0
        # (verified against git 2.50). The safety argument is the one in
        # `matches_long`: an ambiguous abbreviation is refused by git, so consuming
        # its value cannot enable a command git would run.
        return "=" not in flag and matches_long(flag, long_value_opts, exact=False)
    if not is_short_cluster(flag):
        return False
    for idx, ch in enumerate(flag[1:], start=1):
        if ch in value_letters:
            return ch in required_letters and idx + 1 == len(flag)
    return False


def matches_long(base: str, long_names: Sequence[str], exact: bool) -> bool:
    """Whether git would resolve `base` to one of `long_names`.

    git resolves any UNAMBIGUOUS PREFIX of a long option, so an exact-match denylist has
    a legal spelling for every rule it carries. Verified against git 2.50: `git add
    --al` stages the whole tree, `git add --up` stages every tracked modification,
    `git checkout --fo` destroys another session's edits, `git clean --fo` deletes
    untracked work, and `git rm -r --pathspec-fr=list.txt` deleted every tracked file --
    all exit 0 before round 16, and none of them obfuscation: these are spellings git
    documents as supported.

    Prefix matching cannot cause a WRONG denial, and that argument is what makes it safe
    rather than merely stricter. The names compared are exactly the options valid for
    THIS subcommand, so if `base` is a prefix of one of them, git sees at least that
    candidate: either it is the only one, and git resolves to the option being denied --
    so denying is correct -- or there are several, and git refuses the command itself, so
    denying costs nothing.

    EXEMPTIONS pass `exact=True` and stay equality tests, deliberately. Prefix-matching
    an ALLOWLIST is the fail-OPEN direction -- an abbreviation that resolved to some
    other option would lift a denial -- and this hook has been rejected three times for
    an allowlist doing more than it could prove. The price is that an abbreviated
    exemption over-blocks (`git add --dry-ru -A` is denied), which is named in the doc.
    """
    if exact:
        return base in long_names
    # No minimum length: `--` never reaches here (`split_args` consumes it as
    # end-of-options), and a length floor was measured NOT to change any verdict, so it
    # would have shipped as a line no test could bind.
    if not base.startswith("--"):
        return False
    return any(name.startswith(base) for name in long_names)


def has_flag(
    flags: Sequence[str],
    long_names: Sequence[str],
    short_letters: str = "",
    exact: bool = False,
) -> bool:
    """True if any long flag matches, or any short CLUSTER contains a listed letter.

    Callers pass flags already run through `strip_fused_value`, so a short cluster here
    is only flag letters.

    A long name matches by unambiguous PREFIX unless `exact=True`. That polarity is
    chosen so the DEFAULT is the fail-closed one: a denial added later is abbreviation-
    proof without the author thinking about it, and an exemption added later that forgets
    `exact=True` over-blocks rather than leaking. Rounds 13, 14 and 15 were each one site
    updated and its siblings not, so the safe behaviour is the one you get by saying
    nothing.
    """
    for flag in flags:
        base = flag.split("=", 1)[0]
        if matches_long(base, long_names, exact):
            return True
        if short_letters and is_short_cluster(flag):
            if any(letter in flag[1:] for letter in short_letters):
                return True
    return False


def collapse_dot_segments(pathspec: str) -> str:
    """Collapse `.` and `..` components lexically: `a/../..` -> `..`, `./*` -> `*`.

    Only a LEADING run of `../` used to be normalised, so `git add a/../..` walked up
    to the repo root and staged everything (verified against git) while the identical
    `..` and `../..` both blocked.
    """
    out: List[str] = []
    for part in pathspec.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if out and out[-1] != "..":
                out.pop()
            else:
                out.append("..")
            continue
        out.append(part)
    return "/".join(out)


def is_negative_pathspec(pathspec: str) -> bool:
    """True for a pathspec that only EXCLUDES: `:!x`, `:^x`, `:(exclude)x`, `:(top,exclude)x`.

    A pathspec list made only of negatives matches EVERYTHING ELSE, so a negative never
    scopes a command. Verified against git: `git add ':!nope'` stages every modified
    file in the tree. Reading one as a narrowing pathspec inverts the meaning, which is
    how `git add -A ':!node_modules'` -- ordinary usage, not obfuscation -- was allowed.
    """
    if pathspec.startswith((":!", ":^")):
        return True
    if pathspec.startswith(":("):
        close = pathspec.find(")")
        if close != -1:
            return "exclude" in {k.strip() for k in pathspec[2:close].split(",")}
    return False


def is_tree_wide_token(pathspec: str, wildmatch: bool = True) -> bool:
    """True if this ONE token means the whole tree, ignoring any magic prefix.

    `wildmatch=False` for a `:(literal)` remainder: that signature turns git's PATTERN
    matching off, so `*` and `?` are ordinary characters there. It does NOT turn path
    resolution off -- `:(literal)a/../..` still walks to the repo root and stages
    everything (verified against git). Passing a flag to this ONE normaliser is the
    point: the previous shape gave the `literal` branch its own membership-only test,
    which skipped the dot collapse and failed OPEN. A keyword must not be able to opt
    out of normalisation by having its own copy of the rule.

    Membership in `TREE_WIDE_PATHSPECS` is the enumerated part, and enumeration was
    losing a race against git's wildmatch grammar: `./*`, `?*`, `*?`, `[a-z.]*` each
    stage the entire tree (verified) and none of them was a member. So the real test is
    STRUCTURAL -- a pathspec whose FIRST path component carries a wildmatch metacharacter
    can match any top-level entry, and therefore reaches the whole tree. `src/*` keeps
    its literal first component and stays scoped.
    """
    if pathspec in TREE_WIDE_PATHSPECS:
        return True
    # `.` and `..` components are collapsed LEXICALLY first. `./*` is `*`; `../..`
    # walks up to the repo root from a subdirectory and stages everything (verified);
    # and so does `a/../..`, which a leading-run strip could not see -- only the
    # enumerated `..` spelling used to catch any of them.
    stripped = collapse_dot_segments(pathspec)
    while stripped.startswith("../") or stripped == "..":
        stripped = stripped[3:] if stripped.startswith("../") else ""
    if stripped.rstrip("/") in ("", ".", "..", "*", "**", ":"):
        return True
    if not wildmatch:
        return False
    first = stripped.split("/", 1)[0]
    # `*` and `?` WIDEN a match, so a first component carrying either can name any
    # top-level entry. `[` does NOT: a bracket expression matches exactly one
    # character, so it can never reach further than a literal name -- and including it
    # denied `git add 'notes[1].md'`, a scoped stage of a real tracked file (one fleet
    # repo has three such names under `.run/`), while binding no behaviour at all.
    return bool(first) and any(ch in "*?" for ch in first)


def tree_wide(pathspecs: Sequence[str]) -> bool:
    """True if any pathspec means the whole tree. Whole-token compare: `.ai/x` is not `.`."""
    for p in pathspecs:
        # The `:(...)` branch runs FIRST: a signature can turn wildmatch OFF, and the
        # structural rule inside `is_tree_wide_token` would otherwise fire on the `?`
        # in `:(literal)what?.txt` before anything read the keyword.
        if not p.startswith(":(") and is_tree_wide_token(p):
            return True
        if p.startswith(":("):
            # A magic SIGNATURE runs to its closing paren and may carry several
            # comma-separated keywords. Prefix-matching fixed strings missed every
            # COMBINED form -- `git add ':(top,glob)'` stages the whole shared tree
            # (verified against git) and was allowed, because the remainder after the
            # `:(top,` prefix was `glob)` and never matched.
            close = p.find(")")
            if close == -1:
                return True              # unreadable signature: fail closed
            remainder = p[close + 1:]
            keywords = {k.strip() for k in p[2:close].split(",")}
            # Compared against the shipped set, not a hand-copied subset: `**/*` is a
            # member of TREE_WIDE_PATHSPECS but was missing from the copy, so
            # `git add ':(glob)**/*'` staged the whole tree (verified) and was allowed.
            # `.rstrip("/")` first: `:(top)/` is the top of the tree, and dropping
            # the empty-string member from the comparison set lost it once already.
            if remainder.rstrip("/") == "":
                return True
            # `:(literal)` turns WILDMATCH off -- `*` and `?` are ordinary characters,
            # which is why `git add ':(literal)what?.txt'` is scoped (verified). It does
            # NOT turn PATH RESOLUTION off, so the dot collapse still applies: giving
            # this keyword its own membership-only test let `:(literal)a/../..` commit
            # the whole shared tree from a subdirectory and exit 0. One normaliser,
            # one flag.
            if is_tree_wide_token(remainder, wildmatch="literal" not in keywords):
                return True
            continue                     # a concrete path after the signature SCOPES it
        for magic in TREE_WIDE_MAGIC:
            # Only the PREFIX-plus-remainder case reaches here. The bare forms are all
            # decided earlier -- `:/` by TREE_WIDE_PATHSPECS and every `:(...)` by the
            # branch above -- so the `p == magic` test that used to lead this loop was
            # dead: replacing it with `if False:` changed no verdict. Deleted rather
            # than left to read as load-bearing.
            if p.startswith(magic):
                remainder = p[len(magic):]
                # A concrete path after the magic prefix SCOPES it.
                if remainder.rstrip("/") == "" or is_tree_wide_token(remainder):
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


def decide_git(argv: Sequence[str], stdin_fed: bool = False) -> Optional[Tuple[str, str]]:
    """Return (subcommand, rule_id) if this git invocation is tree-wide, else None."""
    # An UnknownGitGlobal propagates to `analyse`'s caller, which fails closed on
    # ValueError exactly as it does for untokenisable text.
    args = strip_git_globals(argv[1:])
    if not args:
        return None
    sub = args[0]
    value_letters = VALUE_SHORT_OPTS.get(sub, "")
    # Every option's separate VALUE is consumed positionally, so what is left in
    # `operands` really is a pathspec list. The commit branch used to drop
    # `operands[0]` whenever `-m` wanted a value, which read the list by COUNT rather
    # than by POSITION: `git commit . -m wip` therefore dropped the `.` as "the
    # message" and committed every modified tracked file in the shared tree while
    # exiting 0 (round 15, verified against git).
    raw_flags, operands, after = split_args(
        args[1:], value_letters,
        REQUIRED_VALUE_SHORT_OPTS.get(sub, ""),
        REQUIRED_VALUE_LONG_OPTS.get(sub, frozenset()))
    # Cut every fused option ARGUMENT before any flag letter is inspected. `raw_flags`
    # is kept so a caller can still tell a fused value from a separated one.
    flags = [strip_fused_value(f, value_letters) for f in raw_flags]
    # Pathspecs are operands plus anything after `--`. For subcommands whose first
    # operand is a revision (checkout/restore/reset), the `--`-separated list is the
    # authoritative pathspec set; operands are only pathspecs when no `--` was used.
    pathspecs = after if after else operands
    if sub == "reset":
        # `git reset HEAD src/a.py` -- the classic unstage-ONE-file -- is SCOPED:
        # verified against git, a second staged path survives it. With TWO OR MORE
        # operands the first is unambiguously the revision and the rest are pathspecs.
        # A SINGLE operand is ambiguous and stays a REVISION: `git reset main` resets
        # the whole index to a branch, and guessing "pathspec" there would fail open on
        # a tree-wide mutation to spare a form the denial message already prescribes a
        # spelling for (`git reset -- <path>`). Named in the doc's residuals.
        if after:
            pathspecs = after
        elif len(operands) > 1:
            # A TREE-WIDE first operand is a PATHSPEC, not a revision: `git reset .
            # src/a.py` empties the shared index (verified against git), so dropping it
            # as "the revision" meant appending any second token turned a denial into
            # an allow. It stays in the set and `tree_wide()` catches it.
            pathspecs = operands if tree_wide(operands[:1]) else operands[1:]
        else:
            # A SINGLE operand is ambiguous and stays a REVISION.
            pathspecs = []
    elif sub == "stash":
        # `git stash push src/a.py` (no `--`) is the ordinary SCOPED form and stashes
        # only that path, so ITS operands are pathspecs. `git stash save wip` takes a
        # MESSAGE, not a pathspec, so its operands must not be read as scoping.
        if operands[:1] == ["push"]:
            # `-m/--message` consumes the NEXT operand. Reading that message as a
            # pathspec made `git stash push -m wip` look scoped -- and it stashes the
            # whole shared tree, which is the loss this hook exists to prevent.
            pathspecs = operands[1:] + after
        else:
            pathspecs = after

    # A NEGATIVE pathspec never scopes: `git add ':!nope'` stages every modified file
    # in the tree. So the POSITIVES are what can narrow a command, and a command with
    # negatives but no positive acts on the whole tree.
    positives = [p for p in pathspecs if not is_negative_pathspec(p)]
    if len(positives) != len(pathspecs):
        pathspecs = positives or ["."]

    # A pathspec list read from a FILE cannot be inspected, so it is treated as
    # TREE-WIDE. `git rm -r --pathspec-from-file=list.txt` with `.` in the file deleted
    # every tracked file and exited 0 -- the fused spelling left `pathspecs` empty, so
    # no rule fired at all. ONE check for every subcommand, above the per-subcommand
    # rules, because a rule carrying its own copy is what caused rounds 13 and 14. Each
    # rule's dry-run and `--patch` exemptions still come first, so a preview is still
    # allowed. The cost is over-blocking a genuinely scoped list, named in the doc.
    # Matched by PREFIX like every other denial: `git rm -r --pathspec-fr=list.txt`
    # is the same command in a spelling git resolves and this check used to miss.
    if has_flag(flags, (PATHSPEC_FROM_FILE,)):
        pathspecs = ["."]

    if sub in PATCH_SUBCOMMANDS and has_flag(flags, ("--patch",), "p", exact=True):
        # ONLY while a human is actually at the prompt. The exemption's whole
        # justification is that every hunk is confirmed, and round 18 refuted it by
        # executing: with stdin fed from the command line nothing is confirmed by
        # anyone, `yes | git commit -p -m wip .` committed BOTH sessions' files and
        # `yes | git checkout -p .` destroyed another session's edit, both exit 0.
        # An exemption resting on an assumption must test the assumption.
        if not stdin_fed:
            return None                      # interactive: the human scopes it

    if sub in ("add", "stage"):
        # `-n`/`--dry-run` PREVIEWS the staging and touches no index entry (verified:
        # `git add -n -A` leaves the index empty). Denying the safe way to look at what
        # `-A` would do is over-blocking of exactly the command this hook teaches.
        if has_flag(flags, ("--dry-run",), "n", exact=True):
            return None
        # -A/-u with an explicit non-tree-wide pathspec is SCOPED, and allowed.
        if pathspecs and not tree_wide(pathspecs):
            return None
        if has_flag(flags, ("--all", "--no-ignore-removal", "--update"), "Au"):
            return sub, "add-tree-wide"
        # `-e`/`--edit` and `-i`/`--interactive` need NO pathspec to reach the whole
        # tree: they open the tree-wide diff, which is `-u` semantics by another name.
        # Verified against git 2.50 -- `GIT_EDITOR=true git add -e` staged another
        # session's file, and `git add -i` fed from a pipe staged both. Round 18, and
        # the fourth instance of "a legal git spelling the denylist does not
        # enumerate". Reached only AFTER the scoped-pathspec return above, so
        # `git add -e src/a.py` stays allowed, and after the `--patch` exemption, so
        # `git add -p` (a per-hunk confirmation at a real terminal) still is too.
        if not pathspecs and has_flag(flags, ("--edit", "--interactive"), "ei"):
            return sub, "add-tree-wide"
        if tree_wide(pathspecs):
            return sub, "add-tree-wide"
        return None

    if sub == "commit":
        # Only the LONG spelling: `commit -n` is `--no-verify`, not a dry run.
        if has_flag(flags, ("--dry-run",), exact=True):
            return None
        # `--all` is tested BEFORE the scoped-pathspec return, not after. git itself
        # refuses `-a` with a pathspec (`fatal: paths '...' with -a does not make
        # sense`), so a bare operand alongside `-a` is ALWAYS an option value and this
        # early return is unreachable by design when `-a` is present -- while with the
        # rules in the other order, any operand the value model failed to consume
        # disarmed the denial. Belt to the operand model's braces: round 15's BLOCKING
        # finding needed both to be wrong at once.
        if has_flag(flags, ("--all",), "a"):
            return "commit", "commit-all"
        # `--interactive` runs the same interactive-add loop as `git add -i` and then
        # COMMITS: verified against git 2.50, it committed both sessions' files at
        # rc 0. LONG spelling only -- `commit -i` is `--include`, which takes paths and
        # is scoped by them. This is `add -i`'s sibling, denied here two rounds later.
        if has_flag(flags, ("--interactive",)):
            return "commit", "commit-all"
        if pathspecs and not tree_wide(pathspecs):
            return None
        if tree_wide(pathspecs):
            # `git commit -- .` and `git commit -- ':!x'` commit every modified tracked
            # file exactly as `commit -a` does; only the spelling differs.
            return "commit", "commit-all"
        return None

    if sub == "reset":
        if has_flag(flags, ("--hard", "--merge", "--keep")):
            return "reset", "reset-destructive"
        if has_flag(flags, ("--soft",), exact=True):
            return None                      # `--soft` touches no index entry
        # A bare / `--mixed` reset with no pathspec unstages every path ANOTHER session
        # staged in the shared index. Recoverable, but still a tree-wide mutation of the
        # shared object -- and `git reset -- .` does precisely the same thing WITH a
        # pathspec: verified against git, the index came back empty. Only the spelling
        # differs, the same argument the `commit` rule above makes for `commit -- .`.
        if not pathspecs or tree_wide(pathspecs):
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
        if has_flag(flags, ("--dry-run",), "n", exact=True):
            return None
        # `-i`/`--interactive` satisfies git's requireForce exactly as `-f` does, and
        # deletes just as much: verified against git 2.50, `printf '1\n' | git clean -i`
        # removed BOTH of another session's untracked files at rc 0 with no `-f`
        # anywhere. Round 20, and the SIXTH instance of "one site updated, its sibling
        # missed" -- round 18 denied `git add -i` and left `clean`'s identical flag.
        if has_flag(flags, ("--force", "--interactive"), "fi"):
            return "clean", "clean-force"
        return None

    if sub == "stash":
        # Restorative and read-only forms stay allowed: they can only give work BACK.
        # This list is an ALLOWLIST, not a courtesy: everything else falls through to
        # the block below. It used to sit in front of a denylist of the three mutating
        # verbs, which made it dead code -- removing `apply` from it changed no verdict
        # and the suite stayed green, while the doc credited it with protecting `pop`.
        # A guard that is credited with a protection it does not provide is worse than
        # no guard, so the default is now DENY and this line is what lifts it.
        if operands and operands[0] in STASH_RESTORATIVE:
            return None
        # `push` is the ONLY stash form that takes pathspecs, so only it may be scoped
        # by one. Testing the pathspec before the verb let an unrecognised verb carrying
        # a path (`git stash frobnicate -- src/a.py`) walk past the default deny, which
        # falsified the doc's "an unknown stash verb fails CLOSED".
        if operands[:1] == ["push"] and pathspecs and not tree_wide(pathspecs):
            return None
        return "stash", "stash-mutating"

    if sub == "rm":
        # `git rm` has a real dry run too, and round 7 exempted every ruled subcommand
        # that has one EXCEPT this one -- the same "updated one, missed its sibling"
        # class the pathspec parity test was written to close.
        if has_flag(flags, ("--dry-run",), "n", exact=True):
            return None
        if tree_wide(pathspecs):
            return "rm", "rm-tree-wide"
        return None

    if sub == "worktree":
        if operands[:1] == ["remove"] and has_flag(flags, ("--force",), "f"):
            return "worktree", "worktree-force-remove"
        return None

    return None


def analyse(command: str, stdin_fed: bool = False) -> Optional[Tuple[str, str]]:
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
    for segment, segment_fed in split_segments(tokens):
        # A wrapper's inner script inherits the stdin its own segment was given, so
        # `yes | bash -c 'git add -p .'` is fed just as the bare command is.
        fed = segment_fed or stdin_fed
        segment = strip_prefixes(segment)
        if not segment:
            continue
        # Unwrap `bash -c '<script>'` / `sh -c '...'` and analyse the inner text.
        if os.path.basename(segment[0]) == "eval":
            # bash CONCATENATES eval's arguments and runs the result, so the JOINED
            # argv is the script. Analysing only each token on its own missed
            # `eval git add -A` entirely -- `analyse("git")` is a git call with no
            # subcommand, so every piece looked harmless. The quoted
            # `eval 'git add -A'` was the only form tested and the only one caught.
            for candidate in [" ".join(segment[1:])] + list(segment[1:]):
                inner = analyse(candidate, fed)
                if inner:
                    return inner
            continue
        if os.path.basename(segment[0]) in SCRIPT_WRAPPERS:
            # `bash`/`sh`/`zsh`/`dash` read STDIN as a SCRIPT, so a heredoc or
            # here-string handed to one is CODE -- and `preprocess` strips heredoc
            # bodies as data, deliberately, so `cat > f <<EOF ... EOF` can document a
            # command without triggering it. The two rules met and the script vanished:
            # `sh <<'EOF' / git reset --hard / EOF` destroyed both sessions' edits and
            # `bash <<< 'git add -A'` staged both, rc 0 (round 22, verified). Only the
            # `-c` spelling was ever unwrapped, and its test asserted only that one.
            # The script text is genuinely not available here, so this fails CLOSED
            # rather than guessing -- the same inversion round 19 chose for unknown
            # globals. `bash -c '<script>'` is still read, and an unfed wrapper
            # (`bash script.sh`) still relies on the named script-file residual.
            # ONLY when the wrapper has no script to read at all. Gating on `fed`
            # alone denied every ordinary piped-into wrapper -- `git status; echo x |
            # bash build.sh` and `echo "git is fine" | sh cleanup.sh` were refused as
            # untokenisable (round 23). A wrapper with a script FILE operand is the
            # already-named script-file residual, whose contents this hook never sees
            # either way; what round 22 closed was a script arriving on STDIN, which is
            # exactly the case where no operand exists.
            # `-s` means READ THE SCRIPT FROM STDIN, so a following operand is a
            # positional parameter, not a script file: `bash -s file <<EOF / git add -A
            # / EOF` staged both sessions' files at rc 0 (round 24 -- found by probing
            # this very fix, verified against bash and git). `sh -- file` really does
            # run the FILE (verified: it printed the file's own output and staged
            # nothing), so `--` is not the same case.
            reads_stdin = any(
                tok == "-s" or (tok.startswith("-") and not tok.startswith("--")
                                and "s" in tok[1:])
                for tok in segment[1:])
            # A bare word is a script FILE only if it is not the VALUE of the
            # wrapper's own option: `bash -O extglob <<EOF … EOF` read `extglob` as a
            # script, skipped the fail-closed raise, and never analysed the stdin
            # script -- it staged both sessions' files, and the `<<< "git checkout
            # -f"` spelling destroyed both sessions' in-flight edits, rc 0 (round 26,
            # verified). The parity test written to close this class enumerated only
            # BARE wrappers, which is why 2521 tests saw nothing.
            words = segment[1:]
            operands = [
                tok for idx, tok in enumerate(words)
                if not tok.startswith("-")
                and not (idx and words[idx - 1] in WRAPPER_VALUE_OPTS)
            ]
            has_script = not reads_stdin and (
                any(tok == "-c" or (tok.startswith("-") and not tok.startswith("--")
                                    and "c" in tok[1:]) for tok in words)
                or bool(operands))
            if fed and not has_script:
                raise ValueError("a script fed to a shell wrapper cannot be read")
            for i, tok in enumerate(segment[1:], start=1):
                is_c = tok == "-c" or (
                    tok.startswith("-") and not tok.startswith("--") and "c" in tok[1:])
                if is_c and i + 1 < len(segment):
                    # No try/except: an untokenisable inner script must fail CLOSED
                    # exactly as the same text does at the top level.
                    inner = analyse(segment[i + 1], fed)
                    if inner:
                        return inner
                    break
            continue
        if not is_git(segment[0]):
            continue
        found = decide_git(segment, fed)
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
    tool_input = payload.get("tool_input")
    if tool_input is not None and not isinstance(tool_input, dict):
        # Present but malformed. Reporting "no command" made this the sibling fail-OPEN
        # of the non-string `command` field, on the same sentence of the same doc.
        return False, None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if command is None:
        command = payload.get("command")
    if command is None:
        return True, None
    if not isinstance(command, str):
        # A `command` key that is not a string is a MALFORMED payload, not an absent
        # one. Reporting "no command" here made a non-string field the one malformed
        # payload that failed OPEN, while the doc claims every one of them blocks.
        return False, None
    return True, command


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
