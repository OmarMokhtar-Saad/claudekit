#!/bin/bash
# =============================================================================
# Commit Quality Hook (PreToolUse — Bash, intercepts git commit)
# Checks staged files for debug artifacts and validates commit message quality.
# Blocks ONLY on staged secrets. Warns on quality issues.
# =============================================================================
# ECC_HOOK_PROFILE: runs in standard + strict (not minimal)
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

LOG=".claude/hooks/hooks.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [commit-quality] [$1] $2" >> "$LOG" 2>/dev/null; }

# Read tool input
TOOL_INPUT=$(cat)
CMD=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('command', ''))
except:
    print('')
" 2>/dev/null)

# Only intercept git commit commands
if ! echo "$CMD" | grep -qE '^\s*git\s+commit'; then
    exit 0
fi

log "INFO" "Intercepting git commit for quality check"

HAS_BLOCKS=0
HAS_WARNINGS=0

# ---------------------------------------------------------------------------
# 1. Extract commit message from -m flag
# ---------------------------------------------------------------------------
COMMIT_MSG=""
if echo "$CMD" | grep -q '\-m'; then
    # Use python3 for reliable cross-platform extraction (avoids BSD sed \x27 issues)
    COMMIT_MSG=$(echo "$CMD" | python3 -c "
import sys, re
cmd = sys.stdin.read()
# Match -m followed by single or double quoted string
m = re.search(r'''-m\s+[\"']([^\"']*)[\"']''', cmd)
if m:
    print(m.group(1))
" 2>/dev/null)
fi

if [ -n "$COMMIT_MSG" ]; then
    MSG_LEN=${#COMMIT_MSG}
    if [ "$MSG_LEN" -lt 10 ]; then
        echo "COMMIT WARNING: Message too short (${MSG_LEN} chars). Use a descriptive message."
        HAS_WARNINGS=1
        log "WARN" "Commit message too short: '$COMMIT_MSG'"
    fi

    # Check for generic/meaningless messages
    GENERIC_PATTERNS="^(fix|update|wip|temp|test|done|ok|changes|stuff|misc|patch|hotfix|asdf|xxx)\.?$"
    if echo "${COMMIT_MSG,,}" | grep -qE "$GENERIC_PATTERNS"; then
        echo "COMMIT WARNING: Generic commit message '$COMMIT_MSG'. Describe what changed and why."
        HAS_WARNINGS=1
        log "WARN" "Generic commit message: '$COMMIT_MSG'"
    fi
fi

# ---------------------------------------------------------------------------
# 2. Check staged files for debug artifacts
# ---------------------------------------------------------------------------
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

if [ -n "$STAGED_FILES" ]; then
    # Warn on console.log / debugger statements (not block)
    DEBUG_FILES=""
    while IFS= read -r file; do
        [[ "$file" =~ \.(ts|tsx|js|jsx|mjs|cjs)$ ]] || continue
        if git show ":$file" 2>/dev/null | grep -nE '^\s*(console\.(log|debug|warn|error)|debugger\s*;)' >/dev/null 2>&1; then
            DEBUG_FILES="$DEBUG_FILES $file"
        fi
    done <<< "$STAGED_FILES"

    if [ -n "$DEBUG_FILES" ]; then
        echo "COMMIT WARNING: Debug statements found in staged files:$DEBUG_FILES"
        echo "  Remove console.log/debugger before committing to main branches."
        HAS_WARNINGS=1
        log "WARN" "Debug statements in:$DEBUG_FILES"
    fi

    # BLOCK on staged secret files
    SECRET_FILES=""
    while IFS= read -r file; do
        BASENAME=$(basename "$file")
        if echo "$BASENAME" | grep -qiE '^(\.env|\.env\..+|.*\.pem|.*\.key|credentials\.json|secrets\.json|id_rsa|id_ed25519)$'; then
            # Skip .env.example and .env.template
            echo "$BASENAME" | grep -qiE '\.(example|template|sample|test)$' && continue
            SECRET_FILES="$SECRET_FILES $file"
        fi
    done <<< "$STAGED_FILES"

    if [ -n "$SECRET_FILES" ]; then
        echo ""
        echo "COMMIT BLOCKED: Secret/key files staged for commit:$SECRET_FILES"
        echo "  Remove these files: git reset HEAD$SECRET_FILES"
        echo "  Add to .gitignore to prevent future accidents."
        log "BLOCK" "Secret files staged:$SECRET_FILES"
        HAS_BLOCKS=1
    fi

    # BLOCK on TODO: FIXME patterns that signal incomplete work
    FIXME_FILES=""
    while IFS= read -r file; do
        if git show ":$file" 2>/dev/null | grep -qE 'TODO:\s*FIXME|HACK:\s*REMOVE|DO NOT COMMIT|TEMP_WORKAROUND'; then
            FIXME_FILES="$FIXME_FILES $file"
        fi
    done <<< "$STAGED_FILES"

    if [ -n "$FIXME_FILES" ]; then
        echo "COMMIT WARNING: Incomplete-work markers found:$FIXME_FILES"
        echo "  Resolve TODO:FIXME / HACK:REMOVE markers before committing."
        HAS_WARNINGS=1
        log "WARN" "Incomplete markers in:$FIXME_FILES"
    fi
fi

# ---------------------------------------------------------------------------
# 3. Report result
# ---------------------------------------------------------------------------
if [ $HAS_WARNINGS -eq 1 ] && [ $HAS_BLOCKS -eq 0 ]; then
    echo ""
    echo "Commit quality warnings above. Commit will proceed — review warnings."
fi

[ $HAS_BLOCKS -eq 1 ] && exit 1
exit 0
