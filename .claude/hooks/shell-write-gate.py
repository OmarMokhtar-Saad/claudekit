#!/usr/bin/env python3
"""shell-write-gate.py - PreToolUse/Bash: deny obvious shell writes to protected paths.

Protected: .claude/reports/reviews/ (the authoritative plan-approval records), the
settings files (.claude/settings.json, .claude/settings.local.json) and
.claude/plan-gate.globs. plan-gate.sh already denies Edit/Write there; this closes the
same paths against the cheapest shell forms: > >> tee, sed -i, touch, cp, mv, and
`python -c` / heredoc scripts that open-for-write.

HONEST LIMIT (kit hard rule 6): a denylist speed bump, not a sandbox. Obvious forms
only; an obfuscated command can still forge a record. The owner approval step is the
real control.

FAILS CLOSED, unlike bash-payload-gate: a payload that cannot be parsed blocks. No
ECC_HOOK_PROFILE early exit - it binds under `minimal` too.
Blocking = exit 2 + stderr (kit hard rule 2).

Also: `rm`, `git rm` and `unlink` of a git-tracked Tier-3 file (plan-lib.sh `pg_is_t3`) are
denied unless the approved plan marks the path `(delete)` in `Files:`. Untracked files
(`rm -rf build`, `.pyc`) are never blocked. Not detected: `find -delete`, `git clean`, `mv`,
scripted `os.remove`, a delete inside `$(...)` (speed bump, not a sandbox).
"""
import glob
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = (
    r"\.claude/reports/reviews",
    r"\.claude/settings(?:\.local)?\.json",
    r"\.claude/plan-gate\.globs",
    r"plan-gate\.globs",
)
_PATH = "(?:%s)" % "|".join(PROTECTED)
# Verbs that write to (or replace) their destination argument.
_WRITE_VERB = re.compile(
    r"(?:^|[;&|(`]|\s)(?:tee|touch|cp|mv|install|ln|dd|truncate|rm|rsync|perl|sed|"
    r"awk|python3?|ruby|node)\b")
_REDIRECT = re.compile(r">>?\s*['\"]?[^\s;&|'\"]*" + _PATH)
_SED_I = re.compile(r"\bsed\b[^;&|\n]*\s-[A-Za-z]*i")
_PY_WRITE = re.compile(r"open\([^)]*['\"][wax]\+?b?['\"]|write_text|write_bytes|\.write\(")


def _violates(command: str) -> str:
    """Name the matched form, or '' when the command is not an obvious protected write."""
    if not re.search(_PATH, command):
        return ""
    if _REDIRECT.search(command):
        return "redirect (> / >>)"
    for segment in re.split(r"[;&|\n]+", command):
        if not re.search(_PATH, segment):
            continue
        if re.search(r"\b(?:tee|touch|cp|mv|install|ln|dd|truncate|rm|rsync)\b", segment):
            return "write verb"
        if _SED_I.search(segment):
            return "sed -i"
        if re.search(r"\b(?:python3?|ruby|node|perl)\b", segment) and _PY_WRITE.search(command):
            return "script open-for-write"
    if re.search(r"\b(?:python3?|ruby|node|perl)\b", command) and _PY_WRITE.search(command):
        return "script open-for-write"
    return ""

_MAX_DELETE_OPERANDS = 200
_HELPER = r"""
SCRIPT_DIR="$CK_SCRIPT_DIR"; ABS_ROOT="$CK_ROOT"
. "$SCRIPT_DIR/plan-lib.sh" || exit 3
while IFS= read -r -d '' rel; do
    if pg_is_t3 "$rel" && ! pg_authorised_delete "$rel"; then printf '%s\n' "$rel"; fi
done
"""


def _token_segments(command: str) -> list:
    """Quote-aware token lists, split at ; & | and newlines (a `;` inside quotes stays)."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
    lex.whitespace_split = True
    lex.whitespace = " \t\r"
    out: list = [[]]
    for tok in lex:
        if set(tok) <= set(";&|\n"):
            out.append([])
        else:
            out[-1].append(tok)
    return out


_WRAPPERS = {"sudo", "env", "nohup", "time", "exec", "command", "builtin", "xargs", "doas", "nice"}
_SHELLS = {"bash", "sh", "zsh", "dash"}


def _find_delete(toks: list):
    """(args, is_git) for the first rm/unlink/git-rm in a segment, skipping wrappers, flags,
    flag values and VAR= prefixes; None when the segment deletes nothing."""
    toks = [t.lstrip("({").rstrip(")}") for t in toks]
    toks = [t for t in toks if t and t not in ("then", "do", "else", "!")]
    for i, t in enumerate(toks):
        base = os.path.basename(t)
        if base in ("rm", "unlink"):
            return toks[i + 1:], False
        if base == "git":
            j, chdir = i + 1, ""
            while j < len(toks) and toks[j].startswith("-"):
                if toks[j] == "-C" and j + 1 < len(toks):
                    chdir = toks[j + 1]
                j += 2 if toks[j] in ("-C", "-c") else 1
            if j < len(toks) and toks[j] == "rm":
                return toks[j + 1:], chdir or True
            return None
        ok = (t in _WRAPPERS or t.startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)
              or (i > 0 and toks[i - 1].startswith("-")))
        if not ok:
            return None
    return None


def _delete_operands(command: str, cwd: str, depth: int = 0):
    """Paths named by rm / git rm / unlink segments (directories as themselves), or None to
    block ('narrow the command'). Variable operands are skipped."""
    out: list = []
    if depth > 3:
        return None
    try:
        segments = _token_segments(command)
    except ValueError:
        return None
    for toks in segments:
        if toks[:1] == ["cd"] and len(toks) > 1:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(toks[1])))
            continue
        for k, t in enumerate(toks):  # bash -c "rm x": recurse into the string
            if os.path.basename(t) in _SHELLS and "-c" in toks[k + 1:]:
                inner = toks[toks.index("-c", k) + 1:][:1]
                if inner:
                    sub = _delete_operands(inner[0], cwd, depth + 1)
                    if sub is None:
                        return None
                    out.extend(sub)
        found = _find_delete(toks)
        if found is None:
            continue
        args, is_git = found
        if is_git and "--cached" in args:
            continue
        base_cwd = os.path.join(cwd, is_git) if isinstance(is_git, str) else cwd
        ops, dashdash = [], False
        for t in args:
            if not dashdash and t == "--":
                dashdash = True
            elif dashdash or not t.startswith("-"):
                ops.append(t)
        for op in ops:
            if "$" in op or "`" in op:
                continue
            out.extend(glob.glob(os.path.join(base_cwd, op)))
        if len(out) > _MAX_DELETE_OPERANDS:
            return None
    return out


def _git_root(path: str):
    d = path if os.path.isdir(path) and not os.path.islink(path) else os.path.dirname(path)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=d or ".",
                         capture_output=True, text=True, timeout=10)
    return os.path.realpath(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else None


def _tier3_delete_violation(command: str, cwd: str):
    """Tracked Tier-3 paths the command deletes without a `(delete)` marker ([] = fine),
    or None when the command cannot be bounded/checked (block)."""
    if not re.search(r"\b(?:rm|unlink)\b", command):
        return []
    try:
        ops = _delete_operands(command, cwd)
        if ops is None:
            return None
        by_root: dict = {}
        for o in ops:
            parent, base = os.path.split(os.path.abspath(o))
            real = os.path.join(os.path.realpath(parent), base)  # a symlink operand is itself
            root = _git_root(real)
            if root and real.startswith(root + os.sep):
                by_root.setdefault(root, []).append(real[len(root) + 1:])
        bad: list = []
        for root, rels in by_root.items():
            if not os.path.isdir(os.path.join(root, ".claude", "plans")):
                continue
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--"] + [":(literal)" + r for r in rels], cwd=root,
                capture_output=True, text=True, timeout=20)
            if tracked.returncode != 0:
                return None
            targets = [r for r in tracked.stdout.split("\0") if r]
            if not targets:
                continue
            hooks = os.path.dirname(os.path.abspath(__file__))
            env = dict(os.environ, CK_SCRIPT_DIR=hooks, CK_ROOT=root)
            proc = subprocess.run(["bash", "-c", _HELPER], input="".join(t + "\0" for t in targets),
                                  env=env, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                return None
            bad += [ln for ln in proc.stdout.splitlines() if ln]
        return bad
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            raise ValueError("no command string")
    except Exception as exc:  # fail CLOSED
        sys.stderr.write("BLOCKED shell-write-gate: could not parse the Bash payload (%s); "
                         "refusing an unverified command.\n" % exc)
        return 2
    form = _violates(command)
    if not form:
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
        bad = _tier3_delete_violation(command, cwd)
        if bad == []:
            return 0
        if bad is None:
            sys.stderr.write("BLOCKED shell-write-gate: could not verify this deletion "
                             "(too many operands or helper failed); narrow the command.\n")
            return 2
        sys.stderr.write(
            "BLOCKED shell-write-gate: deleting Tier-3 file(s) not marked in the approved plan: "
            "%s. List each in the plan's `Files:` as `path` (delete) (max 3 per plan), then "
            "re-review and record it.\n" % ", ".join(bad))
        return 2
    sys.stderr.write(
        "BLOCKED shell-write-gate: %s targets a protected path (review records, settings "
        "files or plan-gate.globs). These are owner-only: ask the owner to run it with "
        "`! <command>`. (Speed bump, not a sandbox.)\n" % form)
    return 2


if __name__ == "__main__":
    # A literal sys.exit(2) path exists in main(); never exit 1 for a block.
    sys.exit(main())
