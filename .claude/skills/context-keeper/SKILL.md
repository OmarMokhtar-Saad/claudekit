---
name: Context Keeper
description: Use for the whole session lifecycle — save and resume structured task state via .claude/session-context.md (auto-loaded by the session-start hook), and prime a fresh session with project identity, tech stack and conventions when there is nothing saved.
trigger: Use before ending a session on an in-progress task, when resuming one, or when switching between tasks in the same project. Works with the /save-session, /resume-session and /load commands.
---

# Context Keeper

Structured session state persistence. When Claude Code sessions end, context is lost. Context Keeper saves a structured snapshot that the `session-start.sh` hook auto-loads at the next session start, so you never have to re-explain what you were working on.

## Which half you need

| Situation | Do this |
|---|---|
| Ending a session, `/save-session` | Write `.claude/session-context.md` -- fields and template in the save reference |
| Resuming, `/resume-session`, or the hook auto-loaded context | Validate freshness (below), reconstruct state, brief the user |
| Wanting decision records, prioritised tasks, history | The structured-state schema (`.claude/session-state.json`) |
| Nothing saved, or a fresh area of the codebase | Prime the session (identity, stack, conventions); there is no `/prime` command -- `/load` and `/resume-session` are the entry points |

Read [references/save-resume.md](references/save-resume.md) when you save or resume -- required/optional fields, the four resume steps and the CONTEXT RESUMED summary.
Read [references/structured-state.md](references/structured-state.md) when you need the JSON state schema, its save/load steps, or the session summary format.
Read [references/priming.md](references/priming.md) when you prime a session -- the five-step sequence, config-file table, priming template, and selective priming by task type and scope.

## Freshness gate (resume)

```
Check save timestamp:
  < 4 hours ago  → Full trust, resume immediately
  4-24 hours ago → Trust but verify: quick git status check
  > 24 hours ago → Stale warning, re-read key files before resuming
  > 72 hours ago → Context may be significantly outdated, recommend fresh start
```

For BLOCKED status: report the blocker immediately and ask for resolution before
proceeding.

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


## Save and load rules (apply to `session-context.md` too)

- ALWAYS save before the session ends if any meaningful work was done
- NEVER save secrets, credentials, or API keys in the state file
- ALWAYS use relative paths (relative to project root)
- ALWAYS overwrite the previous session state (keep history array for past sessions)
- Maximum 10 entries in the history array (oldest are dropped)
- ALWAYS check if state file exists before attempting to load
- NEVER assume the codebase is unchanged since last session
- ALWAYS verify file integrity before resuming work
- If the state file is corrupted or invalid, report the issue and start fresh

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

