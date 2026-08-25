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
    # PROJECT state, resolved through the repo root. This was `.claude/plans` relative to
    # the cwd, and the failure was silent in the worst direction: run from any
    # subdirectory, `[ -d "$dir" ]` is false for every entry, the candidate list is empty
    # and the hook reports "no duplicate plans found". A UserPromptSubmit gate that answers
    # "all clear" because it looked in the wrong place is worse than one that errors.
    local ck_root
    ck_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
    local plan_dirs=("$ck_root/.claude/plans" "$ck_root/operations")
    local found_duplicates=0

    # ONE python3 for the whole corpus, not one per plan file. This spawned an
    # interpreter inside a per-plan loop on a UserPromptSubmit hook: with ~110 plans in
    # `.claude/plans/` that is ~110 interpreter startups before the user's prompt is even
    # seen (finding F40, and part of the ~10-spawns-per-call cluster F105). The similarity
    # arithmetic is unchanged -- word-overlap ratio, threshold 70 -- so the verdicts are
    # identical; only the process count moves.
    local candidates
    candidates=$(for dir in "${plan_dirs[@]}"; do
        [ -d "$dir" ] || continue
        find "$dir" -name "plan-*.md" -o -name "plan.md" 2>/dev/null
    done)

    if [ -n "$candidates" ]; then
        local matches
        matches=$(printf '%s\n' "$candidates" | python3 -c "
import os, re, sys

def norm(text):
    text = re.sub(r'[._-]+', ' ', text.lower())
    return set(text.split())

new_words = norm(sys.argv[1])
for line in sys.stdin:
    path = line.strip()
    if not path:
        continue
    stem = os.path.basename(path)
    if stem.endswith('.md'):
        stem = stem[:-3]
    if stem.startswith('plan-'):
        stem = stem[len('plan-'):]
    existing = norm(stem)
    if not new_words or not existing:
        continue
    score = int(100 * len(new_words & existing) / len(new_words | existing))
    if score >= 70:
        print('%d\t%s' % (score, path))
" "$normalized" 2>/dev/null || true)

        if [ -n "$matches" ]; then
            while IFS="$(printf '\t')" read -r similarity plan_file; do
                [ -z "$plan_file" ] && continue
                log "WARN" "Potential duplicate: $plan_file (${similarity}% similar)"
                echo "WARNING: Potential duplicate plan found"
                echo "  New plan:      $new_plan"
                echo "  Existing plan: $plan_file"
                echo "  Similarity:    ${similarity}%"
                echo ""
                echo "Consider reviewing the existing plan before creating a new one."
                found_duplicates=1
            done <<< "$matches"
        fi
    fi

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
