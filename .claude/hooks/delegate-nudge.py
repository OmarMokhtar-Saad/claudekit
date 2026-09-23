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

ENFORCEMENT (top two tiers): when the session model is on the first two tiers of the
degrade_to ladder (frontier, most-capable) and route-hint.py fired for this prompt_id, the 4th
direct Read/Grep/Glob of the turn is denied - exit 2, the explore Agent call as the reason on
stderr. Re-reading a file opened this turn, or the one file the prompt named, stays allowed;
subagent calls (agent_id in the payload) are never counted. Session model: the transcript's
latest main-thread model, else the session-model.py ledger; unknown stays advisory.
`"delegation": {"enforce": false}` in .claude/settings(.local).json turns the deny off.

Otherwise advisory: exit 0, nothing on stderr. `CK_NO_DELEGATE_NUDGE=1` silences it.
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
        if str(message.get("model") or "").startswith("claude"):
            state["model"] = message["model"]
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


# ---- enforcement on the top two tiers -------------------------------------------------
# On frontier/most-capable, a route-hinted turn gets TURN_LIMIT direct Read/Grep/Glob calls;
# the next is denied with the explore Agent call as the reason. Measured: capped explore on
# sonnet cost $0.14 where opus answering the same question directly cost $0.22 - and opus
# ignored the advisory hint. Sonnet and haiku stay advisory: there the parent is already cheap.
TURN_LIMIT = 3
ENFORCED = ("Read", "Grep", "Glob")


def enforce_enabled(root):
    """`delegation.enforce` from .claude/settings.local.json, then settings.json; default True."""
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as fh:
                value = (json.load(fh).get("delegation") or {}).get("enforce")
        except Exception:
            continue
        if isinstance(value, bool):
            return value
    return True


def top_tiers(tiers):
    """The first two tiers of the degrade_to ladder, starting at the tier nothing degrades to."""
    targets = {spec.get("degrade_to") for spec in tiers.values()}
    heads = [name for name in tiers if name not in targets]
    order, cursor = [], heads[0] if len(heads) == 1 else None
    while cursor in tiers and cursor not in order and len(order) < 2:
        order.append(cursor)
        cursor = tiers[cursor].get("degrade_to")
    return order


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def session_model(state, root, session_id):
    """The transcript's latest main-thread model (tracks /model); before the transcript has
    one, the SessionStart ledger written by session-model.py."""
    if state.get("model"):
        return state["model"]
    safe = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "-_")[:64]
    ledger = os.path.join(root, ".claude", "runtime", "session-model", (safe or "unknown") + ".json")
    return _json(ledger).get("model")


def _named(path, named):
    files = [n for n in named or [] if not n.endswith("/")]
    if len(files) != 1:
        return False
    want = os.path.normpath(files[0])
    got = os.path.normpath(path)
    return got == want or got.endswith(os.sep + want)


def gate(payload, state, report, root):
    """Deny reason for this call, or None. Enforces only when every condition holds: main
    thread (no agent_id), a Read/Grep/Glob, route-hint fired for this prompt_id,
    delegation.enforce on, and the session model on one of the top two tiers."""
    tool = payload.get("tool_name")
    prompt_id = payload.get("prompt_id")
    if payload.get("agent_id") or tool not in ENFORCED or not prompt_id:
        return None
    hint = _json(report.route_state_path(root, payload.get("session_id")))
    if hint.get("prompt_id") != prompt_id or not enforce_enabled(root):
        return None
    tiers = report.load_tiers(root)
    tier = report.tier_for(session_model(state, root, payload.get("session_id")), tiers)
    if tier is None or tier not in top_tiers(tiers):
        return None
    call = report.explore_call(root)
    try:
        turn = state.get("turn") or {}
        if turn.get("prompt_id") != prompt_id:
            turn = {"prompt_id": prompt_id, "count": 0, "opened": []}
        state["turn"] = turn
        path = (payload.get("tool_input") or {}).get("file_path") if tool == "Read" else None
        if isinstance(path, str) and (path in turn["opened"] or _named(path, hint.get("named"))):
            if path not in turn["opened"]:
                turn["opened"].append(path)
            return None
        if turn["count"] >= TURN_LIMIT:
            return ("[ck delegate] %d direct Read/Grep/Glob calls this turn on the %s tier. "
                    "Continue the search with %s and keep only its conclusion. "
                    "(Re-reading a file already opened this turn, or the one file the prompt "
                    "names, stays allowed. Turn off per project: \"delegation\": "
                    "{\"enforce\": false} in .claude/settings.json.)" % (TURN_LIMIT, tier, call))
        turn["count"] += 1
        if isinstance(path, str):
            turn["opened"].append(path)
        return None
    except Exception:
        # Engaged and broken: fail closed, as every blocking hook here does.
        return "[ck delegate] delegation gate error; continue the search with %s." % call


def main():
    if "--dispatched" in sys.argv[1:] or os.environ.get("CK_NO_DELEGATE_NUDGE") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
        transcript = payload.get("transcript_path") if isinstance(payload, dict) else None
        path = _state_path(payload.get("session_id"))
        if path is None:
            return 0
        report = _report_module()
        state = _load(path)
        if isinstance(transcript, str) and os.path.isfile(transcript):
            state = advance(state, transcript, report)
        deny = gate(payload, state, report, report._root())
        nudge = not deny and should_nudge(state)
        if nudge:
            state["nudged_at"] = state["direct"] + state["test"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        return 0
    if deny:
        sys.stderr.write(deny + "\n")
        return 2
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
