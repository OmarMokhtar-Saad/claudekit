#!/bin/bash
# =============================================================================
# Session Start Hook (SessionStart)
# Detects package manager, loads previous session context, prints key project info.
# =============================================================================
# ECC_HOOK_PROFILE: runs in all profiles

LOG=".claude/hooks/hooks.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [session-start] [$1] $2" >> "$LOG" 2>/dev/null; }

log "INFO" "Session started | pwd=$(pwd) | user=$(whoami)"

# ---------------------------------------------------------------------------
# 1. Detect package manager
# ---------------------------------------------------------------------------
PM="unknown"
PM_INSTALL=""
PM_RUN=""

if [ -f "bun.lockb" ] || [ -f "bunfig.toml" ]; then
    PM="bun"
    PM_INSTALL="bun install"
    PM_RUN="bun run"
elif [ -f "pnpm-lock.yaml" ]; then
    PM="pnpm"
    PM_INSTALL="pnpm install"
    PM_RUN="pnpm run"
elif [ -f "yarn.lock" ]; then
    PM="yarn"
    PM_INSTALL="yarn install"
    PM_RUN="yarn"
elif [ -f "package-lock.json" ]; then
    PM="npm"
    PM_INSTALL="npm install"
    PM_RUN="npm run"
elif [ -f "Cargo.toml" ]; then
    PM="cargo"
    PM_INSTALL="cargo build"
    PM_RUN="cargo run"
elif [ -f "go.mod" ]; then
    PM="go"
    PM_INSTALL="go mod tidy"
    PM_RUN="go run"
elif [ -f "pyproject.toml" ] || [ -f "requirements.txt" ]; then
    PM="python"
    PM_INSTALL="pip install -e ."
    PM_RUN="python"
elif [ -f "Gemfile" ]; then
    PM="bundler"
    PM_INSTALL="bundle install"
    PM_RUN="bundle exec"
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
echo "  Project: $(basename $(pwd))"
[ "$PM" != "unknown" ] && echo "  Package manager: $PM"
[ -n "$BUILD_CMD" ] && echo "  Build: $BUILD_CMD"
[ -n "$TEST_CMD"  ] && echo "  Test:  $TEST_CMD"
[ -n "$LINT_CMD"  ] && echo "  Lint:  $LINT_CMD"

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
        echo ""
        echo "Previous session context found (${CONTEXT_AGE_HOURS}h ago):"
        # Print first 20 lines of context
        head -20 "$CONTEXT_FILE" | sed 's/^/  /'
        echo ""
        echo "  Run /resume-session to restore full context."
    else
        log "INFO" "Session context found but is ${CONTEXT_AGE_HOURS}h old — skipping auto-load"
    fi
fi

echo ""
log "INFO" "Session start complete | PM=$PM"
exit 0
