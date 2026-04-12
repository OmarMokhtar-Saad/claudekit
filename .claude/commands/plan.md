---
description: "Create implementation plan via planner agent"
argument-hint: "[task description]"
model: sonnet
---

# Planner Command

Invoke the planner agent to create a structured implementation plan.

## Agent Reference

See @agents/planner.md for the full agent specification.

## Task

Create implementation plan for: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **brainstorming** - Divergent thinking and option generation
- **writing-plans** - Structured plan authoring format
- **generate-operations-config** - ops.json generation and validation

## IRON LAW

Every plan MUST produce a valid `ops.json` file. A plan without ops.json is not a plan -- it is a wish. The ops.json file is the contract between the planner and the implementer. No exceptions.

## Workflow Phases

### Phase 1: Discovery
- Read all relevant source files and configuration
- Identify existing patterns, conventions, and constraints
- Map dependencies and integration points
- Note any blockers or risks

### Phase 2: Analysis
- Break the task into discrete, testable units of work
- Identify the minimal change set required
- Evaluate alternative approaches (at least 2)
- Select the approach with the best tradeoff of simplicity, correctness, and maintainability

### Phase 3: Plan Authoring
- Write the plan in tiered briefing format (see below)
- Generate the ops.json operations config
- Include rollback steps for each operation
- Define success criteria for each step

### Phase 4: Review Trigger
- After the plan is complete, automatically suggest running the reviewer agent
- Provide the command: `/review`

## Tiered Briefing Format

Structure every plan output as follows:

### TL;DR (3 sentences max)
What we are doing, why, and the expected outcome.

### Overview
- **Goal**: One-line objective
- **Scope**: What is in and out of scope
- **Approach**: Selected strategy with brief rationale
- **Risk Level**: Low / Medium / High with justification

### Detailed Steps
For each step:
1. **Step N: Title**
   - Action: What to do
   - Files: Which files are touched
   - Rationale: Why this step
   - Verification: How to confirm it worked
   - Rollback: How to undo if needed

### ops.json Summary
- Total operations count
- Operation types breakdown
- Estimated complexity

## Forbidden Actions

- Do NOT implement any code changes -- planning only
- Do NOT modify any existing files
- Do NOT create branches or make commits
- Do NOT skip the ops.json generation step
- Do NOT produce a plan with fewer than 2 steps or more than 30 steps
- Do NOT assume dependencies exist without verifying
- Do NOT plan changes to files outside the project directory

## Output

Deliver the plan as a structured document followed by the ops.json file content. End with a clear prompt to run the reviewer agent for validation.
