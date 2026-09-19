#!/usr/bin/env bash
# =============================================================================
# Block --no-verify Hook (PreToolUse — Bash)
# Prevents bypassing git hooks via the --no-verify flag.
# Also denies review-record.py --owner-approved to agents, under EVERY profile
# (see "Agent self-approval" below).
# Blocks with exit 2 + stderr (the only contract Claude Code honors).
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="block-no-verify"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

TOOL_INPUT=$(cat)

# --- Agent self-approval: review-record.py --owner-approved -------------------
# Checked BEFORE the profile guard below, so it binds under every profile. The
# approval gate this flag bypasses (execute-json-ops.py -> review-record.py
# check) is profile-independent, so the guard on its escape hatch is too; this
# repo runs its own sessions on the lightest profile, where a guard that stood
# down would never bind.
#
# --owner-approved records an APPROVED verdict with no parsed review. It is for
# the human owner, typed in their own terminal or a `!` shell command, neither
# of which passes through PreToolUse. From an agent it is self-approval.
#
# The match is broad on purpose: quote and backslash characters are deleted
# first; the WHOLE command is scanned, not one ;&| segment, so `bash -c`, a
# heredoc or a variable set earlier on the line is still seen; the full flag
# counts anywhere (a renamed copy of the script), and any argparse prefix of it
# (--ow, --owne, ...) counts on a command that names review-record. An
# unparseable payload is scanned raw: fail closed.
# SPEED BUMP AGAINST AGENTS, NOT A SANDBOX: a script file written first, a
# python -c call to write_verdict(), or a hand-written record file get past it.
OWNER_FLAG="--owner-approved"
OWNER_SCAN=$(extract_json_field "$TOOL_INPUT" command) || OWNER_SCAN="$TOOL_INPUT"
OWNER_SCAN=$(printf '%s' "$OWNER_SCAN" | tr -d "\"'\\\\")
OWNER_HIT=""
for OWNER_TOK in $(printf '%s' "$OWNER_SCAN" | grep -oE -e '--ow[a-z-]*'); do
    if [ "$OWNER_TOK" = "$OWNER_FLAG" ]; then
        OWNER_HIT=1
    fi
    case "$OWNER_FLAG" in
        "$OWNER_TOK"*)
            if printf '%s' "$OWNER_SCAN" | grep -q 'review-record'; then
                OWNER_HIT=1
            fi
            ;;
    esac
done
if [ -n "$OWNER_HIT" ]; then
    deny "BLOCKED: an agent may not record an approval without a review.

Only a reviewer's report authorises execution. Spawn a fresh code-reviewer
(reviewer, for a plan), save its full output to a file, and bind it:
  python3 .claude/operations/scripts/review-record.py write <plan> <ops> --from-review <file>
Do not ask the user to type a score or run an approval for you.
(Searching source for the flag? Leave off its two leading dashes.)"
fi

[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

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
