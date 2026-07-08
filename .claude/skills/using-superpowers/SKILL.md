---
name: using-superpowers
description: "Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response"
user-invocable: false
---

# Using Superpowers

## The Rule

**Before generating ANY response to a user message, you MUST check if a relevant skill exists and invoke it using the Skill tool.**

This is not optional. This is not a suggestion. This is the foundational behavior that makes you effective.

### The Process

1. User sends a message
2. **BEFORE writing any response text**, scan available skills
3. If a matching skill exists, invoke it with the Skill tool
4. Follow the skill's instructions
5. Only then produce your response

### Why This Matters

Skills encode hard-won process knowledge. Skipping them means repeating mistakes that have already been solved. Every skill exists because someone encountered a problem without it.

---

## Red Flags: Rationalizations for Skipping Skills

| Rationalization | Why It Is Wrong |
|---|---|
| "This is a simple question" | Simple questions often have non-obvious process requirements |
| "I need context first" | Skills ARE the context - they tell you what context to gather |
| "I already know how to do this" | Your default behavior likely differs from the project's requirements |
| "The user wants a quick answer" | A correct answer with skills is faster than redoing an incorrect one |
| "I'll check skills after my initial response" | Too late - you may have already violated a process rule |
| "No skill seems to match exactly" | Partial matches still provide valuable guardrails |
| "The skill seems redundant for this case" | The skill exists precisely for cases where it seems unnecessary |

If you catch yourself thinking any of the above, **stop and invoke the skill anyway**.

---

## Skill Priority Order

### 1. Process Skills (invoke FIRST)

These govern HOW you work:
- `golden-rule` - before any code modification
- `context-first-workflow` - before any code exploration
- `verification-before-completion` - before claiming anything is done

### 2. Implementation Skills (invoke SECOND)

These govern WHAT you produce:
- `writing-plans` - when creating plans
- `test-driven-development` - when writing code
- `clean-architecture` - when designing systems

### 3. Coordination Skills (invoke as needed)

These govern WHO does what:
- `multi-agent-coordination` - when parallel work is happening
- `dispatching-parallel-agents` - when distributing tasks

---

## Universal Execution Rules

Every agent, every task, regardless of which skills load after this one:

1. **Batch independent tool calls in ONE message.** Reads, greps, globs, and agent spawns
   that don't depend on each other's results fire together. Sequential-when-independent
   wastes turns and context and silently abandons breadth.
2. **Never end a turn on a question or plan you can resolve yourself.** Finish the work.
   On failure, retry with a DIFFERENT approach (never verbatim, max 2 attempts), then
   escalate with the pasted failure output.
3. **Evidence over plausibility.** Claims carry file:line or executed command output.
   Never state a number you didn't measure. Before claiming done or clean, try to refute
   your own conclusion (see VERIFICATION_PROTOCOL.md).

---

## Skill Discovery

When you are unsure which skill applies:

1. **Search by action**: What is the user asking you to DO? (edit, plan, debug, review)
2. **Search by phase**: What phase of work is this? (exploration, planning, implementation, verification)
3. **Search by concern**: What could go wrong? (security, performance, architecture)

### Common Mappings

| User Says | Skill to Load |
|---|---|
| "Fix this bug" | `systematic-debugging` then `golden-rule` |
| "Add a feature" | `context-first-workflow` then `writing-plans` |
| "Review this code" | `receiving-code-review` or `requesting-code-review` |
| "Refactor this" | `refactoring-patterns` then `golden-rule` |
| "Is this done?" | `verification-before-completion` |
| "Create a plan" | `writing-plans` then `brainstorming` |
| "Run the tests" | `verification-before-completion` |

---

## Enforcement

If you produce a response without checking skills:
1. Stop immediately
2. Acknowledge the skip
3. Invoke the relevant skill
4. Redo your response following the skill's guidance

There is no penalty for invoking a skill that turns out to be irrelevant. There IS a penalty for skipping a skill that was relevant.

**When in doubt, invoke the skill.**
