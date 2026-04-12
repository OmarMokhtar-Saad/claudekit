#!/bin/bash
# =============================================================================
# Config Protection Hook (PreToolUse — Edit / Write)
# Blocks edits to linter, formatter, and type-checker config files.
# Forces the agent to fix code to comply rather than weakening rules.
# =============================================================================
# ECC_HOOK_PROFILE: runs in standard + strict (not minimal)
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

LOG=".claude/hooks/hooks.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [config-protection] [$1] $2" >> "$LOG" 2>/dev/null; }

# Config file patterns that are protected
PROTECTED_PATTERNS=(
    'eslint\.config\.'
    '\.eslintrc'
    '\.prettierrc'
    'prettier\.config\.'
    'tsconfig.*\.json'
    'biome\.json'
    '\.flake8'
    'setup\.cfg'
    'pyproject\.toml'
    '\.rubocop'
    '\.stylelintrc'
    'stylelint\.config\.'
    '\.editorconfig'
    'checkstyle'
    'spotbugs'
    'detekt'
    '\.golangci'
    'clippy\.toml'
    'rustfmt\.toml'
)

# Read tool input from stdin
TOOL_INPUT=$(cat)

# Extract tool name and target path
TOOL_NAME=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_name', d.get('name', '')))
except:
    print('')
" 2>/dev/null)

TARGET_PATH=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    inp = d.get('tool_input', d.get('input', d))
    print(inp.get('path', inp.get('file_path', inp.get('target_file', ''))))
except:
    print('')
" 2>/dev/null)

# Only check Edit and Write tools
if [[ "$TOOL_NAME" != *"edit"* ]] && [[ "$TOOL_NAME" != *"write"* ]] && \
   [[ "$TOOL_NAME" != *"Edit"* ]] && [[ "$TOOL_NAME" != *"Write"* ]]; then
    exit 0
fi

[ -z "$TARGET_PATH" ] && exit 0

# Check if target matches any protected pattern
# Use full path for context-aware matching, basename for pattern matching
FILENAME=$(basename "$TARGET_PATH")
FULL_PATH="$TARGET_PATH"

for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if echo "$FILENAME" | grep -qE "$pattern"; then
        # Special case: pyproject.toml is also used for build metadata and deps.
        # Only block if the file contains a [tool.ruff], [tool.black], [tool.flake8],
        # [tool.mypy], or [tool.pylint] section (i.e. it's acting as a linter config).
        if [ "$FILENAME" = "pyproject.toml" ] && [ -f "$FULL_PATH" ]; then
            if ! grep -qE '^\[tool\.(ruff|black|flake8|mypy|pylint|isort)\]' "$FULL_PATH" 2>/dev/null; then
                exit 0
            fi
        fi
        log "BLOCK" "Blocked edit to protected config: $TARGET_PATH"
        echo ""
        echo "CONFIG PROTECTION: Editing '$TARGET_PATH' is blocked."
        echo ""
        echo "Linter, formatter, and type-checker configs are protected."
        echo "Fix the code to comply with the rules instead of weakening them."
        echo ""
        echo "If you genuinely need to update this config (e.g. adding a new rule),"
        echo "the user must explicitly authorize it first."
        exit 1
    fi
done

exit 0
