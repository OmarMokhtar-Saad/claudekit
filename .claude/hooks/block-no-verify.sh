#!/bin/bash
# =============================================================================
# Block --no-verify Hook
# Prevents bypassing git hooks via the --no-verify flag.
# Runs as a PreToolUse hook on Bash tool calls.
# =============================================================================

set -e

LOG_FILE=".claude/hooks/hooks.log"
HOOK_NAME="block-no-verify"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$1] $2" >> "$LOG_FILE" 2>/dev/null
}

# Read tool input from stdin
TOOL_INPUT=$(cat)

# Extract the command
CMD=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('command', ''))
except:
    print('')
" 2>/dev/null)

# Check if the command uses --no-verify
if echo "$CMD" | grep -qE '\-\-no-verify'; then
    log "BLOCK" "Attempt to use --no-verify detected: $CMD"
    echo "BLOCKED: The --no-verify flag bypasses git hooks and is not allowed."
    echo ""
    echo "Blocked command: $CMD"
    echo ""
    echo "Why this is blocked:"
    echo "  --no-verify skips pre-commit and commit-msg hooks, which enforce code"
    echo "  quality, prevent secrets from being committed, and validate commit messages."
    echo ""
    echo "Alternatives:"
    echo "  1. Fix the issue that the hook is catching"
    echo "  2. If the hook is incorrectly blocking valid work, fix the hook instead"
    echo "  3. If you need to bypass for a legitimate reason, ask the user explicitly"
    exit 1
fi

# Also block --force-with-lease bypass patterns on push
if echo "$CMD" | grep -qE 'git\s+push.*--force\b' && ! echo "$CMD" | grep -qE '--force-with-lease'; then
    log "WARN" "git push --force (without --force-with-lease) detected: $CMD"
    echo "WARNING: git push --force can overwrite remote history."
    echo "Consider using --force-with-lease instead, which fails safely if the remote has changed."
    echo ""
    echo "Command: $CMD"
    echo ""
    echo "To proceed anyway, re-run the command with user approval explicitly granted."
    echo "Exiting with warning — the push has NOT been executed."
    exit 1
fi

exit 0
