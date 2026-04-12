---
name: session-continuity
description: "Use when maintaining context across Claude Code sessions -- saves session state, records key decisions, tracks modified files, and restores context on new session start."
---

# Session Continuity

## Purpose

Maintain development context across Claude Code sessions so that each new session can resume where the previous one left off. Eliminates the "cold start" problem where Claude must re-explore the codebase on every session.

---

## Session State File

Location: `.claude/session-state.json`

### Schema

```json
{
  "version": "1.0",
  "session_id": "uuid-v4",
  "started_at": "ISO-8601 timestamp",
  "ended_at": "ISO-8601 timestamp",
  "status": "active | paused | completed",
  "task": {
    "description": "What the user is working on",
    "goal": "The end-state being targeted",
    "progress": "percentage or phase description"
  },
  "decisions": [
    {
      "timestamp": "ISO-8601",
      "decision": "Description of what was decided",
      "rationale": "Why this choice was made",
      "alternatives_rejected": ["alt1", "alt2"]
    }
  ],
  "modified_files": [
    {
      "path": "relative/path/to/file",
      "action": "created | modified | deleted",
      "summary": "One-line description of change"
    }
  ],
  "pending_tasks": [
    {
      "description": "What still needs to be done",
      "priority": "high | medium | low",
      "blocked_by": "optional dependency description"
    }
  ],
  "context": {
    "key_files": ["paths to files that are central to current work"],
    "tech_stack_notes": "Any discoveries about the tech stack",
    "gotchas": ["Things to watch out for"],
    "conventions": ["Patterns observed in the codebase"]
  },
  "history": [
    {
      "session_id": "previous-session-uuid",
      "summary": "One-paragraph summary of what was accomplished"
    }
  ]
}
```

---

## Save Protocol (End of Session)

Trigger: User says goodbye, session is ending, or `/session save` is invoked.

### Steps

1. **Summarize progress**: What was the task? What was accomplished? What remains?
2. **Record decisions**: List every non-trivial decision made during the session with rationale
3. **Track modifications**: List all files created, modified, or deleted
4. **Identify blockers**: Note anything that prevented completing a task
5. **Capture gotchas**: Document surprising discoveries about the codebase
6. **Write state file**: Save to `.claude/session-state.json`
7. **Confirm to user**: Display a summary of what was saved

### Save Rules

- ALWAYS save before the session ends if any meaningful work was done
- NEVER save secrets, credentials, or API keys in the state file
- ALWAYS use relative paths (relative to project root)
- ALWAYS overwrite the previous session state (keep history array for past sessions)
- Maximum 10 entries in the history array (oldest are dropped)

---

## Load Protocol (Start of Session)

Trigger: New session begins, or `/session load` is invoked.

### Steps

1. **Check for state file**: Read `.claude/session-state.json` if it exists
2. **Display context summary**:
   ```
   Resuming session from <timestamp>
   Task: <task description>
   Progress: <progress>
   Last modified: <list of recently modified files>
   Pending: <pending tasks>
   Gotchas: <any warnings>
   ```
3. **Verify file state**: Check that modified files from the last session still exist and haven't been changed externally
4. **Flag conflicts**: If files were modified outside the session, alert the user
5. **Load key files**: Read the files listed in `context.key_files` to prime the context
6. **Resume or restart**: Ask the user if they want to continue from where they left off or start fresh

### Load Rules

- ALWAYS check if state file exists before attempting to load
- NEVER assume the codebase is unchanged since last session
- ALWAYS verify file integrity before resuming work
- If the state file is corrupted or invalid, report the issue and start fresh

---

## Session Summary Format

When displaying the session summary (on save or load):

```
--- Session State ---
Task:     Add JWT authentication to the API
Progress: 60% -- middleware complete, route guards pending
Status:   Paused

Decisions:
  1. Using RS256 algorithm (asymmetric) over HS256 for token signing
  2. Storing refresh tokens in httpOnly cookies, not localStorage
  3. Token expiry: 15min access, 7d refresh

Modified Files:
  + src/middleware/auth.ts         (created -- JWT validation middleware)
  ~ src/routes/user.ts             (modified -- added auth guard)
  ~ src/config/index.ts            (modified -- added JWT config)

Pending:
  [HIGH] Add auth guards to remaining 8 route files
  [MED]  Write integration tests for auth middleware
  [LOW]  Update API documentation with auth headers

Gotchas:
  - The existing session middleware conflicts with JWT -- must disable for API routes
  - Test database does not have the users table yet
---
```

---

## Integration

- **context-priming** loads session state as part of its priming sequence
- **planner** references pending tasks when creating new plans
- **coordinator** uses session state to understand current work context
- **git** agent can reference modified files for targeted commits
