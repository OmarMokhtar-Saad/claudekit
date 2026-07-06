#!/usr/bin/env bash
# =============================================================================
# lib.sh — shared helpers for ClaudeKit hooks.
#
# Source this at the top of a hook:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   [ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
#
# Everything here is POSIX/bash-3.2 safe (stock macOS bash). No `${VAR,,}`,
# no `mapfile`, no GNU-only date/stat.
# =============================================================================

# Resolve the project root. Prefer git; fall back to PWD. Never returns empty.
resolve_root() {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -z "$root" ]; then
        root="${PWD:-.}"
    fi
    printf '%s' "$root"
}

# Ops-config filename patterns. The repo ships plans as `<name>.ops.json`, while
# older tooling searched `ops-*.json`. Match BOTH everywhere so validation never
# silently matches zero files again.
OPS_FIND_EXPR=('(' -name '*.ops.json' -o -name 'ops-*.json' ')')
# ERE that accepts both `foo.ops.json` and `ops-foo.json` (basename or path).
OPS_REGEX='(^|/)([^/]+\.ops\.json|ops(-[^/]+)?\.json)$'

# Structured logger. Usage: hlog LEVEL "message"
# HOOK_NAME and LOG_FILE should be set by the caller; sane defaults otherwise.
hlog() {
    local level="$1"; shift
    local name="${HOOK_NAME:-hook}"
    local logf="${LOG_FILE:-$(resolve_root)/.claude/hooks/hooks.log}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$name] [$level] $*" >> "$logf" 2>/dev/null
}

# Extract a JSON field from a payload string. Unlike the old `2>/dev/null`
# swallow, a parse failure is LOGGED (so drift is diagnosable) and signalled via
# a non-zero return, letting blocking guards fail closed.
#   value=$(extract_json_field "$PAYLOAD" command) || fail_closed
# The path is dot-free single keys, tried against the payload and common
# nesting (`tool_input`, `input`).
extract_json_field() {
    local payload="$1" key="$2" out
    out=$(printf '%s' "$payload" | HOOK_KEY="$key" python3 -c '
import sys, json, os
key = os.environ["HOOK_KEY"]
try:
    d = json.load(sys.stdin)
except Exception as e:
    sys.stderr.write("PARSE_ERROR: %s\n" % e)
    sys.exit(3)
for scope in (d, d.get("tool_input", {}) if isinstance(d, dict) else {},
              d.get("input", {}) if isinstance(d, dict) else {}):
    if isinstance(scope, dict) and key in scope and scope[key] not in (None, ""):
        print(scope[key]); sys.exit(0)
sys.exit(0)
' 2>>"${LOG_FILE:-/dev/null}")
    local rc=$?
    if [ "$rc" -eq 3 ]; then
        hlog "ERROR" "JSON parse failure extracting '$key' (fail-closed)"
        return 3
    fi
    printf '%s' "$out"
    return 0
}

# Deny an operation: write the reason to STDERR and exit 2 — the ONLY contract
# Claude Code honors for a PreToolUse block. (exit 1 / stdout does NOT block.)
deny() {
    hlog "BLOCK" "$*"
    printf '%s\n' "$*" >&2
    exit 2
}

# Literal-quote ERE fragments: a character class matching either quote, and its
# negation. Avoids the `\x27`-in-a-class bug (grep -E does not decode \x27).
ERE_QUOTE_CLASS="[\"']"
ERE_NOT_QUOTE_CLASS="[^\"']"
