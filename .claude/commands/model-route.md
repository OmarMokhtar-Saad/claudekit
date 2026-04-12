---
description: "Route a task to the optimal Claude model (haiku/sonnet/opus) based on complexity scoring"
argument-hint: "<task-description>"
model: haiku
---

# Model Route Command

Score a task on 4 dimensions (reasoning depth, output complexity, error cost, domain novelty) and recommend the optimal model with cost estimate.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **context-budget** - Token cost awareness

## Task

Route this task to the optimal model: $ARGUMENTS

---

## Execution

Invoke the model-router agent with the task description.

The model-router will:
1. Score the task on 4 dimensions (0–3 each, total 0–12)
2. Apply override rules (security → min Sonnet, docs → max Sonnet)
3. Return: recommended model, score breakdown, cost ratio, reasoning

### Scoring Dimensions

| Dimension | 0 | 1 | 2 | 3 |
|-----------|---|---|---|---|
| Reasoning depth | Lookup/format | Simple 1-step | Multi-step with trade-offs | Novel/adversarial |
| Output complexity | <200 tokens | 200-1k | 1k-5k | >5k |
| Error cost | Trivially reversible | Easily reversible | Moderate to fix | Expensive to fix |
| Domain novelty | Routine with precedent | Slightly unusual | Unfamiliar codebase | Novel problem |

### Decision Table

| Score | Recommendation |
|-------|---------------|
| 0–3 | Haiku |
| 4–7 | Sonnet |
| 8–10 | Sonnet (heavy) |
| 11–12 | Opus |

---

## Usage Examples

- `/model-route "update the README with new installation steps"` → Haiku
- `/model-route "implement JWT refresh token rotation"` → Sonnet
- `/model-route "design the new multi-tenant auth architecture"` → Opus
- `/model-route "review this PR for security vulnerabilities"` → Opus

## Notes

- This command itself runs on Haiku — routing is always cheap
- Use before spawning expensive agents to optimize cost
- Override rules: security review → min Sonnet; docs → max Sonnet
