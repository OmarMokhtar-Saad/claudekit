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

    _lock_dir="${COUNTER_FILE}.lockdir"

    # Clear a stale lock: if the lockdir is older than 1 minute a previous
    # subshell died mid-critical-section. `find -mmin` is portable (BSD + GNU),
    # unlike `date -r`/`stat` which differ across platforms.
    if [ -d "$_lock_dir" ]; then
        find "$_lock_dir" -maxdepth 0 -mmin +1 -exec rmdir {} \; 2>/dev/null
    fi

    # mkdir is an atomic, portable mutex (flock is Linux-only).
    if ! mkdir "$_lock_dir" 2>/dev/null; then
        # Another subshell holds the lock — skip this increment to avoid corruption
        exit 0
    fi

    # The counter file stores "YYYY-MM-DD COUNT" so the daily reset is portable
    # and doesn't depend on file mtime (`date -r` is GNU-only; on macOS it
    # treated the path as epoch seconds, so the reset never fired).
    TODAY=$(date '+%Y-%m-%d')
    COUNT=0
    if [ -f "$COUNTER_FILE" ]; then
        read -r _saved_date _saved_count < "$COUNTER_FILE" 2>/dev/null
        case "$_saved_count" in
            ''|*[!0-9]*) _saved_count=0 ;;
        esac
        if [ "$_saved_date" = "$TODAY" ]; then
            COUNT=$_saved_count
        fi
    fi

    COUNT=$((COUNT + 1))
    echo "$TODAY $COUNT" > "$COUNTER_FILE"

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
