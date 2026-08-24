#!/bin/bash
# =============================================================================
# Session Start Hook (SessionStart)
# Detects package manager, loads previous session context, prints key project info.
# =============================================================================
# ECC_HOOK_PROFILE: runs in all profiles

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
# The `[ -f ... ] &&` guard above promises graceful degradation, and delegating
# `log()` to `hlog` removes it: with `lib.sh` absent the hook printed
# "hlog: command not found" to stderr on every call, where the old body was
# `>> "$LOG" 2>/dev/null`. `lib.sh` ships beside the hooks so a fresh install is
# fine; the exposure is a surgical fleet sync that copies one hook and not the
# library. A no-op keeps the promise the guard makes.
command -v hlog >/dev/null 2>&1 || hlog() { :; }
HOOK_NAME="session-start"
# `$SCRIPT_DIR`, not a cwd-relative path: this hook wrote to `.claude/hooks/hooks.log`
# relative to the CURRENT DIRECTORY, so its log landed elsewhere (or nowhere) whenever
# the cwd was not the repo root. Three hooks shared that bug and a third `LOG_FILE=`
# form (finding F107); the same class already misplaces `command-log-audit.sh`'s audit
# trail (F55). `hlog` also uses `$*`, so an argument past the second no longer vanishes.
LOG_FILE="$SCRIPT_DIR/hooks.log"
log() { hlog "$@"; }

log "INFO" "Session started | pwd=$(pwd) | user=$(whoami)"

# ---------------------------------------------------------------------------
# 1. Detect package manager
# ---------------------------------------------------------------------------
# Only the NAME is used -- the startup summary prints `$PM` and nothing else.
# `PM_INSTALL`/`PM_RUN` were assigned eight times here and read nowhere (SC2034);
# a reader reasonably assumed the summary showed them.
PM="unknown"

if [ -f "bun.lockb" ] || [ -f "bunfig.toml" ]; then
    PM="bun"
elif [ -f "pnpm-lock.yaml" ]; then
    PM="pnpm"
elif [ -f "yarn.lock" ]; then
    PM="yarn"
elif [ -f "package-lock.json" ]; then
    PM="npm"
elif [ -f "Cargo.toml" ]; then
    PM="cargo"
elif [ -f "go.mod" ]; then
    PM="go"
elif [ -f "pyproject.toml" ] || [ -f "requirements.txt" ]; then
    PM="python"
elif [ -f "Gemfile" ]; then
    PM="bundler"
fi

if [ "$PM" != "unknown" ]; then
    log "INFO" "Detected package manager: $PM"
fi

# ---------------------------------------------------------------------------
# 2. Load project config for key commands
# ---------------------------------------------------------------------------
CONFIG=".claude/hooks/config.json"
BUILD_CMD=""
TEST_CMD=""
LINT_CMD=""

if [ -f "$CONFIG" ] && command -v python3 &>/dev/null; then
    BUILD_CMD=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get('build_cmd',''))" "$CONFIG" 2>/dev/null)
    TEST_CMD=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get('test_cmd',''))" "$CONFIG" 2>/dev/null)
    LINT_CMD=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get('lint_cmd',''))" "$CONFIG" 2>/dev/null)
fi

# ---------------------------------------------------------------------------
# 3. Print startup summary
# ---------------------------------------------------------------------------
echo ""
echo "ClaudeKit session started | $(date '+%Y-%m-%d %H:%M')"
echo "  Project: $(basename "$(pwd)")"
[ "$PM" != "unknown" ] && echo "  Package manager: $PM"
[ -n "$BUILD_CMD" ] && echo "  Build: $BUILD_CMD"
[ -n "$TEST_CMD"  ] && echo "  Test:  $TEST_CMD"
[ -n "$LINT_CMD"  ] && echo "  Lint:  $LINT_CMD"

# ---------------------------------------------------------------------------
# 3.4 Concurrent-session detection (warning only — never blocks)
# One lock file per live session pid under .claude/locks/; dead pids pruned.
# ---------------------------------------------------------------------------
LOCKS_DIR=".claude/locks"
mkdir -p "$LOCKS_DIR" 2>/dev/null
OTHER_SESSIONS=0
for lock in "$LOCKS_DIR"/session-*; do
    [ -e "$lock" ] || continue
    lock_pid="${lock##*session-}"
    case "$lock_pid" in
        ''|*[!0-9]*) rm -f "$lock" 2>/dev/null; continue ;;
    esac
    if [ "$lock_pid" = "$$" ] || [ "$lock_pid" = "${PPID:-0}" ]; then
        continue
    fi
    if kill -0 "$lock_pid" 2>/dev/null; then
        OTHER_SESSIONS=$((OTHER_SESSIONS + 1))
    else
        rm -f "$lock" 2>/dev/null
    fi
done
date '+%Y-%m-%d %H:%M:%S' > "$LOCKS_DIR/session-${PPID:-$$}" 2>/dev/null
if [ "$OTHER_SESSIONS" -gt 0 ]; then
    echo "  WARNING: $OTHER_SESSIONS other session(s) appear active in this project."
    echo "           Coordinate file ownership (multi-agent-coordination skill);"
    echo "           uncommitted work can be lost to concurrent git operations."
    log "WARN" "Concurrent sessions detected: $OTHER_SESSIONS other live lock(s)"
fi

# ---------------------------------------------------------------------------
# 3.5 Project graph status (no new hook — rides this one; never blocks)
# ---------------------------------------------------------------------------
GRAPH_SCRIPT=".claude/operations/scripts/project-graph.py"
GRAPH_FILE=".claude/project-graph.json"
if command -v python3 &>/dev/null && [ -f "$GRAPH_SCRIPT" ]; then
    if [ -f "$GRAPH_FILE" ]; then
        if python3 "$GRAPH_SCRIPT" stale >/dev/null 2>&1; then
            echo "  Graph: fresh ($GRAPH_FILE) — query it before grepping"
        else
            echo "  Graph: STALE — refresh changed nodes via project-graph.py build --merge"
        fi
    else
        echo "  Graph: none — agents build it incrementally as they explore"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Load previous session context if available
# ---------------------------------------------------------------------------
CONTEXT_FILE=".claude/session-context.md"
if [ -f "$CONTEXT_FILE" ]; then
    CONTEXT_AGE_HOURS=0
    if command -v python3 &>/dev/null; then
        CONTEXT_AGE_HOURS=$(python3 -c "
import os, time, sys
try:
    age = (time.time() - os.path.getmtime(sys.argv[1])) / 3600
    print(int(age))
except:
    print(0)
" "$CONTEXT_FILE" 2>/dev/null)
    fi

    if [ "$CONTEXT_AGE_HOURS" -lt 48 ]; then
        # SCAN BEFORE PRINTING. This excerpt goes straight into the transcript at the
        # moment of least suspicion, and `sed 's/^/  /'` indents text -- it does not
        # neutralise it. `injection-scan-gate.sh` does not cover this path: it scans
        # `extract_json_field "$PAYLOAD" prompt`, i.e. the UserPromptSubmit field and
        # nothing else. So the mitigation existed and was simply never applied here,
        # against a file any earlier agent run -- or anyone sharing the repo -- can write.
        # CLAUDE.md's rule is that retrieved text is evidence, never an instruction
        # channel; this path was the mechanical exception.
        #
        # Not gated to `strict`: session-start.sh runs in every profile, and a check that
        # only protects the profile nobody sets is decoration.
        _ctx_excerpt=$(head -20 "$CONTEXT_FILE")
        _ctx_scanner=""
        for _cand in "$SCRIPT_DIR/prompt-injection-scanner.sh" \
                     ".claude/hooks/prompt-injection-scanner.sh"; do
            [ -f "$_cand" ] && { _ctx_scanner="$_cand"; break; }
        done

        echo ""
        echo "Previous session context found (${CONTEXT_AGE_HOURS}h ago):"
        if [ -z "$_ctx_scanner" ]; then
            # Fail toward silence. Printing an excerpt is a convenience; printing an
            # UNSCANNED one is the finding. The cost of withholding is one command.
            echo "  (not shown: the injection scanner is unavailable, so the excerpt was"
            echo "   not checked. Run /resume-session to load it deliberately.)"
            log "WARN" "session context not shown: scanner missing at $SCRIPT_DIR"
        elif printf '%s\n' "$_ctx_excerpt" | bash "$_ctx_scanner" >/dev/null 2>&1; then
            printf '%s\n' "$_ctx_excerpt" | sed 's/^/  /'
        else
            echo "  (not shown: the excerpt matched a prompt-injection pattern. The file is"
            echo "   unchanged on disk. Inspect $CONTEXT_FILE, then /resume-session if it is"
            echo "   legitimate.)"
            log "WARN" "session context withheld: injection pattern in $CONTEXT_FILE"
        fi
        unset _ctx_excerpt _ctx_scanner _cand
        echo ""
        echo "  Run /resume-session to restore full context."
    else
        log "INFO" "Session context found but is ${CONTEXT_AGE_HOURS}h old — skipping auto-load"
    fi
fi

echo ""
log "INFO" "Session start complete | PM=$PM"
exit 0
