#!/usr/bin/env python3
"""panel-format-check.py - Stop + PreToolUse(SubagentHandback) hook in the /review critics.

WHY THIS EXISTS
---------------
Audit 2026-11-11: 62/335 critic replies had no `PANEL:` line and 49 ran over 3,000 chars, so
review-panel.py merge had to mark them incomplete. One re-ask with the validation error
(the Instructor re-ask pattern) fixes most of them at the source.

WHAT IT DOES
------------
Reads the SubagentStop JSON on stdin. stop_hook_active true -> allow (one retry max).
last_assistant_message <= 3,000 chars whose last non-empty line is
`PANEL: <n> blocker, <n> major` or `PANEL: incomplete...` -> allow. Otherwise prints
{"decision":"block","reason":...} so the critic reformats once. Any parse error -> allow
(the panel is advisory; merge validates the format a second time). stdlib, py3.9.

V5 live run 2026-11-11: critics end with a SubagentHandback tool call whose
tool_input.message is the reply; last_assistant_message is then not a str, so the Stop
path never fired. The same check therefore also runs as PreToolUse on SubagentHandback:
a bad message is denied once per (session_id, agent_id) with permissionDecision deny and
the critic hands back again. A marker under $TMPDIR/panel-format-check/ records the one
denial; the next handback is allowed.
"""
import hashlib
import json
import os
import re
import sys
import tempfile

PANEL_RE = re.compile(r"^PANEL: (\d+) blocker, (\d+) major\s*$")
INCOMPLETE_RE = re.compile(r"^PANEL: incomplete\b")
MAX_CHARS = 3000
REASON = ("Reformat: at most 8 findings, under 3,000 chars, last line exactly "
          "`PANEL: <n> blocker, <n> major` (or `PANEL: incomplete - <reason>`). Do not call tools.")
HANDBACK_REASON = ("Reformat the handback message: at most 8 findings, under 3,000 chars, last line "
                   "exactly `PANEL: <n> blocker, <n> major` (or `PANEL: incomplete - <reason>`). "
                   "Then call SubagentHandback again with the reformatted message.")


def ok(message):
    if len(message) > MAX_CHARS:
        return False
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    if not lines:
        return False
    return bool(PANEL_RE.match(lines[-1]) or INCOMPLETE_RE.match(lines[-1]))


def decide(payload):
    """JSON text to print, or '' to allow."""
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return ""
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return ""
    if ok(message):
        return ""
    return json.dumps({"decision": "block", "reason": REASON})


def _marker(payload):
    key = "%s|%s" % (payload.get("session_id", ""),
                     payload.get("agent_id") or payload.get("transcript_path", ""))
    name = hashlib.sha256(key.encode()).hexdigest()[:24]
    return os.path.join(tempfile.gettempdir(), "panel-format-check", name)


def decide_handback(payload, marker=None):
    """PreToolUse(SubagentHandback): JSON deny text once per agent, or '' to allow."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "SubagentHandback":
        return ""
    tool_input = payload.get("tool_input")
    message = tool_input.get("message") if isinstance(tool_input, dict) else None
    if not isinstance(message, str) or ok(message):
        return ""
    marker = marker or _marker(payload)
    if os.path.exists(marker):
        return ""
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w") as fh:
        fh.write("denied\n")
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": HANDBACK_REASON}})


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict) and payload.get("hook_event_name") == "PreToolUse":
            out = decide_handback(payload)
        else:
            out = decide(payload)
    except Exception:  # noqa: BLE001 - fail open: advisory panel
        return 0
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
