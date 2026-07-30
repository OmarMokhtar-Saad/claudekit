---
name: multi-agent-coordination
description: "Use when multiple agents might modify same files or need coordination - safe parallel execution patterns"
user-invocable: false
---

# Multi-Agent Coordination

## Core Principle

**Parallel work requires explicit boundaries.** Two agents modifying the same file is a recipe for conflict. Define scope before dispatching.

---

## File Scope Rules

### The Exclusive Ownership Rule

Each file should be owned by exactly ONE agent at any given time. No two agents should modify the same file simultaneously.

### Scope Assignment

When dispatching agents, explicitly list:
1. **Files this agent MAY modify** (exclusive write access)
2. **Files this agent MAY read** (shared read access)
3. **Files this agent MUST NOT touch** (owned by another agent)

### Example Scope Assignment

```
Agent A (Authentication feature):
  WRITE: src/auth/*.py, tests/auth/*.py
  READ:  src/models/user.py, src/config.py
  NO:    src/orders/*, src/payments/*

Agent B (Order processing feature):
  WRITE: src/orders/*.py, tests/orders/*.py
  READ:  src/models/order.py, src/config.py
  NO:    src/auth/*, src/payments/*
```

---

## Safe Parallel Execution

### Tasks That CAN Run in Parallel

| Task A | Task B | Why It Is Safe |
|---|---|---|
| Feature in module X | Feature in module Y | Different file sets |
| Writing tests for X | Writing tests for Y | Different test files |
| Documentation for X | Documentation for Y | Different doc files |
| New file creation | New file creation | No overlap possible |
| Read-only investigation | Read-only investigation | No writes = no conflicts |

### Tasks That MUST Run Sequentially

| Task A | Task B | Why Sequential |
|---|---|---|
| Modify shared interface | Implement that interface | B depends on A's output |
| Refactor module X | Add feature to module X | Same files modified |
| Update config schema | Use new config values | B depends on A's schema |
| Database migration | Code using new schema | B depends on A's migration |
| Create base class | Extend base class | B depends on A's class |

---

## Handoff Protocol

When one agent's output becomes another agent's input:

### Step 1: Agent A Completes

```
Agent A reports:
  - Status: COMPLETE
  - Files modified: [list]
  - Files created: [list]
  - Changes summary: [description]
  - Verification: [test results]
```

### Step 2: Coordinator Reviews

The coordinating agent (or user) verifies:
- Agent A's changes are committed
- Tests pass
- No unexpected side effects

### Step 3: Agent B Receives

```
Agent B receives:
  - Context: Agent A completed [description]
  - New files to be aware of: [list]
  - Modified files to re-read: [list]
  - Your scope: [file list]
  - Prerequisites met: [checklist]
```

---

## Conflict Resolution

### Prevention (Preferred)

1. **Assign exclusive file ownership** before starting
2. **Minimize shared interfaces** during parallel work
3. **Defer integration** to a sequential phase

### Detection

Signs of a conflict:
- Two agents report modifying the same file
- Git merge conflicts when combining work
- Test failures that pass in each agent's branch individually

### Resolution

When conflicts are detected:

1. **Stop both agents** - do not let either proceed
2. **Identify the conflict** - which files, which lines
3. **Determine priority** - which agent's changes should take precedence
4. **Resolve manually** or designate one agent to integrate
5. **Re-verify** after resolution

---

## Coordination Patterns

### Pattern 1: Independent Branches

```
Agent A: works on branch feature/auth
Agent B: works on branch feature/orders
Coordinator: merges both into main after completion
```

**Best for:** Truly independent features

### Pattern 2: Sequential Pipeline

```
Agent A: completes task 1 → commits
Agent B: starts from Agent A's commit → completes task 2 → commits
Agent C: starts from Agent B's commit → completes task 3 → commits
```

**Best for:** Dependent tasks that build on each other

### Pattern 3: Hub and Spoke

```
                    Coordinator
                   /     |     \
              Agent A  Agent B  Agent C
                   \     |     /
                    Integration
```

**Best for:** Multiple agents with a single integration point

---

## Agent Communication Format

### Status Report (from agent to coordinator)

```markdown
## Agent Status: [Agent ID]

### Task: [task description]
### Status: [NOT STARTED | IN PROGRESS | BLOCKED | COMPLETE | FAILED]

### Progress
- [x] Step 1: [description]
- [x] Step 2: [description]
- [ ] Step 3: [description]

### Files Modified
- [file list]

### Blockers
- [any blockers, or "None"]

### Needs From Other Agents
- [any dependencies on other agents' work]
```

### Dispatch Message (from coordinator to agent)

```markdown
## Task Assignment

### Your Task
[Clear description of what to do]

### Scope
- Files you may MODIFY: [list]
- Files you may READ: [list]
- Files you must NOT touch: [list]

### Context
- Other agents working on: [brief description]
- Recent changes to be aware of: [list]

### Completion Criteria
- [ ] [criterion 1]
- [ ] [criterion 2]

### Report When Done
Include: status, files changed, test results, any issues
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| No scope assignment | Agents step on each other | Always assign exclusive file ownership |
| Optimistic parallel edits | Merge conflicts and lost work | Assume conflict unless proven independent |
| Silent agents | Coordinator has no visibility | Require status reports after each task |
| Scope creep | Agent modifies files outside scope | Enforce strict scope boundaries |
| Missing handoffs | Agent B starts without Agent A's output | Require explicit completion confirmation |
