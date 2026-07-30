#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -e

# =============================================================================
# Pre-Plan Hook
# Checks for duplicate plans before creating a new one.
# Uses simple string similarity to detect near-duplicate plan names.
# =============================================================================

HOOK_NAME="pre-plan"
LOG_FILE="$SCRIPT_DIR/hooks.log"
PLAN_NAME="${1:-}"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
    if [ "$level" = "ERROR" ] || [ "$level" = "WARN" ]; then
        echo "[$HOOK_NAME] $*" >&2
    fi
}

get_project_config() {
    local key="$1"
    local config="$SCRIPT_DIR/config.json"
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json, sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get(sys.argv[2],''))" "$config" "$key" 2>/dev/null
    fi
}

# ---------------------------------------------------------------------------
# Check for duplicate plans
# ---------------------------------------------------------------------------
check_duplicates() {
    local new_plan="$1"

    if [ -z "$new_plan" ]; then
        log "INFO" "No plan name provided, skipping duplicate check"
        return 0
    fi

    # Normalize the plan name: lowercase, strip extensions, replace separators
    local normalized
    normalized=$(echo "$new_plan" | tr '[:upper:]' '[:lower:]' | sed 's/[._-]/ /g' | sed 's/  */ /g' | xargs)

    log "INFO" "Checking for duplicates of: $normalized"

    # Search plan directories
    local plan_dirs=(".claude/plans" "operations")
    local found_duplicates=0

    for dir in "${plan_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            continue
        fi

        # Find existing plan files
        while IFS= read -r plan_file; do
            local existing_name
            existing_name=$(basename "$plan_file" .md | sed 's/^plan-//' | tr '[:upper:]' '[:lower:]' | sed 's/[._-]/ /g' | sed 's/  */ /g' | xargs)

            if [ -z "$existing_name" ]; then
                continue
            fi

            # Use python for similarity check (simple word overlap)
            local similarity
            similarity=$(python3 -c "
import sys
new_words = set(sys.argv[1].split())
existing_words = set(sys.argv[2].split())
if not new_words or not existing_words:
    print(0)
else:
    overlap = len(new_words & existing_words)
    total = len(new_words | existing_words)
    print(int(100 * overlap / total))
" "$normalized" "$existing_name" 2>/dev/null || echo "0")

            if [ "$similarity" -ge 70 ] 2>/dev/null; then
                log "WARN" "Potential duplicate: $plan_file (${similarity}% similar)"
                echo "WARNING: Potential duplicate plan found"
                echo "  New plan:      $new_plan"
                echo "  Existing plan: $plan_file"
                echo "  Similarity:    ${similarity}%"
                echo ""
                echo "Consider reviewing the existing plan before creating a new one."
                found_duplicates=1
            fi
        done < <(find "$dir" -name "plan-*.md" -o -name "plan.md" 2>/dev/null)
    done

    if [ $found_duplicates -eq 0 ]; then
        log "INFO" "No duplicate plans found"
    fi

    # This is non-blocking - return 0 even if duplicates found (just warn)
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "INFO" "Starting pre-plan hook for: $PLAN_NAME"

    check_duplicates "$PLAN_NAME"

    log "INFO" "Pre-plan hook complete"
    return 0
}

main "$@"
