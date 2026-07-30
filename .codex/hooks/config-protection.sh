#!/usr/bin/env bash
# =============================================================================
# Config Protection Hook (PreToolUse — Edit / Write)
# Blocks edits to linter, formatter, and type-checker config files, so the agent
# fixes code to comply rather than weakening the rules.
# Blocks with exit 2 + stderr; fails CLOSED on payload parse failure.
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="config-protection"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

PROTECTED_PATTERNS=(
    'eslint\.config\.' '\.eslintrc' '\.prettierrc' 'prettier\.config\.'
    'tsconfig.*\.json' 'biome\.json' '\.flake8' 'setup\.cfg' 'pyproject\.toml'
    '\.rubocop' '\.stylelintrc' 'stylelint\.config\.' '\.editorconfig'
    'checkstyle' 'spotbugs' 'detekt' '\.golangci' 'clippy\.toml' 'rustfmt\.toml'
)

TOOL_INPUT=$(cat)

TOOL_NAME=$(extract_json_field "$TOOL_INPUT" tool_name) || deny \
    "BLOCKED: could not parse the tool payload; refusing an unverified config edit."
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(extract_json_field "$TOOL_INPUT" name)

case "$TOOL_NAME" in
    *edit*|*write*|*Edit*|*Write*) : ;;
    *) exit 0 ;;
esac

TARGET_PATH=$(extract_json_field "$TOOL_INPUT" path) || deny \
    "BLOCKED: could not parse the edit target; refusing an unverified config edit."
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" file_path)
[ -z "$TARGET_PATH" ] && TARGET_PATH=$(extract_json_field "$TOOL_INPUT" target_file)
[ -z "$TARGET_PATH" ] && exit 0

FILENAME=$(basename "$TARGET_PATH")

for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if echo "$FILENAME" | grep -qE "$pattern"; then
        # pyproject.toml doubles as build/dependency metadata. Only block when it
        # actually carries a linter/formatter section AND already exists — creating
        # a brand-new pyproject.toml (no tool sections yet) is legitimate.
        if [ "$FILENAME" = "pyproject.toml" ]; then
            if [ ! -f "$TARGET_PATH" ]; then
                exit 0
            fi
            if ! grep -qE '^\[tool\.(ruff|black|flake8|mypy|pylint|isort)\]' "$TARGET_PATH" 2>/dev/null; then
                exit 0
            fi
        fi
        deny "CONFIG PROTECTION: Editing '$TARGET_PATH' is blocked.

Linter, formatter, and type-checker configs are protected. Fix the code to
comply with the rules instead of weakening them. If you genuinely need to change
this config, the user must explicitly authorize it first."
    fi
done

exit 0
