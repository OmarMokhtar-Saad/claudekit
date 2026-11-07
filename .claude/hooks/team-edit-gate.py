#!/usr/bin/env python3
"""team-edit-gate: PreToolUse (blocking) for Edit|Write|MultiEdit|NotebookEdit.
Refuses an edit when a live peer holds the path (lease or claimed task files),
a hotspot lacks my lease, or the path is outside my claimed task. The decision
lives in team.gate_decision. Silent no-op (exit 0) unless `.team/config.json`
exists. Fails CLOSED once the repo opted in: lock timeout, corrupt state and
any unexpected error all block (exit 2, at most 3 stderr lines)."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HOOK_NAME = "team-edit-gate"
DEFAULT_PROFILE = "standard"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "operations", "scripts"))


def blocking_enabled() -> bool:
    return os.environ.get("ECC_HOOK_PROFILE", DEFAULT_PROFILE) != "minimal"


def hlog(level: str, message: str) -> None:
    """Append one line to hooks.log. Never raises."""
    try:
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        log = Path(os.environ.get("LOG_FILE") or root / ".claude" / "hooks" / "hooks.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log.open("a", encoding="utf-8") as fh:
            fh.write("[%s] [%s] %s: %s\n" % (stamp, level, HOOK_NAME, message))
    except OSError:  # silent-ok: a gate must decide correctly even with an unwritable log
        pass


def block(reason: str, path: str) -> int:
    first = reason.splitlines()[0][:120]
    if not blocking_enabled():
        hlog("WOULD-BLOCK", "%s (%s)" % (path, first))
        return 0
    hlog("BLOCK", "%s (%s)" % (path, first))
    sys.stderr.write("\n".join(reason.splitlines()[:3]) + "\n")
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # unreadable payload: nothing to gate
    ti = payload.get("tool_input") or {}
    path = str(ti.get("file_path") or ti.get("notebook_path") or "")
    if not path:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    sid = str(payload.get("session_id") or "unknown")
    try:
        import team
    except Exception as e:  # cannot even load the engine: fail closed only if opted in
        if any((Path(p) / ".team" / "config.json").is_file()
               for p in [Path(cwd), *Path(cwd).parents]):
            return block("team import failed (%s): run `team doctor`" % type(e).__name__, path)
        return 0
    try:
        d = team.active_dir(cwd)
        if d is None:
            return 0
        team.heartbeat(d, sid, cwd)  # the CLI reads who I am from this
        reason, note = team.gate_decision(d, sid, cwd, path)
    except TimeoutError:
        return block("team busy, retry the edit", path)
    except team.StateCorrupt as e:
        return block("team state corrupt (%s): run `team doctor`" % str(e)[:80], path)
    except Exception as e:  # fail closed once a repo opted in
        return block("team-edit-gate error %s: run `team doctor`" % type(e).__name__, path)
    if reason:
        return block(reason, path)
    if note:
        sys.stderr.write(note.splitlines()[0] + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
