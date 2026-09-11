#!/bin/bash
# Surgical fleet sync: claudekit origin/main -> the 13 kitted repos.
#
# Writes ONLY the 15 files below, each verified to carry no project-specific
# content. Two managed files are deliberately NOT synced:
#
#   .claude/hooks/config.json          - holds each project's own build/test/
#                                        lint commands. Overwriting it would
#                                        point every repo at claudekit's.
#   .claude/skills/skills-registry.json
#                                      - a repo with PROJECT-LOCAL skills has
#                                        them registered HERE. Copying main's
#                                        copy de-registers every one: measured
#                                        at 15 in AppiumLens, 9 in
#                                        MobileUIAutomator, 2 each in qa-agents
#                                        and rest-framework. They stay on disk,
#                                        so nothing looks broken until you read
#                                        `ck doctor`. This file needs a MERGE,
#                                        never a copy -- fix-registry.py does
#                                        it. Run that after this script.
#
#   .claude/hooks/dispatch-registry.json
#                                      - downstream has concurrency-guard at
#                                        "advisory" where main has "blocking".
#                                        That is decision #23, deliberately
#                                        held. Syncing would silently reverse
#                                        an owner decision.
#
# Nothing is committed. Downstream changes are left uncommitted for the owner,
# and every file written is tracked in its own repo, so `git diff` shows
# exactly what moved and `git checkout --` reverts it.
set -u

WT=${CK_MAIN:-/Users/omarmokhtar/IdeaProjects/.ck-main}
cd "$WT" || { echo "no claudekit worktree at $WT"; exit 1; }
git fetch origin main --quiet 2>/dev/null

FILES="
.claude/hooks/session-start.sh
.claude/hooks/command-guard.sh
.claude/operations/scripts/execute-json-ops.py
.claude/operations/scripts/restore-backup.py
.claude/operations/scripts/ops_precompile.py
.claude/profiles/minimal/profile.json
.claude/skills/release-integrity/SKILL.md
.claude/knowledge/heldout/MANIFEST.json
.claude/knowledge/heldout/README.md
.claude/knowledge/rejections/README.md
.claude/lint-baseline.json
.claude/local/CLAUDE.template.md
.claude/local/CONSTITUTION.template.md
.claude/model-policy.json
"

# DISCOVERED, not hardcoded. The literal list this replaced named 13 repos while
# 15 were kitted: ApiForge appeared in neither this script nor fleet-verify.sh,
# so it was never synced AND never reported as unsynced -- 22 files behind with
# 11 missing, invisible because both tools only ever looked at names they
# already knew. claudekit itself is the SOURCE, not a fleet member.
REPOS=$(cd "$HOME/IdeaProjects" && for p in */; do
    p=${p%/}
    [ "$p" = claudekit ] && continue
    [ -d "$p/.claude/hooks" ] && [ -d "$p/.claude/agents" ] && echo "$p"
done)

DRY=${DRY_RUN:-0}
total=0

for r in $REPOS; do
    R="$HOME/IdeaProjects/$r"
    if [ ! -d "$R/.claude" ]; then
        printf '%-24s skipped (no .claude)\n' "$r"
        continue
    fi
    wrote=0
    for f in $FILES; do
        git cat-file -e "origin/main:$f" 2>/dev/null || continue
        if git show "origin/main:$f" 2>/dev/null | diff -q - "$R/$f" >/dev/null 2>&1; then
            continue                       # already identical
        fi
        if [ "$DRY" = "1" ]; then
            echo "    would write $r/$f"
        else
            mkdir -p "$R/$(dirname "$f")"
            git show "origin/main:$f" > "$R/$f" || continue
            # preserve the executable bit git records for hooks/scripts
            case "$f" in
                *.sh|*.py) chmod +x "$R/$f" 2>/dev/null ;;
            esac
        fi
        wrote=$((wrote + 1))
    done
    total=$((total + wrote))
    printf '%-24s %s file(s)\n' "$r" "$wrote"
done

echo
if [ "$DRY" = "1" ]; then
    echo "DRY RUN -- $total file(s) would be written. Re-run without DRY_RUN=1 to apply."
else
    echo "wrote $total file(s). Nothing committed; review with 'git -C <repo> diff'."
    echo "Verify with: bash ~/IdeaProjects/claudekit/fleet-verify.sh"
fi
