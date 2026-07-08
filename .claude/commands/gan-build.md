---
description: "GAN-style adversarial build loop: Generator produces, fresh Evaluator scores, Adjudicator converges. Stops only when score meets threshold or max iterations reached."
argument-hint: "<task description> [--threshold N] [--max-iter N] [--mode standard|quality|strict|fast]"
model: sonnet
---

# GAN Build Command

Runs the GAN harness — a generate-evaluate-iterate loop where an independent Evaluator (spawned fresh each iteration) scores the Generator's output against a configurable threshold. The Adjudicator decides when to iterate or converge.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **gan-harness** - GAN loop protocol, roles, anti-anchoring rules
- **verification-loop** - Post-convergence quality gate

## Task

Build via GAN harness: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Options

```bash
ARGS="$ARGUMENTS"
THRESHOLD=80
MAX_ITER=3
MODE="standard"

# Extract threshold
if echo "$ARGS" | grep -q '\-\-threshold'; then
    THRESHOLD=$(echo "$ARGS" | grep -oE '\-\-threshold\s+[0-9]+' | grep -oE '[0-9]+')
fi

# Extract max iterations
if echo "$ARGS" | grep -q '\-\-max-iter'; then
    MAX_ITER=$(echo "$ARGS" | grep -oE '\-\-max-iter\s+[0-9]+' | grep -oE '[0-9]+')
fi

# Mode overrides threshold and max-iter
if echo "$ARGS" | grep -q '\-\-mode'; then
    MODE=$(echo "$ARGS" | grep -oE '\-\-mode\s+\S+' | awk '{print $2}')
    case "$MODE" in
        fast)     THRESHOLD=70; MAX_ITER=2 ;;
        standard) THRESHOLD=80; MAX_ITER=3 ;;
        quality)  THRESHOLD=90; MAX_ITER=5 ;;
        strict)   THRESHOLD=95; MAX_ITER=5 ;;
    esac
fi

TASK=$(echo "$ARGS" | sed 's/--threshold\s\+[0-9]\+//; s/--max-iter\s\+[0-9]\+//; s/--mode\s\+\S\+//' | xargs)
echo "Task: $TASK"
echo "Mode: $MODE | Threshold: $THRESHOLD | Max iterations: $MAX_ITER"
```

### Step 2: Initialize Generator

Invoke the Generator (Sonnet) with the task spec:

**Generator prompt:**
```
Task: <TASK>
Mode: <MODE>

Produce a complete implementation. Do not leave stubs or TODOs.
Output your artifact as the full file content (or diff if modifying existing code).
Begin producing now.
```

Capture the Generator's output as `artifact_v1`.

### Step 3: Evaluation Loop

For iteration 1 to MAX_ITER:

**3a. Mechanical pre-check (BEFORE spending an Evaluator):** run the cheap compile/syntax
check from Step 4 on the artifact. If it fails, skip the Evaluator this iteration and feed
the compiler output to the Generator as automatic critique #1 — never burn iterations
converging on prose quality for code that doesn't compile.

**3b. Spawn fresh Evaluator (Opus) with NO prior context** — spawn per
`.claude/agents/_shared/INVOCATION.md` (`claude -p --model opus`, no agent file needed for
this ad-hoc role — no local agent definition exists for "Evaluator").
HARD RULE (fresh-state guard): the iteration's score is undefined until THIS Evaluator
returns output — never reuse or remember a previous iteration's score.

```
You are seeing this artifact for the first time. Score it on its own merits.

ARTIFACT:
<artifact content>

SCORING RUBRIC (score each 0-100, weighted):
- Correctness (35%): Does it fully and accurately accomplish the task?
- Quality (25%): Is it clean, idiomatic, and maintainable?
- Completeness (20%): Are edge cases, errors, and boundaries handled?
- Clarity (10%): Is intent obvious to a reader unfamiliar with the task?
- Safety (10%): No security holes, dangerous patterns, or data loss risk?

REQUIRED OUTPUT FORMAT:
SCORE: <composite 0-100>

DIMENSION BREAKDOWN:
- Correctness (35%): <score> — <specific observation>
- Quality (25%): <score> — <specific observation>
- Completeness (20%): <score> — <specific observation>
- Clarity (10%): <score> — <specific observation>
- Safety (10%): <score> — <specific observation>

TOP CRITIQUES (ordered by impact, max 3):
1. [DIMENSION] <specific actionable critique with line reference if applicable>
2. [DIMENSION] <specific actionable critique>
3. [DIMENSION] <specific actionable critique>
```

**3c. Adjudicator evaluates result:**

```
IF score >= THRESHOLD:
  → CONVERGED (exit loop)

IF iteration >= MAX_ITER:
  → ESCALATE (exit loop with partial result)

ELSE:
  → Extract top 3 critiques
  → Pass to Generator for refinement
```

**3d. Generator refines (if continuing):**

```
Your previous output scored <score>/<threshold>.

Top critiques to address:
1. <critique 1>
2. <critique 2>
3. <critique 3>

Address ALL three critiques. State what you changed in a brief "Changes made:" block before the artifact. Do not introduce features beyond what's needed to address these critiques.
```

### Step 4: Post-Convergence Gate

After the loop exits with CONVERGED status, run verification:

```bash
# Apply the artifact (write files or apply diff)
# Then run appropriate checks for the project type — capture EXIT CODES, not truncated tails:
[ -f "tsconfig.json" ] && { npx tsc --noEmit; echo "tsc exit: $?"; }
[ -f "pyproject.toml" ] && { python3 -m py_compile <generated files>; echo "py_compile exit: $?"; }
[ -f "go.mod" ] && { go build ./...; echo "go build exit: $?"; }
# And run the test suite for the touched areas — compiling is not passing:
# <project test command scoped to affected modules>; echo "tests exit: $?"
```

If verification fails, run one targeted fix cycle (not a full GAN iteration). The final
report quotes these executed results verbatim.

### Step 5: Report

```
GAN BUILD COMPLETE
==================
Task: <task>
Mode: <mode> | Threshold: <threshold>
Iterations used: <N> / <max>
Final score: <score>

Dimension scores:
  Correctness: <score>
  Quality: <score>
  Completeness: <score>
  Clarity: <score>
  Safety: <score>

Status: CONVERGED | ESCALATED

Files created/modified:
  + <path>
  ~ <path>

Post-convergence gate: PASS | FAIL

Next steps:
  /prp-commit "<description>"    — commit the result
  /santa <file>                  — adversarial dual review (recommended for strict mode)
  /code-review <file>            — full code review
```

If ESCALATED:
```
GAN BUILD — ESCALATION
========================
Final score: <score> (threshold: <threshold>)
Iterations exhausted: <max>

The artifact reached score <score> but could not converge on:
  - <unresolved critique 1>
  - <unresolved critique 2>

Artifact is at PARTIAL quality. Human review required before use.
Options:
  - Increase --max-iter and retry
  - Switch to --mode quality with more iterations
  - Review manually and fix remaining issues
```

---

## Usage Examples

- `/gan-build "implement rate limiter middleware"` — standard mode, threshold 80
- `/gan-build "write auth token rotation" --mode strict` — threshold 95, max 5 iterations
- `/gan-build "draft changelog entry for v1.3.0" --mode fast` — threshold 70, max 2
- `/gan-build "implement SQL pagination" --threshold 90 --max-iter 4` — explicit config

## Notes

- The Evaluator is ALWAYS spawned fresh — this is what makes the loop adversarial, not incremental
- Generator never sees Evaluator scores — only the top 3 critiques
- Adjudicator is the only role that tracks iteration state
- For security-critical code, always use `--mode strict` and follow with `/santa`
- `--mode fast` is for drafts only — never use for production code
