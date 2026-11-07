#!/usr/bin/env python3
"""team-event-log: PostToolUse + Stop hook (advisory). Heartbeat on every call, an event
for Edit/Write/MultiEdit/NotebookEdit paths; with --stop it writes the <=10-line handoff
to .team/notes/<sid>.md. Prints nothing. No-op unless `.team/config.json` exists."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "operations", "scripts"))
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def main() -> int:
    try:
        import team

        payload = json.loads(sys.stdin.read() or "{}")
        cwd = payload.get("cwd") or os.getcwd()
        d = team.active_dir(cwd)
        if d is None:
            return 0
        sid = str(payload.get("session_id") or "unknown")
        team.heartbeat(d, sid, cwd)
        if "--heartbeat" in sys.argv[1:]:
            return 0  # PreToolUse: only record who this session is, before the tool runs
        if "--stop" in sys.argv[1:]:
            team.append_event(d, sid, "session.stop")
            team.write_handoff(d, sid)
            return 0
        if payload.get("tool_name") in EDIT_TOOLS:
            inp = payload.get("tool_input") or {}
            path = inp.get("file_path") or inp.get("notebook_path") or ""
            if path:
                top = team.worktree_top(cwd)
                real = os.path.realpath(path)
                rel = os.path.relpath(real, top) if real.startswith(top) else real
                team.append_event(d, sid, "edit", ref=rel.replace(os.sep, "/"))
    except Exception:  # advisory: never break a session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
