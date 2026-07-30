---
name: code-explanation
description: Use when explaining how code works — provides visual diagrams, analogies, and gotcha highlights for teaching about a codebase.
user-invocable: false
---

# Code Explanation

## Core Principle

**Explain code by building mental models, not by restating syntax.** The goal is understanding, not narration. Start with the big picture, then zoom into details. Use analogies to connect unfamiliar concepts to familiar ones.

---

## The Explanation Framework

```
[ANALOGY] Connect to something the reader already knows
    |
    v
[ARCHITECTURE] Show the big picture with a visual diagram
    |
    v
[WALKTHROUGH] Step through the code path with annotations
    |
    v
[GOTCHAS] Highlight non-obvious behavior and edge cases
    |
    v
[SUMMARY] One-paragraph distillation of the key insight
```

---

## Phase 1: Analogy-First Explanation

### Rules for Good Analogies

- Connect the code concept to a real-world system the reader knows
- The analogy should explain the STRUCTURE, not just one aspect
- Acknowledge where the analogy breaks down
- Keep it to 2-3 sentences

### Analogy Patterns

| Code Concept | Analogy Pattern |
|---|---|
| Event-driven architecture | Postal system: senders drop letters, postal service routes to recipients |
| Middleware pipeline | Airport security: each checkpoint inspects and passes through or rejects |
| Pub/sub | Radio broadcasting: stations transmit, radios tune to channels they care about |
| Connection pool | Hotel room keys: fixed number of rooms, guests check in/out, wait if full |
| Circuit breaker | Electrical fuse: trips when overloaded, must be manually reset |
| Cache | Sticky note on your monitor: quick to read, might be outdated |
| Load balancer | Restaurant host: directs guests to tables with available servers |
| Dependency injection | Power outlets: the device does not care which power plant, just needs the right socket |
| Saga pattern | Multi-stop travel booking: each leg can be cancelled independently if a later leg fails |
| Observer pattern | Newsletter subscription: sign up once, receive updates automatically |

### Template

```
Think of [code concept] like [familiar system].

[1-2 sentences explaining how the familiar system maps to the code.]

This analogy breaks down when [limitation], but it captures the key idea:
[one sentence stating the core insight].
```

---

## Phase 2: Architecture Diagrams

### ASCII Diagram Conventions

Use consistent symbols across all diagrams:

```
Boxes:      +----------+
            | Component|
            +----------+

Arrows:     ------>  (data flow / calls)
            - - - -> (optional / async)
            ======>  (bulk data)

Decisions:  <condition?>
            /         \
           YES         NO

Layers:     ┌──────────────────┐
            │   Layer Name     │
            ├──────────────────┤
            │   Contents       │
            └──────────────────┘
```

### Diagram Types

#### Request Flow Diagram

```
Client                    Server                    Database
  |                         |                         |
  |--- POST /orders ------->|                         |
  |                         |--- validate input       |
  |                         |--- check inventory ---->|
  |                         |<-- stock count ---------|
  |                         |--- create order ------->|
  |                         |<-- order record --------|
  |<-- 201 Created ---------|                         |
  |                         |                         |
```

#### Component Relationship Diagram

```
+------------+     +------------+     +------------+
|  Controller| --> | Use Case   | --> | Repository |
|  (HTTP)    |     | (Business) |     | (Database) |
+------------+     +------------+     +------------+
      |                  |                  |
      v                  v                  v
  Validates         Orchestrates       Persists
  request           domain logic       data
```

#### State Machine Diagram

```
              create
[Draft] -----------------> [Pending Review]
                                |
                    approve /   | reject
                          /    |
                         v     v
                  [Published] [Rejected]
                       |         |
               archive |         | revise
                       v         v
                  [Archived]  [Draft]
```

---

## Phase 3: Step-by-Step Walkthrough

### Walkthrough Rules

- Follow the EXECUTION PATH, not the file order
- Number every step sequentially
- For each step, state WHAT happens and WHY
- Mark data transformations explicitly
- Call out where control transfers between files/modules

### Walkthrough Template

```
EXECUTION TRACE: <scenario name>

Step 1: [file:line] <what happens>
  WHY: <why this step exists>
  DATA: <what data looks like at this point>

Step 2: [file:line] <what happens>
  WHY: <why this step exists>
  TRANSFORMS: <input> --> <output>

Step 3: [file:line] <control transfers to...>
  WHY: <why this delegation happens>
  ...
```

### Annotation Conventions

When referencing code inline, use these markers:

```
// KEY INSIGHT: This is the most important line to understand
// SIDE EFFECT: This modifies external state
// GUARD: This prevents invalid state from proceeding
// CACHE: This avoids redundant computation
// FALLBACK: This handles the failure case
// INVARIANT: This condition must always hold
```

---

## Phase 4: Gotcha Highlights

### What Qualifies as a Gotcha

A gotcha is any behavior that would surprise a developer reading the code for the first time:

| Category | Example |
|---|---|
| **Hidden mutation** | A getter that modifies state as a side effect |
| **Implicit ordering** | Code that only works because of execution order not enforced by the type system |
| **Silent failure** | Error caught and swallowed without logging or re-raising |
| **Magic values** | Hardcoded numbers or strings whose meaning is not obvious |
| **Temporal coupling** | Method A must be called before method B, but nothing enforces this |
| **Leaky abstraction** | Implementation detail leaking through an interface |
| **Performance cliff** | Code that works fine for N=100 but degrades at N=10000 |

### Gotcha Format

```
GOTCHA: <short title>
  WHERE: <file:line or function name>
  WHAT: <describe the surprising behavior>
  WHY IT MATTERS: <what goes wrong if you do not know this>
  SAFE APPROACH: <how to work with this code correctly>
```

---

## Phase 5: Summary

### Summary Rules

- One paragraph, maximum 4 sentences
- First sentence: what the code DOES (purpose)
- Second sentence: HOW it does it (mechanism)
- Third sentence: the KEY DESIGN DECISION and its tradeoff
- Fourth sentence (optional): what to watch out for

### Template

```
SUMMARY:
<Component/feature> handles <purpose> by <mechanism>.
The key design choice is <decision>, which trades <cost> for <benefit>.
When working with this code, be aware that <gotcha or constraint>.
```

---

## Explanation Depth Levels

Adapt the explanation depth to the audience:

| Level | Audience | Include | Skip |
|---|---|---|---|
| **Overview** | New team member, PM | Analogy, architecture diagram, summary | Code walkthrough, gotchas |
| **Standard** | Developer on the team | All five phases | None |
| **Deep Dive** | Developer debugging or extending | All five phases plus line-by-line trace | None, add extra detail |

Default to **Standard** unless the user specifies otherwise.

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Reading code line by line | Exhausting and misses the point | Follow execution path, explain intent |
| No visual diagrams | Hard to see the big picture | Always include at least one diagram |
| Jargon without explanation | Excludes non-experts | Define terms or use analogies |
| Explaining WHAT but not WHY | Reader learns syntax, not reasoning | Every step needs a WHY annotation |
| Skipping edge cases | Gotchas bite when least expected | Highlight non-obvious behavior |
| Wall of text | Loses reader attention | Use headers, diagrams, tables, and short paragraphs |
