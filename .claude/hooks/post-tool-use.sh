#!/usr/bin/env bash
# =============================================================================
# Post-Tool-Use Hook (PostToolUse — Edit / Write / Bash)
# Tracks tool usage.
# Reads the tool payload as JSON on STDIN (Claude Code does NOT set
# $CLAUDE_TOOL_* env vars — the old arg-based version tracked nothing).
# Advisory only: always exits 0.
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="post-tool-use"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

TOOL_INPUT=$(cat)

TOOL_NAME=$(extract_json_field "$TOOL_INPUT" tool_name)
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(extract_json_field "$TOOL_INPUT" name)
[ -z "$TOOL_NAME" ] && TOOL_NAME="unknown"

FILE_PATH=$(extract_json_field "$TOOL_INPUT" file_path)
[ -z "$FILE_PATH" ] && FILE_PATH=$(extract_json_field "$TOOL_INPUT" path)
CMD=$(extract_json_field "$TOOL_INPUT" command)

# cost-tracker.sh counts "[INFO] Tool:" lines in hooks.log — this is that marker.
hlog "INFO" "Tool: $TOOL_NAME | Target: ${FILE_PATH:-${CMD:0:80}}"

case "$TOOL_NAME" in
    *Edit*|*Write*|*edit*|*write*|NotebookEdit)
        if [ -n "$FILE_PATH" ]; then
            # Record the edited path so the Stop-time format-typecheck hook knows
            # which files actually changed (Edit/Write targets are NOT in
            # bash-commands.log, which only records Bash commands).
            printf '%s\n' "$FILE_PATH" >> "$SCRIPT_DIR/edited-files.log" 2>/dev/null
        fi
        ;;
    *Bash*|*bash*)
        if printf '%s' "$CMD" | grep -qE '^\s*git\s+'; then
            action=$(printf '%s' "$CMD" | grep -oE 'git\s+(commit|push|pull|merge|rebase|checkout|branch|reset|stash|cherry-pick)' | head -1)
            [ -n "$action" ] && hlog "INFO" "Git operation: $action"
        fi
        ;;
esac

exit 0
