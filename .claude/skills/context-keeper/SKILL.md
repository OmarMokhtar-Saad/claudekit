---
name: Context Keeper
description: Structured save/resume for session context. Serializes current task state (project, files touched, decisions made, next steps, open questions) to .claude/session-context.md. The session-start hook auto-loads this on next session start.
trigger: Use before ending a session on an in-progress task, or when switching between tasks in the same project. Works with /save-session and /resume-session commands.
---

# Context Keeper

Structured session state persistence. When Claude Code sessions end, context is lost. Context Keeper saves a structured snapshot that the `session-start.sh` hook auto-loads at the next session start, so you never have to re-explain what you were working on.

## Save Protocol

When `/save-session` is invoked, serialize this state:

### Required Fields

```markdown
# Session Context
**Saved:** <ISO timestamp>
**Project:** <project name from package.json/pyproject.toml/directory name>
**Task:** <one-sentence description of what you were working on>

## Current Status
<COMPLETE | IN_PROGRESS | BLOCKED>
<If BLOCKED: what is blocking progress>

## What Was Done
<Bullet list of completed work — specific, with file paths>
- Modified src/auth/middleware.ts — added JWT validation
- Created tests/auth.test.ts — 12 tests, all passing
- Updated .env.example — added JWT_SECRET placeholder

## Next Steps (in order)
<Ordered list of what to do next>
1. Fix the type error in src/api/routes.ts:87
2. Add integration test for the refresh token flow
3. Update CHANGELOG.md

## Decisions Made
<Key technical decisions made this session — so you don't re-debate them>
- Using RS256 (not HS256) because the auth server controls the private key
- Refresh tokens stored in httpOnly cookies (not localStorage) — XSS mitigation
- Chose to NOT use a library for JWT parsing — only 30 lines of code needed

## Open Questions
<Things that need human input or are unresolved>
- [ ] Should refresh token TTL be 7 days or 30 days? (ask @product)
- [ ] Need to confirm if the auth server supports RS256 key rotation

## Files Touched This Session
<List of all files modified — for quick git diff reference>
- src/auth/middleware.ts
- src/auth/tokens.ts (NEW)
- tests/auth.test.ts (NEW)
- .env.example
- CHANGELOG.md

## Context for Fresh Agent
<Anything a fresh agent needs to know that isn't obvious from the code>
- The auth middleware must come BEFORE the rate limiter in the Express chain
- Tests use a mock JWT server at localhost:9999 (started by jest global setup)
- The "legacy" auth system in src/legacy/ is intentionally NOT being migrated yet
```

### Optional Fields (include if relevant)

```markdown
## Active Plan
<Path to plan file if one is in progress>
.claude/plans/ops-add-auth.json — Step 3 of 5 complete

## Build Status
<Last known build/test status>
- tsc: PASS
- jest: 47/49 passing (2 skipped — need auth server running)
- eslint: PASS

## Key References
<External URLs, internal docs, or issue links needed for this task>
- Auth spec: [internal link]
- Related PR: #142 (merged, has context on old auth approach)
```

---

## Resume Protocol

When `/resume-session` is invoked (or session-start.sh auto-loads the context):

### Step 1: Load and Parse
```
Read .claude/session-context.md
Parse: task, status, next steps, decisions, open questions
```

### Step 2: Validate Freshness
```
Check save timestamp:
  < 4 hours ago  → Full trust, resume immediately
  4-24 hours ago → Trust but verify: quick git status check
  > 24 hours ago → Stale warning, re-read key files before resuming
  > 72 hours ago → Context may be significantly outdated, recommend fresh start
```

### Step 3: Reconstruct State
```
For IN_PROGRESS status:
  1. Run: git status (verify files match "Files Touched" list)
  2. Run: git log --oneline -5 (see what was committed)
  3. Read the first "Next Steps" file to verify it still matches the codebase
  4. Brief the user: "I'm resuming [task]. Last session: [what was done]. Next: [step 1]"

For BLOCKED status:
  1. Report the blocker immediately
  2. Ask for resolution before proceeding
```

### Step 4: Present Summary
```
CONTEXT RESUMED
===============
Task: <task description>
Status: <status>
Last saved: <N hours ago>

What was done:
  <bullet list>

Picking up at:
  <next step 1>

Decisions already made (not re-debating):
  <key decisions>

Open questions (need your input):
  <open questions if any>

Ready to continue. Starting with: <next step>
```

---

## File Location

```
.claude/session-context.md   ← current session context (overwritten on each save)
.claude/session-history/     ← optional: archived past contexts (session-YYYY-MM-DD.md)
```

The `session-start.sh` hook reads `.claude/session-context.md` automatically if it exists and is < 48 hours old.

---

## Integration with Commands

```
/save-session          → serialize current state to .claude/session-context.md
/resume-session        → load and display .claude/session-context.md
/save-session --archive → save + copy to .claude/session-history/session-<date>.md
```

---

## Anti-Patterns

- NEVER include sensitive data (API keys, passwords) in the context file
- NEVER include the full file contents — only paths and relevant snippets
- NEVER save a context file longer than 200 lines (defeats the purpose)
- NEVER resume without validating freshness — stale context causes wrong assumptions
