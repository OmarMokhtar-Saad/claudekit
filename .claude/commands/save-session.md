---
description: "Save current session state to .claude/session-context.md for resumption in the next session"
argument-hint: "[--archive]"
model: haiku
---

# Save Session Command

Serialize the current session state — task, files touched, decisions made, next steps, open questions — to `.claude/session-context.md`. The `session-start.sh` hook auto-loads this at the start of every new session.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **context-keeper** - Session state serialization protocol

## Task

Save session state: $ARGUMENTS

---

## Execution Steps

### Step 1: Gather Session State

Reconstruct the current state from this conversation:

```bash
# Get modified files this session
git status --short 2>/dev/null

# Get recent commits
git log --oneline -5 2>/dev/null

# Check for any active plan
ls .claude/plans/ops-*.json 2>/dev/null | head -3
```

### Step 2: Serialize to context-keeper Format

Write `.claude/session-context.md` with ALL required fields:

```markdown
# Session Context
**Saved:** <current ISO timestamp>
**Project:** <project name>
**Task:** <one-sentence description of active task>

## Current Status
<IN_PROGRESS|COMPLETE|BLOCKED>

## What Was Done
- <specific completed work with file paths>

## Next Steps (in order)
1. <next action>
2. <following action>

## Decisions Made
- <key technical decisions — so they're not re-debated next session>

## Open Questions
- [ ] <unresolved items needing human input>

## Files Touched This Session
- <list of files modified>

## Context for Fresh Agent
<anything a fresh agent needs to know that isn't in the code>
```

### Step 3: Archive (if --archive flag)

```bash
if echo "$ARGUMENTS" | grep -q '\-\-archive'; then
    mkdir -p .claude/session-history
    cp .claude/session-context.md ".claude/session-history/session-$(date '+%Y-%m-%d-%H%M').md"
    echo "Archived to .claude/session-history/"
fi
```

### Step 4: Confirm

```
SESSION SAVED
=============
File: .claude/session-context.md
Task: <task>
Status: <status>
Next step: <step 1>

Auto-loads at next session start via session-start.sh hook.
To restore manually: /resume-session
```

---

## Usage Examples

- `/save-session` — save current state
- `/save-session --archive` — save + archive a timestamped copy

## Notes

- Overwrites previous `.claude/session-context.md` (not archived unless --archive)
- Loaded automatically by `session-start.sh` if < 48 hours old
- Keep under 200 lines — long contexts defeat the purpose
- Never include API keys, passwords, or sensitive data
