#!/bin/bash
set -e

# =============================================================================
# Auto-Checkpoint Hook
# Automatically saves a checkpoint when a session ends or before risky ops.
# Uses git stash to capture working state. Records in registry.json.
# Max 20 checkpoints with automatic pruning of oldest entries.
# =============================================================================

HOOK_NAME="auto-checkpoint"
LOG_FILE=".claude/hooks/hooks.log"
CHECKPOINT_DIR=".claude/checkpoints"
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
# Prune oldest checkpoints if over limit
# ---------------------------------------------------------------------------
prune_old_checkpoints() {
    local count
    count=$(checkpoint_count)

    if [ "$count" -lt "$MAX_CHECKPOINTS" ]; then
        return 0
    fi

    log "INFO" "Checkpoint limit reached ($count/$MAX_CHECKPOINTS), pruning oldest"

    python3 -c "
import json, sys

registry_path = sys.argv[1]
max_cp = int(sys.argv[2])

with open(registry_path, 'r') as f:
    data = json.load(f)

checkpoints = data.get('checkpoints', [])
if len(checkpoints) <= max_cp:
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
            git stash drop "$pos" 2>/dev/null || true
            log "INFO" "Pruned old checkpoint stash: $pos ($stash_ref)"
        else
            log "INFO" "Checkpoint stash already gone: $stash_ref"
        fi
    done
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
    local cp_id="cp-$(date '+%s')-${short_hash}"
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

    # Immediately restore working state (checkpoint is non-destructive)
    git stash apply 2>/dev/null || true

    # Record the stable SHA as the ref; prune resolves it back to a position.
    local stash_ref="$stash_sha"

    # Record in registry
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

    log "INFO" "Checkpoint created: $cp_id ($cp_name) - $files_changed files, branch: $branch"
    echo "[$HOOK_NAME] Checkpoint saved: $cp_name ($files_changed files)" >&2

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
