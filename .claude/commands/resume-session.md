---
description: "Load previous session context from .claude/session-context.md and resume work with full state restored"
argument-hint: "[--list]"
model: haiku
---

# Resume Session Command

Load and reconstruct the last saved session state. Verifies the context is still fresh, checks git state against what was saved, and briefs you on exactly where to pick up.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **context-keeper** - Session resume protocol

## Task

Resume session: $ARGUMENTS

---

## Execution Steps

### Step 1: Handle Flags

```bash
if echo "$ARGUMENTS" | grep -q '\-\-list'; then
    # List available session history
    echo "Current session context:"
    ls -la .claude/session-context.md 2>/dev/null || echo "  (none)"
    echo ""
    echo "Session history:"
    ls -lt .claude/session-history/ 2>/dev/null | head -10 || echo "  (none)"
    exit 0
fi
```

### Step 2: Load Context File

```bash
CONTEXT_FILE=".claude/session-context.md"

if [ ! -f "$CONTEXT_FILE" ]; then
    echo "No session context found at $CONTEXT_FILE"
    echo "Run /save-session to save current session state."
    exit 0
fi

# Check age
SAVED_TIME=$(head -5 "$CONTEXT_FILE" | grep "Saved:" | sed 's/.*Saved: //')
echo "Context from: $SAVED_TIME"
```

### Step 3: Validate Freshness and Git State

Apply context-keeper resume protocol:
- < 4 hours: full trust, resume immediately
- 4–24 hours: verify with `git status` + `git log --oneline -5`
- > 24 hours: stale warning, re-read key files
- > 72 hours: recommend fresh start

```bash
git status --short
git log --oneline -5
```

Cross-reference the "Files Touched" list from context against current git state. Flag any discrepancies.

### Step 4: Present Reconstruction

```
CONTEXT RESUMED
===============
Task: <task from context>
Status: <IN_PROGRESS|COMPLETE|BLOCKED>
Saved: <N hours ago>

What was done last session:
  <bullet list>

Decisions already made (not re-debating):
  <decisions>

Open questions needing your input:
  <open questions if any>

Git state check:
  <MATCHES CONTEXT | DISCREPANCIES: list them>

Picking up at:
  → <next step 1>

Ready. Starting with: "<next step>"
```

---

## Usage Examples

- `/resume-session` — load and resume from last saved context
- `/resume-session --list` — list available context files and history

## Notes

- Reads `.claude/session-context.md` (auto-saved by `/save-session`)
- Also auto-loaded by `session-start.sh` hook if < 48 hours old
- For older contexts, use `/resume-session` manually to control the load
- Context from > 72 hours ago triggers a warning — re-read key files before acting
