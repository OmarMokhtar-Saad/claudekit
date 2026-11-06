#!/usr/bin/env bash
# =============================================================================
# Checkpoint Gate Hook (PreToolUse -- Edit / Write), Tier-3 paths only.
# Replaces the executor's backup/rollback: before the first Tier-3 edit it takes a
# `git stash create` snapshot, tagged ck-checkpoint/<epoch>, unless one newer than 30
# minutes exists. Untracked files are listed in the tag message (stash create does
# not capture them). Budget 5 s. Blocks (exit 2) ONLY when a checkpoint cannot be
# created. Keeps the newest 20 ck-checkpoint/* tags. No ECC_HOOK_PROFILE early exit.
# Restore: git stash apply <tag>   (see /checkpoint).
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="checkpoint-gate"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
. "$SCRIPT_DIR/plan-lib.sh" 2>/dev/null || { echo "BLOCKED: plan-lib.sh missing; refusing an unverified edit." >&2; exit 2; }

CK_FRESH_SECONDS="${CK_CHECKPOINT_FRESH_SECONDS:-1800}"
CK_KEEP_TAGS=20

ROOT=$(resolve_root)
TOOL_INPUT=$(cat)

TOOL_NAME=$(extract_json_field "$TOOL_INPUT" tool_name) || deny \
    "BLOCKED: could not parse the tool payload; refusing an unverified edit."
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(extract_json_field "$TOOL_INPUT" name)
case "$TOOL_NAME" in
    *edit*|*write*|*Edit*|*Write*) : ;;
    *) exit 0 ;;
esac

TARGET_PATH=$(extract_json_field "$TOOL_INPUT" path) || deny \
    "BLOCKED: could not parse the edit target; refusing an unverified edit."
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" file_path)
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" target_file)
[ -z "$TARGET_PATH" ] && exit 0

ABS_TARGET=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$TARGET_PATH" 2>/dev/null) || deny \
    "BLOCKED: could not resolve $TARGET_PATH; refusing an unverified edit."
ABS_ROOT=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$ROOT" 2>/dev/null) || deny \
    "BLOCKED: could not resolve the project root; refusing an unverified edit."

[ -d "$ABS_ROOT/.claude/plans" ] || exit 0
case "$ABS_TARGET" in "$ABS_ROOT"/*) : ;; *) exit 0 ;; esac

REL=$(pg_rel_target)
pg_is_t3 "$REL" || exit 0

# Not a git repo: no checkpoint is possible. T3 edits are plan-gated regardless.
git -C "$ABS_ROOT" rev-parse --git-dir >/dev/null 2>&1 || exit 0

NOW=$(date +%s)
NEWEST=$(git -C "$ABS_ROOT" tag -l 'ck-checkpoint/*' 2>/dev/null | sed 's#.*/##' | grep -E '^[0-9]+$' | sort -n | tail -1)
if [ -n "$NEWEST" ] && [ $((NOW - NEWEST)) -lt "$CK_FRESH_SECONDS" ]; then
    exit 0
fi

# Bounded git call (macOS has no `timeout`; perl's alarm is always present).
ck_git() { perl -e 'alarm 5; exec @ARGV' git -C "$ABS_ROOT" "$@"; }

SNAP=$(ck_git stash create "ck-checkpoint $NOW" 2>/dev/null)
if [ -z "$SNAP" ]; then
    SNAP=$(ck_git rev-parse HEAD 2>/dev/null)   # clean tree: HEAD is the checkpoint
fi
[ -n "$SNAP" ] || deny "CHECKPOINT GATE -- could not create a checkpoint (git stash create failed
or timed out after 5 s). Refusing a Tier-3 edit without a restore point."

UNTRACKED=$(ck_git ls-files --others --exclude-standard 2>/dev/null | head -200)
MSG="ck-checkpoint $NOW"
[ -n "$UNTRACKED" ] && MSG="$MSG
untracked at checkpoint (not in the snapshot):
$UNTRACKED"
if ! ck_git tag -a -m "$MSG" "ck-checkpoint/$NOW" "$SNAP" >/dev/null 2>&1; then
    deny "CHECKPOINT GATE -- could not tag the checkpoint ck-checkpoint/$NOW.
Refusing a Tier-3 edit without a restore point."
fi
hlog "INFO" "checkpoint ck-checkpoint/$NOW ($SNAP) before $REL"

# Prune: keep the newest $CK_KEEP_TAGS.
OLD=$(git -C "$ABS_ROOT" tag -l 'ck-checkpoint/*' 2>/dev/null | sed 's#.*/##' | grep -E '^[0-9]+$' | sort -rn | tail -n +$((CK_KEEP_TAGS + 1)))
for t in $OLD; do git -C "$ABS_ROOT" tag -d "ck-checkpoint/$t" >/dev/null 2>&1; done
exit 0
