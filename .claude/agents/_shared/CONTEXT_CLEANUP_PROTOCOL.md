# Context Cleanup Protocol

Defines how agents manage context boundaries to prevent context pollution across phases and handoffs.

---

## Core Principle

> **Each agent invocation = fresh context.**
>
> An agent receives a structured handoff, performs its work, writes its output
> to a file or structured message, and returns. It does not carry state from
> previous invocations or other agents.

---

## Context Boundaries

### What Crosses Boundaries (Explicit Handoff)
- Structured handoff block (see AGENT_TEMPLATE.md)
- File paths to deliverables (plan.md, ops.json, report files)
- Score/status from the previous agent
- Specific constraints or feedback items

### What Does NOT Cross Boundaries
- Internal reasoning or exploration notes
- Partial search results
- Tool call history
- Abandoned approaches
- Draft content that was not finalized

---

## Agent Lifecycle

```
1. RECEIVE  → Read the handoff block and referenced files
2. LOAD     → Load required skills
3. EXECUTE  → Perform the task (reading files fresh, not from prior memory)
4. VERIFY   → Run verification gate (see VERIFICATION_PROTOCOL.md)
5. OUTPUT   → Write deliverables to files
6. HANDOFF  → Produce structured handoff for next agent
7. EXIT     → Agent context ends
```

At step 7, all internal state is discarded. The next agent starts at step 1 with only the handoff block and referenced files.

---

## Task Tool Spawning

When using the Task tool to spawn subagents:

```
SPAWN RULES:
1. Each Task spawn creates a fresh agent context
2. Pass information via the task prompt (structured handoff)
3. The spawned agent writes output to a file
4. The parent reads the output file after completion
5. The spawned agent's internal context is NOT accessible to the parent
```

### Correct Pattern
```
Parent:
  1. Write context to .claude/state/handoff-<id>.md
  2. Spawn child agent with: "Read .claude/state/handoff-<id>.md and perform <task>"
  3. Child writes result to .claude/state/result-<id>.md
  4. Parent reads .claude/state/result-<id>.md
```

### Incorrect Pattern
```
Parent:
  1. Spawn child with giant inline context blob
  2. Hope the child's output appears in the parent's context
  3. Assume child has access to parent's prior tool calls
```

---

## File-Based State Management

For multi-phase workflows, use files to persist state across context boundaries:

### State Directory
```
.claude/state/
  ├── workflow-<id>.json      → Workflow progress tracker
  ├── handoff-<id>.md         → Handoff context for next agent
  ├── result-<id>.md          → Agent output/deliverables
  └── error-<id>.md           → Error reports
```

### State File Format
```json
{
  "workflow_id": "<id>",
  "current_agent": "<name>",
  "current_step": 3,
  "total_steps": 5,
  "status": "in_progress",
  "history": [
    {"agent": "planner", "status": "complete", "output": ".claude/plans/plan-auth.md"},
    {"agent": "reviewer", "status": "complete", "output": "approved", "score": 92},
    {"agent": "implementer", "status": "in_progress"}
  ]
}
```

---

## Context Pollution Prevention

### Reading Files Fresh
- ALWAYS read a file at the start of your task, even if a prior agent "just wrote it"
- NEVER rely on what a prior agent said a file contains -- read it yourself
- NEVER assume file contents from a handoff description

### No Inherited Assumptions
- If the handoff says "tests pass," verify it yourself
- If the handoff says "file exists at X," check that it does
- If the handoff lists modified files, verify they were actually modified

### Clean Output
- Write deliverables to well-defined file paths
- Do not embed large outputs in the handoff block
- Reference files by path, not by content

---

## Cleanup After Workflow Completion

When a workflow finishes (all agents complete), the coordinator should clean up:

```
1. State files in .claude/state/ can be archived or deleted
2. Handoff files are no longer needed
3. Report files should be preserved for audit
4. Plan and ops.json files should be preserved
```

The coordinator decides what to keep based on the workflow outcome:
- **Success:** Archive state, keep plans and reports
- **Failure:** Keep everything for debugging
- **Escalation:** Keep everything for human review
