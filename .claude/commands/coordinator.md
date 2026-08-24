---
description: "Orchestrate complex workflows via coordinator agent"
argument-hint: "[task or workflow description]"
model: sonnet
---

# Coordinator Command

Invoke the coordinator agent to orchestrate multi-step workflows across agents.

## Agent Reference

See @.claude/agents/coordinator.md for the full agent specification.

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

**The routing table lives in one place: [.claude/agents/coordinator.md](../agents/coordinator.md#task-classification).**
A second copy lived here and the two disagreed on five of eight intents (a feature lost
`Verifier → GitOps`; a bug lost both; docs split between two agents now merged into one).
Route from the canonical table. Two conventions it now states, which lived only here:
`refine` **is** the looped planner → reviewer cycle, not an alternative to it; and docs
route by mode — the one `docs` agent, `mode: create` for new documentation and
`mode: update` for syncing what exists.

## Parallel Groups

Read-only agents with independent inputs (explore, debugger, security-scanner,
code-reviewer, verifier-as-reader) MUST be spawned together in ONE message — never
one per turn. Two independent read-only tasks already justify a parallel group. Only
implementer and gitOps are strictly serialized (they write). Spawn mechanism per routing
row: slash commands where one exists (e.g. `/refine`, `/debug`), otherwise
`claude -p --agent <name>` with the scoped tool row from
`.claude/agents/_shared/INVOCATION.md`.

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
| refine       | APPROVED (score >= 90)   | implementer   |
| refine       | ESCALATED (max iter)     | human review  |
| implementer  | Implementation complete  | verifier      |
| implementer  | Implementation failed    | debugger      |
| verifier     | Score >= 90 (PASS)       | git (commit)  |
| verifier     | Score < 90 (FAIL)        | debugger      |
| debugger     | Diagnosis complete       | refine (fix plan) |
| docs         | Documentation complete   | verifier (optional) |

> Note: `/refine` replaces the manual planner → reviewer → planner cycle. It automatically loops until the plan is APPROVED or the iteration cap is reached. Use `/plan` and `/review` directly only for one-off, single-pass inspection.

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

At the end of orchestration, provide a workflow summary. **The first line is the final
status + goal** (outcome first — the reader should know what happened before reading how),
then: each step executed (agent, status, summary), artifacts produced (files, PRs), and any
follow-up recommendations.
