---
description: "Run evaluation harness — define, execute, and report on agent/feature evaluations"
argument-hint: "[capability/<name>|regression/<name>|--all|--create <name>]"
model: sonnet
---

# Evaluation Harness Command

Run structured evaluations to verify agent and feature quality using evaluation-driven development principles.

## Mandatory Skills

Load before proceeding:

- **using-superpowers** - Core capabilities
- **eval-harness** - Evaluation framework and methodology

## Task

Execute evaluation: $ARGUMENTS

## Workflows

### Run Existing Evaluations

**All evaluations:**
```
/eval --all
```

**Single capability evaluation:**
```
/eval capability/user-authentication
```

**Regression suite:**
```
/eval regression/core-workflows
```

### Create New Evaluation

```
/eval --create <feature-name>
```

This creates `.claude/evals/capability/<feature-name>.yaml` with a template.

### Evaluate an Agent

```
/eval agent/<agent-name>
```

Runs the agent against its defined test cases.

---

## Execution Steps

### Phase 1: Locate Evaluations

```bash
# List available evaluations
echo "=== Capability Evaluations ==="
ls .claude/evals/capability/*.yaml 2>/dev/null | xargs -I{} basename {} .yaml

echo "=== Regression Evaluations ==="
ls .claude/evals/regression/*.yaml 2>/dev/null | xargs -I{} basename {} .yaml
```

### Phase 2: Parse and Execute

For each task in the evaluation file:
1. Extract input prompt and success criteria
2. Execute the task (either by running commands or describing the test)
3. Apply the grader (code, pattern, or model)
4. Record pass/fail

### Phase 3: Report Results

```
## Evaluation Report: <name>

Date: <ISO date>
Tasks: N total

| Task ID | Description | Grader | Result |
|---------|-------------|--------|--------|
| task-1  | Happy path  | code   | PASS   |
| task-2  | Error case  | pattern| FAIL   |

### Pass Rate: XX% (N/M passed)
### Reliability: pass@3 = XX%

### Failures
- task-2: Expected pattern "success" not found in response
  Response excerpt: [...]
  
### Recommendation
[MERGE READY | FIX REQUIRED | NEEDS INVESTIGATION]
```

### Phase 4: Save Results

Append to `.claude/evals/results/<date>.json`:

```json
{
  "date": "YYYY-MM-DD",
  "evaluation": "<name>",
  "pass_rate": 0.95,
  "tasks": { ... }
}
```

---

## Usage Examples

- `/eval --all` — Run all evaluations and summarize
- `/eval capability/auth` — Run only auth feature evaluations
- `/eval regression/core-workflows` — Check for regressions
- `/eval --create payment-flow` — Create new evaluation template
- `/eval --history` — Show pass rates over last 7 days

## Notes

- Evaluations are stored in `.claude/evals/`
- Results are persisted in `.claude/evals/results/`
- Prefer code graders over model graders for deterministic results
- Run regression evaluations before merging any significant change
- Set minimum pass@3 >= 90% for user-facing features
