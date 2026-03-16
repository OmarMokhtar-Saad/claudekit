---
name: brainstorming
description: "Use when exploring solution approaches before creating an implementation plan - creative design exploration"
disable-model-invocation: true
argument-hint: "<topic>"
context: fork
---

# Brainstorming

## Core Principle

**Explore widely before committing narrowly.** Good solutions come from considering multiple approaches, not from implementing the first idea that comes to mind.

---

## The Brainstorming Process

```
[DIVERGE] Generate multiple approaches (minimum 3)
    |
    v
[EVALUATE] Score each approach against constraints
    |
    v
[CONVERGE] Select the best approach with justification
    |
    v
[SELECT] Present recommendation to user for approval
```

---

## Phase 1: DIVERGE

### Rules for Divergence

- Generate **at least 3** distinct approaches
- Each approach must be genuinely different, not a minor variation
- Include at least one "safe" approach and one "bold" approach
- Do not self-censor during this phase
- Consider approaches from different paradigms

### Approach Template

For each approach, document:

```markdown
### Approach [N]: [Name]

**Summary:** One sentence description

**How it works:**
- Step 1: ...
- Step 2: ...
- Step 3: ...

**Pros:**
- [advantage 1]
- [advantage 2]

**Cons:**
- [disadvantage 1]
- [disadvantage 2]

**Effort:** Low / Medium / High

**Risk:** Low / Medium / High
```

---

## Phase 2: EVALUATE

### Constraints Awareness

Before evaluating, list all known constraints:

| Constraint Type | Questions to Ask |
|---|---|
| **Technical** | What are the platform limitations? What dependencies exist? |
| **Architectural** | What patterns must be followed? What layers are involved? |
| **Performance** | Are there speed/memory/resource requirements? |
| **Timeline** | How urgent is this? Can we iterate? |
| **Compatibility** | Must it work with existing code? Backward compatible? |
| **Testability** | Can this approach be easily tested? |
| **Maintainability** | Will future developers understand this? |

### Scoring Matrix

Rate each approach against each constraint:

| Criterion | Approach 1 | Approach 2 | Approach 3 |
|---|---|---|---|
| Fits architecture | 1-5 | 1-5 | 1-5 |
| Implementation effort | 1-5 | 1-5 | 1-5 |
| Testability | 1-5 | 1-5 | 1-5 |
| Maintainability | 1-5 | 1-5 | 1-5 |
| Risk level | 1-5 | 1-5 | 1-5 |
| **Total** | sum | sum | sum |

---

## Phase 3: CONVERGE

After scoring:

1. Identify the highest-scoring approach
2. Check if a hybrid approach combining strengths of multiple options is viable
3. Document why the selected approach wins
4. Note what we lose by not choosing the alternatives

### Convergence Output

```markdown
## Recommendation: [Approach Name]

**Why this approach:**
[2-3 sentences explaining the choice]

**Key tradeoffs accepted:**
- We accept [tradeoff 1] because [reason]
- We accept [tradeoff 2] because [reason]

**What we considered but rejected:**
- [Approach X]: Rejected because [reason]
- [Approach Y]: Rejected because [reason]

**Open questions:**
- [Any remaining uncertainties]
```

---

## Phase 4: SELECT

Present the recommendation to the user:

1. Brief summary of all approaches considered
2. The recommendation with justification
3. Key tradeoffs
4. Ask for approval or discussion

**Remember:** The golden-rule applies. Do not start implementing until the user approves the approach.

---

## When to Brainstorm

| Situation | Brainstorm? |
|---|---|
| Multiple valid approaches exist | **Yes** |
| The user asks "how should we..." | **Yes** |
| Architectural decision needed | **Yes** |
| Bug with obvious single fix | No - just fix it |
| User specified exact approach | No - just plan it |
| Trivial change | No - just do it |
| High-risk or irreversible change | **Yes, always** |

---

## Brainstorming Anti-Patterns

### The One-Trick Pony
**Problem:** Generating three "approaches" that are really the same idea with minor tweaks.
**Fix:** Force each approach to differ in at least one fundamental dimension (data structure, pattern, architecture layer, technology).

### The Analysis Paralysis
**Problem:** Spending too long evaluating without converging.
**Fix:** Set a time limit. If no clear winner after evaluation, go with the safest option.

### The Pet Solution
**Problem:** Having a favorite approach and unconsciously biasing the evaluation.
**Fix:** Score the "boring" approach first. Give it a fair chance.

### The Kitchen Sink
**Problem:** Trying to combine all approaches into one mega-solution.
**Fix:** Hybrids are fine, but they must be simpler than any individual approach, not more complex.

---

## Output Format

The final brainstorming output should be structured as:

1. **Context** (2-3 sentences on what problem we are solving)
2. **Approaches** (3+ approaches using the template above)
3. **Evaluation** (scoring matrix)
4. **Recommendation** (selected approach with justification)
5. **Next Step** (ready for plan creation via writing-plans skill)
