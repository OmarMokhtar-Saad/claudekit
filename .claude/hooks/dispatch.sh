#!/usr/bin/env bash
# =============================================================================
# dispatch.sh — ONE dispatcher per event.
#
# Usage (from .claude/settings.json, shell-form `type: command`):
#     bash "$ROOT/.claude/hooks/dispatch.sh" <EventName>
# The tool payload arrives on STDIN and is replayed to every handler.
#
# WHY THIS EXISTS
# ---------------
# `.claude/settings.json` registers 26 hook entries across 8 events. Six fire on
# PreToolUse/Bash alone, and nothing defined what happens when two of them decide
# differently — the outcome fell out of registration order. Worse, a handler that
# BROKE failed open. Re-measured at 5f3e322, in a clean environment so the outer
# shell's interpreter lookup cannot be mistaken for the hook's own exit code:
#   echo '' | env -i PATH=/nonexistent /bin/bash ops-enforcement.sh; echo $?  ->  0
# 0 is ALLOW: with no dirname/cat and no lib.sh `deny`, the guard emits nothing
# and ends successfully. (An earlier `PATH=/nonexistent bash ...` reading of 127
# was the interpreter not being found -- the hook had not run at all.) Under this
# dispatcher that same broken environment IS observable, because the handler
# process cannot start: `bash`/`python3` unresolvable -> 127 -> ERROR -> exit 2.
# What the codec cannot rescue is a handler that degrades to 0 on its own; that
# hook-level shape is filed in .ai/BACKLOG.md.
#
# THE RULE, ONCE
#   ALLOW(0) < ADVISE(1) < ERROR(2) < DENY(3);  outcome = max over handlers.
#   exit 0 -> ALLOW, exit 2 -> DENY, ANY other exit (crash, signal, 127) -> ERROR.
#   ERROR renders as exit 2 at the boundary: an unknown verdict on a guarded
#   event is a block. Fail closed.
#   `advisory` handlers are CLAMPED to ADVISE before the merge, so advisory
#   output can never override a block, and a flaky advisory handler can never
#   create one.
#   A `command_matcher` (a PRECONDITION) may appear ONLY on an `advisory`
#   row. The resolver rejects any other row and the dispatcher fails closed.
#   ONE NORMALIZATION, USED TWICE: a row's effective tier is
#   `row.get("tier", "advisory")` -- an ABSENT key means advisory; an explicitly
#   empty or null tier does NOT. The invariant reads the tier exactly as the
#   resolver's emitter writes it, so the set the invariant ACCEPTS is exactly the
#   set `ck_clamp_advisory` DISARMS. A divergence between those two sets is not a
#   style difference, it is the bypass: revision 4 read `(tier or "advisory")`
#   here, which ACCEPTED `""` while the clamp refused to disarm it -- leaving a
#   blocking-capable row that carried a precondition, and was therefore skipped
#   on an unreadable payload.
#   This is enforced rather than assumed because the skip-on-unreadable-
#   payload rule below is only safe while such a row cannot block: an
#   invariant the code depends on and does not enforce IS the defect.
# max() is commutative and associative, so no ordering can change the outcome.
# src/claudekit/enforcement/decisions.py carries the same codec and the same
# most-restrictive rule, and tests/test_dispatch_merge.py fails if the two disagree
# on any input -- for from_exit_code, to_exit_code and clamp_advisory, which are the
# three functions under shell<->Python parity test.
#
# `decisions.merge` is NOT one of them, and the distinction is worth stating: the
# merge that actually runs is the bash arithmetic below, and it is mutation-proven
# by test_dispatch_merge.py (flipping this comparison must make a block vanish).
# The Python `merge` is re-exported public API with no caller in this repo, so it
# is covered directly over the decision tuples rather than by parity against a
# shell function that does not exist -- the shell side is inline here, not callable.
#
# NO PYTHON DEPENDENCY FOR THE DECISION. Python is used to read the registry and
# to append the event-log record; the merge itself is bash-3.2 arithmetic, so the
# rule cannot be weakened by an import failure.
#
# WHAT THIS DOES *NOT* DO: THERE IS NO PER-HANDLER TIMEOUT.
# Handlers run synchronously and unbounded. The dispatcher cannot observe a
# timeout, so exit 124 in the codec is only what a handler chooses to report --
# never something measured here. This is stated instead of implemented on
# purpose (CLAUDE.md hard rule 6: never document a control that does not exist):
# macOS has no timeout(1), a background+poll+kill wrapper in bash 3.2 cannot
# reliably kill a handler's descendants without a process group, and
# `pre-commit`/`pre-push` legitimately run for minutes, so any bound short enough
# to help would break them. The one measured stall (round-2 review) had a cause,
# not a symptom -- a guard running out of precondition -- and is fixed at the
# cause, in the resolver below. Filed in .ai/BACKLOG.md so the gap is tracked
# rather than implied away.
#
# bash 3.2 / macOS safe: no associative arrays, no mapfile, no ${VAR,,}.
# =============================================================================
set -u

# Resolve our own directory with PARAMETER EXPANSION FIRST, then canonicalise
# only if that succeeds. `dirname` is an external command: with a broken PATH the
# `$(cd "$(dirname ...)")` form silently degrades to `cd ""`, which bash treats as
# a no-op success, and SCRIPT_DIR becomes the CWD -- so lib.sh is "missing" for
# the wrong reason. Measured: `PATH=/nonexistent bash dispatch.sh PreToolUse`
# still exits 2 either way (fail-closed holds), but it should fail closed for an
# honest reason, and with the codec available it fails closed on the HANDLERS.
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
SCRIPT_DIR="$(cd "$SCRIPT_DIR" 2>/dev/null && pwd 2>/dev/null)" || SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="."
HOOK_NAME="dispatch"
LOG_FILE="$SCRIPT_DIR/hooks.log"

EVENT="${1:-}"

# --- is this a blocking event? ------------------------------------------------
# Only events where Claude Code honours exit 2 may block. Emitting 2 on Stop or
# SessionStart would be noise, not enforcement. Computed FIRST, before anything
# that can fail, so the panic trap below always knows which way to fail.
#
# The `*)` arm is NOT "anything else is advisory" -- that reading is what let a
# misregistered dispatcher fail OPEN. An event name this dispatcher does not
# KNOW is a wiring bug, and a wiring bug on a guarded event is indistinguishable
# from a removed guard, so an unknown name fails closed: EVENT_BLOCKING=1,
# EVENT_KNOWN=0, and the branch below renders it as exit 2.
# The seven non-blocking names plus PreToolUse are exactly the event keys of
# dispatch-registry.json, and test_the_known_event_list_matches_the_registry
# fails if the two ever drift -- so adding an event to the registry cannot leave
# it silently "unknown", and this list cannot rot into a block-everything arm.
case "$EVENT" in
    PreToolUse) EVENT_BLOCKING=1; EVENT_KNOWN=1 ;;
    PostToolUse|PostToolUseFailure|PreCompact|SessionStart|Stop|SubagentStop|UserPromptSubmit)
                EVENT_BLOCKING=0; EVENT_KNOWN=1 ;;
    *)          EVENT_BLOCKING=1; EVENT_KNOWN=0 ;;
esac

# --- the panic trap: an abort is not an allow ---------------------------------
# This dispatcher indicts every other hook for having no trap; it does not get to
# skip its own. Any path that leaves this script WITHOUT reaching the render
# boundary below -- an unset variable under `set -u`, a signal, a `set -e` abort
# inside a sourced helper, an interpreter that died -- lands here and blocks on a
# blocking event. Re-measured baseline this fixes, at 5f3e322:
#     echo '' | env -i PATH=/nonexistent /bin/bash ops-enforcement.sh; echo $?  ->  0
# `CK_RENDERED` is set to 1 immediately before every deliberate exit, so the trap
# can tell "decided, then exited" from "died on the way there". EXIT (not ERR) is
# the trigger on purpose: an ERR trap would also fire on a handler that merely
# exited non-zero, which is a normal, expected outcome here, not a panic.
CK_RENDERED=0
# shellcheck disable=SC2329,SC2317  # invoked indirectly, by the traps below.
# SC2317 ("command appears to be unreachable") is the same claim about the BODY,
# and it is wrong for the same reason. Both are needed: ShellCheck 0.11 (local)
# emits neither, while the version CI installs from apt emits both, so omitting
# SC2317 reddened three CI jobs against a silent local run.
ck_dispatch_panic() {
    local rc=$?
    [ "$CK_RENDERED" -eq 1 ] && exit "$rc"
    printf 'BLOCKED: dispatch.sh aborted before deciding (rc=%s, event=%s); failing closed.\n' \
        "$rc" "${EVENT:-unknown}" >&2
    CK_RENDERED=1
    [ "${EVENT_BLOCKING:-1}" -eq 1 ] && exit 2
    exit 0
}
trap ck_dispatch_panic EXIT
trap 'ck_dispatch_panic' INT TERM

# --- a dispatcher that does not know its own event fails closed ---------------
# This used to `exit 1` on a missing event name. 1 is not a decision Claude Code
# has: it honours 2 as a block and treats every other non-zero code as
# NON-BLOCKING, so a misregistration -- `dispatch.sh` wired with no argument, a
# typo, or the wrong case -- failed OPEN on PreToolUse while looking like an
# error. CLAUDE.md hard rule 2 permits only 0 or 2 at the hook boundary, and
# this was the one path in this file that emitted anything else (found by
# round-4 review's escape probes: 20 of 21 returned 0 or 2, this one returned
# 1). Unreachable through the shipped wiring is not an argument -- that is the
# same "nothing can reach it today" reasoning that produced the round-4
# Critical. Case-sensitivity is deliberate: `pretooluse` is not `PreToolUse`,
# and guessing which one the operator meant is how a guard goes missing.
if [ "$EVENT_KNOWN" -eq 0 ]; then
    printf 'BLOCKED: dispatch.sh cannot dispatch event %s; a dispatcher that does not know its own event cannot prove any guard ran, so it fails closed.\n' \
        "${EVENT:-<missing>}" >&2
    CK_RENDERED=1
    exit 2
fi

# --- lib.sh is REQUIRED, not optional -----------------------------------------
# Every ck_* helper (the codec, the clamp, the event emitter) lives there. If it
# is missing, `ck_decision_from_exit` is command-not-found, the merge silently
# degrades to ALLOW, and the dispatcher becomes a fail-open no-op wearing a
# guard's name. Sourcing it conditionally -- which this file did in the reviewed
# draft -- is exactly the defect this phase exists to remove.
if [ ! -r "$SCRIPT_DIR/lib.sh" ]; then
    printf 'BLOCKED: dispatch.sh cannot read %s; the decision codec is unavailable.\n' \
        "$SCRIPT_DIR/lib.sh" >&2
    CK_RENDERED=1
    [ "$EVENT_BLOCKING" -eq 1 ] && exit 2
    exit 0
fi
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib.sh"

ROOT=$(resolve_root)
REGISTRY="$SCRIPT_DIR/dispatch-registry.json"
PAYLOAD=$(cat)
SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDEKIT_SESSION_ID:-local}}"

# --- fail closed when the registry is unreadable ------------------------------
# We cannot know which guards should have run, so on a blocking event we block.
if [ ! -r "$REGISTRY" ]; then
    hlog "ERROR" "registry unreadable at $REGISTRY (event=$EVENT)"
    if [ "$EVENT_BLOCKING" -eq 1 ]; then
        printf 'BLOCKED: hook registry unreadable (%s); refusing an unguarded operation.\n' \
            "$REGISTRY" >&2
        CK_RENDERED=1
        exit 2
    fi
    CK_RENDERED=1
    exit 0
fi

TOOL_NAME=$(extract_json_field "$PAYLOAD" tool_name) || TOOL_NAME=""
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(extract_json_field "$PAYLOAD" name) 2>/dev/null

# --- resolve the handler list -------------------------------------------------
# One tab-separated line per applicable handler: id, file, runner, tier.
# --- RESOLVER RATIONALE (the code is in dispatch_resolve.py) -----------------
# The resolver body lives in `.claude/hooks/dispatch_resolve.py`, invoked below.
# Its long-form rationale stays HERE, beside the invocation, and the resolver's
# own comments point back at it -- one copy, at the call site a reader reaches
# first. An earlier revision kept this text out of a `<<'PY'` heredoc because
# `scripts/check-silent-failure.py` caps its heredoc skip at MAX_JOIN_LINES=80
# and abandoned the scan of this file. The resolver heredoc is gone (the `done <<EOF`
# further down is a different one), so that constraint is gone with it and only the
# placement it produced remains.
#
# --- REGISTRY INVARIANT: a precondition only on an advisory row ---------------
# The NOT-APPLICABLE skip rule below is safe only because a command_matcher row
# cannot block. A row with tier != "advisory" AND a command_matcher would be
# skipped on an unreadable payload while being ABLE to reach exit 2 -- i.e.
# malformed input silently removes a guard that can block. That is the exact
# fail-open class this dispatcher exists to kill, and at revision 3 NOTHING
# prevented it (no schema, no validator, no gate, no test: round-3 review added
# a command_matcher to the shipped blocking `commit-quality` row and the whole
# suite plus all eight gates stayed green). So it is checked here.
#
# EVERY event is scanned, not only the one being dispatched: an illegal row must
# not be able to hide on an event that happens not to be firing.
#
# WHY EXIT 3. It is this resolver's existing "the registry cannot be trusted"
# code -- the same code used for a parse failure above and for a whitespace arg
# below -- so the codec gains no new vocabulary. 3 never reaches Claude Code:
# any non-zero rc here lands in dispatch.sh's registry-resolution branch, which
# prints BLOCKED and exits 2 on a blocking event and 0 elsewhere. The hook
# boundary still only ever emits 0 or 2 (CLAUDE.md hard rule 2). The message
# goes to hooks.log (the resolver's stderr is appended there); the user-facing
# stderr line is the dispatcher's own BLOCKED line.
#
# THE TOOL MATCHER DOES NOT FILTER AN UNREADABLE PAYLOAD. Caught by executing
# test_command_matcher_asymmetry_on_an_unreadable_payload (revision 2 shipped
# it under a name that asserted the opposite): with a
# malformed payload the tool name resolved to "", so every matcher-scoped
# guard -- ops-enforcement, command-guard, config-protection -- was filtered
# OUT and the dispatch returned 0. That is the same fail-open class this
# phase exists to remove, reintroduced one layer up. When we cannot read the
# payload we cannot prove a guard is irrelevant, so every guard runs and
# decides for itself; ops-enforcement.sh already exits 2 on unparseable
# input, so the block is preserved end to end. The command_matcher below is
# the ONE deliberate exception, for the reason spelled out there.
#
# A command_matcher is a PRECONDITION, not a convenience filter. With an
# unreadable payload there is no command text, so the precondition cannot be
# evaluated and the handler is NOT APPLICABLE -- skipped, not "run anyway".
# This asymmetry with the tool matcher above is deliberate and is the C1 fix
# from round-2 review, which EXECUTED the shipped registry:
#     $ echo 'not json' | ECC_HOOK_PROFILE=standard bash dispatch.sh PreToolUse
#     still running after 25s;  ps -> .claude/hooks/pre-push.sh
# pre-push.sh:138 runs the FULL TEST SUITE. At f5eb927 that was impossible:
# settings.json extracts CMD and greps `^\s*git\s+push`, so the hook never
# started on a malformed payload. Running every guard "to be safe" INVERTED
# that protection twice over -- an unbounded stall on any malformed
# PreToolUse payload, and a guard whose contract is "the user ran git push"
# executing on an arbitrary tool call. Fail-closed is unaffected: both
# command_matcher handlers are advisory (clamped to ADVISE), they cannot
# block, so skipping them cannot turn a DENY into an ALLOW. Bound by
# test_a_command_matcher_handler_is_not_applicable_on_an_unreadable_payload
# plus its mutant, and by the real-registry termination test.
# ----------------------------------------------------------------------------
# The payload travels on STDIN, not the environment. Through the environment it
# hit ARG_MAX (1048576): execve returned E2BIG, the resolver never started, and a
# blocking event exited 2 -- so writing a >1 MB file was refused. The resolver body
# moved to dispatch_resolve.py precisely so stdin is free; a pipe has neither an
# ARG_MAX nor a file-size limit and writes nothing to disk. Spilling to a temp file
# was the other candidate and is WRONG: it adds an RLIMIT_FSIZE kill surface, so the
# boundary emits rc -25 (SIGXFSZ) instead of a fail-closed rc 2, which breaks hard
# rule 2 and plausibly reads as NON-blocking.
# 2>>"$LOG_FILE" on the WRITER: draining stdin first only helps when the resolver
# actually starts. A missing resolver, a syntax error, or a resolver that is a
# directory all die before reading, which SIGPIPEs this printf and leaked
# `printf: write error: Broken pipe` onto user-visible stderr, directly above the
# BLOCKED line, on payloads past the pipe buffer. The verdict was never affected;
# the noise displaced the actual reason. It goes to the log, not /dev/null, so a
# real write failure stays recoverable.
HANDLERS=$(printf '%s' "$PAYLOAD" 2>>"$LOG_FILE" \
    | EVENT="$EVENT" TOOL_NAME="${TOOL_NAME:-}" \
      python3 "$SCRIPT_DIR/dispatch_resolve.py" "$REGISTRY" 2>>"$LOG_FILE")
REG_RC=$?
if [ "$REG_RC" -ne 0 ]; then
    hlog "ERROR" "registry resolution failed rc=$REG_RC (event=$EVENT)"
    if [ "$EVENT_BLOCKING" -eq 1 ]; then
        printf 'BLOCKED: could not resolve hook handlers for %s (resolver rc=%s, payload %s chars); failing closed.\n' \
            "$EVENT" "$REG_RC" "${#PAYLOAD}" >&2
        printf '  The resolver is .claude/hooks/dispatch_resolve.py; see hooks.log for its stderr.\n' >&2
        CK_RENDERED=1
        exit 2
    fi
    CK_RENDERED=1
    exit 0
fi

# --- run each handler, decode, clamp, merge -----------------------------------
MERGED=0            # ALLOW
BLOCK_REASONS=""    # stderr from handlers that reached DENY/ERROR
ADVISORY_NOTES=""   # stdout from advisory handlers — never affects MERGED

while IFS="$(printf '\t')" read -r H_ID H_FILE H_RUNNER H_TIER H_ARGS; do
    [ -z "${H_ID:-}" ] && continue
    H_PATH="$SCRIPT_DIR/$H_FILE"
    if [ ! -f "$H_PATH" ]; then
        # A registered handler that is missing is an unknown verdict, not an allow.
        hlog "ERROR" "handler $H_ID missing at $H_PATH"
        RC=127
    else
        H_ERR="$(ck_mktemp)"
        H_OUT="$(ck_mktemp)"
        START=$(ck_now_ms)
        # shellcheck disable=SC2086  # H_ARGS is registry-controlled argv, split on purpose;
        # the resolver rejects any arg containing whitespace, so this cannot re-split a value.
        # A handler that decides without reading its input exits while this printf
        # is still writing, which SIGPIPEs the writer and leaked
        # `printf: write error: Broken pipe` onto HOOK stderr on payloads >=100 KB.
        # The verdict was never affected, but on a blocking event that text is shown
        # to the user as if it were the reason. Its stderr goes to the log instead of
        # /dev/null so a real write failure is still recoverable from hooks.log.
        printf '%s' "$PAYLOAD" 2>>"$LOG_FILE" | "$H_RUNNER" "$H_PATH" ${H_ARGS:-} \
            >"$H_OUT" 2>"$H_ERR"
        RC=$?
        END=$(ck_now_ms)
    fi

    DECISION=$(ck_decision_from_exit "$RC")
    DECISION=$(ck_clamp_advisory "$DECISION" "$H_TIER")
    if [ "$DECISION" -gt "$MERGED" ]; then MERGED="$DECISION"; fi

    if [ "${H_ERR:-}" ] && [ -s "${H_ERR:-/dev/null}" ]; then
        if [ "$DECISION" -ge 2 ]; then
            BLOCK_REASONS="${BLOCK_REASONS}[$H_ID] $(cat "$H_ERR")
"
        else
            ADVISORY_NOTES="${ADVISORY_NOTES}[$H_ID] $(cat "$H_ERR")
"
        fi
    fi
    if [ "${H_OUT:-}" ] && [ -s "${H_OUT:-/dev/null}" ]; then
        ADVISORY_NOTES="${ADVISORY_NOTES}[$H_ID] $(cat "$H_OUT")
"
    fi

    ck_emit_hook_decision "$EVENT" "$H_ID" "$H_TIER" "$RC" "$DECISION" "$MERGED" \
        "${TOOL_NAME:-}" "$(( ${END:-0} - ${START:-0} ))" "${H_ERR:-}"
    rm -f "${H_ERR:-}" "${H_OUT:-}" 2>/dev/null
    H_ERR=""; H_OUT=""
done <<EOF
$HANDLERS
EOF

# --- render the merged decision at the boundary -------------------------------
# ADVISORY_NOTES go to STDOUT and are emitted regardless — but they are printed
# AFTER the merge is fixed and are never consulted by it. That is the whole
# "advisory cannot override a block" contract, in control flow.
if [ -n "$ADVISORY_NOTES" ]; then
    printf '%s' "$ADVISORY_NOTES"
fi

# `ck_decision_exit` IS the boundary renderer -- called, not decorative. Inlining
# `[ "$MERGED" -ge 2 ]` here (the reviewed draft did) left the function unbound
# dead code that no mutant could reach, so the shell/Python parity test on
# to_exit_code was proving nothing about the code that actually runs.
MERGED_EXIT=$(ck_decision_exit "$MERGED")
if [ "$MERGED_EXIT" -eq 2 ] && [ "$EVENT_BLOCKING" -eq 1 ]; then
    hlog "BLOCK" "event=$EVENT tool=${TOOL_NAME:-} merged=$(ck_decision_label "$MERGED")"
    if [ -n "$BLOCK_REASONS" ]; then
        printf '%s' "$BLOCK_REASONS" >&2
    else
        printf 'BLOCKED: a %s handler failed and its verdict is unknown.\n' "$EVENT" >&2
    fi
    CK_RENDERED=1
    exit 2
fi

if [ "$MERGED_EXIT" -eq 2 ]; then
    # Non-blocking event: surface the failure, do not pretend it blocked.
    hlog "WARN" "event=$EVENT merged=$(ck_decision_label "$MERGED") (event is not blocking)"
    [ -n "$BLOCK_REASONS" ] && printf '%s' "$BLOCK_REASONS" >&2
fi
CK_RENDERED=1
exit 0
