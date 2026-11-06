# Core Pipeline Agents: coordinator, planner, reviewer

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

# Core Pipeline Agents

## coordinator

**Purpose.** Orchestration hub for all multi-agent workflows: classifies incoming tasks, selects the pipeline, spawns agents, manages handoffs and revision loops, tracks workflow state, and escalates to humans.

**Responsibilities.** Task classification (Feature/Bug/Quality/Git/Docs/Explore/Refactor/EPIC plus 14 specialist categories), workflow routing, state tracking, revision management, escalation.

**Inputs.** The raw user request. **Outputs.** Pipeline dispatches (handoff blocks), a `WORKFLOW STATUS` progress report to the user, and optionally file-based workflow state.

**Frontmatter (verbatim).**
- `name: coordinator`
- `description: Orchestration agent that analyzes tasks, routes to appropriate agents, manages handoffs, and tracks workflow state. Use when tasks require multiple agents or complex workflows.`
- `model: sonnet` | `color: gray`
- `tools: ["Read", "Grep", "Glob", "Bash", "Agent"]`

**Internal workflow.** (1) Receive and classify → (2) spawn first agent with structured handoff (Spawn Protocol) → (3) process agent output (success → advance; failure → escalation rules; revision → revision loop) → (4) revision loop: increment `revision_count`, escalate if >3, else route back to producing agent → (5) completion: compile summary, present to user, clean up state.

**Dependencies.** Loads 10 skills: `using-superpowers`, `golden-rule`, `multi-agent-coordination`, `dispatching-parallel-agents`, `subagent-driven-development`, `context-first-workflow`, `verification-before-completion` (which absorbed `verification-loop`), `autonomous-loop`, `context-budget`, `context-keeper` (which absorbed `session-continuity`), `search-first`. References Blueprint, Council, Codebase Onboarding, and Deep Research skills in routing. Dispatches all other agents; the Handoff Table describes what each agent expects/produces.

**Memory/context.** In-memory `WORKFLOW STATE` block (task_id, classification, pipeline, current_step, status, revision_count, max_revisions: 3). Persists to `.claude/state/workflow-<task_id>.json` when the pipeline has >3 agents, a revision loop is triggered, or the user requests persistence.

**Failure recovery.** Re-run a failed agent once with same inputs, then escalate. Six explicit escalation triggers (see Interaction Model above). Never skips agents, never proceeds past failures, never exceeds 3 revision cycles.

**Example invocation.** The coordinator is typically the entry point; it dispatches downstream agents per `_shared/TASK_TOOL_SPECIFICATION.md`:

```
TaskCreate:
  prompt: |
    You are the planner agent.
    Read your agent definition: .claude/agents/planner.md

    HANDOFF FROM: coordinator
    ---
    Task: Add user authentication with JWT tokens
    Classification: Feature
    Pipeline Position: Step 1 of 5
    Prior Agent Output: Initial task, no prior output
    Files Modified: None yet
    Expected Output: plan.md (Tier + Files: list) in .claude/plans/
    Return To: coordinator
  agent: planner
```

**Improvement notes.** Its classification table has no rows for tester, devops, database-architect, or documenter, though all four appear in its Handoff Table. Frontmatter grants the `Agent` tool while `_shared/INVOCATION.md` declares `claude -p --agent` the single spawning source of truth. Its Performance and Docs pipelines disagree with HANDOFF_PROTOCOL.md (see Known Issues).

---

## planner

**Purpose.** Produces implementation plans: a human-readable `plan.md` (with a `Tier:` line and a `Files:` list) for every task. It writes only this one artifact; the main session implements the approved plan directly.

**Responsibilities.** Codebase discovery, plan authoring, Tier and `Files:` list declaration, self-validation, revision handling from Reviewer feedback.

**Inputs.** Task description and codebase context (optionally an Explore or Debugger report). **Outputs.** `.claude/plans/plan-<name>.md` with a `Tier:` line and `Files:` list, a tiered plan brief (Simple/Medium/Complex), and a `HANDOFF TO: reviewer` block.

**Frontmatter (verbatim).**
- `name: planner`
- `description: Creates implementation plans (plan.md with Tier and Files:). Explores codebase, writes the plan the main session then implements. Use when a task needs an implementation plan before coding begins.`
- `model: opus` | `color: cyan`
- `tools: ["Read", "Grep", "Glob", "Write"]`

**Internal workflow.** Phase 1 Discovery (structure, tech stack, relevant files, tests, conventions) → Phase 2 Create Plan (Overview, Scope, Prerequisites, Steps with File/Action/Details, Testing Strategy, Rollback Plan, Risk Assessment) → Phase 3 Declare `Tier:` and the `Files:` list (every file a step touches) → Phase 4 Save the plan and emit handoff.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `context-first-workflow`, `brainstorming`, `writing-plans`. Downstream: reviewer.

**Memory/context.** Writes to `.claude/plans/`. Reads the codebase freely. On revision, overwrites the original plan and re-triggers the Reviewer without asking permission.

**Failure recovery.** Forbidden from asking mid-plan questions — batches all clarifications up front. Revision feedback loop: read all Reviewer feedback, update the plan, re-save, re-trigger Reviewer. Includes a self-review quality checklist before handoff.

**Example invocation.**
```bash
echo "Create a plan for adding a caching layer. Write plan.md to .claude/plans/" | \
  claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write"
```
(Per `_shared/INVOCATION.md`, planner's scoped tool list is `Read,Grep,Glob,Write` — never Bash.)

**Improvement notes.** Frontmatter tools include `Bash` and `Agent`, but INVOCATION.md's scoped list for planner is `Read,Grep,Glob,Write` (no Bash, no Agent, and Write is absent from the frontmatter list even though the agent must write plan files). The purpose of the `Agent` tool in its frontmatter is never used in the body.

---

## reviewer

**Purpose.** Plan validation gate. Scores `plan.md` across three weighted dimensions against a **90/100** threshold before plan-gate allows edits. This is explicitly the plan reviewer, distinct from `code-reviewer.md`.

**Responsibilities.** Pre-validation checks, mandatory rejection rules, weighted scoring, structured findings, revision routing, escalation after 3 revisions.

**Inputs.** `plan.md` path (Planner handoff). **Outputs.** `REVIEW REPORT` with score bars, decision (APPROVED / CONDITIONAL / REJECTED), findings by severity, and one of three handoffs (approved for editing / planner / coordinator).

**Frontmatter (verbatim).**
- `name: reviewer`
- `description: Multi-specialist plan validation with 90/100 approval threshold. Scores Plan Quality (40%), Architecture (30%), Security (30%). Use when a plan.md needs validation before implementation.`
- `model: sonnet` | `color: blue`
- `tools: ["Read", "Grep", "Glob"]`

**Internal workflow.** Pre-validation checklist (plan exists, `Tier:` and `Files:` present, steps match `Files:`, required sections) → mandatory rejection rules (8 automatic rejections that bypass scoring, including missing `Files:` list and hardcoded secrets) → Step 1 structural validation → Step 2 Plan Quality review (criteria table, 40%) → Step 3 Architecture review (30%) → Step 4 Security review (30%) → decision logic (≥90 approve, 70–89 conditional, <70 reject; revision 3 → escalate).

**Dual Review Mode.** With `--dual` (for security-sensitive plans, DB migrations, public API or auth changes) it loads the `santa-method` skill and spawns two independent sub-reviewers — Reviewer A (Skeptic/Opus, threshold 95) and Reviewer B (Pragmatist/Sonnet, threshold 90) — with anti-anchoring isolation; approval requires both.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `clean-architecture`, `security-checklist`, plus `santa-method` in dual mode. Upstream: planner. Downstream: `review-record.py plan-write` then main-session edits, or planner (revision) or coordinator (escalation).

**Memory/context.** Reads `.claude/plans/`. Read-only (no Write/Edit/Bash in tools). Tracks revision number in its handoffs (`Revision Number: <N> of 3`).

**Failure recovery.** Mandatory rejection path for structural failures; revision handoffs carry Critical/Warning findings; escalation handoff to coordinator at revision 3/3 with remaining issues and recommendation. Never approves below 90, never gives a perfect 100.

**Example invocation.**
```bash
echo "Review the plan at .claude/plans/plan-add-caching.md" | \
  claude -p --agent reviewer --model opus --allowedTools "Read,Grep,Glob"
```

**Improvement notes.** Dual mode says to "spawn two independent sub-reviewers in parallel", but its tool list (`Read,Grep,Glob`) contains no Agent/Task/Bash tool with which to spawn anything.

---

