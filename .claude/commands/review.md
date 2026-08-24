---
description: "Validate plan via reviewer agent (90% threshold)"
model: opus
---

# Reviewer Command

Spawns the local `reviewer` agent on its **`balanced` capability tier** (`.claude/model-policy.json`;
escalate to `most-capable` per the role's `escalate_when` — multi-phase, architecture, or security
plans) — Task tool (`subagent_type: "reviewer"`) in
interactive sessions (default; no cold boot); `claude -p --agent reviewer` for scripted/CI
paths. Same `REVIEWER_MSG` and output contract either way.
Verified mechanism: `--agent <name>` loads `.claude/agents/<name>.md` as system prompt.
Canonical spawn contract: see `.claude/agents/_shared/INVOCATION.md` (single source of truth).

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
# Resolve the ops.json this plan owns (all naming forms; ambiguity is an error).
OPS_FILE=$(python3 .claude/operations/scripts/review-record.py resolve "$PLAN_FILE")
if [ $? -ne 0 ] || [ -z "$OPS_FILE" ]; then
  echo "ERROR: could not resolve a unique ops.json for $PLAN_FILE (missing or ambiguous)."
  exit 1
fi

# DELTA MODE: if this plan already has a recorded verdict and only the ops.json moved,
# hand the reviewer the diff instead of a full re-read. review-record.py diff prints
# "(no changes since approval)" and "# FULL REVIEW REQUIRED" with exit 0 too — both mean
# NO delta block (normal/full review runs unmodified). Only a real diff qualifies.
DELTA_BLOCK=""
DIFF_OUT=$(python3 .claude/operations/scripts/review-record.py diff "$PLAN_FILE" "$OPS_FILE" 2>/dev/null)
DIFF_EXIT=$?
if [ $DIFF_EXIT -eq 0 ] && [ -n "$DIFF_OUT" ]; then
  case "$DIFF_OUT" in
    "(no changes since approval)"*|"# FULL REVIEW REQUIRED"*) : ;;
    *)
      echo "Delta review: ops.json changed since the last recorded verdict."
      DELTA_BLOCK="

DELTA REVIEW MODE — a prior review already recorded a verdict for a different version of
this ops.json. Changed content (approved -> current) and the prior findings are below,
deliberately WITHOUT the prior score, so you re-judge rather than reaffirm. You MUST still
verify the CHANGED anchors against the filesystem. Re-score the plan as a whole.

$DIFF_OUT"
      ;;
  esac
fi

REVIEWER_MSG="Review the implementation plan at $PLAN_FILE and the ops config at $OPS_FILE.
Read them yourself with your Read tool — do not expect the contents pasted here.

Before scoring, attempt to REFUTE the plan: verify via Read/Grep that the files, paths, and
anchors referenced in ops.json actually exist in the repo. A plan claim contradicted by the
filesystem is a CRITICAL issue. Ask: what repo state or edge case makes this ops.json fail?

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
**Decision values and score bands: [HANDOFF_PROTOCOL.md](../agents/HANDOFF_PROTOCOL.md#reviewer-decision-taxonomy) is the single definition — findings gate before score.**
REJECTED = no ops.json, invalid ops.json, destructive ops without rollback$DELTA_BLOCK"

review_output=$(echo "$REVIEWER_MSG" | claude -p --agent reviewer --model sonnet --allowedTools "Read,Grep,Glob")
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "ERROR: Reviewer agent failed (exit code $EXIT_CODE). Check that .claude/agents/reviewer.md exists."
  exit 1
fi

echo "$review_output"

# Bind this verdict to the exact ops.json that was scored. Parsing happens inside the
# script (strict anchored patterns), so an echoed format template cannot be mistaken
# for a real verdict. A failed write is reported, never swallowed.
printf '%s' "$review_output" | \
  python3 .claude/operations/scripts/review-record.py write "$PLAN_FILE" "$OPS_FILE" --from-review - \
  || echo "WARNING: verdict NOT recorded — /implement will report NO RECORD until /review succeeds." >&2
```

2. **Record the verdict (Task-tool path).** The bash block above only runs on the
   scripted `claude -p` path. When the reviewer ran via the Task tool (the interactive
   default), save its raw output to a file and record it yourself — a review whose verdict
   was never recorded is not an approval:
   ```bash
   python3 .claude/operations/scripts/review-record.py resolve "$PLAN_FILE"
   ```
   ```bash
   python3 .claude/operations/scripts/review-record.py write "$PLAN_FILE" "<resolved-ops-path>" --from-review "<saved-output-file>"
   ```
   Skipping this step means `/implement`'s STEP 0 gate refuses with exit 3 (no record) —
   it fails closed, not silently.

3. After output, suggest:
   - If APPROVED (score ≥ 90): run `/implement`
   - If CONDITIONAL/REVISE: address issues and re-run `/plan` or `/refine`
   - If REJECTED: restate the task more narrowly and re-run `/plan`
