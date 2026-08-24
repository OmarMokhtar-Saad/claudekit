---
description: "Score a task and name the capability tier it earns (fast/balanced/most-capable)"
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

Score the task with the rubric in
[`.claude/agents/coordinator.md` § Model economy](../agents/coordinator.md#6-model-economy)
— four dimensions, 0–3 each, summed — then apply the overrides. Report the **tier**
(`fast` / `balanced` / `most-capable`) and the score that produced it, never a vendor
model name: `.claude/model-policy.json` is the one place a tier becomes a model.

Applying the rubric, you will:
1. Score the task on 4 dimensions (0–3 each, total 0–12)
2. Apply the overrides, which beat the score
3. Return: the TIER, the score breakdown, and the reasoning

The dimensions and the score→tier table are **not repeated here** — they live once, in
`coordinator.md` § Model economy. This file carried its own copy in vendor model names,
which is both the duplication task 008 exists to remove and the vocabulary the model
policy forbids.

---

## Usage Examples

- `/model-route "update the README"` → `fast`
- `/model-route "implement JWT refresh rotation"` → `balanced`
- `/model-route "design multi-tenant auth"` → `most-capable`
- `/model-route "review this PR for security"` → `most-capable` (override)

## Notes

- Routing runs at `fast`; recursive routing is silly
- Overrides beat the score — see the rubric
