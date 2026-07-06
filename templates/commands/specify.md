---
description: "Define feature requirements -- WHAT and WHY, not HOW. Creates structured specifications."
argument-hint: "<feature-name>"
---

# Specify Command

Define clear, complete requirements for a feature. Focus on WHAT the system should do and WHY, never on HOW it should be implemented.

## Task

Create specification for: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **spec-driven-development** - Spec-first workflow and format
- **clarify** - Ambiguity detection and resolution

## Workflow

### Phase 1: Understand the Feature

Ask the user focused questions, **one at a time**, to build understanding:

1. **What problem does this solve?** Wait for an answer before proceeding.
2. **Who experiences this problem?** Identify users and stakeholders.
3. **What does success look like?** Concrete, measurable outcomes.
4. **What is explicitly out of scope?** Prevent scope creep early.
5. **What constraints exist?** Technical, business, regulatory, timeline.

**Rules for questions:**
- Ask ONE question at a time. Do not dump a list.
- Wait for the answer before asking the next question.
- If the answer is vague, ask a follow-up to sharpen it.
- Offer concrete options when the user seems unsure.
- Stop when you have enough information to write the spec. Do not over-interrogate.

### Phase 2: Draft the Specification

Create the file `.specify/features/{feature-name}/spec.md` using the template below. Derive the feature name from the user's input, using lowercase-kebab-case.

### Phase 3: Review with User

Present the draft specification and ask: "Does this capture your intent? What would you change?"

Iterate until the user approves.

## Specification Template

```markdown
# SPEC: {Feature Name}

## Status: DRAFT

## Problem Statement
{1-3 paragraphs describing the problem this feature solves. Focus on the pain
point, not the solution. Include who is affected and what the impact is.}

## Users & Stakeholders
| Role | Relationship to Feature | Key Concern |
|---|---|---|
| {role} | {how they interact with or are affected by this feature} | {what matters most to them} |

## Functional Requirements
### FR-1: {Requirement Title}
**Description:** {What the system must do}
**Acceptance Criteria:**
- Given {context}, when {action}, then {expected result}
- Given {context}, when {action}, then {expected result}

### FR-2: {Requirement Title}
...

## Non-Functional Requirements
### NFR-1: {Requirement Title}
**Category:** Performance | Security | Reliability | Usability | Accessibility
**Description:** {What quality attribute must be met}
**Measurable Target:** {Specific, testable threshold}

### NFR-2: {Requirement Title}
...

## Success Criteria
{How do we know this feature is complete and working? List 3-5 concrete,
observable outcomes that must all be true for the feature to be considered done.}

- [ ] {Criterion 1}
- [ ] {Criterion 2}
- [ ] {Criterion 3}

## Constraints
- {Technical constraint: e.g., must work with existing database schema}
- {Business constraint: e.g., must ship before Q2}
- {Regulatory constraint: e.g., must comply with GDPR}

## Out of Scope
- {Thing that might seem related but is explicitly NOT part of this feature}
- {Another thing that is out of scope}

## Open Questions
- [ ] {Question that still needs an answer before implementation}
- [ ] {Another unresolved question}
```

## Output Location

All specifications are saved to:

```
.specify/features/{feature-name}/spec.md
```

Create the directory structure if it does not exist.

## Forbidden Actions

- Do NOT propose solutions or implementation approaches in the spec
- Do NOT write code or pseudocode
- Do NOT skip the questioning phase and jump straight to writing
- Do NOT ask more than one question at a time
- Do NOT create a spec with empty or placeholder sections -- ask until you can fill them
- Do NOT include technology choices in functional requirements

## Usage Examples

- `/specify user-authentication` -- Define requirements for user auth
- `/specify search-api` -- Define requirements for a search API
- `/specify billing-notifications` -- Define requirements for billing alerts
