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

Validate the most recent plan. The reviewer is STATIC-ONLY (no Bash — it executed nothing).
If the plan touches hooks, tests or executable scripts, its verdict may NOT be the last
review before implementation; follow it with `/code-review` on the plan, where
`code-reviewer` has Bash and runs the plan's own Validation commands against a scratch copy.
Reviews are on request: Tier 3 plans need one, Tier 1/2 do not.
PANEL: unless `--no-panel`, also run `plan-design-critic` and `plan-readiness-critic` as in `.claude/agents/_shared/REVIEW_PANEL.md` (advisory; only `reviewer`'s block is recorded). The scripted block below runs them itself.

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

REVIEWER_MSG="Review the implementation plan at $PLAN_FILE.
Read it yourself with your Read tool — do not expect the contents pasted here.

Before scoring, attempt to REFUTE the plan: verify via Read/Grep that the files, paths, and
anchors the plan references actually exist in the repo, and that its Files: list covers every
path its steps write. A plan claim contradicted by the filesystem is a CRITICAL issue. Ask:
what repo state or edge case makes this plan fail when it is implemented?

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
REJECTED = no Files: list, a Files: list that omits a path the steps write, destructive steps without a rollback"

review_output=$(echo "$REVIEWER_MSG" | claude -p --agent reviewer --model sonnet --allowedTools "Read,Grep,Glob")
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "ERROR: Reviewer agent failed (exit code $EXIT_CODE). Check that .claude/agents/reviewer.md exists."
  exit 1
fi

echo "$review_output"

# Bind this verdict to the exact plan bytes that were scored. Parsing happens inside the
# script (strict anchored patterns), so an echoed format template cannot be mistaken
# for a real verdict. A failed write is reported, never swallowed.
printf '%s' "$review_output" | \
  python3 .claude/operations/scripts/review-record.py plan-write "$PLAN_FILE" --from-review - --reviewer-role reviewer \
  || echo "WARNING: verdict NOT recorded — plan-gate will report NO RECORD until /review succeeds." >&2
# Advisory panel (_shared/REVIEW_PANEL.md): never recorded, never blocks; --no-panel skips it.
case " $ARGUMENTS " in *" --no-panel "*) ;; *)
  echo "=== PANEL (scripted: raw counts, not deduplicated against reviewer) ==="
  tag='^[[:space:]]*([-*+]|[0-9]+[.)])?[[:space:]]*\*\*'
  for c in plan-design-critic plan-readiness-critic; do
    out=$(echo "Plan: $PLAN_FILE. Review it." | claude -p --agent "$c" --allowedTools "Read,Grep") \
      || { echo "$c: claude exited $?"; out=""; }
    printf '%s\n' "$out"
    last=$(printf '%s\n' "$out" | awk 'NF{l=$0} END{print l}')
    if printf '%s\n' "$last" | grep -Eq '^PANEL: [0-9]+ blocker, [0-9]+ major$'; then
      b=$(printf '%s' "$last" | sed -E 's/^PANEL: ([0-9]+) blocker.*/\1/')
      m=$(printf '%s' "$last" | sed -E 's/.* ([0-9]+) major$/\1/')
      nb=$(printf '%s\n' "$out" | grep -cE "${tag}Blocker\*\*"); nm=$(printf '%s\n' "$out" | grep -cE "${tag}Major\*\*")
      [ "$nb" -gt "$b" ] && b=$nb; [ "$nm" -gt "$m" ] && m=$nm
      echo "$c: PANEL: $b blocker, $m major"
    else echo "$c: PANEL: incomplete"; fi
  done
  echo "=== END PANEL ===" ;;
esac
```

2. **Record the verdict (Task-tool path).** The bash block above only runs on the
   scripted `claude -p` path. When the reviewer ran via the Task tool (the interactive
   default), record from the reviewer's own transcript by the `agentId` the Task tool
   returned (the script reads the last `=== REVIEW ===` block and the harness-recorded
   role, and keeps the text beside the record). Never copy, rewrite or summarise the reply
   by hand; no block records nothing (re-ask, never compose one):
   ```bash
   python3 .claude/operations/scripts/review-record.py plan-write "$PLAN_FILE" --from-task "<agentId>"
   ```
   Skipping this step means `plan-gate` and `/implement` STEP 0 refuse with exit 3 (no
   record) — they fail closed, not silently. A review that exists only as a file:
   `--from-review "<file>" --reviewer-role reviewer`.

   **Record REJECTING rounds too — not optional.** The write call is unconditional on
   purpose: REVISE, REJECTED and CONDITIONAL are recorded exactly like APPROVED, and
   recording a non-approving verdict authorises nothing — `plan-check` still exits 4.
   A bare `--score/--decision` approval is owner-only (`--owner-approved`); never mint one.

3. After output, suggest:
   - If APPROVED (score ≥ 90): ask the user to approve, then run `/implement` — from a compacted or fresh context whose only input is the plan path (run `/compact` first if `suggest-compact` has fired); do not continue implementing inside this review conversation
   - If CONDITIONAL/REVISE: address issues, edit the plan and re-run `/review` (it scores the whole plan again)
   - If REJECTED: restate the task more narrowly and re-run `/plan`
