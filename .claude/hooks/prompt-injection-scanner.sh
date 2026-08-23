#!/bin/bash
set -e

# =============================================================================
# Prompt Injection Scanner Hook
# Scans tool input/output for prompt injection attempts.
# Input: text via $1 or stdin.
# Exit 0 = clean, Exit 1 = injection detected.
# =============================================================================

HOOK_NAME="prompt-injection-scanner"
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
# Prompt injection patterns (case-insensitive)
# ---------------------------------------------------------------------------
PATTERNS=(
    "ignore previous instructions"
    "ignore all previous instructions"
    "ignore your instructions"
    "disregard your instructions"
    "disregard previous instructions"
    "disregard all instructions"
    "system prompt:"
    "you are now"
    "pretend you are"
    "pretend to be"
    "bypass your"
    "override your"
    "override all"
    "jailbreak"
    "DAN mode"
    "developer mode"
    "sudo mode"
    "ignore safety"
    "ignore your safety"
    "ignore all safety"
    "new instructions:"
    "forget your instructions"
    "forget previous instructions"
    "act as if"
    "from now on you"
)

# ---------------------------------------------------------------------------
# Build case-insensitive regex
# ---------------------------------------------------------------------------
build_regex() {
    local regex=""
    for pattern in "${PATTERNS[@]}"; do
        # Escape regex special chars in pattern
        local escaped
        escaped=$(printf '%s' "$pattern" | sed 's/[.[\*^$()+?{|]/\\&/g')
        if [ -n "$regex" ]; then
            regex="$regex|$escaped"
        else
            regex="$escaped"
        fi
    done
    echo "$regex"
}

# ---------------------------------------------------------------------------
# Scan text for injection patterns
# ---------------------------------------------------------------------------
scan_text() {
    local text="$1"
    local regex
    regex=$(build_regex)

    local matches
    matches=$(echo "$text" | grep -iE "$regex" 2>/dev/null || true)

    if [ -n "$matches" ]; then
        echo "" >&2
        echo "[$HOOK_NAME] PROMPT INJECTION ATTEMPT DETECTED" >&2
        echo "[$HOOK_NAME] The following suspicious patterns were found:" >&2
        echo "" >&2
        while IFS= read -r line; do
            echo "  > $line" >&2
        done <<< "$matches"
        echo "" >&2
        echo "[$HOOK_NAME] This input may be attempting to manipulate agent behavior." >&2
        log "ERROR" "Prompt injection detected"
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local input_text=""

    if [ -n "$1" ]; then
        input_text="$1"
    else
        # Read from stdin
        input_text=$(cat)
    fi

    if [ -z "$input_text" ]; then
        log "INFO" "No input to scan"
        exit 0
    fi

    log "INFO" "Scanning input for prompt injection patterns"

    if ! scan_text "$input_text"; then
        exit 1
    fi

    log "INFO" "No prompt injection detected"
    exit 0
}

main "$@"
