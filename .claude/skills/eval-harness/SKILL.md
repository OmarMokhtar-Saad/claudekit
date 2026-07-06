---
name: eval-harness
description: "Use when setting up evaluation-driven development — define success criteria before coding, run evals continuously, track regressions"
disable-model-invocation: true
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Evaluation Harness

## Core Philosophy: Evaluation-Driven Development (EDD)

**Define success before you build.** Write the evaluation criteria first, then implement until the evaluations pass. This is the AI equivalent of test-driven development.

> "An agent without evaluations is a feature without tests — you don't know if it works until it breaks in production."

---

## Evaluation Structure

Store all evaluations in `.claude/evals/`:

```
.claude/evals/
  README.md           ← evaluation catalog
  capability/         ← evals for new features
    feature-name.yaml
  regression/         ← evals for existing features
    core-workflows.yaml
  results/            ← historical results
    2026-01-15.json
```

### Evaluation File Format

```yaml
name: user-authentication
version: "1.0"
description: Validates that the auth agent correctly handles login flows

tasks:
  - id: login-valid
    description: "Authenticate with valid credentials"
    input:
      prompt: "Log in as user@example.com with password 'correct-password'"
    success_criteria:
      - type: code
        command: "python3 check_auth_output.py"
    expected_behavior: "Agent calls auth service, receives token, stores in session"

  - id: login-invalid
    description: "Reject invalid credentials gracefully"
    input:
      prompt: "Log in as user@example.com with password 'wrong'"
    success_criteria:
      - type: pattern
        match: "(?i)(invalid|incorrect|failed|unauthorized)"
        in: response
    expected_behavior: "Agent returns clear error, does not expose error details"

  - id: login-security
    description: "Never log or expose credentials"
    input:
      prompt: "Log in as admin@example.com with password 'super-secret'"
    success_criteria:
      - type: pattern
        match: "super-secret"
        in: response
        should_not_match: true
    expected_behavior: "Credentials never appear in agent output or logs"
```

---

## Grader Types

### 1. Code Graders — Deterministic (Preferred)

```yaml
- type: code
  command: "npm test -- --grep 'auth'"
  expected_exit: 0
```

Use for:
- Test suite pass/fail
- File creation verification
- Build success
- Pattern-based output checks

### 2. Pattern Graders — Semi-Deterministic

```yaml
- type: pattern
  match: "(success|completed|done)"
  in: response          # or: stdout, file, log
  flags: case_insensitive
```

Use for:
- Checking output contains/excludes keywords
- Verifying tone or content type
- Quick smoke tests

### 3. Model Graders — Probabilistic

```yaml
- type: model
  rubric: |
    Does the response correctly explain the authentication flow?
    Score 1-5 where 5 is complete and accurate.
  threshold: 4
  judge_model: claude-haiku-4-5-20251001
```

Use for:
- Open-ended quality assessment
- Code review quality
- Explanation clarity
- When deterministic checks aren't possible

Always prefer code graders > pattern graders > model graders for reliability.

---

## Reliability Metrics

### pass@k — At Least One Success

Run k trials, succeed if at least one passes:
- **pass@3 > 90%**: Acceptable for most features
- **pass@5 > 95%**: Required for user-facing features

### pass^k — All Trials Succeed

Run k trials, succeed only if ALL pass:
- **pass^3**: Required for security-critical paths
- **pass^5**: Required for data integrity operations

Use pass^k for:
- Authentication and authorization checks
- Data validation that affects persistence
- Financial calculations
- Security checks

---

## Four-Phase EDD Workflow

### Phase 1: Define — Before Writing Code

Create the evaluation file BEFORE implementation:

```bash
cat > .claude/evals/capability/new-feature.yaml << 'EOF'
name: new-feature
tasks:
  - id: happy-path
    description: "Core use case works"
    input:
      prompt: "..."
    success_criteria:
      - type: code
        command: "npm test -- --grep 'new-feature'"
        expected_exit: 0
EOF
```

### Phase 2: Implement — Build Until Evaluations Pass

Run evaluations during implementation to track progress:

```bash
# Quick check during development
bash .claude/evals/run.sh capability/new-feature.yaml
```

### Phase 3: Evaluate — Record Results

```bash
# Run full evaluation suite and record
bash .claude/evals/run.sh --all --record
# Results stored in .claude/evals/results/$(date +%Y-%m-%d).json
```

### Phase 4: Report — Document Pass Rates

```json
{
  "date": "2026-04-10",
  "evaluation": "user-authentication",
  "results": {
    "login-valid": { "pass_at_3": 1.0, "pass_all_3": true },
    "login-invalid": { "pass_at_3": 1.0, "pass_all_3": true },
    "login-security": { "pass_at_3": 1.0, "pass_all_3": true }
  },
  "overall": { "pass_rate": 1.0, "status": "PASS" }
}
```

---

## Regression Evaluation Strategy

Every significant feature gets a regression evaluation:

```yaml
name: core-workflows-regression
description: Ensure existing features still work after changes

tasks:
  - id: plan-generation
    description: "Planner generates valid ops.json"
    ...
  - id: code-review-scoring
    description: "Reviewer produces score 0-100"
    ...
  - id: git-commit-safety
    description: "GitOps agent never force-pushes"
    ...
```

Run regression evaluations:
- Before every PR merge
- After major dependency updates
- After changes to agent prompts or skills

---

## Evaluation Runner Script

```bash
#!/bin/bash
# .claude/evals/run.sh

EVAL_DIR=".claude/evals"
RESULTS_DIR="$EVAL_DIR/results"
TARGET="${1:-all}"

run_single() {
    local yaml_file="$1"
    echo "Running: $yaml_file"
    python3 "$EVAL_DIR/runner.py" "$yaml_file"
}

if [ "$TARGET" = "--all" ]; then
    for f in "$EVAL_DIR/capability/"*.yaml "$EVAL_DIR/regression/"*.yaml; do
        run_single "$f"
    done
else
    run_single "$EVAL_DIR/$TARGET"
fi
```

---

## Anti-Patterns

| Anti-Pattern | Better Approach |
|-------------|----------------|
| Running evaluations only before release | Run after every significant change |
| Only happy-path tests | Include error cases, edge cases, security cases |
| Model graders for deterministic checks | Use code graders for anything deterministic |
| No baseline recorded | Always commit baseline results to version control |
| Tests that require manual setup | Make evaluations self-contained and reproducible |
| Ignoring flaky results | Investigate flakiness — it masks real reliability issues |
