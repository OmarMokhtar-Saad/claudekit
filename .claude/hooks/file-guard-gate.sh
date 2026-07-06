#!/usr/bin/env bash
# =============================================================================
# file-guard-gate.sh — advisory wrapper around the file-guard classifier.
#
# Runs `file-guard.sh` against the Edit/Write target and WARNS (never blocks)
# when the path is a sensitive file. Advisory-only so it never interrupts a
# legitimate edit; gated to the `strict` profile so it's opt-in.
#
# ECC_HOOK_PROFILE: strict only. Exit 0 always.
# =============================================================================
set -uo pipefail

HOOK_NAME="file-guard-gate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

ROOT="$(resolve_root)"
LOG_FILE="${LOG_FILE:-$ROOT/.claude/hooks/hooks.log}"

[ "${ECC_HOOK_PROFILE:-standard}" != "strict" ] && exit 0

# Locate the classifier (installed project vs. this repo).
GUARD=""
for candidate in "$SCRIPT_DIR/file-guard.sh" \
                 "$ROOT/.claude/hooks/file-guard.sh" \
                 "$ROOT/templates/hooks/file-guard.sh"; do
    if [ -f "$candidate" ]; then
        GUARD="$candidate"
        break
    fi
done
[ -z "$GUARD" ] && exit 0

PAYLOAD="$(cat)"
FP="$(extract_json_field "$PAYLOAD" file_path)" || exit 0
if [ -z "$FP" ]; then
    FP="$(extract_json_field "$PAYLOAD" path)" || exit 0
fi
[ -z "$FP" ] && exit 0

if ! bash "$GUARD" "$FP" >/dev/null 2>&1; then
    hlog "WARN" "file-guard flagged a sensitive path (advisory): $FP"
    printf 'file-guard (advisory): %s looks like a sensitive file — double-check this edit\n' "$FP" >&2
fi
exit 0
