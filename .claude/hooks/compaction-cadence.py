#!/usr/bin/env python3
"""Turn rapid auto-compaction into a visible stop signal.

Measured on session hermes-agent-20260920-2108: five auto-compactions in 29
minutes, intervals collapsing 10.5 -> 6.9 -> 2.4 -> 2.2 min. Each compaction
writes a summary that is re-injected into the next request, and the summaries
grew 13,796 -> 23,762 chars, so every cycle left less headroom than the last
and the next cycle arrived sooner. That is a spiral, not a plateau, and the
model has no way to notice it: after a compaction it wakes up with a tidy
summary and no sense of how many times it has already done so.

This hook gives it that sense. Two events, one script:

  PreCompact    append {ts, session, cwd, trigger} to the ledger. Never blocks
                -- blocking a compaction would just overflow the context.
  SessionStart  fires again with source="compact" right after a compaction.
                Read the ledger for this session; if the gap between the last
                two compactions is under CK_COMPACT_MIN_INTERVAL seconds, or
                this session has already compacted CK_COMPACT_MAX_CYCLES times,
                inject additionalContext telling the model to stop and hand
                back rather than grind through another cycle.

additionalContext is the only channel here that actually reaches the model:
PreCompact cannot inject text, and stderr on an advisory hook is transcript-only.

Pure stdlib, no kit imports, so it runs from a user-level hooks dir in any
folder on any account. Fails open on every exception -- a broken ledger must
never cost a compaction.
"""

import json
import os
import sys
import time

LEDGER_NAME = "compaction-cadence.jsonl"
MIN_INTERVAL = int(os.environ.get("CK_COMPACT_MIN_INTERVAL", "300"))  # 5 minutes
MAX_CYCLES = int(os.environ.get("CK_COMPACT_MAX_CYCLES", "3"))
KEEP = 400  # ledger rows retained across all sessions


def ledger_path():
    d = os.environ.get("CK_COMPACT_STATE_DIR") or os.path.dirname(
        os.path.abspath(__file__)
    )
    return os.path.join(d, LEDGER_NAME)


def read_rows(path, session):
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("session") == session:
                    rows.append(row)
    except OSError:
        pass
    return rows


def record(path, row):
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        return
    # Trim in place occasionally so the ledger cannot grow without bound.
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        if len(lines) > KEEP * 2:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines[-KEEP:])
    except OSError:
        pass


def advise(rows):
    """Return warning text, or None when the cadence is healthy."""
    if len(rows) < 2:
        return None
    stamps = sorted(r.get("ts", 0) for r in rows)
    gap = stamps[-1] - stamps[-2]
    cycles = len(stamps)
    span = stamps[-1] - stamps[0]

    if gap >= MIN_INTERVAL and cycles <= MAX_CYCLES:
        return None

    why = []
    if gap < MIN_INTERVAL:
        why.append(
            "the last two compactions were %d min apart (floor %d min)"
            % (round(gap / 60), round(MIN_INTERVAL / 60))
        )
    if cycles > MAX_CYCLES:
        why.append(
            "this session has now compacted %d times in %d min (ceiling %d)"
            % (cycles, round(span / 60), MAX_CYCLES)
        )

    return (
        "[ck compaction-cadence] Context is compacting faster than the work is "
        "progressing: %s. Each cycle re-injects a summary that is larger than the "
        "last one, so the next cycle arrives sooner -- this accelerates, it does "
        "not settle.\n"
        "Do NOT respond by reading more files or re-fetching pages you already "
        "fetched. Instead: finish or abandon the step you are on, then stop and "
        "hand back to the user with what you have, what is left, and the one "
        "decision you need from them. If you genuinely must continue, narrow the "
        "next step to a single file or a single command first."
        % ("; and ".join(why))
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    event = payload.get("hook_event_name") or ""
    session = payload.get("session_id") or "unknown"
    path = ledger_path()

    if event == "PreCompact":
        record(
            path,
            {
                "ts": int(time.time()),
                "session": session,
                "cwd": payload.get("cwd") or os.getcwd(),
                "trigger": payload.get("trigger") or "",
            },
        )
        return 0

    if event == "SessionStart":
        if (payload.get("source") or "") != "compact":
            return 0
        text = advise(read_rows(path, session))
        if not text:
            return 0
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                }
            },
            sys.stdout,
        )
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
