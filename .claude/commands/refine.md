---
description: "Automatically loop planner → reviewer until plan scores ≥ 90 with no issues. Sends reviewer feedback back to planner each cycle."
argument-hint: "<task description> [--max-iter N]"
model: sonnet
---

# Refine Command

Runs the plan-review refinement loop: the planner produces a plan, the reviewer scores it, and if the score is below 90 or issues remain, the reviewer's feedback is fed back to the planner automatically. The cycle repeats until the plan is APPROVED or the iteration limit is reached.

**ARCHITECTURAL REQUIREMENT**: Cycle A and Cycle B run in FRESH, isolated subagent
contexts — never inline (self-review bias). Two verified mechanisms:

- **Interactive session (default): Task tool** — spawn `subagent_type: "planner"` (opus)
  for Cycle A and a fresh `subagent_type: "reviewer"` (opus) for Cycle B each iteration.
  Every spawn starts a fresh context, which preserves the anti-anchoring guarantee, with
  no cold boot.
- **Scripted/CI: ONE self-contained Bash script** running the whole loop (all iterations)
  in a single Bash tool call — same isolation (each `claude -p --agent <name>` spawn is
  still a fresh process/context), ~13s cold boot per spawn (measured; worse in MCP-heavy
  projects).

**Delivery contract: paths, never payloads.** Plans and ops configs live on disk for the
ENTIRE loop; only a per-iteration scoreboard (iteration, score, decision, issue count) and
final file paths ever enter the main session's context. Concretely:
- The planner (interactive: Task tool; scripted: `claude -p --agent planner`) WRITES
  `.claude/plans/plan-<slug>.md` and `.claude/plans/ops-<slug>.json` itself on iteration 1,
  and EDITS those same two files in place on revision iterations — it never re-emits the
  full plan body into a response or a shell variable that then gets echoed.
- The reviewer is handed the two FILE PATHS ("Review the plan at `<PLAN_FILE>` and ops
  config at `<OPS_FILE>`. Read them yourself.") and reads them with its own Read tool —
  never the plan text pasted into its prompt.
- Only the reviewer's small structured score block (`=== REFINE REVIEW ITERATION N ===`)
  enters context each iteration; that IS the scoreboard, not a leak.
- A shell variable holding the full plan body must never be interpolated into a later
  Bash `echo`/heredoc — this was the root cause fixed here (see Step 2).

Canonical spawn contract: see `.claude/agents/_shared/INVOCATION.md` (single source of truth).

## Mandatory Skills

- **using-superpowers** - Core agent capabilities
- **writing-plans** - Structured plan authoring format
- **validate-operations-config** - ops.json validation

## Task

Refine plan for: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Options

```
ARGS="$ARGUMENTS"
MAX_ITER=5

if ARGS contains "--max-iter N":
    MAX_ITER = N

TASK = ARGS with --max-iter stripped
```

Decide the plan/ops file paths ONCE, before iteration 1 (a slug derived from the task):
```
PLAN_FILE = ".claude/plans/plan-<slug>.md"
OPS_FILE  = ".claude/plans/ops-<slug>.json"
```

Initialize loop state (NEVER inherit from prior conversation context):
```
iteration            = 1
last_score           = -1    ← must stay -1 until the reviewer subagent runs this invocation
decision             = "PENDING"
critical_major_count = 999
status               = "PENDING"
reviewer_feedback    = ""
iteration_history    = []    ← list of {iteration, score, issue_count}
```

The plan body itself is never held as a loop-state variable — it lives at `PLAN_FILE` /
`OPS_FILE` on disk for the whole loop (see Step 2's delivery-contract note).

**HARD RULE: Do NOT read any SCORE, DECISION, or reviewer output from earlier in this conversation.
Each loop invocation is a fresh run. last_score = -1 until the reviewer SUBAGENT returns output.**

Print:
```
REFINE LOOP STARTING
=====================
Task: <TASK>
Max iterations: <MAX_ITER>
Threshold: score >= 90 AND no CRITICAL or MAJOR issues
Method: Independent subagents (Agent tool) — adversarial planner/reviewer separation
```

---

### Step 2: Iteration Loop

Maintain state across iterations:
- `iteration` — current cycle number (starts at 1)
- `PLAN_FILE` / `OPS_FILE` — fixed paths decided ONCE, before iteration 1
  (`.claude/plans/plan-<slug>.md` / `.claude/plans/ops-<slug>.json`); every iteration reads
  and writes THESE SAME two files in place. The plan body never travels through a shell
  variable that outlives one Bash call, and never gets echoed.
- `reviewer_feedback` — CRITICAL+MAJOR issues returned by the reviewer subagent (small text,
  fine to hold in context — this is the scoreboard, not the payload)
- `last_score` — numeric score from the reviewer (0–100)
- `status` — PENDING → APPROVED | ESCALATED
- `iteration_history` — append `{iteration, score, issue_count}` after each Cycle B

**Interactive session (default):** every Cycle A / Cycle B below is one Task tool call in
THIS same conversation turn sequence — no separate Bash-tool-call boundary, so there is no
shell-variable-doesn't-persist problem to begin with. Still write plan/ops to
`PLAN_FILE`/`OPS_FILE` (never inline them in the spawn message or the response) so the
pattern matches the scripted path and the anti-anchoring guarantee (fresh subagent context
per cycle) is unaffected either way.

**Scripted/CI:** the ENTIRE loop (every iteration's Cycle A, B, C) runs inside ONE Bash tool
call as a single self-contained script. This is the fix for the original bug: shell
variables (`current_plan=$(...)`) do NOT persist across SEPARATE Bash tool calls, which
previously forced the plan text to be pasted by hand into the next call's heredoc (the
observed ~26k-token leak). Inside one script, ordinary shell variables/loops work fine —
but even so, do NOT hold the plan body in a variable longer than the single `claude -p`
call that produced it: write it to `$PLAN_FILE` immediately (`printf '%s\n' > file`, never
`tee`/`echo`) and pass only the PATH to the next spawn.

---

#### Cycle A: Planner

**Interactive:** spawn `subagent_type: "planner"` (opus) via the Task tool.
- Iteration 1: "Create a complete implementation plan for: `<TASK>`. Explore with BATCHED
  parallel Read/Grep/Glob (one message). IRON LAW: must include a valid ops.json. Write the
  plan to `<PLAN_FILE>` and the ops config to `<OPS_FILE>` yourself (Write tool); do not
  print their contents in your response. Return only the paths and a ≤10-line summary."
- Iteration 2+: "Revise the plan at `<PLAN_FILE>` (ops config at `<OPS_FILE>`) for: `<TASK>`.
  Iteration `<N>`/`<MAX_ITER>`. The reviewer scored the previous version `<last_score>`/100
  and found: `<reviewer_feedback>`. Read both files yourself, address EVERY issue, and EDIT
  them in place (Write tool) — do not print the revised contents. Return only a ≤10-line
  change summary."

**Scripted (inside the single loop script):**
```bash
# Iteration 1 only:
PLANNER_MSG="Create a complete implementation plan for the following task.

Task: <TASK>

Before writing anything, explore the codebase with BATCHED parallel Read/Grep/Glob calls —
fire all independent searches in ONE message.

IRON LAW: the plan MUST include a valid ops.json.
Report only a short summary in your response — the wrapper below saves your output to disk."

plan_output=$(echo "$PLANNER_MSG" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write,Bash(python3 .claude/operations/scripts/validate-config-json.py *)")
printf '%s\n' "$plan_output" > "$PLAN_FILE"
python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE"
unset plan_output   # never echo it — the file is now the source of truth

# Iteration 2+ (same script, later loop pass):
PLANNER_MSG="Revise the implementation plan for the following task.

Task: <TASK>

REVISION REQUEST — Iteration <N>/<MAX_ITER>
The reviewer scored the previous plan <last_score>/100 and found these issues:
<reviewer_feedback as numbered list>

The current plan is at $PLAN_FILE and the ops config at $OPS_FILE — read them if you need
to (you do not have Write access headless; this wrapper captures your revised output and
writes it to disk). Address EVERY issue. State what changed, then output the complete
revised plan and a new ops.json — the wrapper saves it; do not expect to Write it yourself."

plan_output=$(echo "$PLANNER_MSG" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Bash(python3 .claude/operations/scripts/validate-config-json.py *)")
printf '%s\n' "$plan_output" > "$PLAN_FILE"
python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE"
unset plan_output
```

Headless `claude -p` spawns cannot Write into `.claude/**` (platform sensitive-path gate) —
that is why the wrapper script itself, not the model, moves the bytes to `$PLAN_FILE`/
`$OPS_FILE` each time. The script's own stdout during this cycle stays silent (no `echo
"$plan_output"`); only the scoreboard printed at the end of Cycle C reaches the caller.

---

#### Cycle B: Reviewer

**Interactive:** spawn a FRESH `subagent_type: "reviewer"` (opus) via the Task tool. Pass
ONLY the file paths — no loop state, no prior review history:

"Review the implementation plan at `<PLAN_FILE>` and the ops config at `<OPS_FILE>`. Read
them yourself. Respond in EXACTLY this format: [format block below]."

**Scripted (same script):**
```bash
REVIEWER_MSG="Review the implementation plan at $PLAN_FILE and the ops config at $OPS_FILE.
Read them yourself with your Read tool — do not expect the contents pasted here.

Respond in EXACTLY this format — no deviations:

=== REFINE REVIEW ITERATION <N> ===
SCORE: <integer 0-100>
DECISION: APPROVED | CONDITIONAL | REVISE | REJECTED
CRITICAL_MAJOR_COUNT: <integer>
ISSUES:
- [CRITICAL] <issue> — Location: <where> — Fix: <how>
- [MAJOR] <issue> — Location: <where> — Fix: <how>
- [MINOR] <issue> — Location: <where> — Fix: <how>
(write ISSUES: none if no issues found)
=== END REVIEW ITERATION <N> ===

DECISION RULES:
APPROVED = score >= 90 AND CRITICAL_MAJOR_COUNT == 0
CONDITIONAL = score 70-89 OR CRITICAL_MAJOR_COUNT > 0
REVISE = score < 70
REJECTED = no ops.json, invalid ops.json, destructive ops without rollback"

review_output=$(echo "$REVIEWER_MSG" | claude -p --agent reviewer --model opus --allowedTools "Read,Grep,Glob")
echo "$review_output"
```

`review_output` is the scoreboard block itself — small by design (a dozen lines), so
printing it is fine; it is not the plan/ops payload. Store `stdout` as `review_output`.
Parse it for `last_score`, `decision`, `critical_major_count`, `reviewer_feedback` from
inside the `=== REFINE REVIEW ITERATION <N> ===` delimiters.

Parse from the reviewer subagent's output (look only inside the
`=== REFINE REVIEW ITERATION <N> ===` ... `=== END REVIEW ITERATION <N> ===` block):
- `last_score` — the integer after `SCORE:`
- `decision` — the word after `DECISION:`
- `critical_major_count` — the integer after `CRITICAL_MAJOR_COUNT:`
- `reviewer_feedback` — everything under `ISSUES:`, excluding MINOR issues
  (MINORs are tracked in iteration_history but do NOT block convergence)

Append to iteration_history: `{iteration: <N>, score: last_score, issue_count: critical_major_count}`

---

#### Cycle C: Convergence Check

**HARD RULE: last_score must be -1 until the reviewer subagent returns output in this iteration's
Cycle B. A last_score of -1 means Cycle B has NOT completed — convergence CANNOT be declared.**

Use a fall-through exit-condition pattern (check exits first; non-exit paths fall through to increment):

```
# Guard: reviewer subagent has not completed
IF last_score == -1:
    → ABORT — reviewer did not return a score. Log error. Do NOT declare convergence.

# Exit condition 1: approved
IF decision == "APPROVED" AND last_score >= 90 AND critical_major_count == 0:
    → EXIT LOOP with status = APPROVED

# Exit condition 2: iteration cap reached
IF iteration >= MAX_ITER:
    → EXIT LOOP with status = ESCALATED (max iterations reached)

# Exit condition 3: fundamental rejection (not fixable by iteration)
IF decision == "REJECTED" AND iteration >= 3:
    → EXIT LOOP with status = ESCALATED (repeated fundamental rejection)

# Fall-through: all non-exit paths reach here and increment unconditionally
iteration += 1
→ continue to Cycle A (planner revision with reviewer_feedback)
```

Note: `CONDITIONAL` (score 70–89) and `REVISE` (score < 70) are revision signals — they fall
through to the increment and loop back. They do NOT trigger early exit.

Print per-cycle summary:
```
--- Iteration <N>/<MAX_ITER> ---
Score:    <score>/100
Decision: <APPROVED|CONDITIONAL|REVISE|REJECTED>
Issues:   <critical_major_count> CRITICAL+MAJOR blocking
Next:     <CONVERGED|REVISING|ESCALATING>
```

---

### Step 3: Final Report

**On APPROVED — verify before you report it.** The success banner's evidence line must be
EARNED, not templated. `PLAN_FILE`/`OPS_FILE` already hold the approved content (every
iteration wrote in place — nothing to save now); just re-validate and dry-run and paste the
real results:

```bash
python3 .claude/operations/scripts/validate-config-json.py "$OPS_FILE"
python3 .claude/operations/scripts/execute-json-ops.py "$OPS_FILE" --dry-run
```

If either fails, the plan is NOT approved — feed the failure back as reviewer feedback and
continue the loop (or escalate if out of iterations).

```
REFINE LOOP — PLAN APPROVED
=============================
Task: <TASK>
Iterations used: <N> / <MAX_ITER>
Final score: <score>/100
Decision: APPROVED

Iteration history:
  [1] Score: <s> — <issue count> CRITICAL+MAJOR issues
  [2] Score: <s> — <issue count> CRITICAL+MAJOR issues
  ...
  [N] Score: <s> — APPROVED

ops.json: <paste the actual validator + dry-run results — never claim this unexecuted>

Next step: run /implement to execute the approved plan
```

**On ESCALATED (max iterations reached):**

```
REFINE LOOP — ESCALATION REQUIRED
====================================
Task: <TASK>
Max iterations reached: <MAX_ITER>
Best score achieved: <best_score>/100

The plan did not reach the approval threshold. Unresolved issues:
<reviewer_feedback from last iteration>

Options:
  1. Run /refine "<TASK>" --max-iter <MAX_ITER + 3>  — give more iterations
  2. Review the issues manually and run /plan with a revised approach
  3. Run /coordinator "<TASK>"  — let the coordinator decide the next agent

Human review required before proceeding to /implement.
```

**On ESCALATED (repeated REJECTED):**

```
REFINE LOOP — FUNDAMENTAL REJECTION
======================================
Task: <TASK>
Rejected at iteration <N> after <N-1> revision attempts.

The reviewer flagged fundamental problems that iteration cannot resolve:
<critical issues list>

This usually means the task scope or approach needs rethinking.
Suggested actions:
  1. Restate the task more narrowly and run /refine again
  2. Run /coordinator for a fresh approach
  3. Run /debug if the root cause is unclear
```

---

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--max-iter N` | 5 | Maximum plan-review cycles before escalation |

## Usage Examples

- `/refine "add rate limiting to the API"` — up to 5 iterations, threshold 90
- `/refine "refactor auth middleware" --max-iter 3` — tighter iteration budget
- `/refine "implement user notification system"` — full refinement with automatic convergence

## Notes

- **Subagent isolation is mandatory** — Cycle A and Cycle B MUST use the Agent tool. Inline
  execution in the same context window causes self-review bias: the model scores its own plan
  90+ and converges after 1 iteration regardless of plan quality. Subagents get clean contexts.
- **Planner receives only task + feedback** — never the reviewer's full output, never prior plans.
  The reviewer receives only the FILE PATH to the plan/ops — never the plan text pasted into
  its prompt, never the refine loop context or prior reviews.
- **Files, not shell variables, carry the plan across iterations** — `PLAN_FILE`/`OPS_FILE`
  are fixed once and every Cycle A writes/edits them in place; no `current_plan=$(...)` shell
  variable survives past the single Bash call that produced it, and nothing pastes the plan
  body into a later heredoc or prompt. This is what keeps a full refine run under ~3k tokens
  of plan-content in the main context, instead of the ~26k-token heredoc leak this replaced.
- **Fresh state every invocation** — `last_score = -1` until the reviewer subagent completes.
  The loop cannot converge on a stale score from a prior `/review` in the conversation.
- **Delimiter blocks prevent context bleed** — reviewer output is wrapped in
  `=== REFINE REVIEW ITERATION N ===` ... `=== END REVIEW ITERATION N ===`. Parser reads only
  inside the current iteration's block.
- **CONDITIONAL is a first-class decision** — treated identically to REVISE (triggers next cycle).
- **Convergence requires three conditions simultaneously**: `decision == APPROVED` AND
  `last_score >= 90` AND `critical_major_count == 0`. APPROVED + MAJOR issues cannot escape.
- **MINOR issues are tracked** in iteration_history but do not block convergence. The planner
  receives a FYI note about MINORs alongside the blocking CRITICAL+MAJOR issues.
- **A REJECTED decision on iteration ≥ 3 triggers immediate escalation** — repeated rejection
  signals a scope or approach problem, not an iteration-solvable quality problem.
- **Cycle C uses fall-through exits** — exit conditions are checked first and return. All
  non-exit paths fall through to an unconditional `iteration += 1`. There is no ELSE chain.
