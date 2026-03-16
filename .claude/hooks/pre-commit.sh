#!/bin/bash
set -e

# =============================================================================
# Pre-Commit Hook
# Validates operations configs and checks staged files for secrets.
# Optionally runs the project build command if source files changed.
# =============================================================================

HOOK_NAME="pre-commit"
LOG_FILE=".claude/hooks/hooks.log"

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
    local config=".claude/hooks/config.json"
    if [ -f "$config" ] && command -v python3 &>/dev/null; then
        python3 -c "import json, sys; c=json.load(open(sys.argv[1])); print(c.get('project',{}).get(sys.argv[2],''))" "$config" "$key" 2>/dev/null
    fi
}

# ---------------------------------------------------------------------------
# Step 1: Validate ops.json files in operations/
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
    done < <(find operations/ -name "ops.json" 2>/dev/null)

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

    # Patterns that indicate potential secrets
    local patterns=(
        'api_key\s*[:=]'
        'apikey\s*[:=]'
        'api_secret\s*[:=]'
        'password\s*[:=]'
        'passwd\s*[:=]'
        'secret\s*[:=]'
        'secret_key\s*[:=]'
        'token\s*[:=]'
        'access_token\s*[:=]'
        'private_key'
        'BEGIN RSA PRIVATE KEY'
        'BEGIN OPENSSH PRIVATE KEY'
        'BEGIN EC PRIVATE KEY'
        'BEGIN DSA PRIVATE KEY'
        'BEGIN PGP PRIVATE KEY'
    )

    for file in $staged_files; do
        # Skip binary files, lock files, and config templates
        if [[ "$file" =~ \.(lock|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|pdf)$ ]]; then
            continue
        fi
        if [[ "$file" =~ (config\.json|config\.template|\.example)$ ]]; then
            continue
        fi

        for pattern in "${patterns[@]}"; do
            if git show ":$file" 2>/dev/null | grep -iE "$pattern" >/dev/null 2>&1; then
                log "WARN" "Potential secret found in $file (pattern: $pattern)"
                echo "WARNING: Potential secret detected in $file (matches: $pattern)"
                has_secrets=1
            fi
        done
    done

    if [ $has_secrets -ne 0 ]; then
        echo ""
        echo "SECRETS CHECK FAILED"
        echo "Review the warnings above. If these are false positives, use:"
        echo "  git commit --no-verify"
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
    build_cmd=$(get_project_config "build_cmd")

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
