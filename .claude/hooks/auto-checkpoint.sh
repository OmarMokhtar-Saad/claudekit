#!/bin/bash
set -e

# =============================================================================
# Auto-Checkpoint Hook
# Automatically saves a checkpoint when a session ends or before risky ops.
# Uses git stash to capture working state. Records in registry.json.
# Max 20 checkpoints with automatic pruning of oldest entries.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# `$SCRIPT_DIR` for files the HOOK owns, `$CK_ROOT` for files the PROJECT owns.
# Measured 2026-08-25 as a property rather than as the sites anyone noticed: 16
# cwd-relative `.claude/` paths across 8 hooks, while exactly ONE of the 11 hooks
# wired in settings.json is invoked with a `cd` to the project root. A hook may not
# assume its working directory. `tests/test_hook_paths.py` now asserts the property,
# so the count cannot grow again while nobody is counting.
# DERIVED FROM THE REPO, then required to be inside it. `CLAUDE_PROJECT_DIR` is honoured
# only when it actually names the work tree git is operating on: otherwise the registry was
# written to one directory while the stash landed in another repo, so a later restore read
# `stash@{0}` refs that resolve nowhere. Measured: registry created in a non-repo directory
# while the stash went to the repo the cwd belonged to.
CK_GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
CK_ROOT="${CLAUDE_PROJECT_DIR:-${CK_GIT_ROOT:-$(pwd)}}"
if [ -n "$CK_GIT_ROOT" ] && [ "$CK_ROOT" != "$CK_GIT_ROOT" ]; then
    case "$CK_ROOT" in
        "$CK_GIT_ROOT"/*) ;;
        *) CK_ROOT="$CK_GIT_ROOT" ;;
    esac
fi
HOOK_NAME="auto-checkpoint"
LOG_FILE="$SCRIPT_DIR/hooks.log"
# Checkpoints are PROJECT state -- they must land in the repo being checkpointed, not
# beside the hook -- so this one resolves through $CK_ROOT rather than $SCRIPT_DIR.
CHECKPOINT_DIR="$CK_ROOT/.claude/checkpoints"
REGISTRY_FILE="$CHECKPOINT_DIR/registry.json"
MAX_CHECKPOINTS=20

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$level] $*" >> "$LOG_FILE" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Ensure checkpoint directory and registry exist
# ---------------------------------------------------------------------------
ensure_registry() {
    if [ ! -d "$CHECKPOINT_DIR" ]; then
        mkdir -p "$CHECKPOINT_DIR"
        log "INFO" "Created checkpoint directory: $CHECKPOINT_DIR"
    fi

    if [ ! -f "$REGISTRY_FILE" ]; then
        cat > "$REGISTRY_FILE" << 'INITJSON'
{
  "version": 1,
  "max_checkpoints": 20,
  "checkpoints": []
}
INITJSON
        log "INFO" "Initialized checkpoint registry"
    fi
}

# ---------------------------------------------------------------------------
# Count current checkpoints
# ---------------------------------------------------------------------------
checkpoint_count() {
    if [ ! -f "$REGISTRY_FILE" ] || ! command -v python3 &>/dev/null; then
        echo "0"
        return
    fi
    python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(len(data.get('checkpoints', [])))
except:
    print('0')
" "$REGISTRY_FILE" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Registry mutex.
#
# `mkdir` is an atomic, portable lock (flock is Linux-only) -- the same idiom
# `suggest-compact.sh` uses, with the same `find -mmin` stale recovery, because
# `date -r`/`stat` differ across platforms.
#
# One deliberate difference from that sibling: it SKIPS its work when the lock is
# held, since a lost counter increment costs nothing. A skipped checkpoint costs
# the user's uncommitted work, so this waits briefly and then proceeds anyway with
# a WARN. The protected sections are short; the failure mode chosen is a possible
# size overshoot, never a lost checkpoint.
# ---------------------------------------------------------------------------
REGISTRY_LOCK=""

registry_lock() {
    REGISTRY_LOCK="${REGISTRY_FILE}.lockdir"
    if [ -d "$REGISTRY_LOCK" ]; then
        find "$REGISTRY_LOCK" -maxdepth 0 -mmin +1 -exec rmdir {} \; 2>/dev/null
    fi
    local i=0
    while [ "$i" -lt 20 ]; do
        if mkdir "$REGISTRY_LOCK" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
        i=$((i + 1))
    done
    log "WARN" "Registry lock held for 2s; proceeding unlocked rather than dropping a checkpoint"
    REGISTRY_LOCK=""
    return 0
}

registry_unlock() {
    [ -n "$REGISTRY_LOCK" ] && rmdir "$REGISTRY_LOCK" 2>/dev/null
    REGISTRY_LOCK=""
}

# ---------------------------------------------------------------------------
# Prune oldest checkpoints if over limit
# ---------------------------------------------------------------------------
prune_old_checkpoints() {
    local count
    count=$(checkpoint_count)

    if [ "$count" -lt "$MAX_CHECKPOINTS" ]; then
        return 0
    fi

    log "INFO" "Checkpoint limit reached ($count/$MAX_CHECKPOINTS), pruning oldest"

    registry_lock
    python3 -c "
import json, sys

registry_path = sys.argv[1]
max_cp = int(sys.argv[2])

with open(registry_path, 'r') as f:
    data = json.load(f)

checkpoints = data.get('checkpoints', [])
# Strictly less-than, not less-or-equal: the shell guard above already decided to
# prune at count >= MAX_CHECKPOINTS, and the +1 below reserves room for the
# checkpoint about to be appended. With <= the two guards disagreed at exactly
# count == max, the append pushed the registry to max + 1, and the next run pruned
# it back -- measured as an oscillation 3 -> 4 -> 3 -> 4 at max=3, i.e. the
# configured cap exceeded on every other checkpoint, each overshoot a retained
# git stash.
# (No backticks in this comment on purpose: it lives inside a double-quoted shell
# string, where a backtick is command substitution and not quoting.)
if len(checkpoints) < max_cp:
    sys.exit(0)

# Sort by timestamp ascending and remove oldest
checkpoints.sort(key=lambda c: c.get('timestamp', ''))
pruned = checkpoints[:len(checkpoints) - max_cp + 1]
data['checkpoints'] = checkpoints[len(checkpoints) - max_cp + 1:]

with open(registry_path, 'w') as f:
    json.dump(data, f, indent=2)

# Print pruned stash refs for cleanup
for cp in pruned:
    ref = cp.get('stash_ref', '')
    if ref:
        print(ref)
" "$REGISTRY_FILE" "$MAX_CHECKPOINTS" 2>/dev/null | while IFS= read -r stash_ref; do
        [ -z "$stash_ref" ] && continue
        # stash_ref is a stable commit SHA. Resolve it to its CURRENT positional
        # ref (stash@{n}) by matching SHAs, then drop that — dropping by SHA or a
        # stale position would hit the wrong stash.
        pos=$(git stash list --format='%gd %H' 2>/dev/null \
              | awk -v s="$stash_ref" '$2==s || index($2,s)==1 {print $1; exit}')
        if [ -n "$pos" ]; then
            # silent-ok: dropping an already-pruned stash is not an error
            git stash drop "$pos" 2>/dev/null || true
            log "INFO" "Pruned old checkpoint stash: $pos ($stash_ref)"
        else
            log "INFO" "Checkpoint stash already gone: $stash_ref"
        fi
    done
    registry_unlock
}

# ---------------------------------------------------------------------------
# Create a checkpoint
# ---------------------------------------------------------------------------
create_checkpoint() {
    local reason="${1:-auto-session-end}"

    # Check if there are any changes to checkpoint
    local status
    status=$(git status --porcelain 2>/dev/null)

    if [ -z "$status" ]; then
        log "INFO" "No uncommitted changes to checkpoint"
        return 0
    fi

    ensure_registry
    prune_old_checkpoints

    # Generate checkpoint metadata
    local timestamp
    timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local date_slug
    date_slug=$(date '+%Y%m%d-%H%M%S')
    local short_hash
    short_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "nohash")
    local cp_id
    cp_id="cp-$(date '+%s')-${short_hash}"
    local cp_name="auto-${date_slug}"
    local branch
    branch=$(git branch --show-current 2>/dev/null || echo "detached")
    local files_changed
    files_changed=$(echo "$status" | wc -l | tr -d ' ')
    local files_list
    files_list=$(echo "$status" | awk '{print $2}' | head -20)

    # Create the stash
    local stash_msg="checkpoint: $cp_name | $reason"
    if ! git stash push --include-untracked -m "$stash_msg" 2>/dev/null; then
        log "ERROR" "Failed to create git stash for checkpoint"
        return 1
    fi

    # Capture the stash's commit SHA NOW — it is stable, unlike the positional
    # `stash@{0}` ref, which shifts every time a newer stash is pushed (so a
    # later prune-by-position would drop the WRONG stash).
    local stash_sha
    stash_sha=$(git rev-parse "stash@{0}" 2>/dev/null || echo "")

    # Immediately restore working state (checkpoint is non-destructive).
    # `git stash apply` exits 1 when the restore conflicts with the working tree, and the
    # stash SURVIVES (verified: `git stash list` still lists it). So the failure mode is a
    # silent SUCCESS, not data loss -- but the user's work then lives only in the stash and
    # NOT in the tree, so say so loudly and name the recovery command.
    #
    # git's stderr goes to a temp file, not a command substitution: `$(git stash apply 2>&1)`
    # would swallow git's stdout summary. The file is replayed to stderr (terminal) AND into
    # hooks.log, which CLAUDE.md makes the first debugging step.
    local restore_note="" stash_err
    stash_err="$(mktemp "${TMPDIR:-/tmp}/auto-checkpoint-stash.XXXXXX")"
    if ! git stash apply 2>"$stash_err"; then
        restore_note=" -- WORKING TREE NOT RESTORED"
        log "ERROR" "Checkpoint stash created, but re-applying it to the working tree failed: $(tr '\n' ' ' < "$stash_err")"
        log "ERROR" "Work is preserved in the stash. Recover with: git stash apply ${stash_sha:-stash@{0}}"
        printf '%s\n' "[$HOOK_NAME] working tree NOT restored after checkpoint." >&2
        printf '%s\n' "[$HOOK_NAME] recover with: git stash apply ${stash_sha:-stash@{0}}" >&2
    fi
    cat "$stash_err" >&2
    rm -f "$stash_err"

    # Record the stable SHA as the ref; prune resolves it back to a position.
    local stash_ref="$stash_sha"

    # Record in registry
    registry_lock
    python3 -c "
import json, sys

registry_path = sys.argv[1]
cp_id = sys.argv[2]
cp_name = sys.argv[3]
reason = sys.argv[4]
stash_ref = sys.argv[5]
timestamp = sys.argv[6]
branch = sys.argv[7]
short_hash = sys.argv[8]
files_changed = int(sys.argv[9])
files_list = sys.argv[10].strip().split('\n') if sys.argv[10].strip() else []

with open(registry_path, 'r') as f:
    data = json.load(f)

data['checkpoints'].append({
    'id': cp_id,
    'name': cp_name,
    'message': reason,
    'stash_ref': stash_ref,
    'timestamp': timestamp,
    'branch': branch,
    'commit': short_hash,
    'files_changed': files_changed,
    'files_list': files_list[:20]
})

with open(registry_path, 'w') as f:
    json.dump(data, f, indent=2)
" "$REGISTRY_FILE" "$cp_id" "$cp_name" "$reason" "$stash_ref" "$timestamp" "$branch" "$short_hash" "$files_changed" "$files_list" 2>/dev/null
    registry_unlock

    log "INFO" "Checkpoint created: $cp_id ($cp_name) - $files_changed files, branch: $branch"
    echo "[$HOOK_NAME] Checkpoint saved: $cp_name ($files_changed files)$restore_note" >&2

    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local reason="${1:-session-end}"

    log "INFO" "Auto-checkpoint triggered (reason: $reason)"

    if ! command -v git &>/dev/null; then
        log "ERROR" "git not found, cannot create checkpoint"
        exit 0  # Non-blocking: don't fail the session
    fi

    # Verify we're in a git repo
    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        log "WARN" "Not inside a git repository, skipping checkpoint"
        exit 0
    fi

    create_checkpoint "$reason"

    exit 0
}

main "$@"
