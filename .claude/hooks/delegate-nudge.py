#!/usr/bin/env python3
"""delegate-nudge.py - PreToolUse (advisory; Read|Grep|Glob|Bash): one line telling the parent
to hand exploration to an `explore` subagent, when the session is paying for not doing so.

WHY THIS EXISTS
---------------
A direct Read/Grep/Glob/Bash call re-sends the parent's whole context on the parent's tier. Past
60k context, a dozen such calls cost more than one fast-tier `explore` agent that returns only
its conclusion. delegation-report.py shows the split after the fact; this says it while it can
still change the turn.

WHEN IT FIRES - all three, then at most once per COOLDOWN further direct/test calls:
  * session context > CONTEXT_FLOOR tokens (last assistant usage in the transcript);
  * >= DIRECT_AT direct exploration calls, or >= TESTS_AT test runs (classify() in
    delegation-report.py - one classifier for both hooks);
  * zero Agent/Task calls this session. One delegation proves the habit; the nudge stops.

Counts come from the transcript itself, scanned INCREMENTALLY: .claude/hooks/.state/
delegate-<session> keeps the byte offset reached and the running counts, so each call reads
only what was appended since the last one. A transcript shorter than the offset (rotated,
replaced) restarts the scan.

DELIVERY: `hookSpecificOutput.additionalContext` JSON on stdout - the only form that reaches
the model (see batch-reads-nudge.py). So this runs DIRECTLY from settings.json. Its
dispatch-registry row passes `--dispatched`, which exits 0 at once: the registry must list every
settings hook (test_dispatch_merge), and dispatch.sh would otherwise run it a second time and
prefix its JSON.

Advisory tier: exit 0 always, nothing on stderr. `CK_NO_DELEGATE_NUDGE=1` silences it.
stdlib only, py3.9.
"""

import importlib.util
import json
import os
import sys

CONTEXT_FLOOR = 60000
DIRECT_AT = 12
TESTS_AT = 3
COOLDOWN = 15


def _report_module():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delegation-report.py")
    spec = importlib.util.spec_from_file_location("ck_delegation_report", here)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state_path(session_id):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.isdir(os.path.join(root, ".claude", "hooks")):
        return None
    safe = "".join(ch for ch in str(session_id or "unknown") if ch.isalnum() or ch in "-_.")[:64]
    return os.path.join(root, ".claude", "hooks", ".state", "delegate-%s" % (safe or "unknown"))


def _load(path):
    fresh = {"offset": 0, "direct": 0, "test": 0, "agent": 0, "context": 0, "nudged_at": None}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        if isinstance(state, dict):
            fresh.update(state)
    except (OSError, ValueError):
        pass
    return fresh


def advance(state, transcript, report):
    """Fold the transcript bytes past state['offset'] into the counts; return state."""
    size = os.path.getsize(transcript)
    if size < state["offset"]:
        state.update(offset=0, direct=0, test=0, agent=0, context=0, nudged_at=None)
    with open(transcript, "rb") as fh:
        fh.seek(state["offset"])
        blob = fh.read()
    # Only whole lines are consumed; a line still being written is read next time.
    end = blob.rfind(b"\n") + 1
    for line in blob[:end].decode("utf-8", errors="replace").split("\n"):
        if '"assistant"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                kind = report.classify(block.get("name"), block.get("input"))
                if kind:
                    state[kind] += 1
        usage = message.get("usage")
        if isinstance(usage, dict):
            context = sum(v for k, v in usage.items()
                          if k in report.CONTEXT_KEYS and isinstance(v, int)
                          and not isinstance(v, bool))
            if context:
                state["context"] = context
    state["offset"] += end
    return state


def should_nudge(state):
    if state["agent"] or state["context"] <= CONTEXT_FLOOR:
        return False
    if state["direct"] < DIRECT_AT and state["test"] < TESTS_AT:
        return False
    work = state["direct"] + state["test"]
    return state["nudged_at"] is None or work - state["nudged_at"] >= COOLDOWN


def main():
    if "--dispatched" in sys.argv[1:] or os.environ.get("CK_NO_DELEGATE_NUDGE") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
        transcript = payload.get("transcript_path") if isinstance(payload, dict) else None
        path = _state_path(payload.get("session_id"))
        if path is None or not isinstance(transcript, str) or not os.path.isfile(transcript):
            return 0
        report = _report_module()
        state = advance(_load(path), transcript, report)
        nudge = should_nudge(state)
        if nudge:
            state["nudged_at"] = state["direct"] + state["test"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        return 0
    if nudge:
        note = (
            "[ck delegate] %d direct exploration calls, %d test runs and no subagent at %dk "
            "context: each call re-sends that whole context on your tier. Hand the remaining "
            "search to %s and keep only its conclusion; "
            "run test suites through a subagent that returns the failures. Silence for one "
            "process tree with CK_NO_DELEGATE_NUDGE=1." % (
                state["direct"], state["test"], state["context"] // 1000,
                report.explore_call(report._root())))
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "additionalContext": note}}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
