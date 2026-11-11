---
description: "Validate plan via reviewer agent (90% threshold)"
model: opus
---

# Reviewer Command

Spawns `reviewer` on its **`balanced` tier** (`.claude/model-policy.json`; `most-capable` per
`escalate_when`) — Task tool (`subagent_type: "reviewer"`) interactively (default; no cold boot),
`claude -p --agent reviewer` for scripted/CI paths; same `REVIEWER_MSG` and output contract.
Spawn contract: `.claude/agents/_shared/INVOCATION.md` (single source of truth).

## Task

Validate the most recent plan. The reviewer is STATIC-ONLY (no Bash — it executed nothing).
If the plan touches hooks, tests or executable scripts, its verdict may NOT be the last
review before implementation; follow it with `/code-review` on the plan, where
`code-reviewer` has Bash and runs the plan's own Validation commands against a scratch copy.
Reviews are on request: Tier 3 plans need one, Tier 1/2 do not.
PANEL: unless `--no-panel` (or `CK_REVIEW_PANEL=off`), `plan-design-critic` and `plan-readiness-critic` run beside `reviewer` as in `.claude/agents/_shared/REVIEW_PANEL.md` (advisory; only `reviewer`'s block is recorded).

## Invocation

0. **Arguments.** Pass `$ARGUMENTS` verbatim to step 1 (`--no-panel`, optional plan path).
1. **Resolve the plan and the panel.** Bash:
   ```bash
   python3 .claude/operations/scripts/review-panel.py prompts $ARGUMENTS
   ```
   It prints `PLAN: <path>`, `PANEL: on|off (<why>)` and `CRITIC_PROMPT: Plan: <path>. Review it.`
   (`ERROR: no plan` → tell the user to run `/plan` first and stop.)
2. **Spawn — In ONE message.** Task tool: `reviewer` with `REVIEWER_MSG` (in the scripted block
   below; `$PLAN_FILE` = the `PLAN:` path) and, when `PANEL: on`, `plan-design-critic` and
   `plan-readiness-critic`, each with the `CRITIC_PROMPT` line **verbatim and nothing else** — no
   history, brief or word limit (`panel-guard.py` denies anything else). All three go in the same
   message so they run in parallel. If any of these spawns is denied (context cap): stop here; the
   handoff carries the whole panel.
3. **Record the verdict (reviewer only)** — the scripted block records on its own. Via the Task
   tool, record from the reviewer's transcript by its `agentId` (the script reads the last
   `=== REVIEW ===` block and the harness-recorded role). Never copy, rewrite or summarise the
   reply; no block records nothing (re-ask, never compose one):
   ```bash
   python3 .claude/operations/scripts/review-record.py plan-write "$PLAN_FILE" --from-task "<agentId>"
   ```
   Skipped → `plan-gate` and `/implement` STEP 0 refuse with exit 3 (fail closed). File-only
   review: `--from-review "<file>" --reviewer-role reviewer`. **Record REJECTING rounds too**:
   REVISE, REJECTED and CONDITIONAL record like APPROVED and authorise nothing (`plan-check`
   still exits 4). A bare `--score/--decision` approval is owner-only (`--owner-approved`).
4. **Merge the panel** (when `PANEL: on`). Bash, then print its output verbatim:
   ```bash
   python3 .claude/operations/scripts/review-panel.py merge "$PLAN_FILE" --reviewer "<reviewer agentId>" \
     --critic plan-design-critic="<agentId>" --critic plan-readiness-critic="<agentId>"
   ```

5. Suggest (advisory; the gate is unchanged) from reviewer's DECISION **and** the panel's stop line:
   - If APPROVED (score ≥ 90): ask the user to approve, then run `/implement` — from a compacted or fresh context whose only input is the plan path (run `/compact` first if `suggest-compact` has fired); do not continue implementing inside this review conversation
   - If CONDITIONAL/REVISE: address issues, edit the plan and re-run `/review` (it scores the whole plan again)
   - If REJECTED: restate the task more narrowly and re-run `/plan`
   - Panel `CONTINUE` with an uncovered Blocker: fix it and re-run `/review` before `/implement`, whatever reviewer scored (advisory; say so). `STOP`: stop re-reviewing, carry Majors as follow-ups. `CAP`: list open findings, ask the owner

## Scripted / CI path (`claude -p`)

Same steps in one block: reviewer, record, both critics (saved per critic), then `merge`.

```bash
PANEL_OUT=$(python3 .claude/operations/scripts/review-panel.py prompts $ARGUMENTS) || {
  echo "ERROR: No plan files found in .claude/plans/. Run /plan first."; exit 1; }
echo "$PANEL_OUT"
PLAN_FILE=$(printf '%s\n' "$PANEL_OUT" | sed -n 's/^PLAN: //p')
CRITIC_PROMPT=$(printf '%s\n' "$PANEL_OUT" | sed -n 's/^CRITIC_PROMPT: //p')
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

# Bind the verdict to the scored plan bytes (strict parse in the script; failure reported).
printf '%s' "$review_output" | \
  python3 .claude/operations/scripts/review-record.py plan-write "$PLAN_FILE" --from-review - --reviewer-role reviewer \
  || echo "WARNING: verdict NOT recorded — plan-gate will report NO RECORD until /review succeeds." >&2

# Panel (advisory): both critics get CRITIC_PROMPT and nothing else; merge dedups and applies the stop rule.
if printf '%s\n' "$PANEL_OUT" | grep -q '^PANEL: on'; then
  SLUG=$(basename "$PLAN_FILE" .md)
  printf '%s' "$review_output" > ".claude/plans/$SLUG.review.md"
  MERGE_ARGS=""
  for CRITIC in plan-design-critic plan-readiness-critic; do
    OUT=".claude/plans/$SLUG.panel-$CRITIC.md"
    echo "$CRITIC_PROMPT" | claude -p --agent "$CRITIC" --allowedTools "Read,Grep" > "$OUT" 2>&1
    MERGE_ARGS="$MERGE_ARGS --critic $CRITIC=$OUT"
  done
  python3 .claude/operations/scripts/review-panel.py merge "$PLAN_FILE" \
    --reviewer ".claude/plans/$SLUG.review.md" $MERGE_ARGS
fi
```
