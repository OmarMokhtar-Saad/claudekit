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

    # 0. Public-by-construction and test material, checked BEFORE any denylist.
    #
    # The extension set below is right -- a `.pem` usually IS a key. The problem was
    # that "usually" had no escape hatch: `public.pem`, `id_rsa.pub`, `ca-bundle.crt`
    # and every `.pem` under `tests/fixtures/` classified as `certificates`, and this
    # classifier is wired through an ADVISORY hook (`file-guard-gate.sh` exits 0 always,
    # `strict` profile only). So the cost was not a blocked edit -- it was a warning that
    # cries wolf, and an advisory nobody believes is worse than none.
    #
    # An allowlist rather than a narrower denylist, deliberately: hard rule 6 calls this
    # a speed bump, and a speed bump needs a marked exit or people drive around it.
    #
    # SCOPED TO THE EXTENSION SET THAT MOTIVATED IT. The first version of this allowlist
    # (2026-08-24, same day) `return`ed before branches 1-13, so a `test`/`fixtures` path
    # component was not a certificate exemption -- it was a blanket exemption from ALL
    # thirteen categories. An adversarial review executed it and found ten regressions,
    # every one a real secret shape: `tests/fixtures/.env`, `test/secrets.json`,
    # `tests/credentials.json`, `tests/id_rsa`, `testdata/wallet.dat`,
    # `spec/fixtures/terraform.tfstate`, `k8s/tests/secret-db.yaml` and three under `pii/`.
    # A checked-in `.env` under `tests/fixtures/` and a `terraform.tfstate` under
    # `testdata/` are the two commonest real shapes of a leaked secret, and both went
    # silent. The differential gate written in the same commit reported OK, because its
    # corpus was drawn from the widening it was meant to police.
    #
    # So the gate is now the extension itself: the allowlist is reachable ONLY for the
    # certificate/key extensions whose false positives justified it. `pub` is in the set
    # because `id_rsa.pub` is the canonical public-key case; nothing else changes.
    case "${basename##*.}" in
        cert|crt|pem|key|p12|pfx|pub)
            # Narrow on purpose, and STEM/COMPONENT matching, never substring:
            # `publickeys.pem`, `samples.key` and `latest.pem` all stay flagged.
            case "$basename" in
                public.*|*.pub|ca-bundle.*|ca-certificates.*|example.*|sample.*|dummy.*)
                    echo ""; return ;;
            esac
            case "/$filepath" in
                */test/*|*/tests/*|*/testdata/*|*/fixtures/*|*/spec/fixtures/*|*/__fixtures__/*)
                    echo ""; return ;;
            esac
            ;;
    esac

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
    # `production/*data*` and `pii/*` are UNCONDITIONAL. The schema/model exclusion below
    # exists only to stop `*"customer"*"data"*` matching `customer_data_schema.sql`, and
    # the first version of it was conjoined ahead of all three predicates -- so it also
    # vetoed `pii/`, freeing `pii/model_training_data.csv` (ML training data in a PII
    # directory: real data, freed by a rule justified as "a schema describes data").
    # An exclusion may never be wider than the predicate it corrects.
    if [[ "$filepath" == *"production/"*"data"* ]] || [[ "$filepath" == *"pii/"* ]]; then
        echo "production-data"; return
    fi
    # Anchored to the `-schema.`/`_schema.` and `-model.`/`_model.` SHAPES, not to the bare
    # substrings: `customer-data-schema-dump.sql` is a dump -- it IS data -- and stays
    # flagged, where a bare `*schema*` freed it.
    if [[ "$filepath" == *"customer"*"data"* ]] &&
       [[ "$basename" != *[-_]schema.* ]] && [[ "$basename" != *[-_]model.* ]]; then
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
