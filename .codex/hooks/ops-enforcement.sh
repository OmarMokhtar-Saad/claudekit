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

# Allow: files inside THIS project's .claude/ directory.
case "$ABS_TARGET" in "$ABS_ROOT/.claude/"*) exit 0 ;; esac

# Allow: pure documentation files anywhere in this project.
echo "$ABS_TARGET" | grep -qE '\.(md|txt|rst|adoc)$' && exit 0

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

# BLOCK: direct source edit inside this project.
deny "OPS ENFORCEMENT — DIRECT EDIT BLOCKED
Target: $TARGET_PATH

Direct Edit/Write to source files is forbidden. All changes must go through:
  1. Generate ops.json (via /plan or /refine)
  2. Validate:  python3 .claude/operations/scripts/validate-config-json.py <ops.json>
  3. Execute:   python3 .claude/operations/scripts/execute-json-ops.py <ops.json>"
