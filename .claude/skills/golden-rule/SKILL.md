---
name: golden-rule
description: "Use when about to modify code - ensures no edits without explicit user approval through the plan/review/implement workflow"
user-invocable: false
---

# The Golden Rule

## Core Principle

**NEVER edit code without explicit user approval.**

This is the single most important rule in this project. No exception. No shortcut. No rationalization.

---

## The Approval Workflow

```
User Request
    |
    v
[1. PLAN] -----> Present plan to user
    |
    v
[2. REVIEW] ---> User reviews and approves/rejects/modifies
    |
    v
[3. IMPLEMENT] -> Only now may you edit files
    |
    v
[4. VERIFY] ---> Confirm changes match the approved plan
```

### Step 1: PLAN

- Analyze the request
- Identify all files that will be modified
- Describe each change you intend to make
- Estimate scope and risk
- Present the plan clearly

### Step 2: REVIEW

- Wait for explicit user approval
- Acceptable approvals: "yes", "go ahead", "approved", "do it", "looks good"
- If the user modifies the plan, update and re-present
- If the user rejects, ask for guidance

### Step 3: IMPLEMENT

- Make ONLY the approved changes
- Do not add "bonus" improvements
- Do not fix "nearby" issues you noticed
- Stay within the approved scope

### Step 4: VERIFY

- Confirm each planned change was made
- Run any relevant verification commands
- Report what was done

---

## When the Golden Rule Applies

The rule applies to ANY operation that modifies the codebase:

| Operation | Requires Approval? |
|---|---|
| `Write` tool (create/overwrite file) | **YES** |
| `Edit` tool (modify file) | **YES** |
| `git commit` | **YES** |
| `git merge` | **YES** |
| `git rebase` | **YES** |
| Deleting files | **YES** |
| Renaming files | **YES** |
| Moving files | **YES** |
| Running scripts that modify files | **YES** |

## When the Golden Rule Does NOT Apply

Read-only operations never require approval:

| Operation | Requires Approval? |
|---|---|
| `Read` tool | No |
| `Grep` tool | No |
| `Glob` tool | No |
| `git status` | No |
| `git log` | No |
| `git diff` | No |
| Running tests (read-only) | No |
| Listing files | No |
| Searching code | No |

---

## Agent-Specific Enforcement

### When Operating as a Subagent

If you are dispatched as a subagent with a specific task:
- The dispatch message IS your approval for that specific task
- You may implement changes within the scope of your task description
- You may NOT expand scope beyond what was dispatched
- When uncertain, complete what you can and report the uncertainty

### When Operating as the Primary Agent

- Full approval workflow applies at all times
- Never assume previous approval covers new changes
- Each new modification requires its own approval cycle

### When Operating in Plan Execution Mode

- If executing an approved plan, each task in the plan is pre-approved
- However, if you discover the plan needs changes, STOP and ask
- Do not deviate from the plan without re-approval

---

## Violation Recovery

If you accidentally edit without approval:

1. **Stop immediately** - do not make any more changes
2. **Report the violation** - tell the user exactly what you changed
3. **Offer to revert** - provide the exact steps to undo your change
4. **Wait for instructions** - the user decides what happens next

### How to Revert

```
# If you used Edit tool, you can undo by editing back
# If you used Write tool, the original content may be in git
git checkout -- <file>       # revert to last commit
git diff HEAD <file>         # see what changed
```

---

## Common Rationalizations (All Invalid)

| Rationalization | Why It Is Wrong |
|---|---|
| "It's a tiny change" | Size does not determine need for approval |
| "It's obviously what they want" | Obvious to you may not be obvious to them |
| "I'm fixing a bug I introduced" | Still requires approval - the fix might be wrong too |
| "It's just formatting" | Formatting changes can break things and muddy diffs |
| "The tests pass" | Passing tests do not equal user approval |
| "I'll ask forgiveness later" | The rule exists precisely to prevent this thinking |
| "Time is critical" | Incorrect changes waste more time than asking |

---

## The Test

Before every edit, ask yourself:

> "Has the user explicitly approved this specific change?"

If the answer is not a clear YES, **do not make the edit**.
