#!/usr/bin/env python3
"""review-round-cap.py - PreToolUse (blocking, Agent/Task): refuse the 4th `code-reviewer`
spawn in one session.

WHY THIS EXISTS
---------------
Measured on qa-agents session 60554075 (2026-09-19): six sequential `code-reviewer` rounds
on ONE screen cost 14.2M tokens (160 turns) for 6,382 output tokens; two were cut off at
the 30-turn cap, so their verdicts were truncated. The documented ceiling is 3 rounds
(code-reviewer.md, CLAUDE.md "Review floor"), but that ceiling was prose: the caller never
recorded a round, so `review-record.py`'s MAX_ROUNDS could not see them. The only thing
that counts a round the caller does not record is the spawn itself.

WHAT IT DOES
------------
Counts `code-reviewer` spawns per session in .claude/hooks/.state/review-rounds-<session>.
Spawns 1..CAP pass. Spawn CAP+1 exits 2 with the owner-escalation text on stderr. The
counter is written only for spawns that pass, so a refused spawn does not inflate it.

Escape hatch: `CK_REVIEW_ROUND_CAP=N` raises (or, with 0, disables) the cap for one
process tree - it is the OWNER's knob, after the owner has read the open blockers. Any
other agent type is never counted and never blocked.

A counter that cannot be read or written cannot count, so an I/O failure ALLOWS with one
advisory line on stderr: this is a spend cap, not a security control, and a broken file
must not stop every review. stdlib only, py3.9.
"""
import json
import os
import sys

CAP = 3
STATE_DIR = os.path.join(".claude", "hooks", ".state")
REVIEWER = "code-reviewer"


def _cap():
    raw = os.environ.get("CK_REVIEW_ROUND_CAP")
    if raw is None or not raw.strip():
        return CAP
    try:
        return max(0, int(raw))
    except ValueError:
        return CAP


def _state_path(session_id):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    safe = "".join(ch for ch in str(session_id or "unknown")
                   if ch.isalnum() or ch in "-_.")[:64]
    return os.path.join(root, STATE_DIR, "review-rounds-" + (safe or "unknown"))


def _read(path):
    try:
        with open(path) as fh:
            return int(fh.read().strip() or 0)
    except FileNotFoundError:
        return 0


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(str(value))
    os.replace(tmp, path)


def _is_reviewer_spawn(payload):
    if not isinstance(payload, dict):
        return False
    tool = payload.get("tool_name") or payload.get("name")
    if tool not in ("Agent", "Task"):
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    return str(tool_input.get("subagent_type") or "").strip() == REVIEWER


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not _is_reviewer_spawn(payload):
        return 0
    cap = _cap()
    if cap == 0:
        return 0
    path = _state_path(payload.get("session_id"))
    try:
        seen = _read(path)
    except (OSError, ValueError) as exc:
        sys.stderr.write("[review-round-cap] advisory: cannot read %s (%s); not counting\n"
                         % (path, exc))
        return 0
    if seen >= cap:
        sys.stderr.write(
            "[review-round-cap] BLOCKED: code-reviewer round %d refused - the ceiling is %d "
            "rounds per session.\n"
            "Reaching it with blockers still open is an OWNER escalation, not another "
            "round: list the open Critical/High findings to the user and stop. The owner "
            "may raise the cap for this process tree with CK_REVIEW_ROUND_CAP=%d after "
            "reading them. (Measured: 6 rounds on one screen = 14.2M tokens, session "
            "60554075.)\n" % (seen + 1, cap, seen + 1))
        sys.exit(2)
    try:
        _write(path, seen + 1)
    except OSError as exc:
        sys.stderr.write("[review-round-cap] advisory: cannot write %s (%s); not counting\n"
                         % (path, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
