---
description: "Create a multi-session construction blueprint for EPIC-scope objectives requiring 3+ PRs"
argument-hint: "<objective> [--review|--status|--next]"
model: opus
---

# Blueprint Command

Turn a high-level objective into a sequenced, agent-ready construction plan where each step is self-contained. Unlike `/plan` which targets a single PR, `/blueprint` handles multi-week, multi-PR work.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **blueprint** - Multi-session plan construction methodology
- **multi-agent-coordination** - Parallel step execution

## Task

Create blueprint: $ARGUMENTS

---

## When to Use Blueprint vs. Plan

| Scope | Command | Signs |
|-------|---------|-------|
| Single PR (<1 day) | `/plan` | Fits in one commit, one PR |
| EPIC (3+ PRs, multiple days) | `/blueprint` | Multiple teams, complex dependencies, multi-session |

---

## Execution Steps

### Step 1: Pre-Flight Checks

```bash
# Verify git state is clean
git status --short

# Check for existing related plans
ls .claude/plans/ 2>/dev/null | grep -i "<objective-keyword>"

# Get codebase context
find . -maxdepth 2 -not -path "*/node_modules/*" -not -path "*/.git/*" | head -30
cat CLAUDE.md 2>/dev/null | head -40
```

### Step 2: Break Into PR-Sized Steps

Decompose the objective into steps that each:
- Can be reviewed independently
- Deploy safely without the next step
- Can be executed by a fresh agent with no prior context

### Step 3: Build Dependency Graph

Identify which steps must be sequential vs. can be parallel:

```
Step 1: Database schema (no deps)
Step 2: Backend API (depends on Step 1)  
Step 3: Frontend UI (can parallel with Step 2 after Step 1)
Step 4: Integration tests (depends on Steps 2 + 3)
```

### Step 4: Write Self-Contained Steps

Each step in `plans/<blueprint-name>.md` must include:
- Context brief (fresh agent can execute cold)
- Specific task list
- Files to create/modify
- Verification commands
- Exit criteria
- Rollback strategy

### Step 5: Adversarial Review

Spawn a reviewer subagent to check for:
- Steps too large (should be split)
- Hidden dependencies not in the graph
- Missing verification commands
- Steps that assume context a fresh agent wouldn't have
- Circular dependencies

Fix all critical findings.

### Step 6: Register and Present

```bash
mkdir -p .claude/plans/
# Save blueprint to .claude/plans/<name>.md
# Update .claude/plans/INDEX.md
```

Present:
```
## Blueprint: [Objective]

Steps: N total (M parallel groups)
Estimated PRs: N

Execution order:
  Group 1 (parallel): Step 1, Step 2
  Group 2 (sequential): Step 3
  Group 3 (parallel): Step 4, Step 5

To start: /implement plans/<name>.md --step 1
```

---

## Usage Examples

- `/blueprint "Add multi-tenant billing system"` — Create full blueprint
- `/blueprint --status` — Show current blueprint progress
- `/blueprint --next` — Identify and execute the next pending step
- `/blueprint --review plans/billing.md` — Review existing blueprint quality

## Notes

- Use Opus model (this command) — complexity justifies it
- Each step MUST pass the cold-start test (fresh agent, no context)
- Plans are saved to `.claude/plans/` and referenced by `/implement`
- Always adversarially review before executing
- Maximum 12 steps per blueprint (split into phases if more needed)
