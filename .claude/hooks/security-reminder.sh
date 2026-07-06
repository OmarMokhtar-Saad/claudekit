#!/bin/bash
# =============================================================================
# Security Reminder Hook (PreToolUse - Write / Edit on SOURCE files only)
# Warns when writing dangerous patterns to actual source code.
# Does NOT trigger on .claude/skills/, docs/, or *.md files.
# =============================================================================
# ECC_HOOK_PROFILE: runs in standard + strict (not minimal)
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

LOG=".claude/hooks/hooks.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [security-reminder] [$1] $2" >> "$LOG" 2>/dev/null; }

TOOL_INPUT=$(cat)

TOOL_NAME=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_name', d.get('name', '')))
except:
    print('')
" 2>/dev/null)

if [[ "$TOOL_NAME" != *"edit"* ]] && [[ "$TOOL_NAME" != *"write"* ]] && \
   [[ "$TOOL_NAME" != *"Edit"* ]] && [[ "$TOOL_NAME" != *"Write"* ]]; then
    exit 0
fi

TARGET_PATH=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    inp = d.get('tool_input', d.get('input', d))
    print(inp.get('path', inp.get('file_path', inp.get('target_file', ''))))
except:
    print('')
" 2>/dev/null)

[ -z "$TARGET_PATH" ] && exit 0

# Skip documentation, skills, and config files
for skip in '.claude/skills/' '.claude/agents/' '.claude/commands/' '.claude/hooks/' \
            'docs/' 'README' 'CHANGELOG' 'LICENSE' 'CONTRIBUTING' 'templates/'; do
    echo "$TARGET_PATH" | grep -q "$skip" && exit 0
done
echo "$TARGET_PATH" | grep -qE '\.(md|txt|rst)$' && exit 0

CONTENT=$(echo "$TOOL_INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    inp = d.get('tool_input', d.get('input', d))
    for key in ['new_string', 'content', 'new_content', 'text']:
        if key in inp:
            print(inp[key][:3000])
            break
except:
    pass
" 2>/dev/null)

[ -z "$CONTENT" ] && exit 0

WARNINGS=()

if echo "$CONTENT" | grep -qE 'shell\s*=\s*True'; then
    WARNINGS+=("Shell injection risk: subprocess with shell=True and dynamic input")
fi

if echo "$CONTENT" | grep -qE 'SELECT.*\+.*WHERE|query.*\+.*\$'; then
    WARNINGS+=("SQL injection risk: string concatenation in database query")
fi

if echo "$CONTENT" | grep -qE 'innerHTML\s*=.*\+|document\.write\(.*\+'; then
    WARNINGS+=("XSS risk: unsanitized content written to DOM")
fi

if echo "$CONTENT" | grep -qE 'verify\s*=\s*False|ssl_verify.*False|check_hostname.*False'; then
    WARNINGS+=("TLS verification disabled")
fi

if echo "$CONTENT" | grep -qE '\bMD5\b|\bSHA1\b|\bRC4\b'; then
    WARNINGS+=("Weak cryptographic algorithm (MD5/SHA1/RC4)")
fi

if echo "$CONTENT" | grep -qE 'Access-Control-Allow-Origin.*\*|cors.*\*'; then
    WARNINGS+=("Overly permissive CORS policy")
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo ""
    echo "SECURITY REMINDER (non-blocking) in $TARGET_PATH:"
    for w in "${WARNINGS[@]}"; do
        echo "  - $w"
        log "WARN" "$w in $TARGET_PATH"
    done
    echo ""
fi

exit 0
