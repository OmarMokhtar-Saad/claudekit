#!/bin/bash
# =============================================================================
# Format + Typecheck Hook (Stop — async, non-blocking)
# Batches Prettier/Biome format and tsc typecheck across ALL JS/TS files
# edited in this response. Runs ONCE at Stop, not after every Edit.
# =============================================================================
# ECC_HOOK_PROFILE: strict only (expensive operation). Written as a NEGATIVE
# guard, like its sibling strict-only gates file-guard-gate.sh and
# injection-scan-gate.sh, so an unrecognised profile value stands the hook
# down instead of silently running it. The old positive list (= minimal,
# = standard) let every other value through, contradicting the "strict only"
# line directly above it. Identical on all three real values.
[ "${ECC_HOOK_PROFILE:-standard}" != "strict" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
# The `[ -f ... ] &&` guard above promises graceful degradation, and delegating
# `log()` to `hlog` removes it: with `lib.sh` absent the hook printed
# "hlog: command not found" to stderr on every call, where the old body was
# `>> "$LOG" 2>/dev/null`. `lib.sh` ships beside the hooks so a fresh install is
# fine; the exposure is a surgical fleet sync that copies one hook and not the
# library. A no-op keeps the promise the guard makes.
command -v hlog >/dev/null 2>&1 || hlog() { :; }
HOOK_NAME="format-typecheck"
# `$SCRIPT_DIR`, not a cwd-relative path: this hook wrote to `.claude/hooks/hooks.log`
# relative to the CURRENT DIRECTORY, so its log landed elsewhere (or nowhere) whenever
# the cwd was not the repo root. Three hooks shared that bug and a third `LOG_FILE=`
# form (finding F107); the same class already misplaces `command-log-audit.sh`'s audit
# trail (F55). `hlog` also uses `$*`, so an argument past the second no longer vanishes.
LOG_FILE="$SCRIPT_DIR/hooks.log"
log() { hlog "$@"; }
# Files actually edited this response come from post-tool-use.sh (Edit/Write
# targets). bash-commands.log only holds Bash commands and misses tool edits.
EDITED_LOG=".claude/hooks/edited-files.log"
REPORT=".claude/hooks/format-typecheck-last.log"


# Run async — non-blocking
{
    log "INFO" "Starting batch format+typecheck"

    # ---------------------------------------------------------------------------
    # 1. Collect JS/TS files edited this response from edited-files.log
    # ---------------------------------------------------------------------------
    # edited-files.log is appended by post-tool-use.sh (PostToolUse Edit/Write).
    # This hook runs at Stop, after those events; the 1s sleep lets any in-flight
    # async writes flush. The log is truncated at the end so each Stop only
    # processes files edited since the previous one.
    sleep 1
    TS_FILES=()
    if [ -f "$EDITED_LOG" ]; then
        while IFS= read -r filepath; do
            case "$filepath" in
                *.ts|*.tsx|*.js|*.jsx|*.mts|*.cts|*.mjs)
                    # A leading-dash path would be parsed as an OPTION by
                    # biome/prettier/tsc (argument injection) — anchor it.
                    case "$filepath" in -*) filepath="./$filepath" ;; esac
                    [ -f "$filepath" ] && TS_FILES+=("$filepath") ;;
            esac
        done < <(tail -500 "$EDITED_LOG" 2>/dev/null)
    fi

    # Deduplicate
    IFS=$'\n' TS_FILES=($(printf '%s\n' "${TS_FILES[@]}" | sort -u))
    unset IFS

    if [ ${#TS_FILES[@]} -eq 0 ]; then
        log "INFO" "No JS/TS files edited this response — skipping"
        : > "$EDITED_LOG" 2>/dev/null
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

    # Consume the edit log so the next Stop only processes newly-edited files.
    : > "$EDITED_LOG" 2>/dev/null

} &

exit 0
