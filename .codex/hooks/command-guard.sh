#!/usr/bin/env bash
# =============================================================================
# command-guard.sh — fail-closed Bash command denylist speed bump.
#
# Runs CommandValidator over the Bash tool's `command`. This is a SPEED BUMP,
# NOT A SANDBOX (see docs/ARCHITECTURE.md "Security Architecture").
#
# ECC_HOOK_PROFILE:
#   strict   -> BLOCK, including when the validator is missing (exit 2)
#   standard -> BLOCK a flagged command (exit 2 + reason on stderr)   [default]
#   minimal  -> off (exit 0)
#
# Fail-closed: a validator-flagged command and an unparseable payload BOTH block
# under standard. Blocking is the DEFAULT — a denylist that only warns unless you
# opt in is a fail-open default, which is what this hook exists to prevent.
#
# ONE deliberate exception (documented, not an oversight): if the validator
# itself is UNAVAILABLE (rc 127), standard warns instead of blocking. `.claude/`
# is frequently installed without the `claude-kit` Python package, and blocking
# there would deny every Bash command in those projects. `ck doctor` reports it,
# and `strict` closes it for anyone who wants no permissive path at all.
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
# Blocks under BOTH standard and strict: an unreadable payload means the guard
# cannot know what it is about to allow.
CMD="$(extract_json_field "$PAYLOAD" command)" || {
    deny "command-guard: unparseable tool payload (fail-closed)"
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

# Validator missing: the ONE permissive path under standard (see header).
if [ "$RC" -eq 127 ]; then
    [ "$PROFILE" = "strict" ] && deny "command-guard: validator unavailable (fail-closed)"
    hlog "WARN" "validator unavailable — command NOT checked (install claude-kit, or set ECC_HOOK_PROFILE=strict to block instead)"
    printf 'command-guard: validator unavailable, command NOT checked. Install the claude-kit package (`ck doctor` diagnoses) or set ECC_HOOK_PROFILE=strict to block instead.\n' >&2
    exit 0
fi

# Flagged command: block under standard AND strict.
if [ "$RC" -ne 0 ]; then
    deny "command-guard: ${OUT:-policy violation}"
fi

exit 0
