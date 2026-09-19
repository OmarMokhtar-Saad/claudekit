#!/usr/bin/env python3
"""batch-reads-nudge.py - PostToolUse (advisory, Bash only): one line after N consecutive
read-only Bash calls, asking the agent to batch them.

WHY THIS EXISTS
---------------
Measured on qa-agents session 13e84805 (2026-09-19): 2.6M tokens, three user messages, zero
edits. Fourteen separate Bash calls read six Kotlin files - head, tail, find, cat, one file
per call - and each call re-sent the whole 77K context. The reads themselves added 32K.
Every turn costs the full context regardless of how little it does, so the cheapest turn is
the one that does not happen: `cat a; sed -n '1,80p' b; grep -n foo c` is one turn, not three.

WHAT IT DOES
------------
Keeps a per-session streak of CONSECUTIVE read-only Bash commands in
.claude/hooks/.state/read-streak-<session>. A command is read-only only when EVERY segment
of the pipeline starts with a command in READ_ONLY (git limited to its read subcommands, sed
without -i) and nothing redirects to a file. Anything else - an edit, a test run, a build, an
unknown binary - resets the streak to zero: an unclassifiable command is treated as work,
never as a read, so the nudge can only under-fire. At NUDGE_AT and every NUDGE_AT after, one
advisory line is emitted as `hookSpecificOutput.additionalContext` JSON on stdout.

DELIVERY, measured (qa-agents transcripts, 2026-09-19): plain stdout from a PostToolUse hook is
recorded in the transcript as a `hook_success` attachment and NEVER reaches the model (18,345
such attachments, 0 in model context); only the `additionalContext` JSON form does (13
`hook_additional_context` attachments, all from hooks that emitted JSON). A nudge on plain
stdout is a dead letter, so this hook emits the JSON form. It runs DIRECTLY from settings.json,
not through dispatch.sh, which would prefix the JSON and break it.

Advisory tier: exit 0 always, nothing on stderr, a broken counter never touches a verdict.
`CK_NO_READ_NUDGE=1` silences it for one process tree. stdlib only, py3.9.
"""

import json
import os
import re
import shlex
import sys

NUDGE_AT = 5

READ_ONLY = frozenset((
    "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ag", "find", "fd",
    "ls", "tree", "wc", "stat", "file", "du", "df", "pwd", "echo", "printf", "awk", "cut",
    "sort", "uniq", "tr", "diff", "cmp", "md5", "md5sum", "shasum", "jq", "which", "type",
    "env", "date", "basename", "dirname", "realpath", "readlink", "test", "[", "true",
    "column", "nl", "od", "xxd", "strings", "tac", "rev", "comm", "paste", "expand", "fold",
))
GIT_READ = frozenset((
    "status", "log", "diff", "show", "branch", "ls-files", "blame", "rev-parse", "describe",
    "remote", "tag", "shortlog", "grep", "cat-file", "ls-tree", "check-ignore", "config",
))
# Splits a compound command into segments; the operators themselves are dropped.
SPLIT = re.compile(r"\s*(?:\|\||&&|\||;|\n)\s*")
# An unquoted redirect that creates or appends a file. `2>&1` and `>/dev/null` are allowed.
WRITES_FILE = re.compile(r"(?<![0-9&])>>?\s*(?!&|/dev/null)\S")


def _segments(command):
    return [seg for seg in SPLIT.split(command) if seg and seg.strip()]


def _first_word(segment):
    """The command a segment runs, after leading `cd DIR`, env assignments and `time`/`nice`."""
    try:
        words = shlex.split(segment, posix=True)
    except ValueError:
        return None
    while words:
        head = words[0]
        if head in ("cd", "pushd") and len(words) >= 2:
            return "cd"  # a bare `cd x` segment; the real command is the NEXT segment
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head) or head in ("time", "nice", "command", "builtin"):
            words = words[1:]
            continue
        return head
    return None


def is_read_only(command):
    """True only when every segment is a known read and nothing writes a file."""
    if not isinstance(command, str) or not command.strip():
        return False
    if WRITES_FILE.search(command):
        return False
    saw_read = False
    for seg in _segments(command):
        if WRITES_FILE.search(seg):
            return False
        try:
            words = shlex.split(seg, posix=True)
        except ValueError:
            return False
        if not words:
            continue
        head = _first_word(seg)
        if head is None:
            return False
        if head == "cd":
            continue
        if head == "sed":
            if any(w == "-i" or w.startswith("-i") for w in words[1:]):
                return False
            saw_read = True
            continue
        if head == "git":
            sub = next((w for w in words[1:] if not w.startswith("-")), None)
            if sub not in GIT_READ:
                return False
            saw_read = True
            continue
        if head not in READ_ONLY:
            return False
        saw_read = True
    return saw_read


def _state_path(session_id):
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        root = os.getcwd()
        if not os.path.isdir(os.path.join(root, ".claude", "hooks")):
            return None
    safe = "".join(ch for ch in str(session_id or "unknown") if ch.isalnum() or ch in "-_.")[:64]
    return os.path.join(root, ".claude", "hooks", ".state", "read-streak-%s" % (safe or "unknown"))


def _streak(session_id, read_only):
    """Update and return the streak; None when there is nowhere to keep it."""
    path = _state_path(session_id)
    if path is None:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        count = 0
        if read_only and os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                try:
                    count = int(handle.read().strip() or "0")
                except ValueError:
                    count = 0
        count = count + 1 if read_only else 0
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("%d\n" % count)
        return count
    except Exception:
        return None


def main():
    if os.environ.get("CK_NO_READ_NUDGE") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict) or (payload.get("tool_name") or payload.get("name")) != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    try:
        streak = _streak(payload.get("session_id"), is_read_only(command))
    except Exception:
        return 0
    if streak and streak % NUDGE_AT == 0:
        note = (
            "[ck batch-reads] %d consecutive read-only Bash calls. Every call re-sends your "
            "whole context, so reads cost by the TURN, not by the byte: combine the next ones "
            "into one call (`cat a; sed -n '1,80p' b; grep -n pat c`) or read only the region "
            "you need. Silence for one process tree with CK_NO_READ_NUDGE=1." % streak)
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": note}}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
