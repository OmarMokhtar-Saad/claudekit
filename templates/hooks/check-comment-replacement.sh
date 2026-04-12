#!/bin/bash
set -e

# =============================================================================
# Check Comment Replacement Hook
# Detects when code is replaced with placeholder comments in staged diffs.
# This prevents AI agents from substituting real implementations with stubs.
# Exit 0 = clean, Exit 1 = suspicious replacements detected.
# =============================================================================

HOOK_NAME="check-comment-replacement"
LOG_FILE=".claude/hooks/hooks.log"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
    if [ "$level" = "ERROR" ] || [ "$level" = "WARN" ]; then
        echo "[$HOOK_NAME] $*" >&2
    fi
}

# ---------------------------------------------------------------------------
# Suspicious placeholder patterns (added lines in diffs)
# These indicate code was replaced with a lazy placeholder comment.
# ---------------------------------------------------------------------------
PATTERNS=(
    '^\+.*//\s*\.\.\.\s*rest'
    '^\+.*#\s*\.\.\.\s*rest'
    '^\+.*//\s*\.\.\.\s*implementation'
    '^\+.*#\s*\.\.\.\s*implementation'
    '^\+.*//\s*\.\.\.\s*existing'
    '^\+.*#\s*\.\.\.\s*existing'
    '^\+.*//\s*\.\.\.\s*unchanged'
    '^\+.*#\s*\.\.\.\s*unchanged'
    '^\+.*//\s*TODO:\s*implement'
    '^\+.*#\s*TODO:\s*implement'
    '^\+.*pass\s*#\s*placeholder'
    '^\+.*raise\s+NotImplementedError'
)

# ---------------------------------------------------------------------------
# Build combined regex from patterns
# ---------------------------------------------------------------------------
build_regex() {
    local regex=""
    for pattern in "${PATTERNS[@]}"; do
        if [ -n "$regex" ]; then
            regex="$regex|$pattern"
        else
            regex="$pattern"
        fi
    done
    echo "$regex"
}

# ---------------------------------------------------------------------------
# Scan staged diffs for placeholder comments
# ---------------------------------------------------------------------------
scan_staged_diffs() {
    local regex
    regex=$(build_regex)

    local staged_files
    staged_files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

    if [ -z "$staged_files" ]; then
        log "INFO" "No staged files to check"
        return 0
    fi

    local found=0
    local violations=""

    while IFS= read -r file; do
        # Skip binary and non-code files
        if [[ "$file" =~ \.(png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|pdf|lock|svg)$ ]]; then
            continue
        fi

        # Get the diff for this file and check for placeholder patterns
        local matches
        matches=$(git diff --cached -- "$file" 2>/dev/null | grep -nE "$regex" 2>/dev/null || true)

        if [ -n "$matches" ]; then
            found=1
            violations="${violations}\n  File: $file"
            while IFS= read -r match; do
                violations="${violations}\n    $match"
            done <<< "$matches"
        fi
    done <<< "$staged_files"

    if [ $found -ne 0 ]; then
        echo "" >&2
        echo "[$HOOK_NAME] SUSPICIOUS PLACEHOLDER COMMENTS DETECTED" >&2
        echo "[$HOOK_NAME] The following staged changes appear to replace code with placeholder comments:" >&2
        echo -e "$violations" >&2
        echo "" >&2
        echo "[$HOOK_NAME] This often means real implementation was removed and replaced with a stub." >&2
        echo "[$HOOK_NAME] Please verify these changes are intentional before committing." >&2
        echo "[$HOOK_NAME] To bypass: git commit --no-verify" >&2
        log "ERROR" "Placeholder comment replacements detected in staged files"
        return 1
    fi

    log "INFO" "No placeholder comment replacements found"
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "INFO" "Scanning staged diffs for placeholder comment replacements"

    if ! scan_staged_diffs; then
        exit 1
    fi

    exit 0
}

main "$@"
