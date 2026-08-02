#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -e

# =============================================================================
# Pre-Push Hook
# Full validation before pushing to remote:
#   - Warns on push to main/master
#   - Runs full test suite
#   - Runs lint/quality checks
#   - Checks for uncommitted changes
# =============================================================================

HOOK_NAME="pre-push"
LOG_FILE="$SCRIPT_DIR/hooks.log"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
    if [ "$level" = "ERROR" ] || [ "$level" = "WARN" ]; then
        echo "[$HOOK_NAME] $*" >&2
    fi
}

get_project_config() {
    local key="$1"
    local config="$SCRIPT_DIR/config.json"
    # Refuse a symlinked config: project.*_cmd values are executed as shell
    # commands, so a swapped-in symlink would be arbitrary code execution.
    if [ -L "$config" ]; then
        log "ERROR" "refusing to read config.json: it is a symlink"
        return 1
    fi
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json, sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get(sys.argv[2],''))" "$config" "$key" 2>/dev/null
    fi
}

# Screen a configured command through the same CommandValidator that guards the
# Bash tool (parity with pre-commit.sh — a config.json command is arbitrary code
# execution if unscreened). Returns 0 = cleared, 1 = flagged, 127 = no validator.
validate_configured_cmd() {
    local cmd="$1" root
    root="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)" || root="$PWD"
    if command -v claudekit >/dev/null 2>&1; then
        claudekit check-command "$cmd" 2>&1
        return $?
    elif [ -d "$root/src/claudekit" ]; then
        PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -m claudekit.security check-command "$cmd" 2>&1
        return $?
    elif python3 -c 'import claudekit.security' 2>/dev/null; then
        # pip-installed package without the console script on PATH
        python3 -m claudekit.security check-command "$cmd" 2>&1
        return $?
    fi
    return 127
}

screen_cmd() {
    local name="$1" cmd="$2" vout vrc
    vout="$(validate_configured_cmd "$cmd")"; vrc=$?
    if [ "$vrc" -eq 127 ]; then
        log "WARN" "CommandValidator unavailable — running $name unscreened"
        return 0
    elif [ "$vrc" -ne 0 ]; then
        log "ERROR" "Refusing to run $name: ${vout:-policy violation}"
        echo "ERROR: config.json project.$name was rejected by CommandValidator: ${vout:-policy violation}"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Step 1: Check if pushing to protected branch
# ---------------------------------------------------------------------------
check_branch() {
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

    log "INFO" "Current branch: $current_branch"

    if [ "$current_branch" = "main" ] || [ "$current_branch" = "master" ]; then
        log "WARN" "Pushing directly to $current_branch"
        echo ""
        echo "WARNING: You are pushing directly to '$current_branch'."
        echo "Consider using a feature branch and a pull request instead."
        echo ""
        # This is a warning, not a blocker - teams can decide their own policy
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Step 2: Check for uncommitted changes
# ---------------------------------------------------------------------------
check_uncommitted() {
    log "INFO" "Checking for uncommitted changes..."

    local uncommitted
    uncommitted=$(git status --porcelain 2>/dev/null)

    if [ -n "$uncommitted" ]; then
        local count
        count=$(echo "$uncommitted" | wc -l | xargs)
        log "WARN" "Found $count uncommitted changes"
        echo "WARNING: You have $count uncommitted change(s):"
        echo "$uncommitted" | head -10
        if [ "$count" -gt 10 ]; then
            echo "  ... and $((count - 10)) more"
        fi
        echo ""
        echo "These changes will NOT be included in the push."
        echo ""
    else
        log "INFO" "Working tree is clean"
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Step 3: Run full test suite
# ---------------------------------------------------------------------------
run_tests() {
    local test_cmd
    test_cmd=$(get_project_config "test_cmd" || echo "")

    if [ -z "$test_cmd" ]; then
        log "INFO" "No test_cmd configured, skipping tests"
        echo "[pre-push] No test command configured. Skipping tests."
        return 0
    fi

    log "INFO" "Running tests: $test_cmd"
    echo "[pre-push] Running full test suite: $test_cmd"

    local output
    screen_cmd test_cmd "$test_cmd" || return 1

    if output=$(bash -c "$test_cmd" 2>&1); then
        log "INFO" "Tests passed"
        echo "[pre-push] Tests: PASSED"
        return 0
    else
        log "ERROR" "Tests failed"
        echo "[pre-push] Tests: FAILED"
        echo "$output" | tail -20
        echo ""
        echo "ERROR: Tests must pass before pushing."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 4: Run lint/quality checks
# ---------------------------------------------------------------------------
run_lint() {
    local lint_cmd
    lint_cmd=$(get_project_config "lint_cmd" || echo "")

    if [ -z "$lint_cmd" ]; then
        log "INFO" "No lint_cmd configured, skipping lint"
        echo "[pre-push] No lint command configured. Skipping lint."
        return 0
    fi

    log "INFO" "Running lint: $lint_cmd"
    echo "[pre-push] Running lint: $lint_cmd"

    local output
    screen_cmd lint_cmd "$lint_cmd" || return 1

    if output=$(bash -c "$lint_cmd" 2>&1); then
        log "INFO" "Lint passed"
        echo "[pre-push] Lint: PASSED"
        return 0
    else
        log "ERROR" "Lint failed"
        echo "[pre-push] Lint: FAILED"
        echo "$output" | tail -20
        echo ""
        echo "ERROR: Lint must pass before pushing."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 5: Run build
# ---------------------------------------------------------------------------
run_build() {
    local build_cmd
    build_cmd=$(get_project_config "build_cmd" || echo "")

    if [ -z "$build_cmd" ]; then
        log "INFO" "No build_cmd configured, skipping build"
        echo "[pre-push] No build command configured. Skipping build."
        return 0
    fi

    log "INFO" "Running build: $build_cmd"
    echo "[pre-push] Running build: $build_cmd"

    local output
    screen_cmd build_cmd "$build_cmd" || return 1

    if output=$(bash -c "$build_cmd" 2>&1); then
        log "INFO" "Build succeeded"
        echo "[pre-push] Build: PASSED"
        return 0
    else
        log "ERROR" "Build failed"
        echo "[pre-push] Build: FAILED"
        echo "$output" | tail -20
        echo ""
        echo "ERROR: Build must succeed before pushing."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "INFO" "Starting pre-push hook"
    echo ""
    echo "PRE-PUSH VALIDATION"
    echo "==================="
    echo ""

    local exit_code=0

    # Check branch (non-blocking warning)
    check_branch

    # Check uncommitted changes (non-blocking warning)
    check_uncommitted

    # Run tests (blocking)
    if ! run_tests; then
        exit_code=1
    fi
    echo ""

    # Run lint (blocking)
    if ! run_lint; then
        exit_code=1
    fi
    echo ""

    # Run build (blocking)
    if ! run_build; then
        exit_code=1
    fi
    echo ""

    # Summary
    echo "---"
    if [ $exit_code -eq 0 ]; then
        log "INFO" "Pre-push hook passed"
        echo "Pre-push validation: PASSED"
    else
        log "ERROR" "Pre-push hook failed"
        echo "Pre-push validation: FAILED"
        echo "Fix the issues above before pushing."
    fi

    return $exit_code
}

main "$@"
