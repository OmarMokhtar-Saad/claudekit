---
name: Context Keeper
description: Use for the whole session lifecycle — save and resume structured task state via .claude/session-context.md (auto-loaded by the session-start hook), and prime a fresh session with project identity, tech stack and conventions when there is nothing saved.
trigger: Use before ending a session on an in-progress task, when resuming one, or when switching between tasks in the same project. Works with the /save-session, /resume-session and /load commands.
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

---

# Structured State (merged from `session-continuity`)

The save/resume protocol above is the *live* one: `/save-session` writes
`.claude/session-context.md` and `.claude/hooks/session-start.sh` reads it. What
follows is the richer machine-readable state model the `session-continuity` skill
defined -- decision records with rationale and rejected alternatives, prioritised
pending tasks, gotchas, and a capped history array. Nothing in the repo reads or
writes `.claude/session-state.json` today, so treat this half as the schema to grow
*into* when markdown stops being enough, and as the source of the save and load
rules below -- which apply to `session-context.md` just as much. Merged from the
`session-continuity` skill, which is gone; the name resolves here through the
registry `renamed` alias map.

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

## Integration (state consumers)

- the priming sequence in the second half of this skill loads session state
- **planner** references pending tasks when creating new plans
- **coordinator** uses session state to understand current work context
- **git** agent can reference modified files for targeted commits

---

# Priming a Session (merged from `context-priming`)

Saving and resuming is half of session lifecycle; the other half is what to load
when there is nothing saved, or when the saved context covers only part of what the
next task touches. Merged from the `context-priming` skill, which is gone; the name
resolves here through the registry `renamed` alias map. There is no `/prime`
command -- `/load` and `/resume-session` are the entry points.

## Priming Sequence

Execute these steps in order on session start or when `/prime` is invoked.

### Step 1: Load Project Identity

Read these files (if they exist):
1. `CLAUDE.md` -- primary project instructions and conventions
2. `CONSTITUTION.md` -- behavioral rules and constraints
3. `.claude/session-state.json` -- the richer structured state described above,
   if a project chooses to keep it; `.claude/session-context.md` is the file the
   `session-start.sh` hook actually reads
4. `.claude/project-index.md` -- project structure map (via codebase-mapping skill)
5. `.claude/project-graph.json` -- dependency graph sidecar; do NOT inline it,
   query via `python3 .claude/operations/scripts/project-graph.py`
   (`query`/`hubs`/`path`) to stay inside the context budget

### Step 2: Scan Project Structure

If no project index exists, perform a lightweight scan:
1. List top-level directory contents
2. Identify the primary language from file extensions
3. Read the main entry point file (first 50 lines)
4. Read the primary config file (`package.json`, `pyproject.toml`, `Cargo.toml`, etc.)

### Step 3: Read Key Config Files

Parse and internalize:
| File | Purpose |
|------|---------|
| `package.json` / `pyproject.toml` / `Cargo.toml` | Dependencies, scripts, project metadata |
| `tsconfig.json` / `setup.cfg` / `rustfmt.toml` | Language/compiler configuration |
| `.eslintrc` / `.prettierrc` / `ruff.toml` | Linting and formatting rules |
| `Dockerfile` / `docker-compose.yml` | Container configuration |
| `.github/workflows/*.yml` | CI/CD pipeline definition |
| `.env.example` | Environment variable structure (NEVER read `.env`) |

### Step 4: Identify Tech Stack

Build a tech stack profile:
```
Language:    TypeScript 5.3
Runtime:     Node.js 20
Framework:   Express 4.18
Database:    PostgreSQL 15 (via Prisma 5.7)
Testing:     Jest 29 + Supertest 6
Linting:     ESLint 8 + Prettier 3
CI:          GitHub Actions
Deployment:  Docker + AWS ECS
```

### Step 5: Load Active Conventions

Extract coding conventions from:
1. `CLAUDE.md` explicit rules
2. Linter/formatter configuration
3. Existing code patterns (naming, structure, error handling)
4. Test patterns (framework, assertion style, file organization)
5. Git conventions (commit message format from recent history)

---

## Priming Template

After loading, internalize this context summary:

```
=== Project Context ===

Project: <name> (<language>)
Stack: <framework> + <database> + <testing>
Architecture: <pattern detected>

Conventions:
- Naming: <camelCase/snake_case/PascalCase>
- File structure: <by feature/by type/by layer>
- Error handling: <pattern observed>
- Testing: <framework, assertion style, coverage expectations>
- Git: <commit format, branch naming>

Active Task: <from session state, or "none">
Key Files: <list of files central to current work>
Gotchas: <from session state warnings>

Constraints:
- <from CLAUDE.md and CONSTITUTION.md>
=== End Context ===
```

---

## Selective Priming

For large projects, prime only the relevant context:

### By Task Type

| Task Type | Prime These |
|-----------|------------|
| Feature development | Target module + its tests + related services |
| Bug fix | Error location + related code paths + test files |
| Refactoring | Target module + all dependents + all dependencies |
| Documentation | Module being documented + existing docs + API surface |
| Testing | Target module + existing tests + test utilities |
| DevOps | CI configs + Dockerfile + deploy scripts + infrastructure |

### By Scope

| Scope | Depth |
|-------|-------|
| Single file | File + direct imports + corresponding test |
| Module | All files in module + shared dependencies + module tests |
| Cross-cutting | All affected modules + shared infrastructure + integration tests |
| Full project | Complete priming sequence |

---

## Refresh Triggers

Re-prime when:
- User switches to a different area of the codebase
- 30+ minutes have passed since last priming
- User reports Claude is "forgetting" project conventions
- After a `git pull` or `git merge` that changes project structure
- User explicitly invokes `/prime`

---

## Performance

- Full priming should complete in under 10 seconds
- Selective priming should complete in under 3 seconds
- Cache parsed config data in memory for the duration of the session
- NEVER re-read files that haven't changed since last read

---

## Integration (priming consumers)

- Invoked automatically by **coordinator** at session start
- Uses **codebase-mapping** output if available, and its graph sidecar
  (`.claude/project-graph.json`) — query it via the script, never inline it
- Feeds context to all downstream agents

