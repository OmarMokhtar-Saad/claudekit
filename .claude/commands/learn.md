---
description: "Extract and save reusable patterns learned in this session as skills for future use"
argument-hint: "[--extract|--list|--show <name>|--delete <name>]"
model: sonnet
---

# Learn Command

Extract reusable patterns from this session and save them as skills for future Claude Code sessions. This implements continuous learning — patterns discovered now become available to future sessions automatically.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **continuous-learning** - Pattern extraction methodology

## Task

Manage learned patterns: $ARGUMENTS

---

## Workflows

### Extract Patterns from This Session

```
/learn --extract
```

Reviews the session, identifies extractable patterns, and proposes saving them.

### List Saved Patterns

```
/learn --list
```

Shows all patterns saved across sessions.

### View a Specific Pattern

```
/learn --show <name>
```

Displays the full content of a learned skill.

### Delete a Stale Pattern

```
/learn --delete <name>
```

Removes a pattern that's no longer accurate.

---

## Extraction Process

### Step 1: Session Review

Ask these questions about the current session:

1. **What novel problem was solved?** — Problems solved in a non-obvious way
2. **What project-specific pattern was discovered?** — How THIS codebase works
3. **What debugging technique worked?** — Systematic approaches that succeeded
4. **What error was resolved?** — Error + root cause + fix
5. **What workflow was effective?** — Sequence of steps that achieved the goal

### Step 2: Assess Extractability

For each candidate pattern, score it:

```
Reusability (applies broadly = high):  _/10
Novelty (not obvious/documented = high): _/10
Combined score >= 10 → Extract
```

### Step 3: Write the Learned Skill

Create `~/.claude/skills/learned/<category>/<name>.md`:

```markdown
---
name: <name>
description: "<what this teaches>"
type: learned
source: <project>
date: <YYYY-MM-DD>
confidence: [high|medium|low]
---

## Context
[When does this apply?]

## Pattern
[The rule or knowledge]

## Evidence
[What confirms this is true]

## Example
[Concrete demonstration]
```

### Step 4: Register Pattern

Add to `~/.claude/skills/learned/INDEX.md` and update the registry.

---

## Output Format

```
## Learning Extraction Report

### Session Analysis
[Brief description of what happened this session]

### Extractable Patterns Found: N

PATTERN #1 — [EXTRACT | SKIP]
Name: <name>
Category: [error-resolution | project-pattern | workflow | debugging]
Reusability: X/10
Novelty: X/10
Summary: <one line>
[If EXTRACT: saved to ~/.claude/skills/learned/...]

### Patterns Saved This Session
[List of newly saved patterns]

### Total Learned Skills: N
[~/.claude/skills/learned/]
```

---

## Usage Examples

- `/learn --extract` — Analyze session and extract patterns
- `/learn --list` — Show all saved patterns with dates
- `/learn --show debugging/null-pointer-in-async` — Read a specific pattern
- `/learn --delete deprecated/old-pattern` — Remove stale pattern
- `/learn --stats` — Show pattern count by category and age

## Notes

- Patterns are stored globally in `~/.claude/skills/learned/`
- They are available across ALL projects, not just this one
- Mark patterns with `confidence: low` if uncertain — re-validate before relying on them
- Review and prune stale patterns monthly
- Project-specific patterns are tagged with `source: <project>`
