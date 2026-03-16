# Task Tool Specification

Patterns for using the Task tool to spawn subagents in ClaudeKit workflows.

---

## Overview

The Task tool spawns an independent agent instance with its own context. It is the mechanism by which the Coordinator (or any orchestrating agent) delegates work to specialist agents.

---

## Spawn Pattern

### Basic Spawn
```
TaskCreate:
  prompt: |
    You are the <agent-name> agent.
    Read your agent definition: .claude/agents/<agent-name>.md

    HANDOFF FROM: <source-agent>
    ---
    Task: <description>
    <... structured handoff block ...>

  agent: <agent-name>
```

### Spawn with File Context
```
TaskCreate:
  prompt: |
    You are the <agent-name> agent.
    Read your agent definition: .claude/agents/<agent-name>.md

    Read the handoff context: .claude/state/handoff-<id>.md
    Read the referenced files listed in the handoff.

    Perform the task described in the handoff.
    Write your output to: .claude/state/result-<id>.md

  agent: <agent-name>
```

---

## Spawn Rules

1. **One agent per Task** -- Never combine multiple agents in a single Task spawn
2. **Structured input** -- Always provide a structured handoff block, not free-form text
3. **File-based output** -- Direct the agent to write output to a specific file path
4. **No nested spawning** -- Agents should not spawn other agents (only the Coordinator spawns)
5. **Timeout awareness** -- Consider the hook timeout when spawning long-running agents

---

## Coordinator Dispatch Pattern

The Coordinator routes tasks through the pipeline by spawning agents sequentially:

```
COORDINATOR DISPATCH LOOP:

for each agent in pipeline:
  1. Prepare handoff context
  2. Spawn agent via Task tool
  3. Wait for completion
  4. Read the agent's output file
  5. Evaluate result:
     - Success → prepare handoff for next agent
     - Failure → evaluate retry or escalation
     - Revision → route back to producing agent
  6. Update workflow state
```

---

## Parallel Spawn Pattern

When agents can run independently:

```
PARALLEL DISPATCH:

1. Prepare handoff for Agent A
2. Prepare handoff for Agent B
3. Spawn Agent A via Task tool
4. Spawn Agent B via Task tool
5. Wait for both to complete
6. Read both output files
7. Merge results
8. Continue pipeline
```

**Parallel-safe combinations:**
- Explore + Debugger (independent analysis)
- Documenter + GitOps (independent outputs)
- Multiple Verifier instances (independent modules)

**Never parallelize:**
- Implementer + anything (writes code)
- GitOps + Implementer (both write)
- Reviewer + Implementer (sequential dependency)

---

## Task Monitoring

### Checking Task Status
```
TaskGet:
  task_id: <id>
```

Returns the task status: `pending`, `in_progress`, `completed`, `failed`.

### Listing Active Tasks
```
TaskList:
  status: in_progress
```

---

## Error Handling in Spawned Tasks

### Agent Reports Error
If the spawned agent writes an error to its output file:
```
1. Coordinator reads the error
2. Evaluates severity
3. Either:
   a. Retries the agent (once)
   b. Routes to a different agent
   c. Escalates to human
```

### Task Spawn Fails
If the Task tool itself fails:
```
1. Log the failure
2. Retry once
3. If retry fails, escalate to human
4. Never silently skip an agent
```

### Agent Exceeds Timeout
If the task exceeds its timeout:
```
1. The task is terminated
2. Coordinator checks for partial output
3. If partial output is usable, continue
4. If not, escalate
```

---

## Handoff Context Size Guidelines

Keep handoff blocks concise. Large context in the spawn prompt wastes tokens.

| Content | Include in prompt | Store in file |
|---------|:-:|:-:|
| Task description (1-3 lines) | Yes | -- |
| File paths (< 10) | Yes | -- |
| File paths (10+) | -- | Yes |
| Scores and status | Yes | -- |
| Full plan content | -- | Yes |
| Full ops.json content | -- | Yes |
| Error logs (> 20 lines) | -- | Yes |
| Code snippets (> 10 lines) | -- | Yes |
| Feedback items (< 5) | Yes | -- |
| Feedback items (5+) | -- | Yes |

---

## Example: Full Pipeline Dispatch

```
Coordinator receives: "Add user authentication"

Step 1: Spawn Explore
  → prompt: "Explore codebase for auth patterns. Write findings to .claude/state/explore-auth.md"
  → wait for completion
  → read .claude/state/explore-auth.md

Step 2: Spawn Planner
  → prompt: "Read .claude/state/explore-auth.md. Create plan for user auth. Write to .claude/plans/"
  → wait for completion
  → read plan.md and ops.json

Step 3: Spawn Reviewer
  → prompt: "Review plan at .claude/plans/plan-auth.md and .claude/plans/ops-auth.json"
  → wait for completion
  → read review result

Step 4 (if approved): Spawn Implementer
  → prompt: "Execute approved plan at .claude/plans/plan-auth.md"
  → wait for completion
  → read implementation result

Step 5: Spawn Verifier
  → prompt: "Verify implementation. Modified files: [list]"
  → wait for completion
  → read verification result

Step 6 (if passed): Spawn GitOps
  → prompt: "Commit and push. Branch: feature/user-auth. Files: [list]"
  → wait for completion
  → read git result

Done: Report to user
```
