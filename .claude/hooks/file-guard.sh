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
# `$2` = "skip_certs": classify as if the certificate branch did not exist. That is how
# the allowlist below is scoped to the category it was written for -- see public_material().
classify() {
    local filepath="$1"
    local skip_certs="${2:-}"
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

    # 8. Certificates and private keys. Extension lowercased: `SERVER.PEM` was clean,
    # and since the allowlist is scoped by this classification, its case-sensitivity is
    # load-bearing in a way it was not when it was only a denylist branch.
    if [ -z "$skip_certs" ]; then
        case "$(printf '%s' "${basename##*.}" | tr '[:upper:]' '[:lower:]')" in
            cert|crt|pem|key|p12|pfx)
                echo "certificates"; return ;;
        esac
    fi

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
    # Anchored to the END OF THE STEM and matched on the BASENAME, not the path. The
    # first version tested `*[-_]schema.*` against the basename while the predicate tested
    # the whole path, so `customer_data_schema.sql.bak` (a BACKUP of the data),
    # `customerdata-schema.csv` (no separator at all) and `customer/data/dump-schema.csv`
    # (the words are DIRECTORIES; the basename is a dump) were all freed. Same defect as
    # the exclusion it replaced, one anchoring level up.
    # Predicate on the PATH (so `customer/data/dump.csv` counts, where the words are
    # directories), exclusion on the BASENAME. Two conditions, both required, because
    # each alone was defeated:
    #   * the stem must END in `-schema`/`_schema`/`-model`/`_model` -- not merely contain
    #     it, or `customerdata-schema.csv` and a bare `*schema*` substring slip through; and
    #   * the EXTENSION must be a description format. `${basename%%.*}` alone freed
    #     `customer_data_schema.sql.bak` -- a BACKUP of the data -- because stripping every
    #     suffix left a stem ending in `_schema`. A `.bak`, `.gz`, `.csv` or `.dump` is
    #     data no matter what the stem says; a `.sql`/`.md`/`.json` schema is a description.
    local _stem="${basename%%.*}"
    local _ext
    _ext="$(printf '%s' "${basename##*.}" | tr '[:upper:]' '[:lower:]')"
    local _is_description=0
    case "$_ext" in
        sql|md|json|yaml|yml|graphql|prisma|proto|xsd|rst|txt) _is_description=1 ;;
    esac
    if [[ "$filepath" == *"customer"* ]] && [[ "$filepath" == *"data"* ]]; then
        if [ "$_is_description" -eq 1 ] &&
           { [[ "$_stem" == *[-_]schema ]] || [[ "$_stem" == *[-_]model ]]; }; then
            :   # a schema or model DESCRIPTION, in a description format
        else
            echo "production-data"; return
        fi
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
# ---------------------------------------------------------------------------
# Is this file public-by-construction or test material?
#
# Called ONLY for a file whose only classification is `certificates` (see check_file).
# The false positives that justify it are real -- `public.pem`, `ca-bundle.crt` and every
# `.pem` under `tests/fixtures/` are not secrets, and this classifier feeds an ADVISORY
# hook (`file-guard-gate.sh` exits 0 always, `strict` profile only), so a false flag costs
# credibility rather than a blocked edit. An advisory nobody believes is worse than none.
#
# STEM and PATH-COMPONENT matching, never substring: `publickeys.pem`, `samples.key`,
# `latest.pem` and `contest/prod.key` all stay flagged.
# ---------------------------------------------------------------------------
public_material() {
    local filepath="$1"
    local basename
    basename=$(basename "$filepath")

    # NAME-ASSERTED PUBLIC MATERIAL FIRST, and this ordering is the documented contract:
    # a `public`/`pub` stem, a CA bundle, and the example/sample/dummy stems are public
    # WHEREVER they live. The veto below used to precede the example/sample case, which
    # silently reversed that promise -- and because `file-guard-gate.sh` passes the
    # ABSOLUTE `file_path`, any project rooted under a directory called `prod` or `keys`
    # had every fixture re-flagged. That is the false-positive noise this allowlist exists
    # to remove.
    #
    # Residual, stated rather than hidden: the veto is a name match on whatever path it is
    # given, so an absolute path can still contribute components from outside the project.
    # For a non-example-named file under such a path the verdict errs toward FLAGGED, which
    # is the safe direction for an advisory.
    # ONLY names that assert a CRYPTOGRAPHIC ROLE sit above the veto. `public.*` and a CA
    # bundle say "this is the half you publish", which is true in any directory.
    # `example.`/`sample.`/`dummy.` assert an AUTHOR'S INTENT -- exactly the class of claim
    # the veto below exists to distrust, since the veto's own reasoning is that a `tests/`
    # component "is not evidence that the file is not a secret" and a filename prefix is
    # under identical authorial control. Placing them above it freed `secrets/example.key`,
    # `vault/sample.pem`, `keys/dummy.key`, `.aws/example.pem` and `.gnupg/sample.key`, and
    # the differential gate certified that widening as clean because no corpus path had an
    # example/sample/dummy basename inside a secret directory. They now sit BELOW the veto.
    case "$basename" in
        public.*|ca-bundle.*|ca-certificates.*)
            return 0 ;;
        # `*.pub` ABOVE the veto only for the ENUMERATED public-key names. A bare `*.pub`
        # here freed `.ssh/deploy.key.pub` -- and branch 3 classifies every file under
        # `.ssh/`, so any private key renamed with a `.pub` suffix walked straight out.
        # `id_rsa.pub` is a name with a meaning; `deploy.key.pub` is an assertion by
        # whoever named the file. Other `*.pub` files are still freed, but below the veto.
        id_rsa.pub|id_ed25519.pub|id_ecdsa.pub|id_dsa.pub)
            return 0 ;;
    esac

    # DIRECTORIES THAT SIGNAL SECRETS OVERRIDE A TEST-SHAPED PATH. `k8s/tests/tls.key` is
    # the case that proves this is needed: branch 13 requires the word "secret" in the
    # path, so a TLS key named `tls.key` never reaches it, falls through to `certificates`,
    # and a `tests/` component then freed it. The differential gate caught this one, which
    # is the ratchet doing its job -- but the lesson is that "no stronger category fired"
    # is not the same as "nothing about this path is sensitive". A test fixture living
    # inside a secrets directory is not evidence that the file is not a secret.
    # Singular AND plural, and the conventional homes of exactly the file branch 8 is
    # about. The first list covered the example that motivated it and not the family:
    # `.kube/` is the client-credential directory, `secret/` (singular) was missed while
    # `secrets/` was covered, and `certs/`, `ssl/`, `private/` are where certificates
    # actually live.
    # LOWERCASED. The veto was case-sensitive, so `K8s/tests/tls.key` -- the canonical case
    # it was written for -- was freed by one capital letter, and `SECRETS/`, `PII/`,
    # `Production/` and `.SSH/` with it. On the case-insensitive APFS this project targets
    # those are THE SAME DIRECTORIES as their lowercase forms, so it was a live bypass
    # rather than a typo. The guard already lowercases extensions in three places.
    local _lc
    _lc="$(printf '%s' "$filepath" | tr '[:upper:]' '[:lower:]')"
    case "/$_lc/" in
        */k8s/*|*/kubernetes/*|*/.kube/*|*/pii/*|*/production/*|*/prod/*|\
        */secret/*|*/secrets/*|*/credential/*|*/credentials/*|*/.ssh/*|*/.aws/*|\
        */.gcloud/*|*/.docker/*|*/.gnupg/*|*/.gpg/*|*/vault/*|*/key/*|*/keys/*|\
        */certs/*|*/certificates/*|*/ssl/*|*/tls/*|*/private/*)
            return 1 ;;
    esac
    case "$basename" in
        *.pub) return 0 ;;
    esac
    case "$basename" in
        example.*|sample.*|dummy.*) return 0 ;;
    esac
    case "/$_lc" in
        */test/*|*/tests/*|*/testdata/*|*/fixtures/*|*/spec/fixtures/*|*/__fixtures__/*)
            return 0 ;;
    esac
    return 1
}

check_file() {
    local filepath="$1"
    [ -z "$filepath" ] && return 0

    local category
    category=$(classify "$filepath")

    # THE ALLOWLIST, applied to the CLASSIFICATION rather than ahead of it.
    #
    # Two prior versions of this got the scope wrong in the same direction. v1 sat at the
    # top of classify() and exempted all thirteen categories. v2 gated that on the file's
    # EXTENSION -- which is not the same as the category, because classify() returns on the
    # FIRST match and `.key`/`.pem` files reach branch 8 before branches 9-13 ever run. So
    # `k8s/tests/tls.key` (the canonical checked-in TLS secret), `tests/api_key.key` and
    # `pii/tests/customers.key` were all still silent. "Unreachable for any other
    # extension" was true and irrelevant.
    #
    # v3 asks the question that actually matters: WOULD ANY OTHER CATEGORY HAVE FIRED?
    # Only a file whose sole claim to sensitivity is "it has a certificate extension" is
    # exemptible. If a stronger category also matches, that category wins and the file
    # stays flagged.
    if [ "$category" = "certificates" ]; then
        local stronger
        stronger=$(classify "$filepath" skip_certs)
        # ALSO ask what the file is with the certificate extension REMOVED. A generated
        # invariant (tests/test_fileguard_allowlist.py) found 150 paths of this shape that
        # the two hand-written corpora both missed: `credentials.json.pem`,
        # `wallet.dat.key`, `prod.sqlite.crt`, `secrets/backup.bak.p12` -- appending a
        # certificate suffix breaks the EXACT-basename match those categories rely on, so
        # only branch 8 fires and the allowlist frees it under a test directory. Strip the
        # suffix and the real category reappears.
        # ITERATE. Branch 8 matches the LAST element of an arbitrarily long extension
        # chain, and stripping exactly one suffix corrected the predicate only for n=1 --
        # so `tests/credentials.json.pem.key`, `tests/passwd.pem.key`,
        # `tests/id_rsa.pem.key` and `testdata/prod.sqlite.crt.pem` all went silent while
        # `tests/credentials.json.pem` (the path this very corpus added) stayed flagged.
        # Fourth occurrence of "the correction is narrower than the predicate it corrects",
        # and the generated invariant missed it because it appends exactly ONE extension.
        #
        # The loop only ever removes a suffix that is itself a certificate extension, and
        # stops at the basename: `tests/foo.bar/key` must not strip into its own directory.
        if [ -z "$stronger" ]; then
            # PEEL ANY SUFFIX, not only certificate ones. Restricting the walk to a chain
            # made entirely of cert extensions was the FIFTH occurrence of the same class:
            # branch 8 matches the LAST element of a chain and cares nothing for what
            # precedes it, so one interposed `.gz`/`.bak`/`.tar`/`.zip` -- a COMPRESSED OR
            # BACKED-UP key, the likeliest real form -- stopped the walk before it reached
            # the real category. Measured: 100 of 360 generated cases freed, including
            # `tests/credentials.json.gz.key`, `tests/id_rsa.tar.pem` and
            # `tests/passwd.bak.crt`, while every `.pem.key` control passed.
            #
            # Over-peeling is SAFE by construction and that is why the restriction was pure
            # loss: `classify` on a shorter stem can only ever return a category, never
            # remove one, so a wrong extra peel can add a flag but never drop one. The
            # `*.*` guard below is the only bound that matters -- it stops the walk at the
            # basename so a dotted DIRECTORY is never entered.
            local _peeled="$filepath" _peeled_base
            while :; do
                _peeled_base="${_peeled##*/}"
                case "$_peeled_base" in *.*) ;; *) break ;; esac
                _peeled="${_peeled%.*}"
                stronger=$(classify "$_peeled" skip_certs)
                [ -n "$stronger" ] && break
            done
        fi
        if [ -n "$stronger" ]; then
            category="$stronger"
        elif public_material "$filepath"; then
            category=""
        fi
    elif [ "$category" = "ssh-keys" ] && [[ "$(basename "$filepath")" == *.pub ]]; then
        # Routed THROUGH public_material, so the secret-directory veto applies. This was
        # a bare `category=""`, which freed anything classified `ssh-keys` whose basename
        # ended `.pub` -- and branch 3 classifies EVERY file under `.ssh/`, so
        # `.ssh/deploy.key.pub` and `.ssh/authorized_keys.pub` were both clean.
        # `authorized_keys` is an access-control file the guard lists deliberately; it is
        # not "the half you publish".
        case "$(basename "$filepath")" in
            authorized_keys.pub|known_hosts.pub) ;;
            *) public_material "$filepath" && category="" ;;
        esac
    fi

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
