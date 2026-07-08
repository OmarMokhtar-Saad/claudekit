# Agent Invocation — Single Source of Truth

This document defines the **one** way ClaudeKit spawns a specialist agent. Any command,
agent, or skill that spawns another agent MUST follow this. If another doc disagrees with
this one, this one wins.

---

## Two verified mechanisms (tested 2026-07-08)

**Precondition for BOTH: valid YAML frontmatter.** Agent registration parses
`.claude/agents/*.md` frontmatter; bare `<example>` blocks between YAML fields made every
kit agent invisible to both the Task tool AND `claude -p --agent` ("agent not found").
Examples belong INSIDE the `description:` block scalar. A structural test now gates this
(`tests/test_behavior_spec.py::TestAgentRegistration`).

### 1. Task-tool invocation — DEFAULT for interactive sessions

With valid frontmatter, local agents register as subagent types at session start. Prefer
this in-session: no cold boot, inherits the session's MCP servers and permission gating,
and parallel groups spawn in ONE message. (Historical note: the old claim that
`subagent_type` "does not resolve local agents" was observed while the frontmatter was
invalid — wrong causality.)

### 2. Scoped headless `claude -p --agent` — for scripted/CI paths

```bash
claude -p --agent <agent-name> --model <model> --allowedTools "<scoped,tool,list>"
```

- `--agent <name>` loads `.claude/agents/<name>.md` as the system prompt.
- The prompt is passed on **stdin** (`echo "$MSG" | claude -p ...`); the result is on **stdout**.
- `--allowedTools` scopes the sub-agent to exactly the tools its role needs.
- **Cost: ~13–14s cold boot measured in this repo** (new CLI + MCP servers). MCP-heavy
  projects can hit timeouts — one field report (AppiumLens, 2026-06-30) did. Use this path
  for string-pipeline commands (/plan, /refine loops) and CI, not for interactive fan-outs.

Verified 2026-07-08: `claude -p --agent explore` failed with "agent not found" pre-fix;
post-fix it completed a trivial haiku task in 13s. Probe agent with clean frontmatter
confirmed causality (14s).

**Headless `.claude/**` write gate (verified 2026-07-08):** in `claude -p` mode the platform
treats `.claude/**` as sensitive and requires interactive approval for Write/Edit there —
bare `Write` in `--allowedTools`, path-scoped `Write(.claude/plans/**)`, and settings-file
allow rules were ALL tested and none bypass it. Consequence: headless agents deliver
`.claude/`-destined artifacts via **stdout**, and the invoking command saves them
(`tee` + `extract-json-from-plan.py` for plans). Full E2E pipeline validated the same day:
plan ($0.68/opus) → review ($0.18/opus, refutation ran) → implement ($0.36/sonnet, ops
engine) → verify ($0.64/sonnet, scores matched ground truth) ≈ $1.86 total on a small task.

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

| Agent                 | `--allowedTools`                                                | Rationale                                             |
|-----------------------|-----------------------------------------------------------------|------------------------------------------------------|
| planner               | `Read,Grep,Glob,Write,Bash(python3 .claude/operations/scripts/validate-config-json.py *)` | Explore; write `plan.md` + `ops.json`; self-validate the config before handoff. Bash is scoped to the validator only. |
| reviewer              | `Read,Grep,Glob`                                                | Read-only: analyze the plan/ops.json, emit a verdict.|
| explore               | `Read,Grep,Glob`                                                | Read-only codebase search.                           |
| debugger              | `Read,Grep,Glob,Bash(git log *),Bash(git diff *)`               | Read-only diagnosis; history inspection.             |
| verifier              | `Read,Grep,Glob,Bash`                                           | Must execute build/test/lint to produce evidence.    |
| implementer           | `Read,Grep,Glob,Bash(python3 .claude/operations/scripts/*)`     | Iron Law: changes flow through the ops engine only — never Edit/Write. |
| security-scanner      | `Read,Grep,Glob`                                                | Read-only scanning.                                  |
| silent-failure-hunter | `Read,Grep,Glob`                                                | Read-only scanning.                                  |
| code-reviewer         | `Read,Grep,Glob`                                                | Read-only review; findings need file:line.           |
| gitOps                | `Read,Bash(git *)`                                              | Git operations only.                                 |

Never grant unrestricted `Bash` to planner/reviewer or any read-only role — planner's Bash is
scoped to the ops validator script, nothing else. Add a row here before wiring a new agent —
do not invent a tool list at the call site.

---

## Verification spike (run when upgrading Claude Code)

In a fixture project:
1. Task-tool invocation of a local agent — does `.claude/agents/<name>.md` load without the
   in-prompt `Read`?
2. `claude -p --agent <name> --allowedTools "Read,Grep,Glob"` **without** any permission
   bypass — does it complete a read-only task headlessly without hanging on prompts?

Record results here and update the table + callers accordingly.
