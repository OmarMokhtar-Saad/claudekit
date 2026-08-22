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
# =============================================================================
# Decision codec — the shell half of src/claudekit/enforcement/decisions.py.
#
# ALLOW(0) < ADVISE(1) < ERROR(2) < DENY(3). Outcome of a dispatch is the MAX.
# This lives in shell, not Python, so the merge rule cannot be weakened by a
# failed import: dispatch.sh must still decide correctly on a box where
# `import claudekit` does not work. tests/test_dispatch_merge.py drives BOTH
# implementations over every input and fails if they disagree — the same
# artifact-binding pattern profiles.scan_hook_guards uses.
# =============================================================================

# exit code -> decision. 0 -> ALLOW, 2 -> DENY, ANYTHING ELSE -> ERROR.
# The last clause is the fix for the fail-open defect: a handler that crashed
# (127), was killed by a signal, or exited 1 has an UNKNOWN verdict, and unknown is not
# permission. Never add a permissive branch here.
ck_decision_from_exit() {
    case "${1:-}" in
        0) printf '0' ;;
        2) printf '3' ;;
        *) printf '2' ;;
    esac
}

# Cap an `advisory`-tier handler at ADVISE. Applied BEFORE the merge, so advisory
# output can neither override a block nor create one.
#
# ONLY the literal string `advisory` clamps. `${2:-}`, not `${2:-advisory}`: an
# omitted or empty tier must NOT clamp, because clamping is what DISARMS a
# handler, so defaulting to `advisory` here would silently turn a guard whose
# tier went missing into a hook that cannot block. Caught by executing
# test_shell_and_python_clamps_agree with tier="" -- the shell clamped, the
# Python did not, and the shell was the wrong one.
#
# THE RESOLVER MUST ACCEPT EXACTLY WHAT THIS FUNCTION DISARMS. dispatch.sh reads
# a row's tier as `row.get("tier", "advisory")` -- an absent key is advisory
# (and the resolver EMITS "advisory" for an absent key, so such a row really is
# clamped here), while `""` and `null` are NOT advisory and are rejected as
# illegal on any row carrying a `command_matcher`. Change one side and you must
# change the other: revision 4 diverged by one word here and that was the
# round-4 Critical. The divergence is caught by
# test_the_invariants_accepted_tiers_are_exactly_the_tiers_the_clamp_disarms.
ck_clamp_advisory() {
    local decision="${1:-0}" tier="${2:-}"
    if [ "$tier" = "advisory" ] && [ "$decision" -gt 1 ]; then
        printf '1'
    else
        printf '%s' "$decision"
    fi
}

ck_decision_label() {
    case "${1:-}" in
        0) printf 'ALLOW' ;;
        1) printf 'ADVISE' ;;
        2) printf 'ERROR' ;;
        3) printf 'DENY' ;;
        *) printf 'UNKNOWN' ;;
    esac
}

# decision -> exit code at the process boundary. ERROR and DENY both give 2.
ck_decision_exit() {
    if [ "${1:-0}" -ge 2 ]; then printf '2'; else printf '0'; fi
}

# mktemp that works on macOS bash 3.2 and GNU alike.
ck_mktemp() {
    mktemp "${TMPDIR:-/tmp}/ck-hook.XXXXXX" 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/ck-hook.$$"
}

# Milliseconds since epoch. macOS `date` has no %N, so fall back to Python and,
# failing that, to 0 — a missing duration must never abort a dispatch.
ck_now_ms() {
    python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || printf '0'
}

# Append one typed `hook_decision` record to the durable event log.
#   ck_emit_hook_decision EVENT HANDLER TIER EXIT DECISION MERGED TOOL DURATION_MS STDERR_FILE
# Best effort by design: a full disk must not brick a session, so a write failure
# is logged to hooks.log and swallowed. The SCHEMA is not best effort — the Python
# side raises on a malformed record rather than writing a partial one.
ck_emit_hook_decision() {
    local root; root=$(resolve_root)
    CK_EVENT="${1:-}" CK_HANDLER="${2:-}" CK_TIER="${3:-}" CK_EXIT="${4:-0}" \
    CK_DECISION="$(ck_decision_label "${5:-0}")" CK_MERGED="$(ck_decision_label "${6:-0}")" \
    CK_TOOL="${7:-}" CK_MS="${8:-0}" CK_ERRFILE="${9:-}" CK_ROOT="$root" \
    CK_SESSION="${CLAUDE_SESSION_ID:-${CLAUDEKIT_SESSION_ID:-local}}" \
    python3 - <<'PY' 2>>"${LOG_FILE:-/dev/null}" || hlog "WARN" "event-log append failed"
import os, sys
root = os.environ["CK_ROOT"]
sys.path.insert(0, os.path.join(root, "src"))
try:
    from claudekit.enforcement import eventlog
except Exception as exc:                      # not installed: log prose, keep going
    sys.stderr.write("eventlog unavailable: %s\n" % exc)
    sys.exit(0)
preview = ""
errfile = os.environ.get("CK_ERRFILE") or ""
if errfile and os.path.exists(errfile):
    with open(errfile, "r", encoding="utf-8", errors="replace") as fh:
        preview = fh.read(512)
session = os.environ["CK_SESSION"]
record = eventlog.new_event(
    "hook_decision", session,
    event=os.environ["CK_EVENT"],
    handler=os.environ["CK_HANDLER"],
    tier=os.environ["CK_TIER"],
    exit_code=int(os.environ.get("CK_EXIT") or 0),
    decision=os.environ["CK_DECISION"],
    merged_decision=os.environ["CK_MERGED"],
    tool_name=os.environ.get("CK_TOOL") or "",
    duration_ms=int(os.environ.get("CK_MS") or 0),
    stderr_preview=preview,
)
eventlog.append(eventlog.default_log_path(root, session), record)
PY
}
