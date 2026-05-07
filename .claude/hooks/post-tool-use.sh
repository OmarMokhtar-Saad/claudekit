#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -e

# =============================================================================
# Post-Tool-Use Hook
# Tracks tool usage and validates ops.json if modified.
# Called after Edit, Write, NotebookEdit, and Bash tool invocations.
# =============================================================================

HOOK_NAME="post-tool-use"
LOG_FILE="$SCRIPT_DIR/hooks.log"

TOOL_NAME="${1:-unknown}"
TOOL_RESULT="${2:-}"
TOOL_ARGS="${3:-}"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
}

get_project_config() {
    local key="$1"
    local config="$SCRIPT_DIR/config.json"
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json, sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get(sys.argv[2],''))" "$config" "$key" 2>/dev/null
    fi
}

# ---------------------------------------------------------------------------
# Track file modifications
# ---------------------------------------------------------------------------
track_modification() {
    local tool="$1"
    local args="$2"

    # Extract file path from tool args (best-effort)
    local file_path
    file_path=$(echo "$args" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('file_path', data.get('path', data.get('command', ''))))
except:
    print(sys.stdin.read().strip()[:200])
" 2>/dev/null || echo "$args" | head -c 200)

    log "INFO" "Tool: $tool | Target: $file_path"
}

# ---------------------------------------------------------------------------
# Validate ops.json if it was modified
# ---------------------------------------------------------------------------
validate_ops_on_edit() {
    local args="$1"

    # Check if the modified file is an ops.json
    local file_path
    file_path=$(echo "$args" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('file_path', ''))
except:
    print('')
" 2>/dev/null || echo "")

    if [[ "$file_path" == *"ops.json"* ]] || [[ "$file_path" == *"ops-"*".json"* ]]; then
        log "INFO" "ops.json modified, running validation: $file_path"

        if [ -f "$file_path" ]; then
            local valid
            valid=$(python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    if 'plan' not in data:
        print('missing plan field')
    elif 'operations' in data:
        if not isinstance(data['operations'], list):
            print('operations must be an array')
        else:
            for i, op in enumerate(data['operations']):
                if 'type' not in op:
                    print(f'operation {i} missing type')
                    sys.exit(0)
                if 'path' not in op:
                    print(f'operation {i} missing path')
                    sys.exit(0)
            print('valid')
    elif 'files' in data:
        if not isinstance(data['files'], list):
            print('files must be an array')
        else:
            for i, f in enumerate(data['files']):
                if 'path' not in f:
                    print(f'file {i} missing path')
                    sys.exit(0)
            print('valid')
    else:
        print('missing operations or files field')
except json.JSONDecodeError as e:
    print(f'invalid JSON: {e}')
except Exception as e:
    print(f'error: {e}')
" "$file_path" 2>/dev/null)

            if [ "$valid" = "valid" ]; then
                log "INFO" "ops.json validation passed: $file_path"
            else
                log "WARN" "ops.json validation issue: $valid"
                echo "[post-tool-use] WARNING: ops.json validation: $valid"
            fi
        fi
    fi
}

# ---------------------------------------------------------------------------
# Track git operations from Bash tool
# ---------------------------------------------------------------------------
track_git_ops() {
    local args="$1"

    # Check if the Bash command involves git
    local command_str
    command_str=$(echo "$args" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('command', ''))
except:
    print(sys.stdin.read().strip()[:500])
" 2>/dev/null || echo "$args" | head -c 500)

    if echo "$command_str" | grep -qE '^\s*git\s+'; then
        local git_action
        git_action=$(echo "$command_str" | grep -oE 'git\s+(commit|push|pull|merge|rebase|checkout|branch|reset|stash|cherry-pick)' | head -1)

        if [ -n "$git_action" ]; then
            log "INFO" "Git operation detected: $git_action"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    # Track the tool usage
    track_modification "$TOOL_NAME" "$TOOL_ARGS"

    # Tool-specific handlers
    case "$TOOL_NAME" in
        Edit|Write|NotebookEdit)
            validate_ops_on_edit "$TOOL_ARGS"
            ;;
        Bash)
            track_git_ops "$TOOL_ARGS"
            ;;
    esac

    return 0
}

main "$@"
