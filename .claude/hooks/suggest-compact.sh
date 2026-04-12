#!/bin/bash
# =============================================================================
# Suggest Compact Hook (PreToolUse — async, non-blocking)
# Counts tool calls this session and suggests /compact every 50 calls.
# =============================================================================
# ECC_HOOK_PROFILE: runs in all profiles including minimal
# Runs async — never blocks the agent

COUNTER_FILE=".claude/hooks/compact-counter.txt"
LOG=".claude/hooks/hooks.log"

# Run async — never block the tool call
{
    mkdir -p .claude/hooks 2>/dev/null

    # Increment counter atomically using a lock file (prevents race with parallel agents)
    LOCK_FILE="${COUNTER_FILE}.lock"
    COUNT=0

    # flock is available on Linux; on macOS use mkdir as a portable mutex
    _lock_acquired=false
    _lock_dir="${COUNTER_FILE}.lockdir"
    if mkdir "$_lock_dir" 2>/dev/null; then
        _lock_acquired=true
    else
        # Another subshell holds the lock — skip this increment to avoid corruption
        exit 0
    fi

    # Critical section
    if [ -f "$COUNTER_FILE" ]; then
        COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
        # Reset counter daily
        FILE_DATE=$(date -r "$COUNTER_FILE" '+%Y-%m-%d' 2>/dev/null || date '+%Y-%m-%d')
        TODAY=$(date '+%Y-%m-%d')
        if [ "$FILE_DATE" != "$TODAY" ]; then
            COUNT=0
        fi
    fi

    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$COUNTER_FILE"

    # Release lock
    rmdir "$_lock_dir" 2>/dev/null

    # Suggest compact every 50 tool calls
    if [ $((COUNT % 50)) -eq 0 ] && [ $COUNT -gt 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [suggest-compact] [INFO] $COUNT tool calls — suggesting compact" >> "$LOG" 2>/dev/null
        echo ""
        echo "CONTEXT TIP: $COUNT tool calls in this session."
        echo "Consider running /compact to compress context and free up space."
        echo ""
    fi
} &

exit 0
