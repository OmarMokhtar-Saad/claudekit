#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# =============================================================================
# Cost Tracker Hook
# Runs as a Stop hook.
#
# NAME vs BEHAVIOUR, stated because the gap is the finding (F49). This counts LINES IN
# THE HOOK LOG -- tool calls, git operations, hook errors. It has no access to token
# counts or prices and therefore cannot estimate a cost; the summary it prints says
# "Session Summary" for that reason. The file is still called `cost-tracker.sh` because
# renaming a shipped hook is user-visible (it appears in settings.json and in 16
# downstream repos), which makes it an owner decision rather than a cleanup. Until then,
# do not read the filename as a promise: no cost is tracked here.
# =============================================================================

LOG_FILE="$SCRIPT_DIR/hooks.log"
# `$SCRIPT_DIR` for the same reason as `LOG_FILE`: only 1 of the 11 hooks wired in
# settings.json is invoked with a `cd` to the project root, and this one is not, so a
# cwd-relative path put the record wherever the session happened to start.
COST_LOG="$SCRIPT_DIR/cost-tracker.log"
SESSION_LOG="$SCRIPT_DIR/session.log"
HOOK_NAME="cost-tracker"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$1] $2" >> "$LOG_FILE" 2>/dev/null
}

# Get session metadata
# CLAUDE_CODE_SESSION_ID is the documented hook-env name (env-vars.md); CLAUDE_SESSION_ID is never set.
SESSION_ID="${CLAUDE_CODE_SESSION_ID:-${CLAUDE_SESSION_ID:-$(date +%s)}}"
SESSION_DATE=$(date '+%Y-%m-%d')
SESSION_TIME=$(date '+%H:%M:%S')
PROJECT=$(basename "$(pwd)")

# Count session activity from hooks log (today's entries)
TODAY=$(date '+%Y-%m-%d')
TOOL_CALLS=$(grep "$TODAY.*\[INFO\].*Tool:" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
GIT_OPS=$(grep "$TODAY.*\[INFO\].*Git operation" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
HOOK_ERRORS=$(grep "$TODAY.*\[ERROR\]" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

# ---------------------------------------------------------------- turn telemetry
# Tool-call counts said nothing about the thing that actually spends: how large the
# window got and how many subagents were paid for. An audit of two qa-agents sessions
# (89.9M tokens) had to be reconstructed by hand from raw transcripts because no hook
# recorded either number. These two are written on every Stop so the next audit is a
# `grep` of cost-tracker.log.
#
# max_ctx is the largest input + cache_read + cache_creation on any assistant record in
# the LAST 64 KB of the transcript, read with one seek + one bounded read exactly as
# context-budget-gate.py does: a Stop hook must not read a 40 MB file. It is therefore
# the peak over the tail, not over the whole session - which is the number that matters
# anyway, because the tail is where a long session sits.
#
# agents is a directory listing of <session>/subagents/, never a file read.
#
# The payload only arrives because settings.json pipes it in: a backgrounded command in
# a non-interactive shell gets stdin from /dev/null (see tests/test_hook_stdin_wiring.py).
PAYLOAD=""
if [ ! -t 0 ]; then
    PAYLOAD=$(cat 2>/dev/null)
fi

TELEMETRY_PY=$(cat <<'PYEOF'
import json, os, sys

TAIL_BYTES = 65536
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def context_of(record):
    message = record.get("message")
    if not isinstance(message, dict):
        return 0
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in USAGE_KEYS:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
path = payload.get("transcript_path") if isinstance(payload, dict) else None

peak = 0
if isinstance(path, str) and os.path.isfile(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            blob = handle.read(TAIL_BYTES)
        lines = blob.decode("utf-8", errors="replace").split("\n")
        if size > TAIL_BYTES and lines:
            lines = lines[1:]
        for line in lines:
            line = line.strip()
            if not line or "usage" not in line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict):
                peak = max(peak, context_of(record))
    except Exception:
        pass

agents = 0
if isinstance(path, str) and path.strip():
    folder = os.path.join(os.path.splitext(path)[0], "subagents")
    try:
        agents = len([n for n in os.listdir(folder)
                      if n.startswith("agent-") and n.endswith(".jsonl")])
    except Exception:
        agents = 0

sys.stdout.write("%d %d\n" % (agents, peak))
PYEOF
)
TELEMETRY=$(printf '%s' "$PAYLOAD" | python3 -c "$TELEMETRY_PY" 2>/dev/null)
AGENTS=$(printf '%s' "$TELEMETRY" | awk 'NR==1 {print $1+0; found=1} END {if (!found) print 0}')
MAX_CTX=$(printf '%s' "$TELEMETRY" | awk 'NR==1 {print $2+0; found=1} END {if (!found) print 0}')

# Append to cost log
mkdir -p "$(dirname "$COST_LOG")"
echo "[${SESSION_DATE}T${SESSION_TIME}] project=$PROJECT session=$SESSION_ID tool_calls=$TOOL_CALLS git_ops=$GIT_OPS hook_errors=$HOOK_ERRORS agents=$AGENTS max_ctx=$MAX_CTX" >> "$COST_LOG" 2>/dev/null

log "INFO" "Session tracked: tool_calls=$TOOL_CALLS git_ops=$GIT_OPS hook_errors=$HOOK_ERRORS agents=$AGENTS max_ctx=$MAX_CTX"

# Print session summary if significant activity
if [ "$TOOL_CALLS" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "Session Summary ($PROJECT):"
    echo "  Tool calls:  $TOOL_CALLS"
    [ "$GIT_OPS" -gt 0 ] && echo "  Git ops:     $GIT_OPS"
    [ "$HOOK_ERRORS" -gt 0 ] && echo "  Hook errors: $HOOK_ERRORS (check .claude/hooks/hooks.log)"
    echo ""
fi

# Learning loop: propose (never write) a candidate skill when open ledger findings cluster.
# Folded in here rather than wired as its own Stop entry because `knowledge-ledger.py`
# lives under operations/scripts/, and every command settings.json names must be a counted
# hook (tests/test_ops_enforcement_scope.py). No profile guard: this hook is not in
# profiles.GUARDED_HOOKS, so a guard here would be an undeclared one (test_profiles.py);
# the call is read-mostly, backgrounded by settings.json, and never blocks.
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LEDGER="$PROJECT_ROOT/.claude/operations/scripts/knowledge-ledger.py"
[ -f "$LEDGER" ] && python3 "$LEDGER" propose >/dev/null 2>&1 || true

exit 0
