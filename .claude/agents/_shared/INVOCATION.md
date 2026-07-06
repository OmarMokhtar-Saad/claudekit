# Agent Invocation — Single Source of Truth

This document defines the **one** way ClaudeKit spawns a specialist agent. Any command,
agent, or skill that spawns another agent MUST follow this. If another doc disagrees with
this one, this one wins.

---

## The verified mechanism: scoped headless `claude -p --agent`

```bash
claude -p --agent <agent-name> --model <model> --allowedTools "<scoped,tool,list>"
```

- `--agent <name>` loads `.claude/agents/<name>.md` as the system prompt.
- The prompt is passed on **stdin** (`echo "$MSG" | claude -p ...`); the result is on **stdout**.
- `--allowedTools` scopes the sub-agent to exactly the tools its role needs.

### Why not the Task tool's `agent:` parameter?
As of the current Claude Code release we do not rely on the Task/`subagent_type`
parameter to resolve **project-local** `.claude/agents/*.md` definitions. Where a workflow
does use the Task tool, it must load the definition explicitly inside the prompt
(`Read your agent definition: .claude/agents/<name>.md`) — see `TASK_TOOL_SPECIFICATION.md`.
Re-run the spike below when upgrading Claude Code; if native resolution is confirmed, migrate
here first and update every caller.

---

## IRON RULE: never `--dangerously-skip-permissions`

Spawned agents read repo files and untrusted plan/source text, so they must run **with**
permission gating. `--dangerously-skip-permissions` is banned in all shipped commands, agents,
and skills. Scope with `--allowedTools` instead — a sub-agent that only needs to read and
write a plan file has no business running arbitrary Bash.

The only sanctioned place a permission bypass may exist is an **explicit, default-off,
loudly-warned opt-in** on `/loop-start` (autonomous mode) — and only once the sandbox profile
lands. It is not present today.

---

## Scoped tool lists per role

| Agent    | `--allowedTools`             | Rationale                                             |
|----------|------------------------------|------------------------------------------------------|
| planner  | `Read,Grep,Glob,Write`       | Explore the codebase; write `plan.md` + `ops.json`.  |
| reviewer | `Read,Grep,Glob`             | Read-only: analyze the plan/ops.json, emit a verdict.|

Never grant `Bash` or unrestricted tools to planner/reviewer. Add a row here before wiring a
new agent — do not invent a tool list at the call site.

---

## Verification spike (run when upgrading Claude Code)

In a fixture project:
1. Task-tool invocation of a local agent — does `.claude/agents/<name>.md` load without the
   in-prompt `Read`?
2. `claude -p --agent <name> --allowedTools "Read,Grep,Glob"` **without** any permission
   bypass — does it complete a read-only task headlessly without hanging on prompts?

Record results here and update the table + callers accordingly.
