#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# =============================================================================
# Command Log Audit Hook
# Logs all Bash tool commands to a persistent audit log.
# Runs as a PostToolUse hook on Bash tool calls.
# =============================================================================

LOG_FILE="$SCRIPT_DIR/hooks.log"
AUDIT_LOG=".claude/hooks/bash-commands.log"
HOOK_NAME="command-log-audit"

# Read tool input (piped from Claude Code)
TOOL_INPUT=$(cat 2>/dev/null)

# Extract the command
CMD=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('command', ''))
except:
    print('')
" 2>/dev/null)

# Skip empty commands
[ -z "$CMD" ] && exit 0

# Truncate very long commands for readability
CMD_TRUNCATED="${CMD:0:500}"
[ ${#CMD} -gt 500 ] && CMD_TRUNCATED="$CMD_TRUNCATED...(truncated)"

# Append to audit log
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] pwd=$(pwd) cmd=$CMD_TRUNCATED" >> "$AUDIT_LOG" 2>/dev/null

exit 0
