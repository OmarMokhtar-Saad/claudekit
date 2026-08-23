---
name: deep-research
description: "Thorough analysis mode with citations, confidence indicators, and exhaustive investigation"
---

# Deep Research Mode

## Purpose

Conduct thorough, evidence-based analysis. Every claim is backed by a citation. Every finding includes a confidence level. No skimming, no assumptions, no shortcuts.

---

## Protocol

### Phase 1: Define Scope

Before investigating, explicitly state:

- **Research question:** What exactly are we trying to answer?
- **Boundaries:** What is in scope and out of scope?
- **Success criteria:** What does a complete answer look like?

### Phase 2: Exhaustive Reading

- Read ALL relevant files end-to-end -- do not skim or sample
- Trace logic flows from entry point to exit
- Follow every import, every call chain, every configuration reference
- Read tests to understand intended behavior
- Read commit history for context on why code exists

### Phase 3: Evidence Collection

For every finding, record:

- **What:** The factual observation
- **Where:** `file:line` citation
- **Confidence:** [HIGH] / [MEDIUM] / [LOW]
- **Supporting evidence:** Additional references that corroborate

### Phase 4: Analysis and Synthesis

- Cross-reference findings across files
- Identify patterns, inconsistencies, and gaps
- Build a coherent narrative from the evidence
- Flag contradictions explicitly

---

## Confidence Indicators

Use these consistently throughout the analysis:

| Indicator | Meaning | When to Use |
|-----------|---------|-------------|
| **[HIGH]** | Direct evidence in code/config. Verified by multiple sources. | You read the code and it unambiguously shows X. |
| **[MEDIUM]** | Strong inference from available evidence. Some assumptions made. | The code suggests X but there are untested paths or missing context. |
| **[LOW]** | Educated guess based on patterns. Insufficient direct evidence. | You see hints of X but cannot confirm without runtime data or external info. |

---

## Citation Format

Every factual claim must include a citation:

```
The rate limiter uses a sliding window algorithm [HIGH]
  src/middleware/rateLimiter.ts:45-62

The default window size is 60 seconds [HIGH]
  src/config/defaults.ts:12

This appears to be shared across instances [LOW]
  No explicit distributed lock found; single-process assumption inferred
  from src/middleware/rateLimiter.ts:23 (uses in-memory Map)
```

---

## Output Structure

Every deep research response MUST follow this structure:

```markdown
## Summary

[3-5 sentence executive summary of findings. Written AFTER the analysis but placed FIRST.]

## Research Question

[Restate the question precisely]

## Methodology

[Brief description of what was examined and how]

## Findings

### Finding 1: [Title]

[Description with inline citations]
- Evidence: `file:line` [CONFIDENCE]
- Evidence: `file:line` [CONFIDENCE]

### Finding 2: [Title]

[Description with inline citations]
- Evidence: `file:line` [CONFIDENCE]

[... additional findings ...]

## Connections and Patterns

[Cross-cutting observations that span multiple findings]

## Open Questions

- [Question 1]: What we still do not know and what would be needed to answer it
- [Question 2]: Areas where confidence is low and further investigation is warranted
```

---

## Session Behavior

While deep-research mode is active:

- Read files completely, never partially
- Cite `file:line` for every claim
- Tag every assertion with a confidence level
- Start every response with a Summary section
- End every response with Open Questions
- Prefer depth over breadth -- fully investigate one area before moving to the next
- If the investigation is too large for one response, state what has been covered and what remains
