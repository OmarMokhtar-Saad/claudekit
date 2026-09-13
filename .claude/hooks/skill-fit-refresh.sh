#!/bin/bash
# =============================================================================
# Skill-Fit Refresh Hook
# Runs as a Stop hook, backgrounded by settings.json. NEVER blocks and never
# fails a session: every path exits 0, and nothing is printed.
#
# At most once per interval (default 24h) it refreshes this project's skill-fit
# state so nobody has to run the loop by hand:
#   1. `ck skill audit --save`   -> reports/skills/audit.json in this project
#   2. `ck skill card --publish` -> this project's cards in the USER-level
#                                   registry (~/.claudekit/registry/cards/)
# Each step is bounded by a timeout; a failure or timeout is logged to
# hooks.log and otherwise ignored. `ck doctor` then reports how many
# suggestions other projects' cards offer this one.
#
# Knobs (environment):
#   CLAUDEKIT_SKILL_REFRESH=0                  opt out entirely
#   CLAUDEKIT_SKILL_REFRESH_INTERVAL_MIN=1440  minutes between runs
#   CLAUDEKIT_SKILL_REFRESH_TIMEOUT=60         seconds per step
# =============================================================================
# ECC_HOOK_PROFILE: off under minimal (the maintainer posture, where an
# automatic publish to the user-level registry is unwanted); runs under
# standard and strict. Declared in profiles.GUARDED_HOOKS and minimal's profile.
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$SCRIPT_DIR/hooks.log"
HOOK_NAME="skill-fit-refresh"
STAMP="$CK_ROOT/.claude/reports/skills/refresh.stamp"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$1] $2" >> "$LOG_FILE" 2>/dev/null
}

[ "${CLAUDEKIT_SKILL_REFRESH:-1}" = "0" ] && exit 0
# Not a ClaudeKit project with skills: nothing to audit or publish.
[ -d "$CK_ROOT/.claude/skills" ] || exit 0

INTERVAL_MIN="${CLAUDEKIT_SKILL_REFRESH_INTERVAL_MIN:-1440}"
case "$INTERVAL_MIN" in ''|*[!0-9]*) INTERVAL_MIN=1440 ;; esac
TIMEOUT_S="${CLAUDEKIT_SKILL_REFRESH_TIMEOUT:-60}"
case "$TIMEOUT_S" in ''|*[!0-9]*) TIMEOUT_S=60 ;; esac
[ "$TIMEOUT_S" -gt 0 ] 2>/dev/null || TIMEOUT_S=60

# Rate limit: a stamp newer than the interval means a run already happened.
# `find -mmin` is the portable (BSD + GNU) mtime comparison; no `stat` flags.
if [ -f "$STAMP" ] && [ -n "$(find "$STAMP" -mmin -"$INTERVAL_MIN" 2>/dev/null)" ]; then
    exit 0
fi
mkdir -p "$(dirname "$STAMP")" 2>/dev/null || exit 0
# Claim the interval BEFORE running, so a second Stop firing meanwhile stands down.
touch "$STAMP" 2>/dev/null || exit 0

# The CLI: the importable package first (matches the python3 the hooks use),
# then a `ck` on PATH. Neither -> log and stand down.
if python3 -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('claudekit.cli.main') else 1)" >/dev/null 2>&1; then
    CK_MODE="python"
elif command -v ck >/dev/null 2>&1; then
    CK_MODE="ck"
else
    log "WARN" "claudekit CLI not found; skill-fit refresh skipped"
    exit 0
fi

# Run one `ck` invocation with a watchdog (macOS ships no `timeout`).
run_ck() {
    if [ "$CK_MODE" = "python" ]; then
        (cd "$CK_ROOT" && exec python3 -m claudekit.cli.main "$@") </dev/null >/dev/null 2>&1 &
    else
        (cd "$CK_ROOT" && exec ck "$@") </dev/null >/dev/null 2>&1 &
    fi
    local pid=$!
    ( sleep "$TIMEOUT_S"; kill "$pid" 2>/dev/null ) </dev/null >/dev/null 2>&1 &
    local watchdog=$!
    # `wait ... 2>/dev/null`: bash reports a killed job ("Terminated") on stderr when it
    # reaps it, and this hook must print nothing.
    wait "$pid" 2>/dev/null
    local rc=$?
    kill "$watchdog" 2>/dev/null
    wait "$watchdog" 2>/dev/null
    return $rc
}

for step in "audit --save" "card --publish"; do
    # shellcheck disable=SC2086  # step is a fixed two-word literal from the list above
    run_ck skill $step
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log "INFO" "skill $step: ok"
    elif [ "$rc" -ge 128 ]; then
        log "WARN" "skill $step: timed out after ${TIMEOUT_S}s"
    else
        log "WARN" "skill $step: exit $rc (ignored)"
    fi
done

exit 0
