---
name: gan-harness
description: "GAN-style generate-evaluate-iterate loop: Generator produces, Evaluator scores independently, Adjudicator decides convergence. Anti-anchoring Evaluator spawned fresh each iteration."
type: skill
version: "1.0.0"
disable-model-invocation: false
user-invocable: false
allowed-tools:
  - Agent
  - Read
  - Write
  - Bash
---

# GAN Harness Skill

Implements a Generative Adversarial Network–inspired multi-agent loop for producing high-quality outputs through adversarial refinement. Three distinct roles ensure no single agent anchors the result.

## Core Principle

**Anti-anchoring is non-negotiable.** The Evaluator must be spawned fresh each iteration with no memory of prior iterations. If the Evaluator sees its own previous scores, it anchors — the same flaws stop feeling like flaws. A fresh Evaluator sees the output as a user would: cold.

## Roles

### Generator (Sonnet)
- Produces the artifact (code, plan, analysis, text)
- On iteration > 1: reads Evaluator feedback, targets specific critiques
- NEVER reads prior Evaluator scores — only the feedback text
- Constraint: must justify every change made in response to feedback

### Evaluator (Opus — spawned fresh every iteration)
- Receives only: the artifact + the scoring rubric + the target threshold
- NEVER receives: prior scores, Generator's rationale, iteration number
- Scores 0–100 across rubric dimensions
- Provides specific, actionable critique (not vague "needs improvement")
- Returns: `SCORE: N` on its own line + structured feedback

### Adjudicator (Haiku — lightweight decision node)
- Reads: current score, target threshold, iteration count, max iterations
- Decides: CONTINUE (score < threshold, iterations remaining) or CONVERGED
- If CONTINUE: extracts top 3 critiques, passes to Generator
- If max iterations reached without convergence: ESCALATE with final state

## Protocol

```
INIT:
  artifact = Generator.produce(task_spec)
  iteration = 1

LOOP:
  score, feedback = Evaluator.fresh_spawn(artifact, rubric, threshold)
  
  IF score >= threshold OR iteration >= max_iterations:
    Adjudicator.decide(score, threshold, iteration, max_iterations)
    → CONVERGED or ESCALATE
  ELSE:
    top_critiques = Adjudicator.extract_critiques(feedback, n=3)
    artifact = Generator.refine(artifact, top_critiques)
    iteration += 1
    GOTO LOOP
```

## Scoring Rubric (Default — Override Per Use Case)

| Dimension      | Weight | Description |
|---------------|--------|-------------|
| Correctness    | 35%    | Does it do what was asked, completely and accurately? |
| Quality        | 25%    | Is it clean, idiomatic, and maintainable? |
| Completeness   | 20%    | Are edge cases, errors, and boundaries handled? |
| Clarity        | 10%    | Is intent obvious to a reader unfamiliar with the task? |
| Safety         | 10%    | No security holes, no dangerous patterns, no data loss risk? |

**Composite Score** = weighted average × 100

## Convergence Thresholds

| Mode      | Threshold | Max Iterations | Use When |
|-----------|-----------|----------------|----------|
| standard  | 80        | 3              | Most tasks |
| quality   | 90        | 5              | Code going to production |
| strict    | 95        | 5              | Security-critical, auth, payments |
| fast      | 70        | 2              | Prototypes, drafts |

## Anti-Anchoring Protocol

**What anchoring looks like:**
- Evaluator iteration 1: "Missing error handling in the retry loop."
- Evaluator iteration 2 (same instance): "Error handling improved" — anchored to prior knowledge.
- Evaluator iteration 2 (fresh instance): still flags it if the fix is incomplete.

**Enforcement:**
1. Each Evaluator Agent call uses a new `Agent()` invocation — no message history passed
2. Evaluator prompt contains ONLY: artifact content + rubric + threshold value
3. Evaluator is explicitly told: "You are seeing this artifact for the first time. Score it on its own merits."
4. Adjudicator, not Evaluator, tracks iteration history

## Feedback Format

Evaluator must return in this exact format so Adjudicator can parse reliably:

```
SCORE: 73

DIMENSION BREAKDOWN:
- Correctness (35%): 65 — Missing retry backoff in network call at line 47
- Quality (25%): 80 — Good structure, one overly complex conditional in parse()
- Completeness (20%): 70 — No handling for empty input, timeout edge case unhandled
- Clarity (10%): 85 — Well-named, one cryptic variable `tmp2`
- Safety (10%): 75 — SQL query at line 88 uses string concat — parameterize it

TOP CRITIQUES (ordered by impact):
1. [CORRECTNESS] No retry backoff — network failures will cascade. Add exponential backoff with jitter at line 47.
2. [SAFETY] SQL string concatenation at line 88. Replace with parameterized query.
3. [COMPLETENESS] Empty input returns undefined instead of raising. Add guard at entry point.
```

## Generator Refinement Contract

When given top critiques, Generator MUST:
1. Address every critique listed (not selectively)
2. State what changed in a brief "Changes made:" block
3. NOT introduce new features beyond what's needed to address critiques
4. NOT refactor code unrelated to the critiques

## Escalation

If max iterations reached without convergence:

```
GAN HARNESS — ESCALATION REPORT
=================================
Task: <description>
Iterations: <N> / <max>
Final Score: <score> / <threshold>

What passed:
  - Correctness: <score>
  - Safety: <score>

What didn't converge:
  - Completeness (<score>): <specific remaining issue>
  - <...>

Recommendation:
  The artifact is at score <N>. Remaining issues require:
  <human decision / architectural choice / scope clarification>

Artifact state: PARTIAL — review before use
```

## Usage (via /gan-build command)

```
/gan-build "implement a rate limiter middleware"
/gan-build "write a SQL migration for user preferences" --threshold 90
/gan-build "create an auth token rotation module" --mode strict
/gan-build "draft PR description for the billing refactor" --mode fast
```

## Integration with Other Skills

- Pair with **santa-method** for final adversarial review after GAN convergence
- Pair with **verification-loop** for post-GAN build/test gate
- Use **context-keeper** to save GAN session state for long-running generations
- Use **model-router** to select Generator model based on task complexity
