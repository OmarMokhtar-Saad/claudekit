#!/usr/bin/env python3
"""team-session-start: SessionStart hook (advisory). Registers the session and prints
`team status` (<=15 lines). Peer notes and inbox text are printed inside a fenced
block marked untrusted. No-op (silent, exit 0) unless `.team/config.json` exists."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "operations", "scripts"))


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
        team.append_event(d, sid, "session.start")
        gate_off = d / "gate.off"
        if gate_off.exists():
            team.append_event(d, sid, "gate.off", msg="mtime=%d" % int(gate_off.stat().st_mtime))
        print("\n".join(team.session_start_lines(d, sid)))
    except Exception:  # advisory: never break a session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
