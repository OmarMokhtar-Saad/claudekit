#!/usr/bin/env bash
# =============================================================================
# Ops Enforcement Hook (PreToolUse — Edit / Write)
# Blocks direct file edits to source code. ALL source changes must go through
# execute-json-ops.py. Only .claude/ config files and docs may be edited directly.
# Blocks with exit 2 + stderr; fails CLOSED on payload parse failure.
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="ops-enforcement"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

ROOT=$(resolve_root)
TOOL_INPUT=$(cat)

# Fail closed: if we cannot parse the payload we cannot verify the edit is safe.
TOOL_NAME=$(extract_json_field "$TOOL_INPUT" tool_name) || deny \
    "BLOCKED: could not parse the tool payload; refusing an unverified edit."
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(extract_json_field "$TOOL_INPUT" name)

# Only guard Edit/Write-family tools.
case "$TOOL_NAME" in
    *edit*|*write*|*Edit*|*Write*) : ;;
    *) exit 0 ;;
esac

TARGET_PATH=$(extract_json_field "$TOOL_INPUT" path) || deny \
    "BLOCKED: could not parse the edit target; refusing an unverified edit."
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" file_path)
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" target_file)
[ -z "$TARGET_PATH" ] && exit 0

ABS_TARGET=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$TARGET_PATH" 2>/dev/null || echo "$TARGET_PATH")
ABS_ROOT=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$ROOT" 2>/dev/null || echo "$ROOT")

# Allow: session scratchpad / OS temp dirs. These live OUTSIDE the project and are
# never source code — blocking them produced false "CROSS-PROJECT EDIT BLOCKED"
# denials on the agent's own scratch files (upstreamed from an AppiumLens field fix).
# Project src/ protection is unaffected.
case "$ABS_TARGET" in
    /private/tmp/claude-*|/tmp/claude-*|/private/var/folders/*|/var/folders/*) exit 0 ;;
esac

# Repo-local source override (opt-in, absent by default).
OPS_SOURCE_MATCH=0
OPS_GLOBS_FILE="$ABS_ROOT/.ops-source-globs"
OPS_SOURCE_PATTERNS=""
if [ -n "${ECC_OPS_SOURCE_GLOBS:-}" ]; then
    OPS_SOURCE_PATTERNS=$(printf '%s' "$ECC_OPS_SOURCE_GLOBS" | tr ':' '\n' | tr -d '\r')
elif [ -f "$OPS_GLOBS_FILE" ]; then
    # `tr -d` \r: a CRLF marker would otherwise yield patterns that match nothing,
    # silently disabling enforcement. 2>/dev/null: an unreadable marker fails dormant
    # without leaking "Permission denied" onto the hook's stderr.
    OPS_SOURCE_PATTERNS=$(cat "$OPS_GLOBS_FILE" 2>/dev/null | tr -d '\r')
fi
if [ -n "$OPS_SOURCE_PATTERNS" ]; then
    REL_TARGET=${ABS_TARGET#"$ABS_ROOT"/}
    case "$REL_TARGET" in
        /*) : ;;
        .claude/plans/*|.claude/reports/*|.claude/knowledge/*|.claude/backups/*) : ;;
        .claude/settings.local.json|*.log|*.tmp|.claude/hooks/compact-counter.txt) : ;;
        *)
            OPS_OLD_IFS=$IFS
            set -f
            IFS='
'
            for pat in $OPS_SOURCE_PATTERNS; do
                case "$pat" in ''|\#*) continue ;; esac
                # shellcheck disable=SC2254
                case "$REL_TARGET" in $pat) OPS_SOURCE_MATCH=1; break ;; esac
            done
            set +f
            IFS=$OPS_OLD_IFS
            ;;
    esac
fi

# Allow: files inside THIS project's .claude/ directory, and pure documentation
# files anywhere in this project — UNLESS the repo-local override reclassified
# this path as source.
if [ "$OPS_SOURCE_MATCH" -eq 0 ]; then
    case "$ABS_TARGET" in "$ABS_ROOT/.claude/"*) exit 0 ;; esac
    if echo "$ABS_TARGET" | grep -qE '\.(md|txt|rst|adoc)$'; then
        exit 0
    fi
fi

# Allow: ops.json files themselves (both `*.ops.json` and `ops-*.json`).
echo "$ABS_TARGET" | grep -qE "$OPS_REGEX" && exit 0

# Allow: project not using the ops system (executor absent).
[ -f "$ABS_ROOT/.claude/operations/scripts/execute-json-ops.py" ] || exit 0

# BLOCK: cross-project edit.
case "$ABS_TARGET" in
    "$ABS_ROOT/"*) : ;;
    *) deny "OPS ENFORCEMENT — CROSS-PROJECT EDIT BLOCKED
Target: $TARGET_PATH
Current project: $ABS_ROOT

Editing files in another project directly is forbidden. Define the change in an
ops.json and execute it via:
  python3 .claude/operations/scripts/execute-json-ops.py <ops.json>" ;;
esac

# BLOCK: repo-local source override — .claude/ prompt assets are THIS repo's product.
if [ "$OPS_SOURCE_MATCH" -eq 1 ]; then
    deny "OPS ENFORCEMENT — DIRECT EDIT BLOCKED (repo-local source override)
Target: $TARGET_PATH

This project's .ops-source-globs marks this path as SOURCE, so the usual
.claude/ and documentation exemptions do not apply here. Route the change
through an ops.json:
  1. Write .claude/plans/<name>.ops.json
  2. Validate:  python3 .claude/operations/scripts/validate-config-json.py <ops.json>
  3. Execute:   python3 .claude/operations/scripts/execute-json-ops.py <ops.json>"
fi

# BLOCK: direct source edit inside this project.
deny "OPS ENFORCEMENT — DIRECT EDIT BLOCKED
Target: $TARGET_PATH

Direct Edit/Write to source files is forbidden. All changes must go through:
  1. Generate ops.json (via /plan or /refine)
  2. Validate:  python3 .claude/operations/scripts/validate-config-json.py <ops.json>
  3. Execute:   python3 .claude/operations/scripts/execute-json-ops.py <ops.json>"
