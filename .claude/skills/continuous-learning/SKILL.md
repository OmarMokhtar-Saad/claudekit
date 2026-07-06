---
name: continuous-learning
description: "Use when setting up automatic pattern extraction from sessions — Stop hook that learns reusable patterns and saves them as skills"
disable-model-invocation: true
---

# Continuous Learning

## Core Principle

**Every session is a learning opportunity.** When you solve a problem in a novel way, debug an unusual issue, or discover a project-specific pattern — that knowledge should persist beyond the current conversation.

This skill governs how Claude extracts reusable patterns at session end and saves them as skills for future sessions.

---

## When Pattern Extraction Triggers

The Stop hook evaluates the session when:

1. The session had **10 or more meaningful exchanges** (not just clarifications)
2. At least one of these occurred:
   - A non-trivial bug was diagnosed and fixed
   - A project-specific pattern was discovered
   - An effective workflow was used that could generalize
   - An error recovery strategy succeeded

If the session was primarily reading/exploring with no novel problem-solving, skip extraction.

---

## What to Extract

### Extractable Patterns

| Pattern Type | Example | Store As |
|-------------|---------|----------|
| Project-specific idiom | "This codebase uses X pattern for Y" | `~/.claude/skills/learned/<project>/patterns.md` |
| Effective debugging technique | "When Foo fails, check Bar first" | `~/.claude/skills/learned/debugging/<topic>.md` |
| Error resolution recipe | "Error X is caused by Y, fix with Z" | `~/.claude/skills/learned/errors/<error-code>.md` |
| Build/tool configuration | "This project needs FLAG=1 to build" | `~/.claude/skills/learned/<project>/setup.md` |
| Workflow that worked well | "For this repo, always X before Y" | `~/.claude/skills/learned/<project>/workflow.md` |

### NOT Extractable

- Information already in CLAUDE.md files (read the file, don't duplicate)
- Generic programming knowledge (belongs in a skill, not a learned pattern)
- Temporary workarounds flagged as "don't do this permanently"
- User-specific preferences (store in user memory, not learned skills)

---

## Extraction Workflow

### Step 1: Session Review

At session end (Stop hook), review the transcript:

```
Questions to ask:
1. What problem was solved that wasn't obvious at the start?
2. What did I learn about THIS codebase specifically?
3. What workflow worked well that I'd want to repeat?
4. What error was diagnosed — and how?
5. Did I discover a pattern that would help a new developer here?
```

### Step 2: Pattern Assessment

Score each potential pattern:

```
Reusability Score:
- Applies to only this file/function: 1 (don't extract)
- Applies to this module: 3 (consider)
- Applies to this project: 7 (extract)
- Applies across projects: 9 (extract as general skill)

Novelty Score:
- Already documented in CLAUDE.md: 0 (skip)
- Common knowledge: 2 (skip)
- Project-specific discovery: 8 (extract)
- Surprising behavior worth remembering: 9 (extract)

Combined score >= 10: Extract
Combined score < 10: Skip
```

### Step 3: Write the Learned Skill

Create a new file in `~/.claude/skills/learned/`:

```markdown
---
name: <descriptive-name>
description: "<one-line summary of what this teaches>"
type: learned
source: <project-name>
date: <YYYY-MM-DD>
confidence: [high|medium|low]
---

# <Title>

## Context
[When does this apply? What project/situation?]

## Pattern
[What to do or know]

## Evidence
[Why this is true — what confirmed it]

## Example
[Concrete example of applying this]

## Caveats
[Any exceptions or conditions where this doesn't apply]
```

### Step 4: Register in Skill Registry

Add to `~/.claude/skills/learned/INDEX.md`:

```markdown
- [Pattern Name](./path/to/skill.md) — one-line description — project: <name>
```

---

## Learning Categories

### Error Resolutions

When a specific error was diagnosed:

```markdown
## Error: <ExactErrorMessage>

**Root Cause:** <why it happens>
**Fix:** <what to do>
**Verification:** <how to confirm it's fixed>
**Recurrence Prevention:** <how to avoid in future>
```

### Project Patterns

When a codebase-specific pattern is discovered:

```markdown
## Pattern: <Name>

**Applies to:** <project or module>
**Discovery:** <how this was found>
**Rule:** <the pattern in one sentence>
**Example:** [code or command]
**Rationale:** <why this codebase does it this way>
```

### Workflow Discoveries

When an effective workflow is used:

```markdown
## Workflow: <Name>

**Use when:** <trigger condition>
**Steps:**
1. [step]
2. [step]
...
**Outcome:** <what this achieves>
**Validated:** YES — used successfully on [date]
```

---

## Anti-Patterns to Avoid

- **Over-extraction:** Don't save every session's details. Quality > quantity.
- **Stale patterns:** Mark patterns with dates; re-validate after major refactors.
- **Circular learning:** Don't extract something that contradicts a CLAUDE.md rule.
- **False confidence:** Mark uncertain patterns as `confidence: low` and validate.

---

## Configuration

Control extraction sensitivity in `.claude/hooks/config.json`:

```json
{
  "continuous_learning": {
    "enabled": true,
    "min_session_messages": 10,
    "auto_approve": false,
    "storage_path": "~/.claude/skills/learned/",
    "categories": ["error-resolution", "project-patterns", "debugging", "workflow"]
  }
}
```
