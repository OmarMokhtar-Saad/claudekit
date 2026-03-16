---
name: batch
description: "Orchestrate large-scale parallel changes across the codebase using worktree agents"
argument-hint: "<instruction>"
disable-model-invocation: true
context: fork
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

# Batch Command

Decompose a large-scale change into independent units and execute them in parallel using isolated worktree agents.

## Task

Batch instruction: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval
- **multi-agent-coordination** - Safe parallel execution patterns
- **using-git-worktrees** - Isolated workspace management

## Workflow

### Phase 1: Decomposition
- Analyze $ARGUMENTS to understand the full scope of the change
- Identify all affected files and modules via Grep and Glob
- Decompose the work into **5-30 independent units** that:
  - Touch non-overlapping files (no merge conflicts)
  - Can be tested in isolation
  - Have clear success criteria
- Present the decomposition plan for user approval before proceeding

### Phase 2: Work Unit Definition
For each unit, define:
```
Unit N: [short title]
- Files: [list of files to modify]
- Change: [specific instruction for this unit]
- Test: [how to verify this unit succeeded]
- Dependencies: [none | unit X must complete first]
```

Validate that:
- No two units modify the same file
- Combined units cover the full scope of $ARGUMENTS
- Each unit is small enough for a single agent to complete

### Phase 3: Parallel Execution
- Create an isolated git worktree per unit using `EnterWorktree`
- Spawn one agent per unit with the unit's specific instruction
- Each agent independently:
  1. Implements the changes in its worktree
  2. Runs relevant tests to verify correctness
  3. Creates a feature branch with a descriptive commit
  4. Reports success or failure with details
- Monitor agent progress and collect results

### Phase 4: Aggregation
- Collect results from all agents
- Categorize: succeeded, failed, needs-review
- For succeeded units: create individual PRs or merge to a staging branch
- For failed units: report the failure with diagnostics

### Phase 5: Report
Generate a comprehensive batch execution summary.

## Safety Rules

- NEVER execute without user approval of the decomposition plan
- NEVER allow two agents to modify the same file
- NEVER merge failed units into any shared branch
- ALWAYS verify each unit independently before aggregation
- If more than 20% of units fail, pause and escalate to the user
- Each agent must work in its own worktree (complete isolation)

## Output Format

```
## Batch Execution Report

### Instruction: [original $ARGUMENTS]
### Units: N total

### Decomposition
| # | Title | Files | Status |
|---|-------|-------|--------|
| 1 | [title] | [N files] | PASS / FAIL / REVIEW |
| 2 | [title] | [N files] | PASS / FAIL / REVIEW |
| ... | ... | ... | ... |

### Results Summary
- Succeeded: N / M (XX%)
- Failed: N
- Needs Review: N

### Failed Units (if any)
1. Unit N: [title]
   - Error: [description]
   - Files affected: [list]
   - Suggested fix: [recommendation]

### Artifacts
- Branches created: [list]
- PRs created: [list, if applicable]

### Next Steps
- [merge instructions or remediation steps]
```

## Usage Examples

- `/batch Add error handling to all API endpoints`
- `/batch Convert all class components to functional components with hooks`
- `/batch Add JSDoc comments to all exported functions`
- `/batch Replace deprecated lodash.get with optional chaining across the codebase`
- `/batch Add input validation to all controller methods`

## Notes

- Ideal for repetitive changes that span many files with a consistent pattern
- Not suitable for changes where files have interdependencies
- Each unit should take 1-5 minutes for a single agent to complete
- If the decomposition yields fewer than 5 units, consider using `/implement` instead
- If it yields more than 30 units, consider splitting into multiple batch runs
- Use `/verify` after all units are merged to validate overall project health
