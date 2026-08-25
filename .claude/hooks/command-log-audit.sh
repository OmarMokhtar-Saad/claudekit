#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# =============================================================================
# Command Log Audit Hook
# Logs all Bash tool commands to a persistent audit log.
# Runs as a PostToolUse hook on Bash tool calls.
# =============================================================================

LOG_FILE="$SCRIPT_DIR/hooks.log"
# `$SCRIPT_DIR`, matching LOG_FILE directly above. This was cwd-relative while its own
# sibling on the line above was not, so from any directory but the repo root the AUDIT
# TRAIL was written somewhere else -- or nowhere, since the `2>/dev/null` on the append
# hides a missing directory. Measured: of the 11 hooks wired in settings.json, exactly ONE
# is invoked with a `cd` to the project root, so cwd is not something a hook may assume.
# An audit log that lands in the wrong directory is the "looks like coverage" failure this
# whole review pass keeps finding (F55).
AUDIT_LOG="$SCRIPT_DIR/bash-commands.log"
HOOK_NAME="command-log-audit"

# Read tool input (piped from Claude Code)
TOOL_INPUT=$(cat 2>/dev/null)

# Extract the command via lib.sh's shared extractor, which searches the top level AND
# `tool_input` AND `input`.
#
# THE AUDIT LOG HAD NEVER RECORDED ANYTHING. This hook carried its own inline extractor
# reading only `data.get('command')` at the TOP LEVEL, while a PostToolUse payload nests it
# under `tool_input` -- so `CMD` was always empty and the `[ -z "$CMD" ] && exit 0` below
# returned before the append, every single time. Empirical confirmation, which is what
# turned this from a theory into a finding: after weeks of hook runs in this repo,
# `.claude/hooks/bash-commands.log` DID NOT EXIST.
#
# That is why finding F55 ("the audit trail lands in the wrong directory") understated it:
# a cwd-relative path is a real defect, and it was the second one. A hook whose whole job is
# to record cannot be judged by whether it exits 0.
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
command -v extract_json_field >/dev/null 2>&1 || extract_json_field() {
    printf '%s' "$1" | HOOK_KEY="$2" python3 -c '
import sys, json, os
key = os.environ["HOOK_KEY"]
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for scope in (d, d.get("tool_input", {}) if isinstance(d, dict) else {},
              d.get("input", {}) if isinstance(d, dict) else {}):
    if isinstance(scope, dict) and scope.get(key):
        print(scope[key]); break
' 2>/dev/null
}

CMD=$(extract_json_field "$TOOL_INPUT" command)

# Skip empty commands
[ -z "$CMD" ] && exit 0

# Truncate very long commands for readability
CMD_TRUNCATED="${CMD:0:500}"
[ ${#CMD} -gt 500 ] && CMD_TRUNCATED="$CMD_TRUNCATED...(truncated)"

# Neutralize embedded newlines/CRs so a logged command can't forge extra
# audit-log lines (log injection / log forging).
CMD_TRUNCATED="${CMD_TRUNCATED//$'\n'/\\n}"
CMD_TRUNCATED="${CMD_TRUNCATED//$'\r'/\\r}"

# Append to audit log
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] pwd=$(pwd) cmd=$CMD_TRUNCATED" >> "$AUDIT_LOG" 2>/dev/null

exit 0
