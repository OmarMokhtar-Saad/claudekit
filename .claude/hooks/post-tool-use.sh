#!/usr/bin/env bash
# =============================================================================
# Post-Tool-Use Hook (PostToolUse — Edit / Write / Bash)
# Tracks tool usage and validates ops.json if modified.
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

# Validate ops.json if one was just written/edited (both filename conventions).
validate_ops_on_edit() {
    local fp="$1"
    printf '%s' "$fp" | grep -qE "$OPS_REGEX" || return 0
    [ -f "$fp" ] || return 0
    hlog "INFO" "ops config modified, validating: $fp"
    local result
    result=$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except json.JSONDecodeError as e:
    print("invalid JSON: %s" % e); sys.exit(0)
if "plan" not in d:
    print("missing plan field"); sys.exit(0)
ops = d.get("operations")
files = d.get("files")
if isinstance(ops, list):
    for i, op in enumerate(ops):
        if "type" not in op: print("operation %d missing type" % i); sys.exit(0)
        if "path" not in op: print("operation %d missing path" % i); sys.exit(0)
    print("valid")
elif isinstance(files, list):
    for i, f in enumerate(files):
        if "path" not in f: print("file %d missing path" % i); sys.exit(0)
    print("valid")
else:
    print("missing operations or files field")
' "$fp" 2>/dev/null)
    if [ "$result" = "valid" ]; then
        hlog "INFO" "ops config valid: $fp"
    else
        hlog "WARN" "ops config issue: $result"
        echo "[post-tool-use] WARNING: ops config validation: $result"
    fi
}

case "$TOOL_NAME" in
    *Edit*|*Write*|*edit*|*write*|NotebookEdit)
        [ -n "$FILE_PATH" ] && validate_ops_on_edit "$FILE_PATH"
        ;;
    *Bash*|*bash*)
        if printf '%s' "$CMD" | grep -qE '^\s*git\s+'; then
            action=$(printf '%s' "$CMD" | grep -oE 'git\s+(commit|push|pull|merge|rebase|checkout|branch|reset|stash|cherry-pick)' | head -1)
            [ -n "$action" ] && hlog "INFO" "Git operation: $action"
        fi
        ;;
esac

exit 0
