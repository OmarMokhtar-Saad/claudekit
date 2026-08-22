#!/usr/bin/env python3
"""iron-law-gate.py - makes hard rule 1 (the Iron Law) harness-enforced, not prompt-enforced.

WHY THIS EXISTS
---------------
`implementer.md` grants `tools: ["Read", "Bash", "Grep", "Glob"]`. It grants no Edit and no
Write - but a frontmatter-declared `Bash(<specifier>)` is NOT applied on the interactive
path (measured, Claude Code 2.1.235; see `_shared/INVOCATION.md`). So the interactive
implementer holds UNSCOPED Bash and can bypass the ops engine entirely with `sed -i`,
`cat > f`, `python3 -c "open(p,'w')"`, `tee`, `git apply`, `patch`, `perl -pi`, a heredoc,
`$(...)` or `sh -c '...'`. This hook closes that on the PreToolUse/Bash event.

LOGGING (project hard rule 6)
-----------------------------
Everything this hook writes to `hooks.log` has already been REJECTED, so it is precisely
the text most likely to contain a credential or a host path
(`AWS_SECRET_ACCESS_KEY=... python3 ...`). Heads and reasons are routed through `safe()`,
which delegates to `reflection.bounded_token`, and `redact()` blanks the value of every
`NAME=value` token before the command is shown or logged. A gate that records the secrets
it blocks is worse than the bypass it prevents.

ALLOWLIST, NOT DENYLIST (project hard rule 6)
---------------------------------------------
An enumeration of forbidden write vectors was tried and rejected: it is trivially evadable
and is exactly the "speed bump, not a sandbox" shape hard rule 6 warns about. This hook
instead permits a NAMED set and rejects everything else, including anything it cannot
confidently parse. Adding a new write tool to the host does not widen it.

SCOPE - THE HOOK IS INVISIBLE TO EVERYONE ELSE
----------------------------------------------
It acts ONLY when the payload's `agent_type` is exactly `implementer`. Absent, empty, or
any other value -> exit 0 without opinion. Verified against the harness rather than assumed:
Claude Code 2.1.237 builds every hook payload through

    function $y(e,t,r,n){let o=n?.agentType??Z$(); ...
      return{session_id:..., cwd:t, permission_mode:r, agent_id:n?.agentId, agent_type:o,...}}

and `executePreToolHooks` spreads exactly that object into the `PreToolUse` input. On the
main thread `Z$()` returns `mainThreadAgentType`, which is undefined unless the session was
started with `--agent`, so `agent_type` is simply absent for the main agent.

FAIL DIRECTIONS - THE TWO UNKNOWNS FAIL OPPOSITE WAYS, DELIBERATELY
-------------------------------------------------------------------
  * Cannot determine the agent type (payload is not JSON at all) -> FAIL OPEN, exit 0.
    Blocking here would deny every Bash call the MAIN agent makes, which is catastrophic
    and outside this hook's remit. No coverage is lost: `reflection-gate.py` is wired on the
    same event with `matcher: ""` and already fails CLOSED on an unparsable PreToolUse
    payload, so the chain still denies.
  * Agent type IS `implementer` but the command cannot be read or tokenised -> FAIL CLOSED,
    exit 2. Here we know who is asking and cannot prove what they asked for.

BLOCKING CONTRACT (project hard rule 2)
---------------------------------------
A block is `exit 2` with the reason on STDERR. Never exit 1, never stdout-as-decision.

PROFILE CONVENTION  ***DELIBERATE DIVERGENCE - DO NOT "FIX" THIS BACK***
------------------------------------------------------------------------
`ops-enforcement.sh:15` short-circuits wholesale under `ECC_HOOK_PROFILE=minimal`. This hook
does NOT, for the same reason `reflection-gate.py` does not: this repo develops with
`minimal` set, so a wholesale `exit 0` yields ZERO dogfood signal - the problem Decision 21
just addressed. Under `minimal` the decision is still computed and logged as `WOULD-BLOCK`
with the offending head, then exit 0. Blocking is suppressed; measurement is not.

HONEST FRAMING (project hard rule 6)
------------------------------------
This is a real harness control on the Bash tool, and it is strictly stronger than the prompt
it replaces - but it is NOT a sandbox. Two residuals are named, not hidden:
  1. `pytest` executes repo code including `conftest.py`, so it is mutation-capable. It is
     permitted anyway (see PYTEST below) and that is a deliberate, recorded trade.
  2. The hook is one PreToolUse entry in `settings.json`. Anything that can rewrite
     `settings.json` disables it. Only the ops engine and the operator can.
  3. The SAFE lists are small and default-deny (see "the flag decision (v2)"), so an
     unknown flag over-blocks rather than bypasses. What remains is that a flag ON the
     safe list must be safe with ANY value - that is a property argued per entry, not
     proven. Adding an entry is a security change and needs a BLOCKED case beside it.

PYTEST
------
`implementer.md` Step 4 makes running the test suite MANDATORY, and this repo's test command
is `python3 -m pytest`. Blocking it would break the implementer's own sanctioned loop at the
verification step. The code pytest runs is repo code that ALREADY EXISTS: the implementer
cannot introduce or alter a `conftest.py` without first passing through the ops engine, which
is the transaction, backup and approval gate the Iron Law actually exists to protect. So
pytest is permitted, and recorded as residual 1.

Separately from that residual, pytest's own WRITERS and CONFIG INJECTORS are refused,
by DEFAULT rather than by enumeration:
they are a different and worse thing - not "runs repo code we already trust" but "points
pytest's writer at a path of our choosing". `--log-file=src/x.py` creates and truncates an
arbitrary file, `--debug=<path>` likewise, and `-o addopts=...` / `-c <ini>` inject
configuration that can load a plugin. `_PYTEST_SAFE` is `{-q, --quiet}`, so every one of
them - and every writer a future pytest release adds - is refused without being named.

Python 3.9, stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # pragma: no cover - exercised by test_sanitizer_falls_back_without_reflection
    import reflection as _reflection
except Exception:  # a gate must never crash on an optional import
    _reflection = None

HOOK_NAME = "iron-law-gate"
GUARDED_AGENT = "implementer"

# `CLAUDEKIT_HOOK_LOG` lets the behavioral tests assert on log lines without appending to
# the developer's real .claude/hooks/hooks.log.
LOG_FILE = Path(os.environ.get("CLAUDEKIT_HOOK_LOG")
                or (Path(__file__).resolve().parent / "hooks.log"))

# ---------------------------------------------------------------- pre-tokenisation filter
# A command containing any of these cannot be safely reduced to a single argv, so no
# allowlist decision about it can be trusted. Rejected BEFORE matching, by design:
#   ;  |  &      -> command chaining and pipelines (covers && and ||, and `| tee`)
#   >  <         -> every redirection form (covers `cat > f`, `>>`, heredoc `<<`, `<()`)
#   `  $(        -> command substitution
#   \n \r        -> a second command on a second line
_METACHARACTERS = (";", "|", "&", ">", "<", "`", "$(", "\n", "\r")

# Wrappers that would launder an arbitrary command through an allowlisted-looking head.
_WRAPPERS = frozenset({
    "sh", "bash", "zsh", "ksh", "dash", "ash", "csh", "tcsh", "fish",
    "env", "xargs", "nohup", "eval", "exec", "command", "builtin",
    "time", "timeout", "sudo", "doas", "su", "watch", "script", "expect",
    "parallel", "setsid", "stdbuf", "nice", "ionice",
})

# --------------------------------------------------------------- the flag decision (v2)
# ROUND 4 ARCHITECTURAL INVERSION - read this before touching any table below.
#
# v1 allowlisted VERBS but DENYLISTED their FLAGS (one write-flag table per verb).
# That is precisely the shape hard rule 6 calls a speed bump, reappearing one level down
# INSIDE an allowlist. Three review rounds each found new writers in the same class:
#   round 2: pytest --log-file, -o, -c            round 3: ruff --add-noqa, pytest --debug
# and round 3 found two of them IN THE VERBS ROUND 2 HAD JUST "SWEPT". `ruff`, `mypy` and
# `pytest` have large versioned flag surfaces; any release can add a writer, so no
# enumeration of the dangerous set is stable and none can ever be proven complete.
#
# So the decision is INVERTED. For every flag-gated verb, a token starting with `-` is
# REFUSED unless it is in that verb's small explicit SAFE list. The denylists are deleted
# outright rather than kept "just in case": keeping them would falsely signal that the
# dangerous set is known.
#
# The burden now runs the right way. A future `ruff` release that adds a writer is denied
# by default. The failure mode of an unknown flag becomes an OVER-BLOCK - annoying,
# visible in `hooks.log`, and fixable by adding one entry - instead of a BYPASS, which is
# silent, invisible and exploitable. That trade is the whole point.
#
# RULES THAT APPLY TO EVERY VERB
#   * `@argfile` (and any response-file syntax) is REFUSED everywhere. It is a flag source
#     the gate cannot inspect, which defeats the entire design - mypy's `@file` would
#     otherwise smuggle `--html-report` straight back in.
#   * `--` is REFUSED everywhere. Not one sanctioned command needs it, and honouring it
#     would add a second parsing mode (post-`--` tokens as positionals) for no gain.
#     Documented decision, not an oversight.
#   * Attached and detached forms are both covered: membership is tested on
#     `token.split("=", 1)[0]`, so `--output=x` is judged as `--output`. A flag therefore
#     only belongs in a SAFE list if it is safe WITH ANY VALUE.
#   * Positionals are path-constrained: no `..` segment, and no absolute path outside the
#     project root. Globs are NOT expanded by the gate - the shell expands them after the
#     hook runs, so `.claude/hooks/*.sh` arrives literally and passes as a relative path.
#
# EVERY SAFE LIST BELOW IS DERIVED FROM A COMMAND THE IMPLEMENTER IS ACTUALLY INSTRUCTED
# TO RUN (CLAUDE.md's six DoD gates, implementer.md Steps 1-4, implement.md Phases 1-3).
# Nothing is added for hypothetical convenience. Where a verb needs no flags, its list is
# empty. `tests/test_iron_law_hook.py::test_dod_command_is_permitted` pins all six.

_INERT = None  # sentinel: this verb has no flag that can write, execute or read flags

# Class 1 - FLAG-INERT verbs. Any `-` token is accepted because the verb's ENTIRE flag
# surface is write-free on both GNU and BSD; `@` and `--` are still refused and
# positionals are still path-constrained. This is NOT a flag denylist: it is a per-verb
# assertion that must be argued before a verb joins the class, and re-argued when one is
# added. Deliberately tiny - it is exactly what implementer.md names as "read-only
# inspection (`cat`, `grep`, `ls`, ...)" plus the three size/slice tools its corpus uses.
# `file` was REMOVED here: `file -C -m <name>` writes a `.mgc` file and nothing instructs
# the implementer to run it. `stat`, `du`, `nl`, `cut`, `tr`, `column`, `diff`, `rg`,
# `which`, `basename`, `dirname`, `pwd` were removed for the same reason - smallest
# surface wins, and every one of them was speculative.
_INERT_VERBS = frozenset({"cat", "head", "tail", "wc", "ls", "grep", "egrep", "fgrep"})

# Class 2 - FLAG-GATED verbs, default-deny SAFE lists.

# `python3 -m pytest tests/ -q`  (CLAUDE.md DoD gate 1)
_PYTEST_SAFE = frozenset({"-q", "--quiet"})

# `ruff check src/ tests/ scripts/`  (DoD gate 2) needs NO flags at all; `--check`/`--diff`
# exist solely so `ruff format` has a non-writing form.
_RUFF_SAFE = frozenset({"--check", "--diff"})

# `mypy`  (DoD gate 3) - no flags.
_MYPY_SAFE = frozenset()

# `shellcheck install.sh .claude/hooks/*.sh`  (DoD gate 6) - no flags.
_SHELLCHECK_SAFE = frozenset()

# `ck doctor --strict`; `ck execute --dry-run` is the ops engine's own front end.
_CK_SUBCOMMANDS = frozenset({"doctor", "validate", "execute"})
_CK_SAFE = frozenset({"--strict", "--dry-run"})

# implementer.md "Build tool not found -> Check common locations". Reporting primaries
# only; every `find` action that executes or writes is simply absent from the list, which
# is now the default rather than an enumeration.
_FIND_SAFE = frozenset({"-name", "-type", "-maxdepth", "-mindepth", "-path"})

# `git` reporters. The subcommand must be the FIRST token after `git`, so global options
# are refused too: `git -c alias.x='!sh -c ...' x` and `git -C <dir> ...` are execution
# vectors, not reporting. checkout / apply / restore / reset / add / commit / push /
# stash / clean are absent on purpose.
_GIT_READ_ONLY = frozenset({
    "status", "diff", "log", "show", "rev-parse", "ls-files", "shortlog", "blame",
})
_GIT_SAFE = frozenset({
    "--porcelain", "--short", "--stat", "--numstat", "--name-only", "--name-status",
    "--oneline", "--cached", "--staged", "--show-toplevel", "-n",
})

# `branch` and `remote` are NOT read-only subcommands: `git branch -D feature` and
# `git remote add|remove|set-url|prune` all mutate repository state, destructively in the
# `-D`/`prune` case. They are kept as reporters only, with a listing-only SAFE list.
# A POSITIONAL is permitted here so `git branch --list 'feat*'` works (round-3 over-block).
_GIT_LIST_ONLY = frozenset({"branch", "remote"})
_GIT_LIST_SAFE = frozenset({"-v", "-vv", "--verbose", "--list", "--show-current",
                            "-a", "--all"})

# Interpreter flags that precede the script. All inert: none of them can write or read a
# flag source. `-c` is deliberately absent - that is `python3 -c "open(p,'w')"`.
_PYTHON_HEADS = frozenset({"python", "python3", "py"})
_PYTHON_FLAGS = frozenset({"-u", "-B", "-E", "-s", "-S", "-I"})

# The two ops-engine entrypoints, relative to the project root. Matched by resolved
# absolute path, never by substring, so naming an unrelated file `execute-json-ops.py`
# does not buy anything. `--no-approval` is deliberately NOT safe: implement.md requires
# explicit user authorization for it.
_OPS_SCRIPTS = ("execute-json-ops.py", "validate-config-json.py")
_OPS_DIR = (".claude", "operations", "scripts")
_OPS_SAFE = frozenset({"--dry-run", "--stamp-baseline"})

# The reflection escape hatch. `reflection-gate.py` can block the implementer on a pending
# checkpoint, and this CLI is the ONLY way out (the receipt inbox is a `Write`, which the
# implementer does not hold). Two gates fighting over an escape hatch has already happened
# in this repo once. Over-blocking it is the one fatal failure mode, so its argument VALUES
# are exempt from the positional path constraint - a receipt payload is data, not a path.
_REFLECTION_VERBS = frozenset({"receipt", "trigger", "non-attempt", "status"})
_REFLECTION_SAFE = frozenset({
    "--session-id", "--session-token", "--json", "--file", "--trigger",
    "--fingerprint", "--failure-id", "--reason",
})

# CLAUDE.md DoD gates 4 and 5. Permitted ONLY with `--check`: without it gen-docs.py
# REWRITES the docs, which is exactly the un-transacted mutation this gate exists to stop.
_CHECK_ONLY_SCRIPTS = frozenset({"gen-docs.py", "gen-registry.py"})
_CHECK_ONLY_SAFE = frozenset({"--check"})


def hlog(level: str, message: str) -> None:
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write("[%s] [%s] [%s] %s\n" % (stamp, HOOK_NAME, level, message))
    except OSError:
        pass


def safe(value: str, fallback: str = "unknown") -> str:
    """Collapse a value to a low-cardinality, privacy-safe token before it touches disk.

    A GATE THAT RECORDS THE SECRETS IT BLOCKS IS WORSE THAN THE BYPASS IT PREVENTS.
    Everything this hook logs has already been rejected, so it is by definition attacker-
    or accident-shaped: `AWS_SECRET_ACCESS_KEY=<value> python3 ...`, absolute host paths,
    tokens pasted into a command line. `reflection.bounded_token` already digests exactly
    that shape and is the sanitizer this repo standardised on (`reflection-gate.py:339`),
    so it is reused rather than reinvented. If the import is unavailable the fallback is
    still conservative: basename-only, truncated, non-word characters collapsed.
    """
    if _reflection is not None:
        try:
            return _reflection.bounded_token(value, fallback)
        except Exception:
            pass
    rendered = re.split(r"[/\\]", str(value or ""))[-1].casefold()
    rendered = re.sub(r"[^a-z0-9_.:-]+", "-", rendered).strip("-")
    return rendered[:80] or fallback


_SECRET_FLAG = re.compile(
    r"^--?(?:password|passwd|pass|token|secret|api[-_]?key|apikey|auth|credential|"
    r"session[-_]?token|bearer|private[-_]?key)$", re.IGNORECASE)


def redact(command: str) -> str:
    """Blank every secret-shaped value before the command is shown on stderr or logged.

    Three shapes, because the first revision only handled the first and round 4 showed the
    rest surviving into `denial_message()`:
      1. `NAME=value`            -> `NAME=<redacted>`
      2. `--token=value` / `--token value` (space-separated) -> value blanked
      3. anything `reflection.looks_like_credential()` flags - bare high-entropy strings
         and `https://user:tok@host` - which is the existing, already-tuned detector in
         this repo rather than another regex invented here.
    `hooks.log` was never the exposure (that line is `head=` + `reason=`, both digested by
    `safe()`); stderr is, and stderr is persisted in the transcript.
    """
    parts = []
    blank_next = False
    for token in command.split():
        if blank_next:
            parts.append("<redacted>")
            blank_next = False
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            parts.append(token.split("=", 1)[0] + "=<redacted>")
            continue
        bare, sep, _ = token.partition("=")
        if _SECRET_FLAG.match(bare):
            if sep:
                parts.append(bare + "=<redacted>")
            else:
                parts.append(bare)
                blank_next = True
            continue
        if _credential_like(token):
            parts.append("<redacted>")
            continue
        parts.append(token)
    return " ".join(parts)


def _credential_like(token: str) -> bool:
    if _reflection is None:
        return False
    try:
        return bool(_reflection.looks_like_credential(token))
    except Exception:
        return False


_ROOT_CACHE = []


def project_root() -> Path:
    """Memoized: this runs on EVERY implementer Bash call, and the git fallback forks."""
    if _ROOT_CACHE:
        return _ROOT_CACHE[0]
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        root = Path(env)
    else:
        root = Path.cwd()
        try:
            out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, timeout=2)
            if out.returncode == 0 and out.stdout.strip():
                root = Path(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    _ROOT_CACHE.append(root)
    return root


def extra_verbs() -> frozenset:
    """Opt-in widening for downstream projects whose build/test verbs differ.

    Bare basenames only, colon-separated - mirrors `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW`
    in the ops validator. Deliberately accepts no argv patterns: a pattern in an env var
    would read as scoping while providing none.
    """
    raw = os.environ.get("CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS", "")
    return frozenset(part.strip() for part in raw.split(":")
                     if part.strip() and "/" not in part)


def resolve_script(token: str, root: Path) -> Optional[Tuple[str, str]]:
    """(realpath(parent), basename) for a script argument.

    The parent is resolved but the full path is NOT, mirroring the anti-symlink discipline
    in `reflection-gate.is_receipt_inbox_write`: resolving the whole path would let a
    symlink named `execute-json-ops.py` launder an arbitrary script into the allowlist.
    """
    candidate = Path(token)
    if not candidate.is_absolute():
        candidate = root / candidate
    if os.path.islink(str(candidate)):
        return None
    try:
        return (os.path.realpath(str(candidate.parent)), candidate.name)
    except OSError:
        return None


def _skip_python_flags(tokens: Sequence[str], index: int) -> int:
    while index < len(tokens) and tokens[index] in _PYTHON_FLAGS:
        index += 1
    return index


def _positional_ok(token: str, root: Path) -> Tuple[bool, str]:
    """A positional may not escape the project root.

    Globs are left alone deliberately: the shell expands them AFTER this hook runs, so
    `.claude/hooks/*.sh` arrives literally and is judged as an ordinary relative path.
    """
    if token.startswith("~"):
        return False, "positional %s expands outside the project" % safe(token)
    parts = PurePosixPath(token.replace("\\", "/")).parts
    if ".." in parts:
        return False, "positional %s escapes the project root with '..'" % safe(token)
    if os.path.isabs(token):
        try:
            base = os.path.realpath(str(root))
            here = os.path.realpath(token)
        except OSError:
            return False, "positional %s cannot be resolved" % safe(token)
        if here != base and not here.startswith(base + os.sep):
            return False, "positional %s is outside the project root" % safe(token)
    return True, ""


def _check_argv(rest: Sequence[str], safe_flags, label: str, root: Path,
                numeric_ok: bool = False, path_check: bool = True) -> Tuple[bool, str]:
    """DEFAULT-DENY flag check. See "the flag decision (v2)" above.

    `safe_flags is _INERT` means the verb's whole flag surface is write-free, so `-`
    tokens pass; `@` and `--` never do, and positionals are still constrained.
    """
    for token in rest:
        if token.startswith("@"):
            return False, ("%s response-file argument %s is refused: it is a flag source "
                           "this gate cannot inspect" % (label, safe(token)))
        if token == "--":
            return False, ("%s uses the `--` separator, which this gate refuses; no "
                           "sanctioned command needs it" % label)
        if token.startswith("-"):
            if safe_flags is _INERT:
                continue
            if numeric_ok and re.match(r"^-\d+$", token):
                continue
            bare = token.split("=", 1)[0]
            if bare not in safe_flags:
                return False, ("%s flag %s is not on the safe list. Flags are DEFAULT-DENY: "
                               "only %s are permitted, because no enumeration of the "
                               "writing flags is ever complete."
                               % (label, safe(bare),
                                  ", ".join(sorted(safe_flags)) or "(none)"))
            continue
        if path_check:
            ok, reason = _positional_ok(token, root)
            if not ok:
                return False, reason
    return True, ""


def _decide_python(tokens: List[str], root: Path) -> Tuple[bool, str]:
    index = _skip_python_flags(tokens, 1)
    if index >= len(tokens):
        return False, "bare interpreter with no script"
    head = tokens[index]

    if head == "-m":
        if index + 1 < len(tokens) and tokens[index + 1] == "pytest":
            return _check_argv(tokens[index + 2:], _PYTEST_SAFE, "pytest", root)
        return False, "`%s -m %s` is not the ops engine or pytest" % (
            safe(tokens[0]), safe(tokens[index + 1] if index + 1 < len(tokens) else ""))
    if head.startswith("-"):
        # `-c`, `-`, anything else. `python3 -c "open(p,'w')"` dies here.
        return False, "interpreter flag %s can execute arbitrary code" % safe(head)
    if head.startswith("@"):
        return False, "response-file argument %s is refused" % safe(head)

    resolved = resolve_script(head, root)
    if resolved is None:
        return False, "script %s is a symlink or cannot be resolved" % safe(head)
    parent, name = resolved
    rest = tokens[index + 1:]

    if parent == os.path.realpath(str(root.joinpath(*_OPS_DIR))) and name in _OPS_SCRIPTS:
        return _check_argv(rest, _OPS_SAFE, name, root)
    if parent == os.path.realpath(str(root / ".claude" / "hooks")) and name == "reflection.py":
        if not rest or rest[0] not in _REFLECTION_VERBS:
            return False, "reflection.py needs one of %s" % sorted(_REFLECTION_VERBS)
        # path_check=False: a receipt payload is data, not a path, and over-blocking the
        # ONE escape hatch out of a reflection checkpoint is the fatal failure mode.
        # KNOWN AND ACCEPTED: this lets `--file <any readable path>` through. Traced in
        # review to reflection.py:930-946 - `--file` is READ-only and every write stays
        # inside the ledger directory, so it is not a write vector. At worst it is an
        # error-message read-leak of a file the implementer already holds `Read` for.
        return _check_argv(rest[1:], _REFLECTION_SAFE, "reflection.py", root,
                           path_check=False)
    if parent == os.path.realpath(str(root / "scripts")) and name in _CHECK_ONLY_SCRIPTS:
        if "--check" not in rest:
            return False, ("`%s` REWRITES generated content without --check; it is a "
                           "Definition-of-Done gate only in its --check form" % name)
        return _check_argv(rest, _CHECK_ONLY_SAFE, name, root)
    return False, ("%s is not an ops-engine entrypoint; the only scripts the implementer "
                   "may run through an interpreter are "
                   ".claude/operations/scripts/{execute-json-ops,validate-config-json}.py, "
                   ".claude/hooks/reflection.py, and scripts/{gen-docs,gen-registry}.py "
                   "--check" % safe(name))


def _decide_git(rest: List[str], root: Path) -> Tuple[bool, str]:
    if not rest:
        return False, "bare `git` - no subcommand to check"
    if rest[0].startswith("-"):
        return False, ("git global option %s must not precede the subcommand "
                       "(`git -c alias...` and `git -C dir` are execution vectors)"
                       % safe(rest[0]))
    if rest[0] in _GIT_LIST_ONLY:
        # A POSITIONAL here is how `git remote add origin <url>` and `git branch -m old new`
        # mutate: the flag list alone does not stop them, because their verbs are bare
        # words. Positionals are therefore refused UNLESS `--list` is present, which is the
        # one form that legitimately takes one (`git branch --list 'feat*'`).
        listing = "--list" in rest[1:]
        for token in rest[1:]:
            if not token.startswith("-") and not listing:
                return False, ("`git %s %s` names a positional; without --list that is a "
                               "mutating form (add/remove/set-url/prune/rename)"
                               % (safe(rest[0]), safe(token)))
        return _check_argv(rest[1:], _GIT_LIST_SAFE, "git " + rest[0], root)
    if rest[0] not in _GIT_READ_ONLY:
        return False, ("`git %s` is not a read-only reporter. Permitted: %s"
                       % (safe(rest[0]),
                          ", ".join(sorted(_GIT_READ_ONLY | _GIT_LIST_ONLY))))
    return _check_argv(rest[1:], _GIT_SAFE, "git " + rest[0], root, numeric_ok=True)


def decide(command: str, root: Path) -> Tuple[bool, str]:
    """(allowed, reason_when_denied). Never raises."""
    if not command.strip():
        return False, "empty command - nothing to verify"
    for meta in _METACHARACTERS:
        if meta in command:
            shown = {"\n": "\\n", "\r": "\\r"}.get(meta, meta)
            return False, (
                "shell metacharacter %r - a chained, piped, redirected or substituted "
                "command cannot be reduced to one argv, so it cannot be allowlisted. "
                "Run ONE command with absolute paths and no operators." % shown)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        return False, "command does not tokenise (%s)" % exc
    if not tokens:
        return False, "command tokenises to nothing"
    if "=" in tokens[0] and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        # NAME only. The VALUE is frequently a credential and this reason is written to
        # hooks.log - see safe()/redact().
        return False, ("leading environment assignment %s= - the implementer has no "
                       "documented need for one and it can alter what a binary does "
                       "(PYTHONPATH, LD_PRELOAD)" % tokens[0].split("=", 1)[0])

    head = re.split(r"[/\\]", tokens[0])[-1]
    if head in _WRAPPERS:
        return False, "%s is a wrapper; it can execute anything" % safe(head)
    rest = tokens[1:]

    # EVERY verb, INTERPRETERS INCLUDED, must be a bare basename resolved through PATH.
    # Without this the allowlist names a WORD, not a PROGRAM: `/tmp/evil/cat` and
    # `./shellcheck` matched by basename and ran whatever binary sat there.
    #
    # THIS CHECK MUST STAY ABOVE THE _PYTHON_HEADS DISPATCH. It used to sit below it, so
    # the interpreter branch returned first and `/tmp/evil/python3
    # .claude/operations/scripts/execute-json-ops.py p.ops.json` was ALLOWED: the SCRIPT
    # argument resolved into the ops directory and satisfied _OPS_SAFE, and the gate then
    # ran an arbitrary binary that merely happened to be named `python3`, with an argv of
    # the caller's choosing. Resolving the SCRIPT is not resolving the INTERPRETER - they
    # are different controls and both are required.
    if "/" in tokens[0] or "\\" in tokens[0]:
        return False, ("%s was given as a path; allowlisted verbs must be bare names "
                       "resolved through PATH, or the allowlist names a word rather than "
                       "a program" % safe(head))

    if head in _PYTHON_HEADS:
        # The interpreter is now a bare PATH-resolved name. Its SCRIPT argument is a
        # separate control, resolved against the project root by resolve_script().
        return _decide_python(tokens, root)

    if head == "pytest":
        return _check_argv(rest, _PYTEST_SAFE, "pytest", root)
    if head == "git":
        return _decide_git(rest, root)
    if head == "find":
        return _check_argv(rest, _FIND_SAFE, "find", root)
    if head == "ruff":
        if not rest:
            return False, "bare `ruff` - no subcommand to check"
        if rest[0] == "format":
            if not any(t in ("--check", "--diff") for t in rest[1:]):
                return False, "`ruff format` rewrites source; use --check or --diff"
        elif rest[0] != "check":
            return False, "only `ruff check` and `ruff format --check` are permitted"
        return _check_argv(rest[1:], _RUFF_SAFE, "ruff " + rest[0], root)
    if head == "mypy":
        return _check_argv(rest, _MYPY_SAFE, "mypy", root)
    if head == "shellcheck":
        return _check_argv(rest, _SHELLCHECK_SAFE, "shellcheck", root)
    if head in ("ck", "claudekit"):
        if not rest or rest[0] not in _CK_SUBCOMMANDS:
            return False, ("only `%s {%s}` is permitted"
                           % (head, ",".join(sorted(_CK_SUBCOMMANDS))))
        return _check_argv(rest[1:], _CK_SAFE, head + " " + rest[0], root)
    if head in _INERT_VERBS:
        return _check_argv(rest, _INERT, head, root)
    if head in extra_verbs():
        # Opt-in widening. Flags stay default-deny: an extra verb gets NO safe flags, so
        # it is usable only in its bare form. An env var must not be able to grant more
        # than the built-in verbs get.
        return _check_argv(rest, frozenset(), head, root)
    return False, ("%s is not on the implementer's allowlist. The Iron Law permits the ops "
                   "engine plus read-only inspection and verification, nothing else."
                   % safe(head))


def denial_message(command: str, reason: str) -> str:
    command = redact(command)
    shown = command if len(command) <= 300 else command[:300] + " ..."
    return (
        "IRON LAW - IMPLEMENTER COMMAND BLOCKED\n"
        "Command: %s\n"
        "Reason:  %s\n\n"
        "The implementer mutates the tree through ONE path only:\n"
        "  python3 .claude/operations/scripts/validate-config-json.py <ops.json> "
        "--stamp-baseline\n"
        "  python3 .claude/operations/scripts/execute-json-ops.py <ops.json> --dry-run\n"
        "  python3 .claude/operations/scripts/execute-json-ops.py <ops.json>\n\n"
        "If this was a VERIFICATION command that this allowlist does not cover, do not "
        "retry it and do not work around it. Take the path implementer.md already "
        "documents: report \"executed via ops.json - verification pending\" and hand off "
        "to the Verifier, whose tool grant covers build/test/lint.\n"
        "If this was an EDIT, it belongs in an ops.json. Ask the Planner for one."
        % (shown, reason)
    )


def read_payload() -> Optional[Dict]:
    # .buffer + surrogateescape, and the reason is NOT that a decode error escaped:
    # UnicodeDecodeError is a subclass of ValueError, so the `except` below already
    # caught it and this hook already returned None. Measured on the unpatched hook
    # under LC_ALL=en_US.UTF-8 with an invalid byte: rc 0, no traceback.
    #
    # The point is WHICH branch that None reached. `main()` treats an unreadable
    # payload as FAIL OPEN by design (see "FAIL DIRECTIONS" in the header): it cannot
    # tell whose command it is, so it passes through and relies on reflection-gate.py
    # failing closed on the same event. That made a byte a passthrough key — an
    # implementer command carrying one invalid byte skipped the Iron Law allowlist
    # entirely. Decoding with surrogateescape cannot raise, so the payload becomes
    # READABLE and the gate decides on its merits instead of waving it through.
    #
    # This is a deliberate TIGHTENING, and it flips a verdict: an implementer
    # `rm -rf` with an invalid byte goes rc 0 -> rc 2. Both directions are covered in
    # tests/test_iron_law_hook.py; a block/allow flip in a hard-rule-1 hook does not
    # ship on a comment's word.
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def tool_command(event: Dict) -> Optional[str]:
    tool_input = event.get("tool_input")
    if isinstance(tool_input, str):
        return tool_input
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get("command", tool_input.get("cmd"))
    return value if isinstance(value, str) else None


def main() -> int:
    event = read_payload()
    if event is None:
        # FAIL OPEN. See "FAIL DIRECTIONS" in the header: we cannot tell whose command this
        # is, and denying would hit the main agent. reflection-gate.py fails CLOSED on the
        # same event, so the chain still denies.
        hlog("ERROR", "unparsable PreToolUse payload - passing through (fail open); "
                      "reflection-gate.py fails closed on the same event")
        return 0

    agent = str(event.get("agent_type") or "").strip().casefold()
    if agent != GUARDED_AGENT:
        # Explicit pass-through. The main agent (agent_type absent) and every other
        # subagent must not notice this hook exists.
        return 0

    tool_name = str(event.get("tool_name") or "")
    if tool_name and tool_name != "Bash":
        return 0

    command = tool_command(event)
    if command is None:
        # FAIL CLOSED: we know it is the implementer and cannot read what it asked for.
        return emit(False, "<unreadable>", "the Bash payload carries no readable command")

    allowed, reason = decide(command, project_root())
    if allowed:
        return 0
    return emit(False, command, reason)


def emit(_allowed: bool, command: str, reason: str) -> int:
    message = denial_message(command, reason)
    tokens = redact(command).split()
    first = safe(re.split(r"[/\\]", tokens[0])[-1], "empty") if tokens else "empty"
    # Both the head and the reason go through safe(): everything logged here was already
    # rejected, so it is exactly the text most likely to carry a credential or host path.
    # NOT safe(reason): every value interpolated into a reason has already been through
    # safe(), and the one deliberate exception is the bare NAME of an environment
    # assignment - which is exactly the detail that makes the block actionable and
    # carries no secret. Digesting the whole sentence would throw that away.
    flat = " ".join((reason or "unspecified").split())
    record = "head=%s reason=%s" % (first, flat[:200])
    if os.environ.get("ECC_HOOK_PROFILE", "standard") == "minimal":
        # DELIBERATE DIVERGENCE - see PROFILE CONVENTION in the header.
        hlog("WOULD-BLOCK", record)
        return 0
    hlog("BLOCK", record)
    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
