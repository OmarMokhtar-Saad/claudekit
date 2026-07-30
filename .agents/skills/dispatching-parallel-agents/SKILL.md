---
name: dispatching-parallel-agents
description: "Use when facing multiple independent failures that can be investigated simultaneously"
disable-model-invocation: true
---

# Dispatching Parallel Agents

## Core Principle

**When multiple independent problems exist, investigate them simultaneously rather than sequentially.** Parallel investigation reduces total resolution time proportionally to the number of agents.

---

## When to Use Parallel Agents

### Prerequisites (ALL must be true)

1. **Two or more independent problems** exist — dispatch ALL of them in ONE message
2. Problems are **truly independent** (different root causes, different files)
3. Each problem can be **fully investigated in isolation**
4. No agent needs another agent's output to proceed

### Good Candidates

| Scenario | Why Parallel Works |
|---|---|
| Multiple failing tests in different modules | Each failure has independent root cause |
| Several lint/style violations in different files | Each fix is independent |
| Multiple feature tasks on different modules | No shared files |
| Investigation of several unrelated bugs | Different code areas |

### Bad Candidates (Use Sequential Instead)

| Scenario | Why Sequential Is Better |
|---|---|
| Cascading failures from one root cause | Fix the root cause, all may resolve |
| Tasks that modify shared files | Merge conflicts guaranteed |
| Tasks where B depends on A's output | Cannot parallelize dependencies |
| Single complex problem | One deep investigation beats three shallow ones |

---

## The Pattern

### Step 1: IDENTIFY Independent Problems

List all problems and verify independence:

```markdown
## Problems Identified

1. **Problem A**: [description]
   - Affected files: [list]
   - Independent from: B, C (different modules)

2. **Problem B**: [description]
   - Affected files: [list]
   - Independent from: A, C (different modules)

3. **Problem C**: [description]
   - Affected files: [list]
   - Independent from: A, B (different modules)

Independence verification: No shared files between any pair.
```

### Step 2: CREATE Task Descriptions

For each problem, create a complete, self-contained task:

```markdown
## Task for Agent [N]

### Problem
[Clear description of the specific problem]

### Scope
- Files to investigate: [list]
- Files you may modify: [list]
- Files you must NOT modify: [list]

### Expected Output
- Root cause identified
- Fix implemented (if authorized)
- Tests passing
- Summary of changes

### Constraints
- Do not modify files outside your scope
- If you discover the problem requires changes to shared files, STOP and report
- Follow TDD: write test first, then fix
```

### Step 3: DISPATCH Agents

Dispatch each agent with its task description. Each agent receives:
1. The task description from Step 2
2. Relevant project context (skills, conventions)
3. Clear scope boundaries

### Step 4: REVIEW Results

When all agents report back:

1. **Verify no conflicts** - check that no two agents modified the same file
2. **Verify each fix** - run the full test suite with all changes combined
3. **Resolve any issues** - if combined changes cause problems, investigate
4. **Report overall results** - summarize what was fixed

---

## Agent Prompt Structure

Each dispatched agent should receive a prompt following this template:

```markdown
## Your Task

You are investigating and fixing a specific problem. Follow these instructions carefully.

### Problem Description
[Detailed description of the problem to solve]

### Files In Your Scope
You may read and modify ONLY these files:
- [file 1]
- [file 2]
- [file 3]

### Files You Must NOT Modify
These files are being handled by other agents:
- [file A] (Agent 1)
- [file B] (Agent 2)

### Process
1. Investigate the problem using Read, Grep, Glob tools
2. Identify the root cause
3. Write a test that reproduces the issue (if applicable)
4. Implement the fix
5. Verify all tests pass
6. Report your findings

### Report Format
When done, report:
- Root cause (one sentence)
- Files modified (list)
- Tests added/changed (list)
- Verification results (pass/fail)
- Any concerns or related issues found
```

---

## Coordination Checklist

Before dispatching:
- [ ] Problems are listed and independence verified
- [ ] File scopes do not overlap between agents
- [ ] Each task description is self-contained
- [ ] Expected output is clearly defined
- [ ] No agent depends on another agent's output

After all agents complete:
- [ ] All agents reported success
- [ ] No file conflicts between agents
- [ ] Full test suite passes with all changes combined
- [ ] All changes are committed

---

## Handling Unexpected Dependencies

If an agent discovers its problem is connected to another agent's problem:

1. **Agent stops work** on the connected portion
2. **Agent reports** the dependency to the coordinator
3. **Coordinator decides**:
   - Reassign the connected work to one agent
   - Complete independent portions, then handle the connection sequentially
   - Abort parallel approach and investigate holistically

---

## When NOT to Use This Pattern

| Situation | Better Approach |
|---|---|
| Only 1 problem | Handle directly - dispatch overhead not worth it |
| Problems might be related | Investigate holistically first |
| Shared file modifications needed | Assign one agent per shared file area |
| Time pressure for a single critical issue | Focus all effort on the one issue |
| Unclear problem boundaries | Investigate first to identify boundaries |

---

## Result Aggregation

After all agents complete, produce a summary:

```markdown
## Parallel Investigation Results

### Dispatched: [N] agents
### Completed: [N] successfully, [N] failed

### Agent 1: [Problem A]
- Status: RESOLVED
- Root cause: [one sentence]
- Files changed: [list]

### Agent 2: [Problem B]
- Status: RESOLVED
- Root cause: [one sentence]
- Files changed: [list]

### Agent 3: [Problem C]
- Status: NEEDS ATTENTION
- Finding: [description]
- Blocked by: [reason]

### Combined Verification
- Full test suite: PASS / FAIL
- Conflicts detected: None / [description]

### Follow-Up Items
- [Any remaining work]
```
