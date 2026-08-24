#!/bin/bash
# =============================================================================
# Security Reminder Hook (PreToolUse - Write / Edit on SOURCE files only)
# Warns when writing dangerous patterns to actual source code.
# Does NOT trigger on .claude/skills/, docs/, or *.md files.
# =============================================================================
# ECC_HOOK_PROFILE: runs in standard + strict (not minimal)
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
# The `[ -f ... ] &&` guard above promises graceful degradation, and delegating
# `log()` to `hlog` removes it: with `lib.sh` absent the hook printed
# "hlog: command not found" to stderr on every call, where the old body was
# `>> "$LOG" 2>/dev/null`. `lib.sh` ships beside the hooks so a fresh install is
# fine; the exposure is a surgical fleet sync that copies one hook and not the
# library. A no-op keeps the promise the guard makes.
command -v hlog >/dev/null 2>&1 || hlog() { :; }
HOOK_NAME="security-reminder"
# `$SCRIPT_DIR`, not a cwd-relative path: this hook wrote to `.claude/hooks/hooks.log`
# relative to the CURRENT DIRECTORY, so its log landed elsewhere (or nowhere) whenever
# the cwd was not the repo root. Three hooks shared that bug and a third `LOG_FILE=`
# form (finding F107); the same class already misplaces `command-log-audit.sh`'s audit
# trail (F55). `hlog` also uses `$*`, so an argument past the second no longer vanishes.
LOG_FILE="$SCRIPT_DIR/hooks.log"
log() { hlog "$@"; }

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
