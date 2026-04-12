#!/bin/bash
# =============================================================================
# Format + Typecheck Hook (Stop — async, non-blocking)
# Batches Prettier/Biome format and tsc typecheck across ALL JS/TS files
# edited in this response. Runs ONCE at Stop, not after every Edit.
# =============================================================================
# ECC_HOOK_PROFILE: runs in strict only (expensive operation)
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal"  ] && exit 0
[ "${ECC_HOOK_PROFILE:-standard}" = "standard" ] && exit 0

LOG=".claude/hooks/hooks.log"
BASH_LOG=".claude/hooks/bash-commands.log"
REPORT=".claude/hooks/format-typecheck-last.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [format-typecheck] [$1] $2" >> "$LOG" 2>/dev/null; }

# Run async — non-blocking
{
    log "INFO" "Starting batch format+typecheck"

    # ---------------------------------------------------------------------------
    # 1. Collect JS/TS files edited in this session from bash-commands.log
    # ---------------------------------------------------------------------------
    # Timing note: bash-commands.log is written by command-log-audit.sh (PostToolUse/Bash).
    # This hook runs at Stop, after all PostToolUse events have completed, so the log
    # should be fully written. The 1s sleep gives any in-flight async writes time to flush.
    sleep 1
    TS_FILES=()
    if [ -f "$BASH_LOG" ]; then
        # Extract file paths from log entries that contain .ts/.tsx/.js/.jsx
        while IFS= read -r line; do
            # Match file paths in log lines
            while IFS= read -r filepath; do
                if [ -f "$filepath" ]; then
                    TS_FILES+=("$filepath")
                fi
            done < <(echo "$line" | grep -oE '[a-zA-Z0-9_./-]+\.(ts|tsx|js|jsx|mts|cts|mjs)' 2>/dev/null)
        done < <(tail -200 "$BASH_LOG" 2>/dev/null)
    fi

    # Deduplicate
    IFS=$'\n' TS_FILES=($(printf '%s\n' "${TS_FILES[@]}" | sort -u))
    unset IFS

    if [ ${#TS_FILES[@]} -eq 0 ]; then
        log "INFO" "No JS/TS files edited this session — skipping"
        exit 0
    fi

    log "INFO" "Found ${#TS_FILES[@]} JS/TS files to format+check"
    echo "format-typecheck: processing ${#TS_FILES[@]} files..." > "$REPORT"

    # ---------------------------------------------------------------------------
    # 2. Format with Biome (preferred) or Prettier (fallback)
    # ---------------------------------------------------------------------------
    FORMAT_RESULT="skipped"
    if command -v biome &>/dev/null || [ -f "node_modules/.bin/biome" ]; then
        BIOME=$(command -v biome 2>/dev/null || echo "node_modules/.bin/biome")
        if "$BIOME" format --write "${TS_FILES[@]}" >> "$REPORT" 2>&1; then
            FORMAT_RESULT="biome:pass"
        else
            FORMAT_RESULT="biome:warn"
        fi
    elif command -v prettier &>/dev/null || [ -f "node_modules/.bin/prettier" ]; then
        PRETTIER=$(command -v prettier 2>/dev/null || echo "node_modules/.bin/prettier")
        if "$PRETTIER" --write "${TS_FILES[@]}" >> "$REPORT" 2>&1; then
            FORMAT_RESULT="prettier:pass"
        else
            FORMAT_RESULT="prettier:warn"
        fi
    fi

    # ---------------------------------------------------------------------------
    # 3. Typecheck with tsc --noEmit
    # ---------------------------------------------------------------------------
    TSC_RESULT="skipped"
    TSC_ERRORS=0
    if command -v tsc &>/dev/null || [ -f "node_modules/.bin/tsc" ]; then
        TSC=$(command -v tsc 2>/dev/null || echo "node_modules/.bin/tsc")
        if [ -f "tsconfig.json" ]; then
            if "$TSC" --noEmit >> "$REPORT" 2>&1; then
                TSC_RESULT="pass"
            else
                TSC_ERRORS=$(grep -c "error TS" "$REPORT" 2>/dev/null || echo "?")
                TSC_RESULT="fail:${TSC_ERRORS}_errors"
            fi
        fi
    fi

    log "INFO" "format=$FORMAT_RESULT tsc=$TSC_RESULT"

    # Report issues if any
    if [[ "$TSC_RESULT" == fail* ]]; then
        echo ""
        echo "TYPECHECK ISSUES: $TSC_ERRORS TypeScript error(s) found."
        echo "Run 'tsc --noEmit' to see details, or check .claude/hooks/format-typecheck-last.log"
        echo ""
    fi

} &

exit 0
