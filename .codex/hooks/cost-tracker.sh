#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# =============================================================================
# Cost Tracker Hook
# Tracks session activity and estimates costs at session end.
# Runs as a Stop hook.
# =============================================================================

LOG_FILE="$SCRIPT_DIR/hooks.log"
COST_LOG=".claude/hooks/cost-tracker.log"
SESSION_LOG=".claude/hooks/session.log"
HOOK_NAME="cost-tracker"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$1] $2" >> "$LOG_FILE" 2>/dev/null
}

# Get session metadata
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%s)}"
SESSION_DATE=$(date '+%Y-%m-%d')
SESSION_TIME=$(date '+%H:%M:%S')
PROJECT=$(basename "$(pwd)")

# Count session activity from hooks log (today's entries)
TODAY=$(date '+%Y-%m-%d')
TOOL_CALLS=$(grep "$TODAY.*\[INFO\].*Tool:" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
GIT_OPS=$(grep "$TODAY.*\[INFO\].*Git operation" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
HOOK_ERRORS=$(grep "$TODAY.*\[ERROR\]" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

# Append to cost log
mkdir -p "$(dirname "$COST_LOG")"
echo "[${SESSION_DATE}T${SESSION_TIME}] project=$PROJECT session=$SESSION_ID tool_calls=$TOOL_CALLS git_ops=$GIT_OPS hook_errors=$HOOK_ERRORS" >> "$COST_LOG" 2>/dev/null

log "INFO" "Session tracked: tool_calls=$TOOL_CALLS git_ops=$GIT_OPS hook_errors=$HOOK_ERRORS"

# Print session summary if significant activity
if [ "$TOOL_CALLS" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "Session Summary ($PROJECT):"
    echo "  Tool calls:  $TOOL_CALLS"
    [ "$GIT_OPS" -gt 0 ] && echo "  Git ops:     $GIT_OPS"
    [ "$HOOK_ERRORS" -gt 0 ] && echo "  Hook errors: $HOOK_ERRORS (check .claude/hooks/hooks.log)"
    echo ""
fi

exit 0
