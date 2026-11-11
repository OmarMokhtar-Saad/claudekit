#!/usr/bin/env python3
"""panel-format-check.py - Stop hook in the /review critics' frontmatter (runs as SubagentStop).

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
"""
import json
import re
import sys

PANEL_RE = re.compile(r"^PANEL: (\d+) blocker, (\d+) major\s*$")
INCOMPLETE_RE = re.compile(r"^PANEL: incomplete\b")
MAX_CHARS = 3000
REASON = ("Reformat: at most 8 findings, under 3,000 chars, last line exactly "
          "`PANEL: <n> blocker, <n> major` (or `PANEL: incomplete - <reason>`). Do not call tools.")


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


def main():
    try:
        out = decide(json.loads(sys.stdin.read() or "{}"))
    except Exception:  # noqa: BLE001 - fail open: advisory panel
        return 0
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
