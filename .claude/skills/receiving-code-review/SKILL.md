---
name: receiving-code-review
description: "Use when receiving code review feedback - technical evaluation without emotional response"
disable-model-invocation: true
---

# Receiving Code Review

## Core Principle

**Review feedback is about the code, not about you.** Evaluate every piece of feedback on its technical merits, without defensiveness.

---

## The Response Pattern

For every piece of feedback, follow this sequence:

```
[READ] Read the feedback completely before responding
    |
    v
[UNDERSTAND] Make sure you understand what is being asked
    |
    v
[VERIFY] Check if the feedback is technically valid
    |
    v
[EVALUATE] Determine if the suggestion improves the code
    |
    v
[RESPOND] Acknowledge and state your action
    |
    v
[IMPLEMENT] Make the change (or explain why not)
```

### Step 1: READ

- Read the entire review before responding to any individual comment
- Look for themes across multiple comments
- Note the severity the reviewer is signaling

### Step 2: UNDERSTAND

- If unclear, ask the reviewer to elaborate
- Restate the feedback in your own words to confirm understanding
- Do not assume you know what they mean

### Step 3: VERIFY

- Check if the claim is factually correct
- Read the code the reviewer is referencing
- Look at the context they may be seeing that you missed

### Step 4: EVALUATE

- Does this suggestion make the code better?
- Is the tradeoff worth it?
- Does it align with project standards?
- Is it addressing a real problem or a stylistic preference?

### Step 5: RESPOND

Choose one:
- "Good catch, I'll fix this." (agree and will fix)
- "I agree, but I'd prefer to address it in a follow-up." (agree, defer)
- "I see your point, but I believe the current approach is better because [reason]." (respectful pushback)

### Step 6: IMPLEMENT

- Make the agreed-upon changes
- Re-run tests after changes
- Mark the feedback as addressed

---

## Forbidden Responses

These responses are never appropriate:

| Forbidden | Why | Better Alternative |
|---|---|---|
| "It works though" | Working is the minimum bar, not the goal | "You're right, I can improve this" |
| "That's just your opinion" | Dismissive; maybe it is valid | "Can you explain the concern further?" |
| "I don't have time for this" | Quality is not optional | "Can we prioritize which items to address now?" |
| "The old code was worse" | Not a justification for bad new code | "Fair point, I'll improve it" |
| "Nobody will notice" | Someone already noticed - the reviewer | "You're right, let me fix it" |
| "We can fix it later" | Technical debt compounds with interest | "I'll address it now" or give a concrete timeline |
| Silence / ignoring feedback | Disrespectful, blocks progress | Acknowledge every comment, even if briefly |

---

## The YAGNI Check

When a reviewer suggests adding something new (abstraction, feature, generalization):

1. **Is it needed now?** Does the current requirement demand it?
2. **Is there evidence** it will be needed soon?
3. **What is the cost** of adding it now vs later?
4. **What is the cost** of NOT adding it now?

If YAGNI applies, respond:
```
"I considered this, but I believe it's premature because [reason].
I've kept the code structured so we can add this easily when needed.
Would you like to create a tracking issue for it?"
```

---

## When to Push Back

You should push back on feedback when:

| Situation | How to Push Back |
|---|---|
| Suggestion contradicts project standards | "Our project convention is [X], per [reference]" |
| Suggestion adds unnecessary complexity | "I think this adds complexity without proportional benefit because [reason]" |
| Suggestion is based on incorrect assumption | "I think there might be a misunderstanding - [explanation of actual behavior]" |
| Suggestion would require scope expansion | "This would be a good improvement but expands the scope. Should I track it separately?" |
| Reviewer asks for premature optimization | "I'd prefer to optimize based on measurements. Current performance is [metric]" |

### Rules for Pushing Back

1. **Always provide reasoning** - never just say "no"
2. **Cite evidence** - project standards, measurements, documentation
3. **Offer alternatives** - if you reject a suggestion, propose another solution
4. **Be open to being wrong** - if the reviewer provides convincing counter-evidence, yield gracefully
5. **Escalate if stuck** - if you cannot agree, involve a third party or team lead

---

## Categorizing Feedback

### Must Fix

- Security vulnerabilities
- Correctness bugs
- Violations of critical project standards
- Missing error handling for common cases
- Data loss risks

### Should Fix

- Performance improvements with clear benefit
- Architecture improvements aligned with project direction
- Missing test coverage for important paths
- Unclear naming or confusing logic

### Nice to Fix

- Style preferences within project conventions
- Minor readability improvements
- Additional documentation
- Extra test cases for edge cases

### Discuss

- Fundamental approach disagreements
- Suggestions that change the scope
- Tradeoff decisions where reasonable people could differ

---

## After Addressing Feedback

1. Re-run all tests
2. Mark each comment as resolved
3. Add a summary comment: "Addressed all feedback. Key changes: [list]"
4. Request re-review if substantial changes were made
5. Thank the reviewer for their time
