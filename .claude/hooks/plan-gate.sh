#!/usr/bin/env bash
# =============================================================================
# Plan Gate Hook (PreToolUse -- Edit / Write)
# Replaces ops-enforcement: Tier-3 source may be edited directly only when an
# APPROVED, unchanged plan.md names the path in its `Files:` header.
# Active only where <root>/.claude/plans/ exists. Blocks with exit 2 + stderr and
# FAILS CLOSED on any parse failure. NO ECC_HOOK_PROFILE early exit: it must bind
# under `minimal` too (declared "on" in profiles/minimal/profile.json).
# Honest limit: a denylist speed bump, not a sandbox (kit hard rule 6).
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="plan-gate"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
. "$SCRIPT_DIR/plan-lib.sh" 2>/dev/null || { echo "BLOCKED: plan-lib.sh missing; refusing an unverified edit." >&2; exit 2; }

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
[ -z "$TARGET_PATH" ] && deny "BLOCKED: the edit names no target path; refusing an unverified edit."

ABS_TARGET=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$TARGET_PATH" 2>/dev/null) || deny \
    "BLOCKED: could not resolve $TARGET_PATH; refusing an unverified edit."
ABS_ROOT=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$ROOT" 2>/dev/null) || deny \
    "BLOCKED: could not resolve the project root; refusing an unverified edit."

# Not a plan-gated project.
[ -d "$ABS_ROOT/.claude/plans" ] || exit 0

REL=$(pg_rel_target)

# Allow: OS temp / session scratchpad OUTSIDE the project (never source).
case "$ABS_TARGET" in
    "$ABS_ROOT"/*) : ;;
    /private/tmp/claude-*|/tmp/claude-*|/private/var/folders/*|/var/folders/*) exit 0 ;;
    *) exit 0 ;;   # other projects are not this gate's business
esac
case "$REL" in .hermes/scratch/*) exit 0 ;; esac

# 1. Deny list -- before every allow rule, the carve-out included.
if pg_is_denied_path "$REL"; then
    deny "PLAN GATE -- PROTECTED PATH
Target: $TARGET_PATH

Review records, settings files and plan-gate.globs are owner-only. Ask the owner to
make this change with: ! <command>"
fi
# An approved plan's Files:/Tier header is frozen (any edit is drift anyway).
if pg_is_approved_plan "$ABS_TARGET"; then
    if printf '%s' "$TOOL_INPUT" | python3 -c '
import json, re, sys
t = json.load(sys.stdin).get("tool_input") or {}
text = "\n".join(str(t.get(k) or "") for k in ("old_string", "new_string", "content"))
sys.exit(0 if re.search(r"(?mi)^\s*(?:[-*]\s*)?\**(files|tier)\b", text) or "Files:" in text else 1)' 2>/dev/null; then
        deny "PLAN GATE -- APPROVED PLAN HEADER IS FROZEN
Target: $TARGET_PATH

Do not edit Files:/Tier lines of an approved plan. Write a new plan and get it reviewed."
    fi
    exit 0
fi

# 2. Tier.
PG_T3_SOURCE=""
if ! pg_is_t3 "$REL"; then
    # Advisory tier: stderr nudge for non-doc source outside the T3 list, exit 0.
    # ECC_PLAN_GATE=off silences ONLY this nudge; it never loosens the T3 block.
    if [ "${ECC_PLAN_GATE:-on}" != "off" ]; then
        case "$REL" in
            .claude/*|*.md|*.txt|*.rst|*.adoc|*.log|*.tmp) : ;;
            *) echo "plan-gate (advisory): $REL is outside the Tier-3 list; no plan required." >&2 ;;
        esac
    fi
    exit 0
fi

# 3. Tier-1 single-line carve-out: only where T3 came from the DEFAULT rule, never from
#    plan-gate.globs. Same shape as the retired ops-enforcement carve-out: tool Edit on an
#    existing file, non-empty old_string, no newline either side, replace_all unset.
if [ "$PG_T3_SOURCE" = "default" ] && [ "$TOOL_NAME" = "Edit" ] && [ -f "$ABS_TARGET" ] \
   && printf '%s' "$TOOL_INPUT" | python3 -c '
import json, sys
t = json.load(sys.stdin).get("tool_input") or {}
old, new = t.get("old_string"), t.get("new_string")
ok = (isinstance(old, str) and isinstance(new, str) and old != ""
      and "\n" not in old and "\n" not in new and t.get("replace_all") is not True)
sys.exit(0 if ok else 1)' 2>/dev/null; then
    exit 0
fi

# 4. Plan binding.
if pg_authorised "$REL"; then
    exit 0
fi

deny "PLAN GATE -- NO APPROVED PLAN COVERS THIS EDIT
Target: $TARGET_PATH

This is a Tier-3 path. Write .claude/plans/plan-<slug>.md naming it in its Files:
header, get it reviewed (>= 90), then record it:
  python3 .claude/operations/scripts/review-record.py plan-write <plan.md> --from-task <agentId>
An edited plan needs a fresh review (its sha256 is bound)."
