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

## Delivery contract: paths, never payloads

Handoffs between agents (and between an agent and the main session) pass **file paths and
short summaries — never full file bodies.** A subagent response, an Agent-tool result, or a
Bash `echo`/`tee` that reprints a plan, ops.json, or other artifact's full contents is a
**contract violation**: that payload gets pinned in context for every subsequent turn,
which is exactly what caused a measured 80.3M-token session burn (`.claude/plans/
plan-token-waste-workflow-fixes.md`).

- **Interactive spawns** (Task tool) write their own artifacts with their own Write access
  and return only the path(s) plus a ≤10-line summary. Never instruct an interactive
  subagent to "return the complete plan" or "print the full ops.json."
- **Headless spawns** (`claude -p`) cannot Write into `.claude/**` (see the write-gate note
  above), so they legitimately deliver via stdout — but the invoking command's wrapper must
  capture that stdout and redirect it straight to disk (`printf '%s\n' "$out" > "$FILE"`)
  **without ever teeing or echoing it**. The only stdout that should reach the caller is a
  short scoreboard: file paths, a validation verdict, an op count, a few summary lines.
- **Revision/edit requests** operate in place on the existing file (Write/Edit on the same
  path) — never re-emit the complete artifact from scratch.

This is the rule the `/plan` (Issues 1–2) and `/refine` (Issue 3) fixes both apply; keep any
new command or agent that moves a plan/ops payload consistent with it.

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
| implementer           | `Read,Grep,Glob,Bash(python3 .claude/operations/scripts/*)`     | Iron Law: changes flow through the ops engine only — never Edit/Write. **(headless only — see "Frontmatter `tools:` CANNOT scope Bash" below; the interactive Task path grants unscoped Bash and this scoping is NOT applied there.)** |
| security-scanner      | `Read,Grep,Glob`                                                | Read-only scanning.                                  |
| silent-failure-hunter | `Read,Grep,Glob`                                                | Read-only scanning.                                  |
| code-reviewer         | `Read,Grep,Glob,Bash(git show *),Bash(git diff *),Bash(git rev-parse *),Bash(git ls-files *),Bash(git worktree *),Bash(gh pr *)` | Phase 0 must pin the revision under review before any finding: `gh pr diff/view`, `git diff <base>...<ref>`, `git show <ref>:<path>`, `git rev-parse HEAD`, `git ls-files --others` for untracked files, and a detached `git worktree` for whole-tree search. Non-mutating with respect to the repository under review — `git worktree` writes only to a detached tmpdir; no commit, no checkout of the shared tree. (Space-form specifiers verified honoured on this path, 2026-08-19.) |
| gitOps                | `Read,Bash(git *)`                                              | Git operations only.                                 |

Never grant unrestricted `Bash` to planner/reviewer or any read-only role — planner's Bash is
scoped to the ops validator script, nothing else. Add a row here before wiring a new agent —
do not invent a tool list at the call site.

---

## Frontmatter `tools:` CANNOT scope Bash (measured 2026-08-19, Claude Code 2.1.235)

**The table above is the headless `claude -p --allowedTools` contract, where scoping is real.
It does NOT describe the interactive Task-tool path.** That path reads
`.claude/agents/<name>.md` frontmatter instead, and frontmatter accepts **bare tool names
only**.

### How this was established

Fixture projects, `permissions: {"allow": [], "deny": []}` (**no allow rule, no deny rule**),
observed `permission_mode: "default"` read straight from the `PreToolUse` payload for the
command in question, no permission-bypass flag.

**Primary evidence — a differential test with the spawn path held constant.** The same
rule `Bash(python3 *)` was given the same write command (`python3 -c "open(...,'w')..."`),
with **both arms loaded through `--agent`** so the spawn path is not a variable:

| Arm | How the agent was configured | Result |
|---|---|---|
| frontmatter | frontmatter `tools: ["Read", "Bash(python3 *)"]` | **approval demanded**, no file — rule NOT applied |
| CLI | bare frontmatter `tools: ["Read", "Bash"]` + `--allowedTools "Read,Bash(python3 *)"` | ran **unapproved**, file written — rule APPLIED |

The only variable is where the rule was declared. An allow-rule IS honoured by an
agent-loaded session; the identical rule in frontmatter is not. Write-based, so no safe
read-only auto-approval explains it, and it relies on no self-report.

**What this establishes, and what it does not — do not overstate this sentence.** It
establishes that the **frontmatter-declared specifier is not applied**. It does NOT separate
*why*: whether the specifier is stripped at parse time or retained but ignored by the
permission layer was not distinguished, and the interactive **Task-tool** subagent path was
not isolated (both arms used `--agent`), so the hypothesis "the Task path applies no
allow-rule to subagents at all" remains untested there. Missing arm, so this stays
falsifiable: trust a fixture workspace, put `Bash(python3 *)` in `.claude/settings.json`
`permissions.allow`, and spawn via the Task tool; if the write still demands approval, that
hypothesis holds. (Attempted 2026-08-19, blocked by the workspace trust dialog.)

**The operational conclusion is unaffected and keeps high confidence:** frontmatter cannot
scope Bash, so the interactive implementer effectively holds unscoped Bash. Every hypothesis
above predicts that.

**Control.** Under `--allowedTools "Read,Bash(python3 *)"`, a `perl` write **required
approval** while the `python3` write ran freely — `--allowedTools` scoping is genuine
enforcement, which is what makes the differential meaningful.

**Corroborating only (weak instruments, not load-bearing).** An agent declaring
`tools: ["Read", "Bash(git status:*)"]` self-reported its tools as exactly `Read` and `Bash`;
`uname -s && whoami` ran unapproved under it. The first is an LLM narrating its own
registration; the second involves safe read-only commands `default` mode may auto-approve
regardless. Neither is used to carry the conclusion.

**Specifier syntax — both forms parse.** On the `--allowedTools` path, `Bash(python3 *)`
(space) and `Bash(python3:*)` (colon) were BOTH honoured, with no
`Ignoring --allowedTools rule` diagnostic for either. The space form used in the table above
is therefore live, not silently dropped.

**Hooks.** `agent_type` IS present in the `PreToolUse` payload on BOTH the `--agent` and the
Task-tool (`subagent_type`) paths, alongside `tool_name`, `tool_input.command`,
`permission_mode`, `cwd`, and `tool_use_id`. A hook CAN attribute a Bash call to the calling
subagent.

### Consequences, stated honestly (hard rule 6)

- **Never write a `Tool(specifier)` form in frontmatter `tools:`.** It reads as enforcement
  and is not — it is silently discarded, leaving the bare, unrestricted tool. A test gates
  this (`tests/test_agent_tool_grant_drift.py`).
- **On the interactive path the implementer holds UNSCOPED Bash, so the Iron Law is
  PROMPT-enforced there, not harness-enforced.** Removing `Bash` is not an option: the ops
  engine is invoked *through* Bash (`python3 .claude/operations/scripts/execute-json-ops.py`),
  so dropping it would break `/implement` outright. The mechanical fix is a `PreToolUse` hook
  keyed on `agent_type == "implementer"` that **allowlists** `execute-json-ops.py` plus a
  named read-only verb set and rejects everything else, failing closed (`exit 2` + stderr).
  A denylist of mutating commands would not do: `git apply`, `git checkout -- <path>`,
  `patch`, `ed`, `perl -pi`, `xargs`, `sh -c`, heredocs and `$(...)` all evade pattern
  lists. The allowlist must reject shell metacharacters and wrappers before matching,
  match on tokenised argv rather than a prefix, refuse `sed` when any token starts with
  `-i`, and pass through untouched when `agent_type` is absent or is not `implementer`.
  **The hook is not in place yet** — do not describe the interactive Iron Law as enforced
  until it is.

### Actual frontmatter grants (bare names — the interactive Task path)

This table records what the harness will really grant, not what we wish it granted. Narrowing
the wide rows is owned by each agent's maintainer.

| Agent | frontmatter `tools:` |
|-----------------------|--------------------------------|
| planner | `Read, Grep, Glob, Write, Bash` |
| reviewer | `Read, Grep, Glob` |
| explore | `Read, Grep, Glob, Bash` |
| debugger | `Read, Grep, Glob, Bash` |
| verifier | `Read, Bash, Grep, Glob` |
| implementer | `Read, Bash, Grep, Glob` |
| security-scanner | `Read, Bash, Grep, Glob` |
| silent-failure-hunter | `Read, Grep, Glob, Bash` |
| code-reviewer | `Read, Grep, Glob, Bash` |
| gitOps | `Read, Bash, Grep, Glob` |

**Wider than their documented role (known drift, not yet narrowed):** `explore`,
`security-scanner`, and `silent-failure-hunter` are documented above as read-only
`Read,Grep,Glob` but each declares `Bash` in frontmatter. `planner` declares bare `Bash`
where the headless row scopes it to the ops validator. Recorded rather than hidden.

---

## Verification spike (run when upgrading Claude Code)

In a fixture project:
1. Task-tool invocation of a local agent — does `.claude/agents/<name>.md` load without the
   in-prompt `Read`?
2. `claude -p --agent <name> --allowedTools "Read,Grep,Glob"` **without** any permission
   bypass — does it complete a read-only task headlessly without hanging on prompts?

Record results here and update the table + callers accordingly.
