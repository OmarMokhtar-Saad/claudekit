#!/bin/bash
# Commit ONLY the files the agent-memory fleet sync wrote, per kitted repo.
#
# Copied files are staged unconditionally (they are byte-identical to origin/main --
# verified by fleet-verify.sh). The three MERGED files are staged only when their whole
# diff is the sync hunk, so a foreign edit is never swept into this commit; a repo whose
# merged file carries extra changes is reported and left for a human.
#
# Never deletes. Never touches a file this sync did not write. Run from anywhere.
set -u

COPY=".claude/agents/code-reviewer.md .claude/agents/debugger.md .claude/agents/explore.md \
.claude/agents/planner.md .claude/agents/reviewer.md .claude/agents/security-scanner.md \
.claude/agents/verifier.md .claude/hooks/cost-tracker.sh .claude/hooks/reflection.py \
.claude/hooks/session-start.sh .claude/knowledge/issues/README.md \
.claude/operations/scripts/knowledge-ledger.py .claude/skills/continuous-learning/SKILL.md \
.claude/agent-memory/README.md .claude/hooks/session-memory-context.py \
.claude/knowledge/proposals/README.md"

MSG="chore(claudekit): sync agent-memory learning loop from claudekit 3.2.0

Seven agents declare memory: project; SessionStart injects open ledger
findings, sanitized and scanner-gated; knowledge-ledger.py gains
open --evidence / prune --supersede / propose; skillListingBudgetFraction
0.03 stops Claude Code silently dropping skill descriptions.

Files copied byte-for-byte from claudekit origin/main.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

printf '%s\n' "| repo | staged | skipped (foreign hunks) | commit |" "|---|---|---|---|"

for r in ai-agent-system AppiumLens AutomationApp Eatizaz Lean LeanApis \
         MobileUIAutomator qa-agents qaforge-ai rest-framework SehhatyApp \
         shsmartassistant-agent shsmartassistant-qa; do
  d=/Users/omarmokhtar/IdeaProjects/$r
  cd "$d" || { echo "| $r | SKIPPED: no such directory | | |"; continue; }
  n=0; skip=""

  for f in $COPY; do
    [ -f "$f" ] && git add -- "$f" && n=$((n+1))
  done
  if [ -f .agents/skills/continuous-learning/SKILL.md ]; then
    git add -- .agents/skills/continuous-learning/SKILL.md && n=$((n+1))
  fi

  # A merged file is staged only when its changed-line count equals the sync hunk's.
  stage_if_clean() {
    f=$1; expected=$2
    [ -f "$f" ] || return 0
    got=$(git diff -- "$f" | grep -c '^[-+][^-+]')
    if [ "$got" = "$expected" ]; then
      git add -- "$f"; n=$((n+1))
    else
      skip="$skip $f(changed=$got expected=$expected)"
    fi
  }
  stage_if_clean .claude/settings.json 2
  stage_if_clean .gitignore 11
  stage_if_clean .claude/skills/skills-registry.json 2

  if git diff --cached --quiet; then
    c="nothing staged"
  elif git commit -q -m "$MSG" 2>/dev/null; then
    c=$(git log --oneline -1 | cut -c1-7)
  else
    c="COMMIT FAILED"
  fi
  echo "| $r | $n | ${skip:-none} | $c |"
done
