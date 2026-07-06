#!/usr/bin/env bash
# =============================================================================
# command-guard.sh — fail-closed Bash command denylist speed bump.
#
# Runs CommandValidator over the Bash tool's `command`. This is a SPEED BUMP,
# NOT A SANDBOX (see docs/ARCHITECTURE.md "Security Architecture").
#
# ECC_HOOK_PROFILE rollout:
#   strict   -> BLOCK (exit 2 + reason on stderr)
#   standard -> WARN only (exit 0, reason on stderr + log)   [default]
#   minimal  -> off (exit 0)
#
# Fail-closed: an unparseable payload or an unavailable validator BLOCKS under
# strict (never silently allows).
# =============================================================================
set -uo pipefail

HOOK_NAME="command-guard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

ROOT="$(resolve_root)"
LOG_FILE="${LOG_FILE:-$ROOT/.claude/hooks/hooks.log}"

PROFILE="${ECC_HOOK_PROFILE:-standard}"
[ "$PROFILE" = "minimal" ] && exit 0

PAYLOAD="$(cat)"

# Extract the command; a JSON parse failure returns rc 3 -> fail closed.
CMD="$(extract_json_field "$PAYLOAD" command)" || {
    [ "$PROFILE" = "strict" ] && deny "command-guard: unparseable tool payload (fail-closed)"
    hlog "WARN" "unparseable payload (standard warn-only)"
    exit 0
}
[ -z "$CMD" ] && exit 0

# Resolve the validator: prefer the installed console script, else run from the
# source tree. If neither is available, fail closed under strict.
run_validator() {
    if command -v claudekit >/dev/null 2>&1; then
        claudekit check-command "$1" 2>&1
        return $?
    elif [ -d "$ROOT/src/claudekit" ]; then
        PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -m claudekit.security check-command "$1" 2>&1
        return $?
    fi
    return 127
}

OUT="$(run_validator "$CMD")"; RC=$?

if [ "$RC" -eq 127 ]; then
    [ "$PROFILE" = "strict" ] && deny "command-guard: validator unavailable (fail-closed)"
    hlog "WARN" "validator unavailable (standard warn-only)"
    exit 0
fi

if [ "$RC" -ne 0 ]; then
    REASON="${OUT:-policy violation}"
    if [ "$PROFILE" = "strict" ]; then
        deny "command-guard: $REASON"
    fi
    # standard: warn only, do not block.
    hlog "WARN" "would block (standard warn-only): $REASON"
    printf 'command-guard (warn-only, set ECC_HOOK_PROFILE=strict to block): %s\n' "$REASON" >&2
    exit 0
fi

exit 0
