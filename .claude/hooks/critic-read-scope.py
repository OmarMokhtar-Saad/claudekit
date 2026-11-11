#!/usr/bin/env python3
"""critic-read-scope.py - PreToolUse (Read|Grep|Glob) in the /review critics' frontmatter.

WHY THIS EXISTS
---------------
The critics are zero-context by contract, but `tools: Read, Grep` is unscoped: a critic could
read the reviewer's saved review, the other critic's reply, a coordinator brief or a session
handoff and stop being independent. Frontmatter has no path-scoped Read, so this hook is the
scope (docs: PreToolUse on tool_input.file_path / path).

WHAT IT DOES
------------
Target = tool_input.file_path or tool_input.path (Grep/Glob with no path = cwd = allowed).
Exit 2 with a reason when the real path is outside $CLAUDE_PROJECT_DIR (except a
.claude/plans/plan-*.md plan itself in another repo, or behind a .claude/plans dir that
is a symlink to a dir outside the project; a symlinked plan file is never excepted), or is a
*.review.md / *.panel-*.md plan sibling, hook state, a report, a brief*.md, a
session-context.md or anything under handoffs/. Missing or odd input -> allow. stdlib, py3.9.
"""
import fnmatch
import json
import os
import sys

DENY_GLOBS = (
    ".claude/plans/*.review.md",
    ".claude/plans/*.panel-*.md",
    ".claude/hooks/.state/*",
    ".claude/reports/*",
)
DENY_NAMES = ("brief*.md", "session-context.md")


def _plan_behind_symlinked_dir(target, root):
    """True for a regular plan-*.md whose lexical parent is a .claude/plans dir that is a
    symlink to a dir outside the project. The leaf itself may not be a symlink; an
    in-project target falls through to the realpath deny checks below."""
    lex = os.path.normpath(os.path.join(root, os.path.expanduser(target)))
    name = os.path.basename(lex)
    if not fnmatch.fnmatch(lex.replace(os.sep, "/"), "*/.claude/plans/plan-*.md") \
            or os.path.basename(os.path.dirname(lex)) != "plans" \
            or any(fnmatch.fnmatch(name, g) for g in ("*.review.md", "*.panel-*.md")) \
            or os.path.islink(lex):
        return False
    real = os.path.realpath(lex)
    if real == root or real.startswith(root + os.sep):
        return False
    return os.path.isfile(real) and not os.path.islink(real) and os.path.basename(real) == name


def blocked(target, root):
    """Reason string when `target` is out of scope, else ''."""
    root = os.path.realpath(root)
    if _plan_behind_symlinked_dir(target, root):
        return ""
    path = os.path.realpath(os.path.join(root, os.path.expanduser(target)))
    if path != root and not path.startswith(root + os.sep):
        # /review may name a plan in another repo (the critics are user-level): that plan
        # file itself is in scope, never its siblings or anything else outside the project.
        name = os.path.basename(path)
        if fnmatch.fnmatch(path.replace(os.sep, "/"), "*/.claude/plans/plan-*.md") \
                and not any(fnmatch.fnmatch(name, g) for g in ("*.review.md", "*.panel-*.md")):
            return ""
        return "outside the project"
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    for pattern in DENY_GLOBS:
        if fnmatch.fnmatch(rel, pattern):
            return "matches %s" % pattern
    parts = rel.split("/")
    if "handoffs" in parts:
        return "under handoffs/"
    for pattern in DENY_NAMES:
        if fnmatch.fnmatch(parts[-1], pattern):
            return "matches **/%s" % pattern
    return ""


def decide(payload):
    """(exit code, stderr)."""
    if not isinstance(payload, dict):
        return 0, ""
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return 0, ""
    target = ti.get("file_path") or ti.get("path")
    if not isinstance(target, str) or not target.strip():
        return 0, ""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    reason = blocked(target, root)
    if reason:
        return 2, ("critic-read-scope: %s is out of scope for a zero-context critic (%s). "
                   "Read only the plan and the repo files it names." % (target, reason))
    return 0, ""


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    code, err = decide(payload)
    if err:
        print(err, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
