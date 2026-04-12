---
description: "Orchestrate complex workflows via coordinator agent"
argument-hint: "[task or workflow description]"
model: sonnet
---

# Coordinator Command

Invoke the coordinator agent to orchestrate multi-step workflows across agents.

## Agent Reference

See @agents/coordinator.md for the full agent specification.

## Task

Orchestrate: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **multi-agent-coordination** - Workflow orchestration and agent handoff management

## When To Use

Use the coordinator when the task requires:

- **Multiple agents** working in sequence or parallel
- **Complex workflows** that span planning, implementation, and verification
- **Unclear routing** where the right agent is not obvious
- **Multi-phase projects** that need structured progression
- **Recovery workflows** after a failure in another agent

Do NOT use the coordinator for:

- Simple, single-agent tasks (route directly to the appropriate agent)
- Tasks that are clearly within one agent's domain
- Quick queries or lookups

## Workflow Routing Table

Use this table to determine which agent(s) to invoke:

| User Intent                        | Primary Agent  | Follow-up Agent(s)         |
|------------------------------------|----------------|----------------------------|
| "Build feature X"                  | planner        | reviewer -> implementer -> verifier |
| "Fix bug Y"                        | debugger       | planner -> reviewer -> implementer |
| "Refactor module Z"               | planner        | reviewer -> implementer -> verifier |
| "Why is X broken?"                | debugger       | (optional) planner         |
| "Add tests for X"                 | planner        | implementer -> verifier    |
| "Refactor X"                      | planner        | reviewer -> implementer -> verifier |
| "Document X"                      | documenter     | (none)                     |
| "Deploy / release"                | gitOps         | verifier -> gitOps         |
| "Review my changes"               | verifier       | (optional) reviewer        |
| "Create PR"                       | gitOps         | (none)                     |
| "Full project setup"              | planner        | reviewer -> implementer -> verifier -> documenter -> gitOps |

## Automatic Handoff Management

### Handoff Protocol

When transitioning between agents:

1. **Capture state**: Record what the previous agent produced
2. **Validate prerequisites**: Ensure the next agent has what it needs
3. **Brief the next agent**: Provide context from prior steps
4. **Invoke the agent**: Use the appropriate slash command
5. **Collect results**: Capture the agent's output
6. **Decide next step**: Continue the workflow or escalate

### State Tracking

Maintain a workflow state throughout the orchestration:

```
## Workflow State

- **Goal**: [user's original request]
- **Current Phase**: [phase name]
- **Completed Steps**:
  1. [agent] - [status] - [summary]
  2. [agent] - [status] - [summary]
- **Next Step**: [agent] - [what it will do]
- **Blockers**: [any issues preventing progress]
```

### Handoff Triggers

| From Agent   | Condition                | Hand Off To   |
|--------------|--------------------------|---------------|
| planner      | Plan complete            | reviewer      |
| reviewer     | Score >= 90 (APPROVED)   | implementer   |
| reviewer     | Score 70-89 (REVISE)     | planner       |
| reviewer     | Score < 70 (REJECTED)    | planner (with new approach) |
| implementer  | Implementation complete  | verifier      |
| implementer  | Implementation failed    | debugger      |
| verifier     | Score >= 90 (PASS)       | git (commit)  |
| verifier     | Score < 90 (FAIL)        | debugger      |
| debugger     | Diagnosis complete       | planner (fix plan) |
| docs         | Documentation complete   | verifier (optional) |

## Escalation Rules

### Automatic Escalation

Escalate to the user (pause and ask for direction) when:

- A plan has been REJECTED twice for the same task
- An implementation has failed and rollback also failed
- The debugger confidence is LOW (<60%) on a critical issue
- A workflow has cycled through the same agent 3+ times
- Conflicting requirements are detected between agents
- The task scope has expanded significantly beyond the original request

### Escalation Format

When escalating, provide: the workflow goal, current phase, what went wrong, a summary of what has been tried, 2-3 options with tradeoffs, and your recommendation. Then pause and await user direction.

## Usage Examples

- `/coordinator Build a REST API for user management`
- `/coordinator Fix the failing CI pipeline and deploy`
- `/coordinator Refactor the auth module to use JWT`
- `/coordinator Set up the project from scratch with tests and docs`
- `/coordinator Diagnose and fix the memory leak in the worker service`

## Output

At the end of orchestration, provide a workflow summary covering: the original goal, each step executed (agent, status, summary), final status (SUCCESS/PARTIAL/FAILED), artifacts produced (files, PRs), and any follow-up recommendations.
