#!/usr/bin/env python3
"""delegation-report.py - Stop (advisory): one line per turn-end saying who did the reading
and what it cost, in raw tokens and in dollars by capability tier.

WHY THIS EXISTS
---------------
Every main-thread turn re-sends the whole context, so exploration done directly by the parent
is paid at the parent's context size and the parent's tier. The same reads done by an
`explore` subagent on the fast tier cost a small, separate context that is thrown away. The
split was invisible: nothing reported how many calls the parent made itself versus delegated,
or what each side cost. This hook reports it; delegate-nudge.py acts on the same counts.

WHAT IT DOES
------------
Scans the session transcript (payload `transcript_path`) and its subagent transcripts
(`<transcript minus .jsonl>/subagents/agent-*.jsonl`, the layout Claude Code writes):
  * main-thread tool calls, classified by `classify()`: `agent` (Agent/Task), `test` (a Bash
    test runner), `direct` (Read/Grep/Glob and every other Bash call);
  * tokens per assistant message, deduplicated by message id (one message is split across
    several transcript lines that repeat the same usage);
  * peak context (input + cache read + cache write of the largest main-thread request).
Tokens are priced with `usd_per_mtok` from .claude/model-policy.json capability_tiers - the one
price table; a model matching no tier is counted as tokens and reported as unpriced.

Writes one line to stderr and one `delegation_report` record to
.claude/runtime/events/<safe-session>.jsonl (O_APPEND, 0o600).

Advisory tier: exit 0 always; any failure is silent. `CK_NO_DELEGATION_REPORT=1` silences it.
stdlib only, py3.9.
"""

import glob
import json
import os
import re
import sys
import time

DIRECT_TOOLS = ("Read", "Grep", "Glob", "Bash")
AGENT_TOOLS = ("Agent", "Task")
TEST_RUN = re.compile(
    r"(^|[\s;&|(])("
    r"pytest|python3?\s+-m\s+pytest|tox|nox|jest|vitest|mocha|"
    r"(npm|pnpm|yarn|bun)\s+(run\s+)?test|go\s+test|cargo\s+test|"
    r"\S*gradlew\S*\s+(\S+\s+)*\S*test\S*|mvn\s+(\S+\s+)*test|swift\s+test|xcodebuild\s+(\S+\s+)*test"
    r")\b")
PRICE_KEYS = (("input_tokens", "input"), ("output_tokens", "output"),
              ("cache_read_input_tokens", "cache_read"),
              ("cache_creation_input_tokens", "cache_write"))
CONTEXT_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def classify(tool_name, tool_input):
    """'agent', 'test', 'direct', or None for a tool that is neither exploration nor delegation."""
    if tool_name in AGENT_TOOLS:
        return "agent"
    if tool_name not in DIRECT_TOOLS:
        return None
    if tool_name == "Bash":
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if isinstance(command, str) and TEST_RUN.search(command):
            return "test"
    return "direct"


def _root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def load_tiers(root):
    """{tier: {"model": str, "usd_per_mtok": dict}} from model-policy.json; {} when absent."""
    try:
        with open(os.path.join(root, ".claude", "model-policy.json"), encoding="utf-8") as fh:
            tiers = json.load(fh).get("capability_tiers") or {}
    except Exception:
        return {}
    return {name: spec for name, spec in tiers.items() if isinstance(spec, dict)}


EXPLORE_MAX_TURNS = 12


def route_state_path(root, session_id):
    """Where route-hint.py records the prompt it fired on, for delegate-nudge.py's gate."""
    safe = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "-_")[:64]
    return os.path.join(root, ".claude", "hooks", ".state", "route-%s" % (safe or "unknown"))


def explore_call(root):
    """The Agent call the nudge and route hint suggest: explore's tier model from the policy,
    its turn cap, and the next rung up the degrade_to ladder to escalate to."""
    try:
        with open(os.path.join(root, ".claude", "model-policy.json"), encoding="utf-8") as fh:
            policy = json.load(fh)
        tiers = policy["capability_tiers"]
        role = policy["roles"]["explore"]
        tier = role["tier"]
        up = role.get("escalate_to") or next(
            (name for name, spec in tiers.items() if spec.get("degrade_to") == tier), None)
        model, up_model = tiers[tier]["model"], tiers[up]["model"] if up else None
    except Exception:
        model, up_model = "haiku", "sonnet"
    text = "Agent(subagent_type=explore, model=%s, maxTurns %d" % (model, EXPLORE_MAX_TURNS)
    if up_model:
        text += "; escalate to model=%s only if it comes back empty" % up_model
    return text + ")"


def open_agents(path):
    """Ids of background Agent calls launched in this transcript with no completion notice yet.

    A Stop that fires while one is open reports a partial session, and fires again when the
    notice lands; deferring to the later Stop prints the report once, complete."""
    launched, done = [], set()
    for record in _records(path):
        if record.get("type") != "user":
            continue
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        result = record.get("toolUseResult")
        if isinstance(result, dict) and result.get("status") == "async_launched":
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("tool_use_id"):
                    launched.append(block["tool_use_id"])
        texts = [content] if isinstance(content, str) else [
            b.get("text") for b in content or [] if isinstance(b, dict)]
        for text in texts:
            if isinstance(text, str) and "<task-notification>" in text:
                done.update(re.findall(r"<tool-use-id>([^<]+)</tool-use-id>", text))
    return [tool_id for tool_id in launched if tool_id not in done]


def tier_for(model_id, tiers):
    model_id = str(model_id or "").lower()
    for name, spec in tiers.items():
        family = str(spec.get("model") or "").lower()
        if family and family in model_id:
            return name
    return "unpriced"


def _records(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def scan(path):
    """Tool-call counts and per-model usage for one transcript.

    Returns {"direct", "agent", "test", "peak_context", "usage": {model: {key: int}}}.
    """
    out = {"direct": 0, "agent": 0, "test": 0, "peak_context": 0, "usage": {}}
    seen = set()
    for record in _records(path):
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                if block.get("id") and block["id"] in seen:
                    continue
                if block.get("id"):
                    seen.add(block["id"])
                kind = classify(block.get("name"), block.get("input"))
                if kind:
                    out[kind] += 1
        usage = message.get("usage")
        msg_id = message.get("id")
        if not isinstance(usage, dict) or (msg_id and msg_id in seen):
            continue
        if msg_id:
            seen.add(msg_id)
        bucket = out["usage"].setdefault(str(message.get("model") or "unknown"), {})
        context = 0
        for key, _ in PRICE_KEYS:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                bucket[key] = bucket.get(key, 0) + value
                if key in CONTEXT_KEYS:
                    context += value
        out["peak_context"] = max(out["peak_context"], context)
    return out


def price(usage_by_model, tiers):
    """(total tokens, {tier: usd}, {unpriced model: tokens}) for a {model: {key: int}} map.

    A model no tier prices is reported by token count, never as $0 - a $0 line would read
    as "free" when the price table simply does not cover it.
    """
    tokens, cost, unpriced = 0, {}, {}
    for model, usage in usage_by_model.items():
        tier = tier_for(model, tiers)
        rates = (tiers.get(tier) or {}).get("usd_per_mtok") or {}
        count = sum(usage.get(key, 0) for key, _ in PRICE_KEYS)
        tokens += count
        if not rates:
            unpriced[model] = unpriced.get(model, 0) + count
            continue
        usd = 0.0
        for key, rate_key in PRICE_KEYS:
            rate = rates.get(rate_key)
            if isinstance(rate, (int, float)):
                usd += usage.get(key, 0) * rate / 1e6
        cost[tier] = cost.get(tier, 0.0) + usd
    return tokens, cost, unpriced


def report(transcript_path, root):
    tiers = load_tiers(root)
    main = scan(transcript_path)
    sub_usage = {}
    base = transcript_path[:-6] if transcript_path.endswith(".jsonl") else transcript_path
    for sub in sorted(glob.glob(os.path.join(base, "subagents", "agent-*.jsonl"))):
        for model, usage in scan(sub)["usage"].items():
            bucket = sub_usage.setdefault(model, {})
            for key, value in usage.items():
                bucket[key] = bucket.get(key, 0) + value
    main_tokens, main_cost, main_unpriced = price(main["usage"], tiers)
    sub_tokens, sub_cost, sub_unpriced = price(sub_usage, tiers)
    unpriced = dict(main_unpriced)
    for model, count in sub_unpriced.items():
        unpriced[model] = unpriced.get(model, 0) + count
    cost_by_tier = {}
    for side in (main_cost, sub_cost):
        for tier, usd in side.items():
            cost_by_tier[tier] = round(cost_by_tier.get(tier, 0.0) + usd, 4)
    return {
        "direct_calls": main["direct"], "agent_calls": main["agent"], "test_runs": main["test"],
        "peak_context": main["peak_context"], "main_tokens": main_tokens,
        "subagent_tokens": sub_tokens, "cost_by_tier": cost_by_tier, "unpriced": unpriced,
    }


def _k(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%dk" % round(n / 1e3)


def render(fields):
    costs = " ".join("%s $%.2f" % (tier, usd)
                     for tier, usd in sorted(fields["cost_by_tier"].items()) if usd)
    total = sum(fields["cost_by_tier"].values())
    line = ("[ck delegation] direct %d · agent %d · tests %d · peak ctx %s · main %s tok · "
            "subagents %s tok · $%.2f (%s)" % (
                fields["direct_calls"], fields["agent_calls"], fields["test_runs"],
                _k(fields["peak_context"]), _k(fields["main_tokens"]),
                _k(fields["subagent_tokens"]), total, costs or "no priced tier"))
    unpriced = fields.get("unpriced") or {}
    if unpriced:
        line += " · unpriced %s tok (%s)" % (_k(sum(unpriced.values())),
                                            ", ".join(sorted(unpriced)))
    return line


def write_event(root, session_id, fields):
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(session_id)) or "unknown"
    directory = os.path.join(root, ".claude", "runtime", "events")
    os.makedirs(directory, exist_ok=True)
    record = {"schema_version": 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "session_id": str(session_id), "kind": "delegation_report"}
    record.update(fields)
    fd = os.open(os.path.join(directory, safe + ".jsonl"),
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def main():
    if os.environ.get("CK_NO_DELEGATION_REPORT") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
        path = payload.get("transcript_path") if isinstance(payload, dict) else None
        if not isinstance(path, str) or not os.path.isfile(path):
            return 0
        if open_agents(path):
            return 0
        root = _root()
        fields = report(path, root)
        sys.stderr.write(render(fields) + "\n")
        write_event(root, payload.get("session_id") or "unknown", fields)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
