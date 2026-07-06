---
description: "Automatically loop planner → reviewer until plan scores ≥ 90 with no issues. Sends reviewer feedback back to planner each cycle."
argument-hint: "<task description> [--max-iter N]"
model: sonnet
---

# Refine Command

Runs the plan-review refinement loop: the planner produces a plan, the reviewer scores it, and if the score is below 90 or issues remain, the reviewer's feedback is fed back to the planner automatically. The cycle repeats until the plan is APPROVED or the iteration limit is reached.

**ARCHITECTURAL REQUIREMENT**: Cycle A and Cycle B MUST run via the Bash tool using
`claude -p --agent <name>`. This is the only verified mechanism that correctly loads local
`.claude/agents/` definitions. The `--agent planner` flag loads `planner.md` as the system
prompt of a fresh, isolated Claude process. The Agent tool's `subagent_type` parameter does
NOT resolve local agent names — it falls back to built-in types (`feature-dev:code-architect`,
`feature-dev:code-reviewer`) regardless of what name is specified.

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

Initialize loop state (NEVER inherit from prior conversation context):
```
iteration            = 1
last_score           = -1    ← must stay -1 until the reviewer subagent runs this invocation
decision             = "PENDING"
critical_major_count = 999
status               = "PENDING"
reviewer_feedback    = ""
current_plan         = ""
iteration_history    = []    ← list of {iteration, score, issue_count}
```

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
- `current_plan` — the plan artifact returned by the planner subagent
- `reviewer_feedback` — CRITICAL+MAJOR issues returned by the reviewer subagent
- `last_score` — numeric score from the reviewer (0–100)
- `status` — PENDING → APPROVED | ESCALATED
- `iteration_history` — append `{iteration, score, issue_count}` after each Cycle B

---

#### Cycle A: Planner

Use the **Bash tool** to run this command. Build `PLANNER_MSG` first, then pipe it into `claude -p`.
`--agent planner` loads `.claude/agents/planner.md` as the system prompt.

**On iteration 1:**
```bash
PLANNER_MSG="Create a complete implementation plan for the following task.

Task: <TASK>

IRON LAW: the plan MUST include a valid ops.json."

current_plan=$(echo "$PLANNER_MSG" | claude -p --agent planner --model sonnet --allowedTools "Read,Grep,Glob,Write")
echo "$current_plan"
```

**On iteration 2+:**
```bash
PLANNER_MSG="Revise the implementation plan for the following task.

Task: <TASK>

REVISION REQUEST — Iteration <N>/<MAX_ITER>
The reviewer scored the previous plan <last_score>/100 and found these issues:
<reviewer_feedback as numbered list>

Address EVERY issue. State what changed. Produce the complete revised plan and a new ops.json."

current_plan=$(echo "$PLANNER_MSG" | claude -p --agent planner --model sonnet --allowedTools "Read,Grep,Glob,Write")
echo "$current_plan"
```

Store `stdout` as `current_plan`.

---

#### Cycle B: Reviewer

Use the **Bash tool** to run this command. `--agent reviewer` loads `.claude/agents/reviewer.md`
as the system prompt. Pass ONLY `current_plan` — no loop state, no prior review history.

```bash
REVIEWER_MSG="Review the following implementation plan and ops.json.

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
REJECTED = no ops.json, invalid ops.json, destructive ops without rollback

PLAN TO REVIEW:
$current_plan"

review_output=$(echo "$REVIEWER_MSG" | claude -p --agent reviewer --model opus --allowedTools "Read,Grep,Glob")
echo "$review_output"
```

Store `stdout` as `review_output`. Parse it for `last_score`, `decision`, `critical_major_count`,
`reviewer_feedback` from inside the `=== REFINE REVIEW ITERATION <N> ===` delimiters.

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

**On APPROVED:**

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

ops.json: validated and dry-run clean

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
  The reviewer receives only the plan — never the refine loop context or prior reviews.
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
