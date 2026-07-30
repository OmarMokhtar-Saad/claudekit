#!/usr/bin/env bash
# =============================================================================
# Block --no-verify Hook (PreToolUse — Bash)
# Prevents bypassing git hooks via the --no-verify flag.
# Blocks with exit 2 + stderr (the only contract Claude Code honors).
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="block-no-verify"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

TOOL_INPUT=$(cat)

# Fail closed: an unparseable payload to a blocking guard is blocked, not allowed.
CMD=$(extract_json_field "$TOOL_INPUT" command) || deny \
    "BLOCKED: could not parse the tool payload; refusing to run an unverified command."

# Nothing to check if there is no command.
[ -z "$CMD" ] && exit 0

# Strip quoted substrings so a commit *message* that merely mentions the flag
# (e.g. git commit -m "wip --no-verify") is not mistaken for an actual bypass.
CMD_NOQUOTES=$(printf '%s' "$CMD" | sed "s/'[^']*'//g; s/\"[^\"]*\"//g")

# Block only when --no-verify appears as a flag inside a real git invocation.
if printf '%s' "$CMD_NOQUOTES" | grep -qE '(^|[;&|]|[[:space:]])git[[:space:]][^;&|]*--no-verify'; then
    deny "BLOCKED: The --no-verify flag bypasses git hooks and is not allowed.

Blocked command: $CMD

Why: --no-verify skips pre-commit and commit-msg hooks, which enforce code
quality, prevent secrets from being committed, and validate commit messages.

Alternatives:
  1. Fix the issue the hook is catching.
  2. If the hook is wrong, fix the hook.
  3. If a bypass is genuinely required, ask the user explicitly."
fi

# Warn (do NOT block) on git push --force without --force-with-lease.
if printf '%s' "$CMD_NOQUOTES" | grep -qE 'git[[:space:]].*--force\b' && \
   ! printf '%s' "$CMD_NOQUOTES" | grep -qE '--force-with-lease'; then
    hlog "WARN" "git push --force without --force-with-lease: $CMD"
    echo "WARNING: git push --force can overwrite remote history. Prefer --force-with-lease."
fi

exit 0
