#!/bin/bash
set -e

# =============================================================================
# File Guard Hook
# Blocks AI agent access to sensitive files across 13 categories.
# Input: file path via $1 or stdin (one path per line).
# Exit 0 = allow, Exit 1 = block.
# Blocked files are reported to stderr with category and path.
# =============================================================================

HOOK_NAME="file-guard"
LOG_FILE=".claude/hooks/hooks.log"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
}

block() {
    local category="$1"
    local filepath="$2"
    echo "[$HOOK_NAME] BLOCKED [$category]: $filepath" >&2
    log "WARN" "Blocked access to $filepath (category: $category)"
}

# ---------------------------------------------------------------------------
# Classify a single file path against 13 sensitive-file categories.
# Returns the category name if blocked, empty string if allowed.
# ---------------------------------------------------------------------------
classify() {
    local filepath="$1"
    local basename
    basename=$(basename "$filepath")

    # 1. Env files
    case "$basename" in
        .env|.envrc) echo "env-files"; return ;;
    esac
    if [[ "$basename" =~ ^\.env\. ]]; then
        echo "env-files"; return
    fi

    # 2. Credential files
    case "$basename" in
        credentials.json|.netrc|.npmrc|.pypirc)
            echo "credential-files"; return ;;
    esac

    # 3. SSH keys
    case "$basename" in
        id_rsa|id_rsa.pub|id_ed25519|id_ed25519.pub|id_ecdsa|id_ecdsa.pub|id_dsa|id_dsa.pub|known_hosts|authorized_keys)
            echo "ssh-keys"; return ;;
    esac
    if [[ "$filepath" == *".ssh/"* ]]; then
        echo "ssh-keys"; return
    fi

    # 4. API tokens
    case "$basename" in
        .token|.secret|secrets.json)
            echo "api-tokens"; return ;;
    esac
    if [[ "$basename" == api_key* ]]; then
        echo "api-tokens"; return
    fi

    # 5. Cloud configs
    if [[ "$filepath" == *".aws/credentials"* ]] || \
       [[ "$filepath" == *".aws/config"* ]] || \
       [[ "$filepath" == *".gcloud/"* ]] || \
       [[ "$basename" == "terraform.tfstate" ]] || \
       [[ "$basename" == "terraform.tfstate.backup" ]]; then
        echo "cloud-configs"; return
    fi

    # 6. Database files
    case "$basename" in
        .pgpass|my.cnf)
            echo "database-files"; return ;;
    esac
    if [[ "$basename" == *.sqlite ]] || [[ "$basename" == *.sqlite3 ]]; then
        echo "database-files"; return
    fi

    # 7. CI/CD secrets
    if [[ "$filepath" == *".github/secrets"* ]] || \
       [[ "$basename" == vault-secrets* ]]; then
        echo "cicd-secrets"; return
    fi

    # 8. Certificates and private keys
    case "${basename##*.}" in
        cert|crt|pem|key|p12|pfx)
            echo "certificates"; return ;;
    esac

    # 9. Password files
    case "$basename" in
        passwd|shadow|.htpasswd)
            echo "password-files"; return ;;
    esac
    if [[ "$basename" == password* ]]; then
        echo "password-files"; return
    fi

    # 10. Crypto wallets
    case "$basename" in
        wallet.dat|keystore.json)
            echo "crypto-wallets"; return ;;
    esac
    if [[ "$basename" == *.wallet ]]; then
        echo "crypto-wallets"; return
    fi

    # 11. Sensitive backups
    if [[ "$filepath" == *"secrets/"*.bak ]] || \
       [[ "$filepath" == *"credentials/"*.backup ]]; then
        echo "sensitive-backups"; return
    fi

    # 12. Production data
    if [[ "$filepath" == *"production/"*"data"* ]] || \
       [[ "$filepath" == *"customer"*"data"* ]] || \
       [[ "$filepath" == *"pii/"* ]]; then
        echo "production-data"; return
    fi

    # 13. Kubernetes secrets
    if [[ "$filepath" == *"k8s/"*"secret"* ]] || \
       [[ "$filepath" == *"kubernetes/"*"secret"* ]]; then
        echo "k8s-secrets"; return
    fi

    # No match — allowed
    echo ""
}

# ---------------------------------------------------------------------------
# Process a single file path
# ---------------------------------------------------------------------------
check_file() {
    local filepath="$1"
    [ -z "$filepath" ] && return 0

    local category
    category=$(classify "$filepath")

    if [ -n "$category" ]; then
        block "$category" "$filepath"
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local blocked=0

    if [ -n "$1" ]; then
        # File path provided as argument
        if ! check_file "$1"; then
            blocked=1
        fi
    else
        # Read file paths from stdin
        while IFS= read -r filepath; do
            if ! check_file "$filepath"; then
                blocked=1
            fi
        done
    fi

    if [ $blocked -ne 0 ]; then
        exit 1
    fi

    exit 0
}

main "$@"
