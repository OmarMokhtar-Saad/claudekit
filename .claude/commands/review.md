---
description: "Validate plan via reviewer agent (90% threshold)"
model: opus
---

# Reviewer Command

Runs the local `reviewer` agent via `claude -p --agent reviewer`.
Verified mechanism: `--agent <name>` loads `.claude/agents/<name>.md` as system prompt.

## Task

Validate the most recent plan.

## Invocation

1. Use the Bash tool to auto-detect the latest plan and run the reviewer:

```bash
# Find the most recently saved plan
PLAN_FILE=$(ls -t .claude/plans/plan-*.md 2>/dev/null | head -1)

if [ -z "$PLAN_FILE" ]; then
  echo "ERROR: No plan files found in .claude/plans/. Run /plan first."
  exit 1
fi

echo "Reviewing: $PLAN_FILE"
PLAN_CONTENT=$(cat "$PLAN_FILE")

REVIEWER_MSG="Review the following implementation plan and ops.json.

Respond in EXACTLY this format — no deviations:

=== REVIEW ===
SCORE: <integer 0-100>
DECISION: APPROVED | CONDITIONAL | REVISE | REJECTED
CRITICAL_MAJOR_COUNT: <integer>
ISSUES:
- [CRITICAL] <issue> — Location: <where> — Fix: <how>
- [MAJOR] <issue> — Location: <where> — Fix: <how>
- [MINOR] <issue> — Location: <where> — Fix: <how>
(write ISSUES: none if no issues found)
=== END REVIEW ===

DECISION RULES:
APPROVED = score >= 90 AND CRITICAL_MAJOR_COUNT == 0
CONDITIONAL = score 70-89 OR CRITICAL_MAJOR_COUNT > 0
REVISE = score < 70
REJECTED = no ops.json, invalid ops.json, destructive ops without rollback

PLAN TO REVIEW:
$PLAN_CONTENT"

review_output=$(echo "$REVIEWER_MSG" | claude -p --agent reviewer --model opus --allowedTools "Read,Grep,Glob")
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "ERROR: Reviewer agent failed (exit code $EXIT_CODE). Check that .claude/agents/reviewer.md exists."
  exit 1
fi

echo "$review_output"
```

2. After output, suggest:
   - If APPROVED (score ≥ 90): run `/implement`
   - If CONDITIONAL/REVISE: address issues and re-run `/plan` or `/refine`
   - If REJECTED: restate the task more narrowly and re-run `/plan`
