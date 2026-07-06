---
name: token-budget-advisor
description: "Use when asked about response depth or token budget — lets users choose detail level (25%/50%/75%/100%) before Claude responds"
disable-model-invocation: true
---

# Token Budget Advisor

## Purpose

Allow users to control response depth before receiving an answer. This prevents over-explaining simple questions and ensures thorough answers for complex ones.

**Trigger words:** "token budget", "response length", "brief", "detailed", "exhaustive", "short version", "full explanation", or any explicit depth request.

---

## Token Estimation Heuristics

Before presenting depth options, estimate the full response cost:

| Content Type | Estimate |
|-------------|----------|
| Prose | words × 1.3 tokens |
| Code blocks | characters ÷ 4 tokens |
| Tables | rows × columns × 5 tokens |

**Complexity multipliers:**

| Classification | Multiplier | Examples |
|---------------|-----------|---------|
| Simple | 3× input | Single factual question, one-liner fix |
| Moderate | 8× input | Explanation with examples, multi-step process |
| Complex | 20× input | Architecture review, debugging multi-file issue |
| Creative/Exhaustive | 40× input | Full system design, comprehensive audit |

---

## Depth Levels

When the response would be non-trivial, present these options:

```
This answer could range from brief to exhaustive. Choose your depth:

  25% Essential   — Key facts only, no examples, ~[N] tokens
  50% Moderate    — Core explanation with 1-2 examples, ~[N] tokens  
  75% Detailed    — Full explanation, multiple examples, edge cases, ~[N] tokens
 100% Exhaustive  — Complete coverage, all variants, full reference, ~[N] tokens

Reply with a number (25/50/75/100) or a shorthand ("brief", "full", etc.)
```

---

## Depth Descriptions

### 25% — Essential
- Core answer in 1-3 sentences
- No background context
- No examples unless the question is about an example
- Direct action or fact only

### 50% — Moderate
- Core answer with brief rationale
- 1-2 illustrative examples
- Key caveats (not exhaustive)
- Suitable for intermediate users who know the domain

### 75% — Detailed
- Full explanation with context
- Multiple examples covering different cases
- Edge cases and gotchas
- Comparison with alternatives where relevant
- Suitable for learning or implementation reference

### 100% — Exhaustive
- Complete coverage of the topic
- All variants, options, and configurations
- Full code examples that run independently
- Anti-patterns and what to avoid
- Links to further reading when relevant
- Suitable for documentation, deep understanding, or reference

---

## Shorthand Recognition

Users can signal depth without the menu:

| User Says | Maps To |
|-----------|--------|
| "briefly", "short", "quick", "tl;dr" | 25% |
| "explain", "how does", "overview" | 50% |
| "in detail", "walk me through", "thoroughly" | 75% |
| "exhaustive", "complete", "everything", "full" | 100% |

When shorthand is detected, skip the menu and deliver at the matched level.

---

## Session Memory

Once a depth preference is set, apply it to all subsequent responses in the session unless the user changes it.

```
[Token Budget: 75% Detailed] ← Show this indicator when a preference is active
```

---

## When NOT to Trigger

Skip the depth menu when:

1. The answer is trivially short (≤5 sentences regardless of depth)
2. The user references tokens in a non-depth context (e.g., "authentication token", "API token")
3. A depth preference already exists for this session and wasn't just reset
4. The user is asking a yes/no question

---

## Example Interaction

**User:** "How does JWT authentication work?"

**Claude (applying this skill):**
```
JWT authentication is moderately complex. How much detail do you want?

  25% Essential   — What JWT is and the 3-step flow, ~200 tokens
  50% Moderate    — Explanation + code example, ~500 tokens
  75% Detailed    — Full breakdown with signing, validation, refresh tokens, ~1,200 tokens
 100% Exhaustive  — Complete reference: attacks, best practices, library usage, ~2,500 tokens

Reply: 25 / 50 / 75 / 100 (or: "brief" / "standard" / "detailed" / "full")
```

**User:** "50"

**Claude:** [Delivers moderate-depth response]
