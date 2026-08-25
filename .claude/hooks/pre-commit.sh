#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -e

# =============================================================================
# Pre-Commit Hook
# Validates operations configs and checks staged files for secrets.
# Optionally runs the project build command if source files changed.
# =============================================================================

HOOK_NAME="pre-commit"
LOG_FILE="$SCRIPT_DIR/hooks.log"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"

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
    # Refuse a symlinked config: `project.build_cmd` is executed as a shell
    # command below, so a swapped-in symlink would be arbitrary code execution
    # triggered by an ordinary `git commit`.
    if [ -L "$config" ]; then
        log "ERROR" "refusing to read config.json: it is a symlink"
        return 1
    fi
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json, sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get(sys.argv[2],''))" "$config" "$key" 2>/dev/null
    fi
}

# Screen a configured command through the same CommandValidator that guards the
# Bash tool, so `project.build_cmd` can't smuggle `rm -rf /` (or a curl-to-shell)
# into every commit. Returns 0 = cleared to run, 1 = flagged, 127 = no validator.
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

# ---------------------------------------------------------------------------
# Step 1: Validate ops.json files in .claude/plans/
# ---------------------------------------------------------------------------
validate_ops_configs() {
    log "INFO" "Validating operations configs..."
    local has_errors=0

    while IFS= read -r ops_file; do
        if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$ops_file" 2>/dev/null; then
            log "ERROR" "Invalid JSON: $ops_file"
            echo "ERROR: Invalid JSON in $ops_file"
            has_errors=1
            continue
        fi

        # Validate required fields (supports both legacy and modern formats)
        local valid
        valid=$(python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    if 'plan' not in data:
        print('missing plan field')
    elif 'operations' in data:
        if not isinstance(data['operations'], list):
            print('operations must be array')
        else:
            for i, op in enumerate(data['operations']):
                if 'type' not in op:
                    print(f'operation {i} missing type')
                    sys.exit(0)
                if 'path' not in op:
                    print(f'operation {i} missing path')
                    sys.exit(0)
            print('ok')
    elif 'files' in data:
        if not isinstance(data['files'], list):
            print('files must be array')
        else:
            for i, f in enumerate(data['files']):
                if 'path' not in f:
                    print(f'file {i} missing path')
                    sys.exit(0)
                if 'edits' not in f:
                    print(f'file {i} missing edits')
                    sys.exit(0)
            print('ok')
    else:
        print('missing operations or files field')
except Exception as e:
    print(f'parse error: {e}')
" "$ops_file" 2>/dev/null)

        if [ "$valid" != "ok" ]; then
            log "ERROR" "Validation failed for $ops_file: $valid"
            echo "ERROR: $ops_file - $valid"
            has_errors=1
        else
            log "INFO" "Valid: $ops_file"
        fi
    done < <(find .claude/plans/ "${OPS_FIND_EXPR[@]}" 2>/dev/null)

    return $has_errors
}

# ---------------------------------------------------------------------------
# Step 2: Check staged files for secrets
# ---------------------------------------------------------------------------
check_secrets() {
    log "INFO" "Checking staged files for secrets..."
    local has_secrets=0

    # Get list of staged files
    local staged_files
    staged_files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

    if [ -z "$staged_files" ]; then
        log "INFO" "No staged files to check"
        return 0
    fi

    # Patterns that indicate potential secrets.
    # Deliberately exclude bare `token\s*:` and `password\s*:` (TypeScript type annotations).
    # Require an actual value after the separator: a quote, digit, or env var reference.
    # Quote classes come from lib.sh (ERE_QUOTE_CLASS = ["'] , negation = [^"']).
    # The previous inline `["\x27]` was NOT decoded by grep -E, so single-quoted
    # secrets slipped through entirely.
    # Built WITHOUT a `'` inside a double-quoted ${:-} default: that form opens a
    # single-quote context, bash reports `bad substitution`, the two statements merge and
    # `nq` ends up EMPTY - which shipped `api_key\\s*[:=]\\s*["']{8}`, i.e. eight
    # consecutive QUOTES. All seven value-bearing patterns were dead (measured: 0 of 7
    # planted credentials detected) and `private_key` was left over-broad.
    # `if` rather than `[ -z ... ] && ...` because this file runs under `set -e`.
    # Correct standalone: pre-commit.sh does not source lib.sh, so these defaults are the
    # only values that ever apply here.
    local q="${ERE_QUOTE_CLASS:-}"
    if [ -z "$q" ]; then q='["'"'"']'; fi
    local nq="${ERE_NOT_QUOTE_CLASS:-}"
    if [ -z "$nq" ]; then nq='[^"'"'"']'; fi
    local patterns=(
        "api_key\\s*[:=]\\s*${q}${nq}{8}"
        "apikey\\s*[:=]\\s*${q}${nq}{8}"
        "api_secret\\s*[:=]\\s*${q}${nq}{8}"
        "password\\s*=\\s*${q}${nq}{4}"
        "passwd\\s*=\\s*${q}${nq}{4}"
        "secret_key\\s*[:=]\\s*${q}${nq}{8}"
        "access_token\\s*[:=]\\s*${q}${nq}{8}"
        "private_key\\s*[:=]\\s*${q}"
        # `[ ]` is an ERE matching exactly one space, so detection is byte-for-byte
        # identical - but this file's own text now reads PRIVATE[ ]KEY, which the
        # pattern does not match. Do NOT 'fix' self-matching by excluding this file
        # or a region of it: that creates a named hiding place for a real key.
        'BEGIN RSA PRIVATE[ ]KEY'
        'BEGIN OPENSSH PRIVATE[ ]KEY'
        'BEGIN EC PRIVATE[ ]KEY'
        'BEGIN DSA PRIVATE[ ]KEY'
        'BEGIN PGP PRIVATE[ ]KEY'
    )

    # The alternation, built once. Each element is already an ERE.
    local combined_pattern
    combined_pattern=$(printf '%s|' "${patterns[@]}")
    combined_pattern="${combined_pattern%|}"

    while IFS= read -r file; do
        # Skip binary files, lock files, and config templates
        if [[ "$file" =~ \.(lock|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|pdf)$ ]]; then
            continue
        fi
        if [[ "$file" =~ (config\.json|config\.template|\.example)$ ]]; then
            continue
        fi

        # ONE pass per file, not one per (file x pattern). This was a `git show | grep`
        # per pattern inside a per-file loop -- 2 subprocesses x N files x M patterns on
        # the commit path, where a single alternation does the same work. The matched
        # pattern is still reported, because "a secret is in this file somewhere" is not
        # an actionable message: `grep -oiE` names which alternative fired.
        local content
        content=$(git show ":$file" 2>/dev/null) || continue
        # Combined pass FIRST as a filter; only a file that matched pays for the
        # per-pattern identification. `grep -oiE` was the obvious way to name the match
        # and it is the wrong one: `-o` prints the MATCHED TEXT, which for
        # `api_key\s*[:=]\s*["'][^"']{8}` is the first eight characters of the secret --
        # into the hook log and the transcript. The whole point of this check is to keep
        # secrets out of places they should not be.
        if printf '%s\n' "$content" | grep -qiE "$combined_pattern" 2>/dev/null; then
            local hits=""
            for pattern in "${patterns[@]}"; do
                if printf '%s\n' "$content" | grep -qiE "$pattern" 2>/dev/null; then
                    hits="$hits${hits:+, }$pattern"
                fi
            done
            log "WARN" "Potential secret found in $file (patterns: $hits)"
            echo "WARNING: Potential secret detected in $file (matches: $hits)"
            has_secrets=1
        fi
    done <<< "$staged_files"

    if [ $has_secrets -ne 0 ]; then
        echo ""
        echo "SECRETS CHECK FAILED"
        echo "Review the warnings above and remove the secrets from staged content."
        echo "Sanctioned ways forward: remove the value and commit a reference to a"
        echo "secret store; unstage the file; or, for a genuine false positive, narrow"
        echo "the pattern in .claude/hooks/pre-commit.sh (write literals as"
        echo "PRIVATE[ ]KEY so the definition cannot match itself). Do NOT skip files"
        echo "wholesale, and do NOT bypass with --no-verify (block-no-verify blocks it)."
        return 1
    fi

    log "INFO" "No secrets detected in staged files"
    return 0
}

# ---------------------------------------------------------------------------
# Step 3: Run build command if source files changed
# ---------------------------------------------------------------------------
run_build() {
    local build_cmd
    build_cmd=$(get_project_config "build_cmd" || echo "")

    if [ -z "$build_cmd" ]; then
        log "INFO" "No build_cmd configured, skipping build step"
        return 0
    fi

    # Check if any source files are staged (exclude docs, configs, etc.)
    local source_changed
    source_changed=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | \
        grep -vE '\.(md|txt|json|yaml|yml|toml|cfg|ini|env|log)$' | \
        grep -vE '^(\.github|\.claude|docs|README|LICENSE|CHANGELOG)' | \
        head -1)

    if [ -z "$source_changed" ]; then
        log "INFO" "No source files changed, skipping build"
        return 0
    fi

    # Screen the configured command before handing it to a shell.
    local vout vrc
    vout="$(validate_configured_cmd "$build_cmd")"; vrc=$?
    if [ "$vrc" -eq 127 ]; then
        log "WARN" "CommandValidator unavailable — running build_cmd unscreened"
    elif [ "$vrc" -ne 0 ]; then
        log "ERROR" "Refusing to run build_cmd: ${vout:-policy violation}"
        echo "ERROR: config.json project.build_cmd was rejected by CommandValidator:"
        echo "  ${vout:-policy violation}"
        echo "Fix build_cmd in .claude/hooks/config.json — the hook will not execute it."
        return 1
    fi

    log "INFO" "Source files changed, running build: $build_cmd"
    echo "Running build: $build_cmd"

    if ! bash -c "$build_cmd" 2>&1; then
        log "ERROR" "Build failed"
        echo "ERROR: Build failed. Fix build errors before committing."
        return 1
    fi

    log "INFO" "Build succeeded"
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "INFO" "Starting pre-commit hook"

    local exit_code=0

    # Validate ops configs
    if ! validate_ops_configs; then
        exit_code=1
    fi

    # Check for secrets
    if ! check_secrets; then
        exit_code=1
    fi

    # Run build if source files changed
    if ! run_build; then
        exit_code=1
    fi

    if [ $exit_code -eq 0 ]; then
        log "INFO" "Pre-commit hook passed"
    else
        log "ERROR" "Pre-commit hook failed"
    fi

    return $exit_code
}

main "$@"
