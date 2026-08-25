#!/bin/bash
# =============================================================================
# Suggest Compact Hook (PostToolUse — synchronous, non-blocking)
# Counts tool calls this session and suggests /compact every 40 calls.
#
# Must run as PostToolUse: PreToolUse stdout is never shown to the model, so a
# hook registered there can never actually nudge the agent (regression fixed
# 2026-07-31 — see CHANGELOG). The counter/lock bookkeeping is fast file-touch
# work (<100ms) and runs in the FOREGROUND so its stdout is captured by the
# PostToolUse event; do not background this with `&` or the tip is lost again.
# =============================================================================
# ECC_HOOK_PROFILE: runs in all profiles including minimal
# Always exits 0 — a broken counter must never block a tool.
# Tool-call count chosen over byte-size/wall-clock as the context-growth proxy —
# see plan-remaining-fixes-2026-07-31.md §5b for the rejected alternatives and why.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# `$SCRIPT_DIR` for files the HOOK owns; see tests/test_hook_paths.py for the
# property this maintains (no hook assumes its working directory).
# This hook IS invoked with a `cd` to the project root -- the only one of the eleven that
# is -- so these worked. They are still made explicit: the guarantee lives in
# settings.json, one file away, and the next edit to that entry silently removes it.
COUNTER_FILE="$SCRIPT_DIR/compact-counter.txt"
LOG="$SCRIPT_DIR/hooks.log"

mkdir -p "$SCRIPT_DIR" 2>/dev/null

_lock_dir="${COUNTER_FILE}.lockdir"

# Clear a stale lock: if the lockdir is older than 1 minute a previous
# invocation died mid-critical-section. `find -mmin` is portable (BSD + GNU),
# unlike `date -r`/`stat` which differ across platforms.
if [ -d "$_lock_dir" ]; then
    find "$_lock_dir" -maxdepth 0 -mmin +1 -exec rmdir {} \; 2>/dev/null
fi

# mkdir is an atomic, portable mutex (flock is Linux-only).
if ! mkdir "$_lock_dir" 2>/dev/null; then
    # Another invocation holds the lock — skip this increment to avoid corruption.
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

# Suggest compact every 40 tool calls, from the foreground so PostToolUse
# captures the stdout as the tool result the model actually sees.
if [ $((COUNT % 40)) -eq 0 ] && [ $COUNT -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [suggest-compact] [INFO] $COUNT tool calls — suggesting compact" >> "$LOG" 2>/dev/null
    echo ""
    echo "CONTEXT TIP: $COUNT tool calls this session — run /compact now unless mid-edit."
    echo ""
fi

exit 0
