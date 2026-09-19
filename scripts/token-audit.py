#!/usr/bin/env python3
"""token-audit.py — reproducible token-spend measurement over Claude Code transcripts.

Dedups by requestId (a retried/duplicated record is billed once), separates
billed = input + cache_read + cache_creation + output, buckets every request by
the context it was sent at, and ranks the drivers: turns, prefix size, tool
results, compactions, delegation, duplicate records, hook nags.

Usage: token-audit.py [--json OUT] [--top N] PATH [PATH ...]
  PATH is a transcript .jsonl or a directory of them (subagents/ are folded in).
"""
import argparse
import json
import os
import re
from collections import Counter

USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
BUCKETS = [(0, 100_000, "<100k"), (100_000, 200_000, "100-200k"),
           (200_000, 400_000, "200-400k"), (400_000, 700_000, "400-700k"),
           (700_000, 10**9, ">700k")]
NAG_PATTERNS = {
    "suggest-compact": re.compile(r"CONTEXT TIP: \d+ tool calls"),
    "batch-reads-nudge": re.compile(r"batch|BATCH", re.I),
    "output-filter": re.compile(r"\[output (truncated|filtered)|truncated by output_filter", re.I),
    "context-budget-gate": re.compile(r"context-budget-gate|context budget", re.I),
}


def bucket(ctx):
    for lo, hi, name in BUCKETS:
        if lo <= ctx < hi:
            return name
    return ">700k"


def iter_records(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    out.append(c.get("text", ""))
                elif c.get("type") == "tool_result":
                    out.append(text_of(c.get("content")))
            elif isinstance(c, str):
                out.append(c)
        return "\n".join(out)
    return ""


def new_session():
    return {
        "lines": 0, "assistant_lines": 0, "unique_requests": 0, "dup_lines": 0,
        "billed": 0, "cache_read": 0, "cache_create": 0, "input": 0, "output": 0,
        "raw_sum_undeduped": 0, "peak_context": 0, "first_context": None,
        "buckets": Counter(), "models": Counter(), "tools": Counter(),
        "tool_result_bytes": 0, "tool_result_max": 0, "tool_result_count": 0,
        "compactions": [], "sidechain_requests": 0, "agent_calls": [],
        "skill_calls": Counter(), "attachments": Counter(), "attachment_bytes": Counter(),
        "nags": Counter(), "user_prompts": 0, "user_prompt_bytes": 0,
        "assistant_text_bytes": 0, "single_tool_turns": 0, "multi_tool_turns": 0,
        "consecutive_single_read_turns": 0, "first_ts": None, "last_ts": None,
        "dup_field_diffs": Counter(), "cwd": None, "version": None,
    }


def audit_file(path, agg):
    sid = os.path.basename(path).replace(".jsonl", "")
    s = new_session()
    seen = {}
    tool_use_names = {}
    prev_turn_single_read = False
    for rec in iter_records(path):
        s["lines"] += 1
        t = rec.get("type")
        ts = rec.get("timestamp")
        if ts:
            s["first_ts"] = s["first_ts"] or ts
            s["last_ts"] = ts
        s["cwd"] = s["cwd"] or rec.get("cwd")
        s["version"] = s["version"] or rec.get("version")
        if t == "assistant":
            s["assistant_lines"] += 1
            msg = rec.get("message") or {}
            usage = msg.get("usage") or {}
            ctx = sum(int(usage.get(k) or 0) for k in USAGE_KEYS)
            out = int(usage.get("output_tokens") or 0)
            s["raw_sum_undeduped"] += ctx + out
            rid = rec.get("requestId") or rec.get("uuid")
            content = msg.get("content") or []
            tools_here = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
            for c in tools_here:
                tool_use_names[c.get("id")] = c.get("name")
                s["tools"][c.get("name")] += 1
                inp = c.get("input") or {}
                if c.get("name") in ("Agent", "Task"):
                    s["agent_calls"].append({"type": inp.get("subagent_type"), "id": c.get("id"),
                                             "desc": (inp.get("description") or "")[:60]})
                if c.get("name") == "Skill":
                    s["skill_calls"][inp.get("skill")] += 1
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    s["assistant_text_bytes"] += len(c.get("text", ""))
            if rid in seen:
                s["dup_lines"] += 1
                prev = seen[rid]
                for k in ("usage", "content", "stop_reason", "model"):
                    if (prev.get(k) != msg.get(k)):
                        s["dup_field_diffs"][k] += 1
                continue
            seen[rid] = msg
            s["unique_requests"] += 1
            if rec.get("isSidechain"):
                s["sidechain_requests"] += 1
            s["models"][msg.get("model") or "?"] += 1
            s["billed"] += ctx + out
            s["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
            s["cache_create"] += int(usage.get("cache_creation_input_tokens") or 0)
            s["input"] += int(usage.get("input_tokens") or 0)
            s["output"] += out
            s["peak_context"] = max(s["peak_context"], ctx)
            if s["first_context"] is None and ctx:
                s["first_context"] = ctx
            s["buckets"][bucket(ctx)] += ctx + out
            agg["bucket_tokens"][bucket(ctx)] += ctx + out
            agg["bucket_requests"][bucket(ctx)] += 1
            if tools_here:
                if len(tools_here) == 1:
                    s["single_tool_turns"] += 1
                    n = tools_here[0].get("name")
                    is_read = n in ("Read", "Grep", "Glob", "Bash")
                    if is_read and prev_turn_single_read:
                        s["consecutive_single_read_turns"] += 1
                    prev_turn_single_read = is_read
                else:
                    s["multi_tool_turns"] += 1
                    prev_turn_single_read = False
            else:
                prev_turn_single_read = False
        elif t == "user":
            msg = rec.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        body = text_of(c.get("content"))
                        n = len(body)
                        s["tool_result_bytes"] += n
                        s["tool_result_count"] += 1
                        s["tool_result_max"] = max(s["tool_result_max"], n)
                        name = tool_use_names.get(c.get("tool_use_id"))
                        if name in ("Agent", "Task"):
                            for a in s["agent_calls"]:
                                if a["id"] == c.get("tool_use_id"):
                                    a["refused"] = bool(re.search(r"refus|blocked|denied|not allowed", body, re.I))
                                    a["result_bytes"] = n
                        for nag, pat in NAG_PATTERNS.items():
                            if pat.search(body):
                                s["nags"][nag] += 1
                    elif isinstance(c, dict) and c.get("type") == "text":
                        s["user_prompts"] += 1
                        s["user_prompt_bytes"] += len(c.get("text", ""))
            elif isinstance(content, str):
                s["user_prompts"] += 1
                s["user_prompt_bytes"] += len(content)
        elif t == "system":
            if rec.get("subtype") == "compact_boundary":
                cm = rec.get("compactMetadata") or {}
                s["compactions"].append({"trigger": cm.get("trigger"),
                                         "pre": cm.get("preTokens"), "post": cm.get("postTokens")})
        elif t == "attachment":
            a = rec.get("attachment") or {}
            at = a.get("type") or "?"
            s["attachments"][at] += 1
            s["attachment_bytes"][at] += len(json.dumps(a, ensure_ascii=False))
            body = json.dumps(a, ensure_ascii=False)
            for nag, pat in NAG_PATTERNS.items():
                if nag != "batch-reads-nudge" and pat.search(body):
                    s["nags"][nag] += 1
    # fold subagent transcripts
    subdir = os.path.join(os.path.dirname(path), sid, "subagents")
    s["subagent_files"] = 0
    s["subagent_billed"] = 0
    if os.path.isdir(subdir):
        for f in os.listdir(subdir):
            if f.endswith(".jsonl"):
                s["subagent_files"] += 1
                sub_seen = set()
                for rec in iter_records(os.path.join(subdir, f)):
                    if rec.get("type") == "assistant":
                        rid = rec.get("requestId") or rec.get("uuid")
                        if rid in sub_seen:
                            continue
                        sub_seen.add(rid)
                        u = (rec.get("message") or {}).get("usage") or {}
                        s["subagent_billed"] += sum(int(u.get(k) or 0) for k in USAGE_KEYS) + int(u.get("output_tokens") or 0)
    s["id"] = sid
    s["path"] = path
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-requests", type=int, default=1)
    args = ap.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.endswith(".jsonl"):
                    files.append(os.path.join(p, f))
        elif p.endswith(".jsonl"):
            files.append(p)
    agg = {"bucket_tokens": Counter(), "bucket_requests": Counter()}
    sessions = [audit_file(f, agg) for f in files]
    sessions = [s for s in sessions if s["unique_requests"] >= args.min_requests]

    total_billed = sum(s["billed"] for s in sessions)
    total_req = sum(s["unique_requests"] for s in sessions)
    total_dup = sum(s["dup_lines"] for s in sessions)
    total_raw = sum(s["raw_sum_undeduped"] for s in sessions)
    print(f"sessions={len(sessions)} unique_requests={total_req} dup_lines={total_dup}")
    print(f"billed(deduped)={total_billed:,}  raw_undeduped_sum={total_raw:,}  "
          f"(dedup removed {total_raw - total_billed:,} = {100*(total_raw-total_billed)/max(total_raw,1):.1f}%)")
    print(f"  cache_read={sum(s['cache_read'] for s in sessions):,}  cache_create={sum(s['cache_create'] for s in sessions):,}  "
          f"input={sum(s['input'] for s in sessions):,}  output={sum(s['output'] for s in sessions):,}")
    print("\nBy context at call (share of billed tokens / share of requests):")
    for _, _, name in BUCKETS:
        tk = agg["bucket_tokens"][name]
        rq = agg["bucket_requests"][name]
        print(f"  {name:>9}: {100*tk/max(total_billed,1):5.1f}% tokens  {100*rq/max(total_req,1):5.1f}% requests  (n={rq})")

    n_side = sum(1 for s in sessions if s["sidechain_requests"] or s["subagent_files"])
    n_comp = sum(len(s["compactions"]) for s in sessions)
    over200 = sum(1 for s in sessions if s["peak_context"] > 200_000)
    print(f"\nsessions with any delegation (sidechain or subagents/): {n_side}/{len(sessions)}")
    print(f"sessions whose peak context > 200k: {over200}/{len(sessions)}   compactions total: {n_comp}")
    pre = sorted(c["pre"] for s in sessions for c in s["compactions"] if c.get("pre"))
    if pre:
        print(f"compaction preTokens: min={pre[0]:,} median={pre[len(pre)//2]:,} max={pre[-1]:,}  "
              f"(<130k: {sum(1 for p in pre if p < 130_000)}, 130k-250k: {sum(1 for p in pre if 130_000 <= p < 250_000)}, >=250k: {sum(1 for p in pre if p >= 250_000)})")
    triggers = Counter(c["trigger"] for s in sessions for c in s["compactions"])
    print(f"compaction triggers: {dict(triggers)}")

    tools = Counter()
    for s in sessions:
        tools.update(s["tools"])
    print(f"\nTool calls (all sessions): {dict(tools.most_common(12))}")
    agent_calls = [a for s in sessions for a in s["agent_calls"]]
    print(f"Agent/Task calls: {len(agent_calls)}  refused: {sum(1 for a in agent_calls if a.get('refused'))}  "
          f"by type: {dict(Counter(a['type'] for a in agent_calls))}")
    skills = Counter()
    for s in sessions:
        skills.update(s["skill_calls"])
    print(f"Skill invocations: {dict(skills.most_common(15))}")
    nags = Counter()
    for s in sessions:
        nags.update(s["nags"])
    print(f"Hook nags seen in tool results/attachments: {dict(nags)}")
    single = sum(s["single_tool_turns"] for s in sessions)
    multi = sum(s["multi_tool_turns"] for s in sessions)
    cons = sum(s["consecutive_single_read_turns"] for s in sessions)
    print(f"tool turns: single-tool={single} multi-tool={multi}  consecutive single read-only turns={cons}")
    dupdiff = Counter()
    for s in sessions:
        dupdiff.update(s["dup_field_diffs"])
    print(f"duplicate-record field differences: {dict(dupdiff)}")
    att_b = Counter()
    att_n = Counter()
    for s in sessions:
        att_b.update(s["attachment_bytes"])
        att_n.update(s["attachments"])
    print("\nAttachments (total bytes across sessions, count, mean bytes):")
    for at, b in att_b.most_common(14):
        print(f"  {at:28} {b:>12,}  n={att_n[at]:<6} mean={b//max(att_n[at],1):,}")
    models = Counter()
    for s in sessions:
        for m, n in s["models"].items():
            models[m] += s["billed"] * n // max(s["unique_requests"], 1)
    print(f"\nBilled by model (approx): {dict(models.most_common())}")

    print(f"\nTop {args.top} sessions by billed tokens:")
    for s in sorted(sessions, key=lambda x: -x["billed"])[:args.top]:
        print(f"  {s['id'][:8]} billed={s['billed']:>13,} req={s['unique_requests']:>4} peak={s['peak_context']:>9,} "
              f"first={s['first_context'] or 0:>7,} comp={len(s['compactions'])} side={s['sidechain_requests']} "
              f"sub={s['subagent_files']} agent={len(s['agent_calls'])} tool_res={s['tool_result_bytes']:>9,}B "
              f"dup={s['dup_lines']} model={next(iter(s['models']), '?')[:16]} {s['first_ts'] or ''}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"sessions": [{k: (dict(v) if isinstance(v, Counter) else v) for k, v in s.items()} for s in sessions],
                       "bucket_tokens": dict(agg["bucket_tokens"]), "bucket_requests": dict(agg["bucket_requests"])}, fh, indent=1, default=str)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
