#!/usr/bin/env bash
# =============================================================================
# plan-lib.sh -- shared by plan-gate.sh and checkpoint-gate.sh (sourced, never run).
# Tier classification and plan-approval lookup. bash 3.2 safe. Callers must set
# ABS_ROOT and ABS_TARGET (realpaths) and SCRIPT_DIR before calling.
# =============================================================================

# Tier-3 globs live in <root>/.claude/plan-gate.globs: one pattern per line, '#' comments,
# shell-glob syntax where '*' crosses '/', a trailing '/' means "everything below".
# Without the file, EVERY source path that is not allow-listed is Tier 3 (conservative).
PG_GLOBS_NAME="plan-gate.globs"   # lives under <root>/.claude/

pg_rel_target() {
    case "$ABS_TARGET" in
        "$ABS_ROOT"/*) printf '%s' "${ABS_TARGET#"$ABS_ROOT"/}" ;;
        *) printf '%s' "$ABS_TARGET" ;;
    esac
}

# Sets PG_T3_SOURCE to "globs" or "default" when it returns 0 (path is Tier 3).
pg_is_t3() {
    local rel="$1" pat file="$ABS_ROOT/.claude/$PG_GLOBS_NAME"
    case "$rel" in /*) return 1 ;; esac   # outside the project: not this gate's business
    if [ -f "$file" ]; then
        PG_T3_SOURCE="globs"
        local old_ifs=$IFS
        set -f
        IFS='
'
        for pat in $(tr -d '\r' < "$file" 2>/dev/null); do
            case "$pat" in ''|\#*) continue ;; esac
            case "$pat" in */) pat="${pat}*" ;; esac
            # shellcheck disable=SC2254
            case "$rel" in $pat) set +f; IFS=$old_ifs; return 0 ;; esac
        done
        set +f
        IFS=$old_ifs
        return 1
    fi
    PG_T3_SOURCE="default"
    case "$rel" in
        .claude/*|.hermes/scratch/*) return 1 ;;
        *.md|*.txt|*.rst|*.adoc|*.log|*.tmp) return 1 ;;
    esac
    return 0
}

# Paths the main session may never write directly: the authoritative review records,
# settings files and the T3 glob list. Checked BEFORE every allow rule.
pg_is_denied_path() {
    case "$1" in
        .claude/reports/reviews|.claude/reports/reviews/*) return 0 ;;
        .claude/settings.json|.claude/settings.local.json|.claude/"$PG_GLOBS_NAME") return 0 ;;
    esac
    return 1
}

# Exit 0 when some plan in <root>/.claude/plans has an unchanged APPROVED record
# (score >= 90) whose Files: covers $1 (project-relative path). Fails closed: a missing
# recorder means no plan can authorise anything.
pg_authorised() {
    local rel="$1" recorder plan
    recorder="$SCRIPT_DIR/../operations/scripts/review-record.py"
    [ -f "$recorder" ] || return 1
    for plan in "$ABS_ROOT"/.claude/plans/plan-*.md; do
        [ -f "$plan" ] || continue
        if (cd "$ABS_ROOT" && python3 "$recorder" plan-check "$plan" --path "$rel" >/dev/null 2>&1); then
            return 0
        fi
    done
    return 1
}

# Like pg_authorised, but the plan must also mark $1 with `(delete)` in its Files: header.
pg_authorised_delete() {
    local rel="$1" recorder plan
    recorder="$SCRIPT_DIR/../operations/scripts/review-record.py"
    [ -f "$recorder" ] || return 1
    for plan in "$ABS_ROOT"/.claude/plans/plan-*.md; do
        [ -f "$plan" ] || continue
        if (cd "$ABS_ROOT" && python3 "$recorder" plan-check "$plan" --path "$rel" --delete >/dev/null 2>&1); then
            return 0
        fi
    done
    return 1
}

# Exit 0 when $1 is a plan file with a currently valid APPROVED record (its Files:/Tier
# header lines are then frozen: editing them would only be drift, so refuse up front).
pg_is_approved_plan() {
    local abs="$1" recorder
    recorder="$SCRIPT_DIR/../operations/scripts/review-record.py"
    case "$abs" in "$ABS_ROOT"/.claude/plans/plan-*.md) : ;; *) return 1 ;; esac
    [ -f "$recorder" ] || return 1
    (cd "$ABS_ROOT" && python3 "$recorder" plan-check "$abs" >/dev/null 2>&1)
}
