#!/usr/bin/env bash
# =============================================================================
# injection-scan-gate.sh — advisory wrapper around the prompt-injection scanner.
#
# Runs `prompt-injection-scanner.sh` over the submitted prompt and WARNS (never
# blocks) when a known injection pattern is present. Advisory-only to avoid
# false positives on legitimate security discussion; gated to `strict`.
#
# ECC_HOOK_PROFILE: strict only. Exit 0 always.
# =============================================================================
set -uo pipefail

HOOK_NAME="injection-scan-gate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

ROOT="$(resolve_root)"
LOG_FILE="${LOG_FILE:-$ROOT/.claude/hooks/hooks.log}"

[ "${ECC_HOOK_PROFILE:-standard}" != "strict" ] && exit 0

SCANNER=""
for candidate in "$SCRIPT_DIR/prompt-injection-scanner.sh" \
                 "$ROOT/.claude/hooks/prompt-injection-scanner.sh" \
                 "$ROOT/templates/hooks/prompt-injection-scanner.sh"; do
    if [ -f "$candidate" ]; then
        SCANNER="$candidate"
        break
    fi
done
[ -z "$SCANNER" ] && exit 0

PAYLOAD="$(cat)"
TEXT="$(extract_json_field "$PAYLOAD" prompt)" || exit 0
[ -z "$TEXT" ] && exit 0

if ! printf '%s\n' "$TEXT" | bash "$SCANNER" >/dev/null 2>&1; then
    hlog "WARN" "prompt-injection scanner flagged the prompt (advisory)"
    printf 'prompt-injection scanner (advisory): the prompt matched a known injection pattern\n' >&2
fi
exit 0
