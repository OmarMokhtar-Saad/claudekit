---
name: documentation-standards
description: "Use when creating or updating documentation - formatting, structure, knowledge base patterns"
user-invocable: false
---

# Documentation Standards

## Core Principle

**Documentation exists to transfer knowledge, not to demonstrate effort.** Every document should answer a specific question that a reader would actually have.

---

## Knowledge Base Update Workflow

When new knowledge needs to be documented:

```
[IDENTIFY] What knowledge needs to be captured?
    |
    v
[CLASSIFY] What type of document is this?
    |
    v
[LOCATE] Where does this belong in the knowledge base?
    |
    v
[WRITE] Write using the appropriate template
    |
    v
[LINK] Connect to related documents
    |
    v
[VERIFY] Ensure accuracy and completeness
```

### Step 1: IDENTIFY

Trigger documentation when:
- A decision is made and the reasoning should be preserved
- A process is established or changed
- A common question keeps being asked
- A bug is found that reveals non-obvious behavior
- An architectural pattern is chosen

### Step 2: CLASSIFY

| Document Type | Purpose | Template |
|---|---|---|
| **Decision Record** | Record why a decision was made | ADR format |
| **How-To Guide** | Step-by-step instructions | Procedural format |
| **Reference** | Lookup information | Table/catalog format |
| **Explanation** | Conceptual understanding | Narrative format |
| **Pattern Entry** | Reusable solution | Problem/Solution format |
| **Troubleshooting** | Fix known issues | Symptom/Cause/Fix format |

### Step 3: LOCATE

Place documentation close to what it documents:
- API docs next to API code
- Architecture docs in a top-level docs directory
- Process docs in the team wiki or CONTRIBUTING guide
- Decision records in a dedicated ADR directory

---

## Pattern Entry Format

When documenting a reusable pattern:

```markdown
## Pattern: [Name]

### Problem
[What problem does this pattern solve?]

### Context
[When should this pattern be applied?]

### Solution
[How does the pattern work?]

### Consequences
- Positive: [benefits]
- Negative: [tradeoffs]

### Examples
[Concrete examples of the pattern in use]

### Related Patterns
- [Pattern A]: [how they relate]
- [Pattern B]: [how they relate]
```

---

## Documentation Structure Rules

### File Organization

```
docs/
├── architecture/         # System design and decisions
│   ├── overview.md       # High-level system architecture
│   ├── adr/              # Architecture Decision Records
│   │   ├── 001-use-event-sourcing.md
│   │   └── 002-choose-message-broker.md
│   └── diagrams/         # Architecture diagrams
├── guides/               # How-to guides
│   ├── getting-started.md
│   ├── deployment.md
│   └── troubleshooting.md
├── reference/            # Reference documentation
│   ├── api.md
│   ├── configuration.md
│   └── error-codes.md
└── processes/            # Team processes
    ├── code-review.md
    ├── release.md
    └── on-call.md
```

### Document Structure

Every document should have:

1. **Title** - Clear, descriptive, searchable
2. **Purpose** - One sentence explaining why this document exists
3. **Audience** - Who should read this
4. **Content** - The actual information
5. **Last Updated** - When this was last verified as accurate

### Formatting Rules

| Rule | Rationale |
|---|---|
| Use headers for scanability | Readers skim before reading |
| Use tables for comparisons | Easier to parse than prose |
| Use code blocks for code | Preserves formatting and enables copy |
| Use numbered lists for sequences | Order matters in procedures |
| Use bullet lists for collections | Order does not matter |
| Keep paragraphs short (3-5 sentences) | Long paragraphs lose readers |
| Use bold for key terms | Helps scanning |

---

## Architecture Decision Records (ADR)

### ADR Template

```markdown
# ADR-[number]: [Title]

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context
[What is the issue that we are seeing that motivates this decision?]

## Decision
[What is the change that we are proposing and/or doing?]

## Consequences

### Positive
- [benefit 1]
- [benefit 2]

### Negative
- [tradeoff 1]
- [tradeoff 2]

### Neutral
- [observation 1]

## Alternatives Considered
- [Alternative 1]: [why rejected]
- [Alternative 2]: [why rejected]
```

### ADR Rules

- ADRs are **immutable** once accepted (create a new ADR to supersede)
- Number ADRs sequentially
- Keep them short (1-2 pages)
- Record the decision AND the reasoning
- Link to related ADRs

---

## How-To Guide Template

```markdown
# How to [accomplish specific task]

## Prerequisites
- [what you need before starting]

## Steps

### 1. [First step]
[Detailed instructions]

### 2. [Second step]
[Detailed instructions]

### 3. [Third step]
[Detailed instructions]

## Verification
[How to confirm the task was completed successfully]

## Troubleshooting
- **Problem:** [common issue]
  **Solution:** [how to fix]
```

---

## Documentation Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| **Write Once, Read Never** | Documentation not maintained | Schedule regular reviews |
| **Documentation Island** | Doc exists but nobody can find it | Link from README and related code |
| **Copy-Paste Docs** | Same info in multiple places | Single source of truth, link to it |
| **Stale Screenshots** | Images become outdated | Use text descriptions when possible |
| **Tribal Knowledge** | Information only in people's heads | Write it down when you learn it |
| **Wall of Text** | Nobody reads long unstructured docs | Use headers, lists, tables |
| **Aspirational Docs** | Describes what we wish, not what is | Document current state, note planned changes |

---

## Documentation Review Checklist

Before publishing:
- [ ] Title clearly describes the content
- [ ] Purpose is stated in the first paragraph
- [ ] All code examples are tested and working
- [ ] No outdated information
- [ ] Linked to from relevant places (README, related docs)
- [ ] Follows the project's formatting conventions
- [ ] Spelling and grammar checked
- [ ] Technical terms are defined or linked
