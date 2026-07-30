---
name: clarify
description: "Use when a request is ambiguous or could be interpreted multiple ways - reverse-question protocol"
disable-model-invocation: true
argument-hint: "<ambiguous-request>"
---

# Clarify

## Core Principle

**When in doubt, ask. A minute of clarification saves hours of rework.** Ambiguous requirements are the #1 cause of implementing the wrong thing.

---

## Ambiguity Detection

### When to Trigger Clarification

Ask clarifying questions when you detect any of these:

| Signal | Example |
|---|---|
| **Multiple interpretations** | "Make it faster" (faster loading? faster rendering? faster build?) |
| **Vague scope** | "Fix the login" (which aspect? UI? auth? validation? all?) |
| **Missing context** | "Add error handling" (which errors? where? what behavior?) |
| **Implicit assumptions** | "Like we discussed" (you have no conversation history) |
| **Contradictory requirements** | "Make it simple but handle all edge cases" |
| **Undefined terms** | "Use the standard approach" (standard to whom?) |
| **Missing acceptance criteria** | "Improve the performance" (by how much? for which operation?) |

### Ambiguity Severity Levels

| Level | Description | Action |
|---|---|---|
| **Blocking** | Cannot proceed without answer | Must ask before doing anything |
| **Risky** | Could proceed but might waste significant effort | Should ask unless time-critical |
| **Minor** | Multiple approaches, all reasonable | Can proceed with best guess, note assumption |

---

## The Reverse-Question Protocol

When you detect ambiguity, follow this protocol:

### Step 1: State What You Understand

```
"I understand you want to [your interpretation]. Let me confirm a few things:"
```

### Step 2: Ask Specific Questions

**Rules for good questions:**
- Ask about ONE thing per question
- Offer concrete options when possible
- Frame questions to minimize back-and-forth
- Number your questions for easy reference

**Good questions:**
```
1. Should the error message be shown to the user, or only logged internally?
2. For the caching behavior, which of these do you prefer?
   a) Cache for 5 minutes (fast, may serve stale data)
   b) Cache for 60 seconds (balanced)
   c) No cache (always fresh, slower)
3. When you say "the login page", do you mean:
   a) The initial sign-in form
   b) The password reset flow
   c) Both
```

**Bad questions:**
```
"What do you want?" (too vague)
"Should I use pattern X or Y?" (assumes knowledge of patterns)
"Can you be more specific?" (lazy - YOU should identify the ambiguity)
```

### Step 3: State Your Default

If the question is not blocking, offer your recommended approach:

```
"If you don't have a strong preference, I'd recommend option (b) because [reason].
I'll proceed with that unless you say otherwise."
```

---

## Question Generation Framework

### For Feature Requests

1. **Scope:** What exactly should be included/excluded?
2. **Behavior:** What should happen in edge cases?
3. **Integration:** How should this interact with existing features?
4. **Users:** Who is the target user for this?
5. **Priority:** Is this MVP or full implementation?

### For Bug Reports

1. **Reproduction:** Can you share exact steps to reproduce?
2. **Expected vs Actual:** What should happen vs what does happen?
3. **Environment:** Where does this occur? (browser, OS, version)
4. **Frequency:** Always, sometimes, or once?
5. **Impact:** How many users are affected?

### For Refactoring Requests

1. **Motivation:** What problem does this refactoring solve?
2. **Scope:** Which parts of the codebase are in scope?
3. **Constraints:** What must NOT change? (API contracts, behavior)
4. **Success criteria:** How do we know the refactoring is complete?
5. **Risk tolerance:** How much change is acceptable?

---

## When to Clarify vs When to Proceed

### Always Clarify When:

- The request could result in data loss
- The request involves security-sensitive changes
- The request would take more than 30 minutes to implement wrong
- Multiple team members might be affected
- The change is irreversible

### Safe to Proceed With Best Guess When:

- The request is clearly scoped with minor ambiguity
- The change is easily reversible
- You can implement incrementally and get feedback
- The ambiguity is about style, not substance
- You state your assumption clearly

---

## Stating Assumptions

When you proceed without full clarification, always state your assumptions:

```
"I'm proceeding with these assumptions:
- Assumption 1: [what you assumed]
- Assumption 2: [what you assumed]
If any of these are wrong, let me know and I'll adjust."
```

This gives the user a chance to correct misunderstandings before you go too far.

---

## Anti-Patterns

### The Mind Reader
**Problem:** Assuming you know what the user means without asking.
**Fix:** If there is any doubt, ask.

### The Question Flood
**Problem:** Asking 15 questions at once, overwhelming the user.
**Fix:** Prioritize. Ask the 2-3 most important questions. Proceed with reasonable defaults for the rest.

### The Yes/No Trap
**Problem:** Asking questions that only get yes/no answers.
**Fix:** Offer options with tradeoffs so the user can make informed choices.

### The Delayed Clarifier
**Problem:** Implementing first, then asking questions when stuck.
**Fix:** Identify ambiguity BEFORE starting work, not in the middle of it.
