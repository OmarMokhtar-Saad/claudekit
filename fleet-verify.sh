#!/bin/bash
# Verify every kitted repo against claudekit origin/main, and prove the synced hooks RUN.
#
# Two independent checks per repo:
#   1. byte-identity of the 16 files the agent-memory sync wrote, vs `git show origin/main:<f>`
#   2. execution: each hook is actually invoked under the standard profile and must exit 0
# Read-only. Never writes into a kitted repo.
set -u

WT=${CK_MAIN:-/Users/omarmokhtar/IdeaProjects/.ck-main}
[ -d "$WT/.git" ] || WT=/Users/omarmokhtar/IdeaProjects/.ck-agent-memory-wt

FILES=".claude/agents/code-reviewer.md .claude/agents/debugger.md .claude/agents/explore.md \
.claude/agents/planner.md .claude/agents/reviewer.md .claude/agents/security-scanner.md \
.claude/agents/verifier.md .claude/hooks/cost-tracker.sh .claude/hooks/reflection.py \
.claude/hooks/session-start.sh .claude/knowledge/issues/README.md \
.claude/operations/scripts/knowledge-ledger.py .claude/skills/continuous-learning/SKILL.md \
.claude/agent-memory/README.md .claude/hooks/session-memory-context.py \
.claude/knowledge/proposals/README.md"

printf '%s\n' "| repo | identical to main | hooks exit 0 | settings | manifest | doctor |" \
              "|---|---|---|---|---|---|"

for r in ai-agent-system AppiumLens AutomationApp Eatizaz Lean LeanApis \
         MobileUIAutomator qa-agents qaforge-ai rest-framework SehhatyApp \
         shsmartassistant-agent shsmartassistant-qa; do
  d=/Users/omarmokhtar/IdeaProjects/$r
  [ -d "$d/.claude" ] || { echo "| $r | NOT KITTED | | | | |"; continue; }

  same=0; diff=""
  for f in $FILES; do
    if cmp -s "$d/$f" <(cd "$WT" && git show "origin/main:$f" 2>/dev/null); then
      same=$((same+1))
    else
      diff="$diff $(basename "$f")"
    fi
  done

  cd "$d" || continue
  export CLAUDE_PROJECT_DIR="$d" ECC_HOOK_PROFILE=standard
  ss=$(echo '{}' | bash .claude/hooks/session-start.sh >/dev/null 2>&1; echo $?)
  ct=$(echo '{}' | bash .claude/hooks/cost-tracker.sh >/dev/null 2>&1; echo $?)
  sm=$(python3 .claude/hooks/session-memory-context.py >/dev/null 2>&1; echo $?)
  hooks="ss=$ss ct=$ct sm=$sm"
  [ "$ss$ct$sm" = "000" ] && hooks="all 0"

  sj=$(python3 -c "import json;json.load(open('.claude/settings.json'));print('valid')" 2>&1 | tail -1)
  m=none
  for p in .claudekit-manifest.json .claude/.claudekit-manifest.json; do
    [ -f "$p" ] && m=$(python3 -c "import json;print(json.load(open('$p')).get('version','?'))" 2>/dev/null)
  done
  bang=$(ck doctor 2>/dev/null | grep -c '^\[!\]')
  passed=$(ck doctor 2>/dev/null | grep -o 'Passed: *[0-9]*/[0-9]*' | tr -s ' ')

  echo "| $r | $same/16${diff:+ DIFFERS:$diff} | $hooks | $sj | $m | $passed warn=$bang |"
done
