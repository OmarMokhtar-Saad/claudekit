---
name: systematic-debugging
description: "Use when diagnosing bugs - 4-phase root cause investigation methodology"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash
context: fork
agent: Explore
---

# Systematic Debugging

## Core Principle

**Never apply a fix without first understanding the root cause.** Guessing at fixes creates new bugs and masks the real problem.

---

## The 4-Phase Methodology

```
[Phase 1] ROOT CAUSE INVESTIGATION
    |
    v
[Phase 2] PATTERN ANALYSIS
    |
    v
[Phase 3] HYPOTHESIS TESTING
    |
    v
[Phase 4] IMPLEMENTATION
```

---

## Phase 1: Root Cause Investigation

### Gather Evidence

Before forming any theory, collect facts:

1. **Reproduce the bug**
   - Get exact steps to reproduce
   - Identify the expected vs actual behavior
   - Determine if it is consistent or intermittent

2. **Read the error**
   - Full stack trace (not just the top line)
   - Error message (exact text)
   - Error code if applicable

3. **Identify the scope**
   - When did this start? (check git log)
   - What changed recently? (check recent commits)
   - Who else is affected?
   - Is it environment-specific?

4. **Trace the data flow**
   - Where does the input come from?
   - What transformations does it undergo?
   - Where does the output go?
   - At which point does it diverge from expected behavior?

### Evidence Collection Checklist

- [ ] Error message/stack trace captured
- [ ] Steps to reproduce documented
- [ ] Recent changes to affected area reviewed
- [ ] Input data that triggers the bug identified
- [ ] Environment details noted (OS, versions, config)

---

## Phase 2: Pattern Analysis

### Look for Patterns

| Pattern | Suggests |
|---|---|
| Happens only with specific input | Input validation or edge case issue |
| Happens intermittently | Race condition, timing, or external dependency |
| Happens after recent deploy | Regression from recent change |
| Happens in one environment only | Configuration or environment issue |
| Happens under load only | Resource exhaustion or concurrency issue |
| Happens at specific time | Scheduled job, cache expiry, or timeout |
| Multiple users affected simultaneously | Shared resource or global state issue |
| Only affects new data | Schema change or migration issue |

### Narrow the Scope

Use binary search to isolate the problem:

1. **In code:** Add logging/checks at midpoint of the flow. Is the bug before or after?
2. **In time:** Use git bisect to find the commit that introduced it.
3. **In data:** Test with different inputs to find the minimal reproducing case.

---

## Phase 3: Hypothesis Testing

### Form Hypotheses

Based on evidence and patterns, form testable hypotheses:

```
Hypothesis 1: [description]
  Evidence for: [what supports this]
  Evidence against: [what contradicts this]
  Test: [how to verify]

Hypothesis 2: [description]
  Evidence for: [what supports this]
  Evidence against: [what contradicts this]
  Test: [how to verify]
```

### Rules for Hypothesis Testing

1. **Test one hypothesis at a time** - changing multiple things obscures which fixed it
2. **Start with the most likely** - rank by evidence strength
3. **Design definitive tests** - each test should either confirm or eliminate a hypothesis
4. **Record results** - document what you tried and what happened

### Testing Methods

| Method | When to Use |
|---|---|
| Add logging | When you need to see runtime state |
| Write a test | When you can reproduce with specific input |
| Read the code | When the logic path is unclear |
| Check configuration | When environment differences are suspected |
| Review git history | When looking for introducing change |
| Simplify reproduction | When the bug case is too complex |

---

## Phase 4: Implementation

### Only After Root Cause Is Confirmed

Do NOT proceed to implementation until:
- [ ] You can explain the root cause in one sentence
- [ ] You can explain why the current code is wrong
- [ ] You can explain why your fix is correct
- [ ] You have a test that reproduces the bug

### Fix Implementation

1. **Write a failing test** that reproduces the bug
2. **Implement the minimal fix** - fix the root cause, not symptoms
3. **Verify the test passes** with the fix
4. **Check for similar bugs** - the same pattern may exist elsewhere
5. **Run the full test suite** to check for regressions

### Fix Quality Criteria

| Criterion | Question |
|---|---|
| **Correct** | Does it fix the root cause, not just symptoms? |
| **Minimal** | Does it change only what is necessary? |
| **Safe** | Could this fix introduce new bugs? |
| **Complete** | Does it handle all instances of the pattern? |
| **Tested** | Is there a test that would catch regression? |

---

## Red Flags

### Signs You Are Guessing, Not Debugging

| Red Flag | What to Do Instead |
|---|---|
| "Let me try changing this..." | Stop. Form a hypothesis first |
| "Maybe if I add a null check here..." | Stop. Find out WHY it is null |
| "I'll just catch this exception..." | Stop. Find out WHY it is thrown |
| "It works on my machine" | Find the environment difference |
| "It just started happening randomly" | Something changed. Find what |
| "I don't know why this fixes it" | You have not found the root cause |

### The "Shotgun Debugging" Anti-Pattern

Making multiple changes at once and hoping one of them works:
- You will not know which change fixed it
- You may have introduced new bugs with the other changes
- You have not learned anything about the system

### The "Blame the Framework" Anti-Pattern

Assuming the bug is in a library or framework before checking your code:
- 99% of the time, the bug is in your code
- Check your code first, thoroughly
- Only investigate framework bugs after eliminating your code

---

## Debugging Session Template

```markdown
## Bug Report
- Symptom: [what is happening]
- Expected: [what should happen]
- Steps to reproduce: [numbered steps]

## Investigation
### Evidence Gathered
- [evidence 1]
- [evidence 2]

### Hypotheses
1. [hypothesis] - [CONFIRMED/REJECTED/UNTESTED]
2. [hypothesis] - [CONFIRMED/REJECTED/UNTESTED]

### Root Cause
[One sentence explaining the root cause]

### Fix
[Description of the fix]

### Verification
- [ ] Reproducing test written and fails without fix
- [ ] Fix applied and test passes
- [ ] No regressions in full test suite
```
