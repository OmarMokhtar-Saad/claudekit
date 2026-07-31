#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -e

# =============================================================================
# Post-Implement Hook
# Runs build, test suite, and coverage report after implementation completes.
# All commands are read from config.json project section.
# =============================================================================

HOOK_NAME="post-implement"
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
# Step 1: Run build/compile command
# ---------------------------------------------------------------------------
run_build() {
    local build_cmd
    build_cmd=$(get_project_config "build_cmd" || echo "")

    if [ -z "$build_cmd" ]; then
        log "INFO" "No build_cmd configured, skipping build"
        echo "[post-implement] No build command configured. Skipping build step."
        return 0
    fi

    log "INFO" "Running build: $build_cmd"
    echo "[post-implement] Running build: $build_cmd"

    local output
    screen_cmd build_cmd "$build_cmd" || return 1

    if output=$(bash -c "$build_cmd" 2>&1); then
        log "INFO" "Build succeeded"
        echo "[post-implement] Build: PASSED"
        return 0
    else
        log "ERROR" "Build failed: $output"
        echo "[post-implement] Build: FAILED"
        echo "$output" | tail -20
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Run test suite
# ---------------------------------------------------------------------------
run_tests() {
    local test_cmd
    test_cmd=$(get_project_config "test_cmd" || echo "")

    if [ -z "$test_cmd" ]; then
        log "INFO" "No test_cmd configured, skipping tests"
        echo "[post-implement] No test command configured. Skipping test step."
        return 0
    fi

    log "INFO" "Running tests: $test_cmd"
    echo "[post-implement] Running tests: $test_cmd"

    local output
    screen_cmd test_cmd "$test_cmd" || return 1

    if output=$(bash -c "$test_cmd" 2>&1); then
        log "INFO" "Tests passed"
        echo "[post-implement] Tests: PASSED"
        echo "$output" | tail -5
        return 0
    else
        log "WARN" "Tests failed: $output"
        echo "[post-implement] Tests: FAILED"
        echo "$output" | tail -20
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 3: Generate coverage report
# ---------------------------------------------------------------------------
run_coverage() {
    local coverage_cmd
    coverage_cmd=$(get_project_config "coverage_cmd" || echo "")

    if [ -z "$coverage_cmd" ]; then
        log "INFO" "No coverage_cmd configured, skipping coverage"
        echo "[post-implement] No coverage command configured. Skipping coverage step."
        return 0
    fi

    log "INFO" "Running coverage: $coverage_cmd"
    echo "[post-implement] Running coverage: $coverage_cmd"

    local output
    screen_cmd coverage_cmd "$coverage_cmd" || return 1

    if output=$(bash -c "$coverage_cmd" 2>&1); then
        log "INFO" "Coverage report generated"
        echo "[post-implement] Coverage: GENERATED"
        echo "$output" | tail -10
        return 0
    else
        log "WARN" "Coverage report failed: $output"
        echo "[post-implement] Coverage: FAILED"
        echo "$output" | tail -10
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "INFO" "Starting post-implement hook"
    echo ""
    echo "POST-IMPLEMENT VERIFICATION"
    echo "==========================="
    echo ""

    local build_ok=0
    local tests_ok=0
    local coverage_ok=0

    # Run build
    if run_build; then
        build_ok=1
    fi
    echo ""

    # Run tests
    if run_tests; then
        tests_ok=1
    fi
    echo ""

    # Run coverage
    if run_coverage; then
        coverage_ok=1
    fi
    echo ""

    # Summary
    echo "SUMMARY"
    echo "-------"
    [ $build_ok -eq 1 ] && echo "  Build:    PASS" || echo "  Build:    FAIL"
    [ $tests_ok -eq 1 ] && echo "  Tests:    PASS" || echo "  Tests:    FAIL"
    [ $coverage_ok -eq 1 ] && echo "  Coverage: PASS" || echo "  Coverage: FAIL"
    echo ""

    if [ $build_ok -eq 1 ] && [ $tests_ok -eq 1 ]; then
        log "INFO" "Post-implement hook passed"
        echo "Result: READY FOR VERIFICATION"
        return 0
    else
        log "WARN" "Post-implement hook found issues"
        echo "Result: ISSUES FOUND - Review output above"
        return 1
    fi
}

main "$@"
