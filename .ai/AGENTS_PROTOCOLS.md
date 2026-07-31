# Meta Docs and Shared Protocols

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

# Meta Docs and Shared Protocols

## HANDOFF_PROTOCOL.md

Defines the standardized handoff block format (quoted in full in the Interaction Model above), six handoff rules, eleven agent-specific handoff variants, the pipeline flow reference for all named pipelines, a pre-send handoff validation checklist (target correct, fields present, paths valid, status accurate, expected output defined, return routing set, no sensitive data), and failed-handoff recovery (log → retry once → escalate to Coordinator → Coordinator retries differently, skips if non-critical, or escalates to human). Applied at every agent-to-agent transition. Notably, it is the only document that formally splits the Docs pipeline into "New Documentation" (Documenter) and "Update Existing Documentation" (DocUpdater), and its Performance pipeline shape differs from coordinator.md's.

## QUICK_START.md

The system's fast reference: agents-at-a-glance tables (10 Core Pipeline agents, 18 Specialist agents, with role/permissions/model columns), 12 common workflows with trigger keywords, the six Key Rules (ops.json mandatory; 90/100 plan approval with 40/30/30 weights; 80/100 verification with 30/40/30 weights; max 3 plan revisions; max 2 implementation retries; agents are silent), the `_shared/` template index, the full file-location map of `.claude/` (agents, hooks, commands, skills, operations, state, reports, plans), and customization steps (hook config in `.claude/hooks/config.json`, chmod hooks, adding custom agents per AGENT_TEMPLATE.md with a matching command and coordinator routing update, and threshold tuning by editing reviewer.md/verifier.md/coordinator.md). Several of its permission and model entries disagree with agent frontmatter (see Known Issues). See also [./HOOKS.md](./HOOKS.md) and [./COMMANDS.md](./COMMANDS.md).

## _shared/AGENT_TEMPLATE.md

The initialization contract for every agent: silent mode rules (no narration, no permission requests, no mid-task status, no option menus, completion under 100 tokens, detailed output goes to report files; the single exception is batching blocking questions up front), the skill loading protocol (load in order, log failures, never block on a failed skill; `using-superpowers` is mandatory first for ALL agents), non-negotiable safety rules across four domains (file, git, execution, scope), the standard `<AGENT> COMPLETE` output format, the generic handoff format, error handling severity ladder (minor → fix and continue; moderate → one fix attempt then report; critical → stop and escalate; never retry more than once without escalating), and anti-patterns including "NEVER modify your own agent definition file." Applied by every agent at initialization; QUICK_START directs custom-agent authors to follow it.

## _shared/CONTEXT_CLEANUP_PROTOCOL.md

Context hygiene: "Each agent invocation = fresh context." Defines what crosses boundaries (handoff block, deliverable file paths, scores/statuses, constraints) versus what never does (internal reasoning, partial search results, tool history, abandoned drafts); the 7-step agent lifecycle (RECEIVE → LOAD → EXECUTE → VERIFY → OUTPUT → HANDOFF → EXIT with total state discard); Task-tool spawn rules with the correct file-mediated pattern (`.claude/state/handoff-<id>.md` in, `.claude/state/result-<id>.md` out) versus the incorrect inline-blob pattern; the `.claude/state/` directory layout and workflow state JSON format; pollution-prevention rules (always re-read files, verify inherited claims like "tests pass" yourself); and post-workflow cleanup policy (success: archive state, keep plans/reports; failure or escalation: keep everything). Applied whenever agents are spawned or hand off.

## _shared/INVOCATION.md

The declared **single source of truth** for spawning agents: scoped headless `claude -p --agent <name> --model <model> --allowedTools "<list>"` with the prompt on stdin and result on stdout. Explains why the Task tool's `agent:`/`subagent_type` parameter is not relied on for project-local definitions (must `Read your agent definition` in-prompt instead), with a verification spike to re-run on Claude Code upgrades. Contains the IRON RULE banning `--dangerously-skip-permissions` everywhere (the only sanctioned future exception being an explicit opt-in on `/loop-start` once a sandbox profile exists). Its scoped tool table currently covers only two agents — planner (`Read,Grep,Glob,Write`) and reviewer (`Read,Grep,Glob`) — with the instruction to add a row before wiring any new agent. Applied by every command/agent/skill that spawns another agent; "If another doc disagrees with this one, this one wins."

## _shared/OUTPUT_TEMPLATE.md

Silent-mode output standards: token limits per output type (completion 100, inline error 50, handoff 200, escalation 150 — anything larger goes to a report file); the completion message format with example; report file conventions (`.claude/reports/<agent>-<descriptor>-<YYYYMMDD>.md` with Summary/Details/Evidence/Next Steps sections); error output formats; progress output format (permitted only when a hook/command enables it, `verbose: true`, or the coordinator requests it); structured data conventions (25-char score bars using U+2588/U+2591 at 4 points per char, checklist glyphs `[x] [ ] [-] [!]`, table and key-value alignment); and forbidden output patterns ("Let me start by...", "Would you like me to...", filler acknowledgments, narrating tool use). Applied to every agent's user-facing and pipeline-facing output.

## _shared/TASK_TOOL_SPECIFICATION.md

Task-tool spawn patterns, explicitly subordinate to INVOCATION.md ("Authority: `_shared/INVOCATION.md` is the single source of truth"). Defines the basic spawn pattern (always begins `You are the <agent-name> agent. Read your agent definition: .claude/agents/<agent-name>.md` followed by a structured handoff), the file-context spawn variant, five spawn rules (one agent per Task, structured input, file-based output, **no nested spawning — only the Coordinator spawns**, timeout awareness), the Coordinator dispatch loop, parallel spawn patterns with safe/forbidden combinations, task monitoring via TaskGet/TaskList, error handling for agent errors / spawn failures / timeouts (each: retry once then escalate, never silently skip), handoff context size guidelines (what goes inline versus in a file), and a worked full-pipeline dispatch example for "Add user authentication." Applied wherever a workflow uses the Task tool rather than headless invocation.

## _shared/VALIDATION_CHECKLIST.md

Pre-flight and post-completion validation. The universal pre-flight covers Environment (project root, tools available, agent definition exists), Input (structured handoff, readable referenced files, clear task, no conflicts), Safety (within permissions, no unapproved destructive ops, no secrets in input, targets inside the project), and Dependencies (prior steps complete, deliverables exist, no blockers) — ending in READY or BLOCKED (do not proceed). Adds agent-specific pre-flights for planner, reviewer, implementer, verifier, gitOps, debugger, documenter, and explore, plus a post-completion checklist (deliverables exist/non-empty/well-formed; verification gate run with evidence; handoff structured; cleanup done). A condensed two-line variant is allowed for simple tasks; the full version is required for >3 files, pipeline dependencies, code execution, or security implications. Applied at the start and end of every agent task.

## _shared/VERIFICATION_PROTOCOL.md

Evidence-based completion: "No claims without evidence." Defines the VERIFICATION GATE every agent must pass before reporting completion (at least one concrete verification step, evidence included, no unresolved errors, deliverables accessible), per-agent evidence types (Planner: files exist, ops count matches steps; Reviewer: all criteria scored, formula matches; Implementer: build exit code, lint, test counts, dry run; Verifier: tools actually run with outputs; GitOps: branch, commit hash, secret scan, push confirmation; Debugger: reproduction, file:line root cause, traced path, justified confidence; Documenter: paths exist, no placeholders, links resolve; Explore: queries executed, files actually read), quick versus full verification formats, the unacceptable-evidence list ("I believe this is correct", "should work", quoting from memory), and the escalation format on unresolvable verification failure. Applied before any agent claims completion; referenced by AGENT_TEMPLATE.md's anti-patterns.

## _shared/WORKFLOW_FILE_TEMPLATES.md

Canonical file templates: the plan file (`.claude/plans/plan-<descriptor>.md`), operations config (`.claude/plans/ops-<descriptor>.json`), review report (`.claude/reports/review-<descriptor>.md` with the 40/30/30 scoring table), verification report (`.claude/reports/verification-<descriptor>.md` with the 30/40/30 table and penalties), exploration report, debug report, workflow state (`.claude/state/workflow-<id>.json` with `max_revisions: 3`), and handoff file (`.claude/state/handoff-<id>.md`). Applied whenever agents write workflow artifacts. **Warning:** its ops.json template uses a legacy schema (`version`, `plan_ref`, types `create|modify|delete|move|rename`, `file` key, `changes` array, `rollback`, `validation` block) that planner.md's modern canonical schema explicitly says the validator will reject (see Known Issues).

---

