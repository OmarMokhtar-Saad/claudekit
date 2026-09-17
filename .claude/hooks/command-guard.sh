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
# is frequently installed without the `claudekit-agents` Python package, and blocking
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
    # STDOUT carries the VERDICT, STDERR carries the validator's own health.
    # They are never merged: the caller has to tell an attacker-supplied string
    # echoed back inside a refusal apart from a Python traceback the validator
    # emitted about itself. See the discriminator below.
    if command -v claudekit >/dev/null 2>&1; then
        claudekit check-command "$1"
        return $?
    elif [ -d "$ROOT/src/claudekit" ]; then
        PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -m claudekit.security check-command "$1"
        return $?
    elif python3 -c 'import claudekit.security' 2>/dev/null; then
        # pip-installed package without the console script on PATH
        python3 -m claudekit.security check-command "$1"
        return $?
    fi
    return 127
}

# A temp file we cannot create must not become a refusal of everything. Since
# the EXIT CODE does the deciding below, ERR is consulted only for rc outside
# {0,2,127}: losing it degrades crash DETECTION and leaves every verdict fully
# enforced.
ERR_FILE="$(mktemp "${TMPDIR:-/tmp}/command-guard-err.XXXXXX" 2>/dev/null || true)"
if [ -n "$ERR_FILE" ] && [ -w "$ERR_FILE" ]; then
    OUT="$(run_validator "$CMD" 2>"$ERR_FILE")"; RC=$?
    ERR="$(cat "$ERR_FILE" 2>/dev/null)"
    rm -f "$ERR_FILE"
else
    hlog "WARN" "no writable temp file for the validator's stderr — verdicts still enforced, crash detection degraded"
    OUT="$(run_validator "$CMD" 2>/dev/null)"; RC=$?
    ERR=""
fi

# A validator that CRASHED is unavailable, not a verdict.
#
# `command -v claudekit` succeeds for a console script whose package is gone, so
# the shim runs, dies on ImportError and exits 1 — which fell through to the
# `RC -ne 0` deny below and blocked EVERY Bash command, `git status` included,
# while printing a Python traceback dressed as a policy decision. The header
# already documents "validator unavailable" as the one permissive path; an
# import-time crash IS that case, so it routes there. `strict` still blocks.
#
# TWO independent conditions, because ONE of them was measured to be defeatable.
# Grepping the MERGED output for crash tokens is unsound: a refusal ECHOES THE
# COMMAND, so `ImportError=1 rm -rf /tmp/zzz` put the token `ImportError` inside
# a genuine rc=2 verdict and routed it to the permissive branch. Splitting the
# channels is not enough on its own either, because this validator writes its
# verdict to stderr too.
#
# So the EXIT CODE decides and the text only corroborates:
#   rc 0   -> allowed.
#   rc 2   -> a VERDICT. Never permissive, whatever the text says. A caller
#             controls the message, never the exit status.
#   rc 127 -> unavailable, handled below.
#   else   -> a candidate crash, and only then is stderr consulted.
#
# The pattern is ANCHORED because a real traceback starts a line with
# `Traceback (most recent call last):` or with `SomeError: `, while an echoed
# token sits mid-sentence. Anchoring also keeps a legacy validator that reports
# violations with rc 1 from being walked through the same way.
if [ "$RC" -ne 0 ] && [ "$RC" -ne 2 ] && [ "$RC" -ne 127 ] \
        && printf '%s\n' "$ERR" | grep -qE \
            '^(Traceback \(most recent call last\):|[A-Za-z_.]*(ModuleNotFoundError|ImportError): )'; then
    hlog "WARN" "validator CRASHED (rc=$RC) — treating as unavailable, command NOT checked"
    printf 'command-guard: the validator crashed rather than returning a verdict, so this command was NOT checked.\n' >&2
    printf 'This is a BROKEN TOOL, not a policy refusal. Repair the claudekit-agents install (`ck doctor`), or set ECC_HOOK_PROFILE=strict to block instead.\n' >&2
    printf '%s\n' "$ERR" | head -5 >&2
    RC=127
fi


# Validator missing: the ONE permissive path under standard (see header).
if [ "$RC" -eq 127 ]; then
    [ "$PROFILE" = "strict" ] && deny "command-guard: validator unavailable (fail-closed)"
    hlog "WARN" "validator unavailable — command NOT checked (install claudekit-agents, or set ECC_HOOK_PROFILE=strict to block instead)"
    printf 'command-guard: validator unavailable, command NOT checked. Install the claudekit-agents package (`ck doctor` diagnoses) or set ECC_HOOK_PROFILE=strict to block instead.\n' >&2
    exit 0
fi

# Flagged command: block under standard AND strict.
if [ "$RC" -ne 0 ]; then
    # OUT first, ERR as the fallback: with the channels split, a validator that
    # writes its reason to stderr would otherwise refuse with no reason at all.
    deny "command-guard: ${OUT:-${ERR:-policy violation}}"
fi

exit 0
