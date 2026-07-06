# ClaudeKit AI Surface Audit — Agents, Commands, Skills, Hooks, Orchestration

**Auditor role:** AI Agent Architect + Prompt Engineer
**Date:** 2026-07-05
**Scope:** `.claude/agents/` (30 agents + `_shared/` + HANDOFF_PROTOCOL.md), `.claude/commands/` (39), `.claude/skills/` (73 + registry), `.claude/hooks/` (16 shell hooks + settings.json), `templates/` (modes, commands, hooks, per-language CLAUDE.md), `i18n/`, `operations/scripts/`.

**Headline numbers**

| Metric | Value |
|---|---|
| Total instruction surface (agents + skills + commands) | ~835 KB ≈ **~208K tokens** |
| Always-loaded metadata (agent descriptions + skill descriptions + command descriptions) | **~11.6K tokens** before any work happens |
| Coordinator "mandatory skill loading" (12 skills) | ~2,400 lines ≈ **~28–35K tokens** to boot one orchestrator |
| Agents | 30 (recommend keep 18, merge 9, delete/convert 3) |
| Skills | 73 (recommend consolidating ~20 into ~8) |
| Commands | 39 (recommend ~28 after merging wrappers) |
| Registry drift | 3 issues (minor — see Registry Hygiene) |

**Overall assessment:** This is one of the more ambitious Claude Code harnesses I've reviewed. The ops.json pipeline is *genuinely enforced* (Python validators + a PreToolUse hook that hard-blocks Edit/Write on source files) — that is rare and valuable. The Santa/GAN anti-anchoring designs are conceptually correct. But the kit suffers from severe instruction inflation, at least four direct self-contradictions on its most critical path (plan → review → implement), duplicated capability across agents/skills/commands, and quality gates whose numbers (90/100, 80/100) are self-reported LLM scores with no calibration anchors — enforceable in ritual, not in substance.

---

## 1. Agent Roster Audit

| Agent | Lines | Model | Verdict | Why |
|---|---|---|---|---|
| **coordinator** | 408 | sonnet | **KEEP — slim by 60%** | Core orchestrator, but boots 12 mandatory skills (~30K tokens) and duplicates HANDOFF_PROTOCOL.md pipelines verbatim. Route tables are good; keep those, delete duplicated pipeline diagrams and state-file boilerplate. |
| **planner** | 327 | sonnet | **KEEP — fix critical schema bug** | Embeds an ops.json schema (`version/plan_ref/id/type: create\|modify…/changes[{action,target}]`) that **fails the actual validator**, which requires `{plan, operations[{type: file_create\|file_delete\|code_edit}]}` per `generate-operations-config`. Every plan written by following planner.md verbatim is auto-rejected by the pipeline it feeds. Severity: **CRITICAL**. |
| **reviewer** | 341 | opus | **KEEP — calibrate** | Good structure (mandatory-rejection rules are real gates). But 90/100 threshold is theater without scoring anchors (see §4). Its decision taxonomy (APPROVED/CONDITIONAL/REJECTED) conflicts with `/review` command's (APPROVED/CONDITIONAL/REVISE/REJECTED). Unicode progress bars waste tokens. |
| **implementer** | 303 | sonnet | **KEEP — resolve contradiction** | Iron Law: "Edit/Write PERMANENTLY FORBIDDEN." Yet its mandatory skill `execute-operations-config` instructs "Write the modified content using Edit tool" and declares `allowed-tools: Edit, Write`. Direct self-contradiction on the execution path. Severity: **CRITICAL**. |
| **verifier** | 325 | haiku | **KEEP — model mismatch** | Haiku is asked to judge "test quality — meaningful, not trivial assertions" and detect 10 anti-pattern classes — judgment tasks Haiku is weakest at, while also loading 5 skills (~12K tokens). Either upgrade to sonnet or strip judgment criteria and keep only tool-verifiable checks (exit codes, coverage numbers). |
| **explore** | 410 | sonnet | **KEEP — cut to ~120 lines** | Duplicates Claude Code's built-in Explore agent. 410 lines teaching a model how to use Grep is padding; the search-strategy cookbook belongs in a skill (`search-first` already exists). |
| **code-reviewer** | 196 | opus | **KEEP** | Well-scoped, correctly distinguished from plan reviewer, prioritized dimensions (P0/P1). Best-written reviewer in the kit. |
| **python-reviewer** | 233 | sonnet | **MERGE → code-reviewer** | It's a checklist of Python gotchas with code examples — that's a *skill*, not an agent. Convert body to `skills/python-review-checklist/`, have code-reviewer load it when `*.py` in diff. |
| **typescript-reviewer** | 215 | sonnet | **MERGE → code-reviewer** | Same as python-reviewer. Also creates a routing ambiguity in coordinator's table (two "Code Review" rows with different targets). |
| **debugger** | 423 | sonnet | **KEEP — trim** | Longest agent in the kit. Read-only diagnosis is a sound role; the pattern library inside it should be the `systematic-debugging` skill (which already exists — duplication). |
| **gitOps** | 374 | sonnet | **KEEP** | Necessary. Note: pipeline auto-commits after verify, which contradicts golden-rule's "git commit requires approval" table (see §3). |
| **documenter** | 381 | haiku | **MERGE with doc-updater** | Two doc agents split by "create new" vs "update existing" — a distinction models routinely get wrong at routing time. One `docs` agent with `mode: create|update` removes a coordinator branch and ~300 lines. |
| **doc-updater** | 230 | haiku | **MERGE with documenter** | See above. Its "generate from code, don't invent" principle should survive the merge — it's the better core idea. |
| **tester** | 148 | sonnet | **KEEP** | Compact, well-scoped. |
| **tdd-guide** | 218 | sonnet | **DELETE (convert to skill)** | Duplicates the existing `test-driven-development` skill almost entirely. RED/GREEN/REFACTOR is methodology, not an actor. Keep the TDDGuide→Implementer handoff block by moving it into the skill. |
| **refactor-cleaner** | 209 | sonnet | **KEEP** | Tool-driven (knip/ts-prune/depcheck), batch-with-rollback discipline — good agent design. |
| **code-simplifier** | 233 | sonnet | **MERGE → refactor-cleaner** | "Reduce complexity" vs "remove dead code" overlap heavily; one "simplifier" agent with two modes suffices. |
| **build-error-resolver** | 153 | sonnet | **KEEP** | Exemplary: single job, minimum-diff constraint, explicit prohibitions. The best role-clarity in the roster. |
| **silent-failure-hunter** | 282 | sonnet | **MERGE → code-reviewer dimension or skill** | Empty-catch/swallowed-error detection is one review dimension, not a standing agent. Coordinator already runs it parallel with security-scanner — fold it in there. |
| **security-scanner** | 255 | sonnet | **KEEP** | Distinct from review-time security checklist (does SAST/CVE/secrets). Fine. |
| **performance-optimizer** | 261 | sonnet | **KEEP** | Legitimate specialist. |
| **database-architect** | 278 | sonnet | **KEEP** | Legitimate specialist. |
| **devops** | 255 | sonnet | **KEEP** | Legitimate specialist. |
| **harness-optimizer** | 203 | sonnet | **MERGE → /context-budget skill+command** | Three artifacts (this agent, `context-budget` skill, `/context-budget` command) do the same audit. Keep one. |
| **loop-operator** | 168 | sonnet | **KEEP** | Compact, clear intervention levels, real thresholds. Good design. |
| **model-router** | 148 | haiku | **CONVERT to skill/inline table** | The rubric is a static lookup table. Spawning an agent (even Haiku) to read a table costs more latency/tokens than it saves; embed the decision table in coordinator + keep `/model-route` as a thin command. Its own override rules also self-contradict: "Code review for merge approval → minimum Opus" vs task table "Code review (non-critical) → Sonnet" — and vs python/ts reviewers being sonnet. |
| **opensource-sanitizer** | 194 | sonnet | **KEEP** | Well-scoped, PASS/FAIL output. |
| **opensource-packager** | 191 | haiku | **KEEP — fix stale ref** | References an `opensource-forker` "Stage 2" agent that **does not exist** anywhere on disk. Pipeline will stall looking for it. |
| HANDOFF_PROTOCOL.md | 302 | — | KEEP — dedupe | Canonical, but coordinator.md and every pipeline agent re-paste its blocks. Reference, don't duplicate. |
| QUICK_START.md | 231 | — | KEEP | Docs, not loaded. |

**Net recommendation:** 30 → ~20 agents. Merges: python-reviewer, typescript-reviewer, silent-failure-hunter → code-reviewer; documenter+doc-updater → docs; code-simplifier → refactor-cleaner; harness-optimizer → context-budget; tdd-guide → skill; model-router → skill.

---

## 2. Command Audit

39 commands, ~5,100 lines. Three structural problems:

### 2.1 Thin agent wrappers (13 commands)
`/plan /implement /review /debug /docs /doc-updater /explore /git /verify /security /performance /test /coordinator` mostly restate the target agent's spec ("Mandatory Skills", permissions, workflow phases) *inside the command file*. This is instruction duplication: the agent definition is loaded as system prompt anyway (via `claude -p --agent`), so the command re-teaching the agent its own rules doubles token cost and creates drift (e.g., `/review`'s decision rules differ from reviewer.md's — see §3.4). **Fix:** commands should carry only: description frontmatter, argument parsing, the invocation snippet, and success/failure handling. Target ≤ 40 lines each.

### 2.2 Two incompatible invocation mechanisms — undocumented split
`/refine` asserts (correctly and emphatically) that the Agent tool's `subagent_type` does NOT resolve local agents and that `claude -p --agent <name>` via Bash is "the only verified mechanism." But `/implement`, `/coordinator`, `/docs`, and coordinator.md itself say "invoke the X agent" via Task/Agent tool semantics, and TASK_TOOL_SPECIFICATION.md documents `TaskCreate: agent: <agent-name>` spawning. If `/refine`'s claim is true, **half the orchestration docs describe a mechanism that silently routes to the wrong agent**. This must be resolved kit-wide, one way, in one place. Severity: **HIGH**.

### 2.3 Security smell
`/plan` runs `claude -p --agent planner --model sonnet --dangerously-skip-permissions`. A kit whose identity is safety hooks and golden-rule approval ships a default command that disables the permission system for a subprocess that has Bash access. At minimum scope it with `--allowedTools` or run planner with read-only tools. Severity: **HIGH**.

### Command-by-command verdicts (abridged)

| Command | Verdict | Note |
|---|---|---|
| plan, implement, review, refine | KEEP | Core pipeline; slim wrappers; fix §2.2/§2.3; `/refine` is the best-engineered command (fresh-state hard rules, iteration history). |
| gan-build, santa, council (via skill), loop-start, eval | KEEP | The advanced harnesses; well parameterized (`--mode`, `--threshold`). |
| coordinator | KEEP | But its routing table says "Build feature X → refine" while coordinator *agent* says "Feature → Planner → Reviewer → …". Two routing tables, different first hops. Unify. |
| docs + doc-updater | MERGE | Mirrors the agent merge. |
| code-review vs review vs audit vs security | OVERLAP | Four review-ish entry points. Keep `/review` (plans) and `/code-review` (code); fold `/audit`'s code-quality portion into `/code-review`; keep `/security` for the scanner. |
| deps vs audit | OVERLAP | Dependency-audit lives in both. Pick `/deps`. |
| prp-plan / prp-implement / prp-commit / prp-pr | MERGE → flags | A parallel 4-command pipeline duplicating plan/implement/git with "PRP" framing. Make it `/plan --prp` etc., or document why two pipelines exist. |
| context-budget | KEEP | Delete the harness-optimizer agent instead. |
| model-route | KEEP as thin command | Backing agent becomes a skill. |
| save-session / resume-session | KEEP | Pairs with session-start hook nicely. |
| batch, blueprint, migrate, deploy, rollback, onboard, learn, hookify, build-fix, opensource, verify, test, git, debug, explore | KEEP | Mostly reasonable; each should shed inline agent-spec duplication. |

---

## 3. Instruction Conflicts (the most damaging category)

### 3.1 CRITICAL — Two incompatible ops.json schemas on the critical path
- `planner.md` Phase 3 teaches: `{"version":"1.0","plan_ref":…,"operations":[{"id","type":"create|modify|delete|move|rename","changes":[{"action":"insert|replace|delete|append","target",…}],"rollback",…}],"validation":{…}}`
- `generate-operations-config` skill + `validate-config-json.py` (the actual 29-guard validator) require: `{"plan":"kebab-name","operations":[{"type":"file_create|file_delete|code_edit", "path", "content"/"edits":[{"find","replace"}]}]}`

A planner that follows its own system prompt produces a config the validator rejects; a reviewer that follows `validate-operations-config` must FAIL it. The pipeline only works if the planner happens to load the skill and lets it override its own embedded schema — nondeterministic. **Fix:** delete the schema from planner.md, reference the skill as the single source of truth (rewrite in §7, Offender #1).

### 3.2 CRITICAL — Implementer's Iron Law vs its own mandatory skill
implementer.md: "Direct use of Edit or Write tools is PERMANENTLY FORBIDDEN — with or without ops.json." Its mandatory skill `execute-operations-config`: "Apply the replacement… Write the modified content using Edit tool" (`allowed-tools: Read, Write, Edit, Bash…`). The hook `ops-enforcement.sh` sides with the agent (blocks Edit/Write on source). The skill was written for a manual-execution era and never updated. **Fix:** rewrite skill Step 2 to invoke `execute-json-ops.py` only (§7, Offender #2).

### 3.3 HIGH — golden-rule vs autonomy features
`golden-rule` (mandatory for ALL agents): "NEVER edit code without explicit user approval… Wait for explicit user approval." Meanwhile: planner's Forbidden Actions ("NEVER ask 'Would you like me to proceed?'"), `/loop-start` (10 autonomous iterations), `autonomous-loop` (Ralph pattern, "minimal human intervention"), and the coordinator pipeline that flows Reviewer→Implementer with no human gate. The skill's subagent carve-out ("the dispatch message IS your approval") papers over it, but the *primary agent* running `/loop-start` violates golden-rule on iteration 2 by its own text. Practical effect: models resolve this unpredictably — some stall asking for approval mid-loop, some ignore golden-rule entirely (the worse failure, because it erodes the rule where it matters). **Fix:** define approval *modes* explicitly: `interactive` (golden-rule full), `pipeline` (reviewer approval = approval), `autonomous` (loop charter = approval, loop-operator supervises); state the active mode in every handoff block.

### 3.4 MEDIUM — Reviewer decision taxonomies disagree
reviewer.md: APPROVED ≥90 / CONDITIONAL 70–89 / REJECTED <70. `/review` command message: APPROVED = ≥90 AND zero critical/major; CONDITIONAL = 70–89 OR count>0; REVISE = <70; REJECTED = ops.json problems. Since the command's message arrives as user-turn text while the agent def is the system prompt, output format is a coin-flip; `/refine`'s parser expects the command's format. **Fix:** one taxonomy, defined once in HANDOFF_PROTOCOL.md; the agent's Output Format section should *be* the parseable block.

### 3.5 MEDIUM — Question-asking policy contradicts itself
AGENT_TEMPLATE + planner: "ask ALL questions in a single batch at the very beginning." templates/modes/brainstorm.md: "ask exactly ONE question… Never front-load a list of questions." Both can be right in their own mode, but nothing tells an agent which policy wins when brainstorming feeds planning (the standard creative flow). Add a mode-precedence line to AGENT_TEMPLATE.

### 3.6 MEDIUM — using-superpowers vs direct-answer routing
`using-superpowers`: "Before generating ANY response… you MUST invoke a skill… There is no penalty for invoking a skill that turns out to be irrelevant." Downstream CLAUDE.md templates (and the derived AppiumLens CLAUDE.md) say "Pure question? Answer directly (no skills needed)." Also the claim of "no penalty" is false — every gratuitous skill load costs 1.5–4K tokens and a tool round-trip. **Fix:** §7, Offender #4.

### 3.7 MEDIUM — Nested-spawn rules vs actual designs
TASK_TOOL_SPECIFICATION: "No nested spawning — agents should not spawn other agents (only the Coordinator spawns)." But reviewer `--dual` spawns two sub-reviewers, gan-harness's Generator/Evaluator/Adjudicator are spawned from within a skill run by whoever, and planner ships with `Agent` in its tools list. Either the rule or the designs must change; today both exist.

### 3.8 LOW — golden-rule's approval table vs gitOps pipeline
Golden-rule lists `git commit` as requiring approval; the Feature pipeline auto-commits via GitOps after Verifier passes. Covered by the "pipeline mode" fix in 3.3.

### 3.9 LOW — ops-enforcement.sh documents its own bypass
The block message ends: "If this is a legitimate one-off edit, get explicit user approval and use Bash cp/sed." Printing the bypass instruction inside the denial teaches every agent that hits the wall how to tunnel under it (and `sed -i` via Bash is not blocked by any hook). Either gate Bash write-patterns too, or remove the hint and route to an approval flow.

---

## 4. Prompt Engineering Findings

### 4.1 Score thresholds are precise but uncalibrated (HIGH)
Reviewer (90/100, weighted 40/30/30 with per-criterion point tables) and Verifier (80/100, with a penalty table) present as objective. They are LLM self-reports. There are:
- **No scoring anchors / few-shot exemplars** — nothing shows what an 87 plan vs a 92 plan looks like. Point tables without anchors produce scores clustered wherever the model's prior lands (typically 82–93), making the 90 gate a soft coin-flip near threshold.
- **No output validation** — nothing machine-checks that `SCORE:` is present, integer, or that the weighted math is consistent with sub-scores (models routinely emit sub-scores that don't sum). `/refine` greps the score; a malformed reply silently breaks the loop.
- **Anti-gaming rules that invite gaming** — "NEVER give a perfect 100" plus "APPROVED requires ≥90" creates a known attractor at 90–95. Combined with `/refine` iterating *until* ≥90, the system optimizes for the score string, not plan quality (Goodhart). The Santa/GAN fresh-evaluator designs fix exactly this — but the default pipeline doesn't use them.
**Fixes:** (a) add 3 calibration anchors per dimension (snippet in §7 Offender #5); (b) validate reviewer output with a tiny script (regex + arithmetic check) before accepting the verdict; (c) make `/refine` use a fresh reviewer spawn per iteration (it does) *and* forbid the reviewer from seeing prior scores (it partially does — make it explicit in the reviewer prompt, not just refine.md).

### 4.2 Verifier judgment on the cheapest model (MEDIUM)
"Test quality: tests are meaningful, not trivial assertions" (15 pts) and 10 anti-pattern detections are assigned to Haiku. Haiku is fine for running commands and reading exit codes; it is the wrong model for "is this test meaningful?" Either: split Verifier into mechanical (Haiku: build/lint/test/coverage numbers) + judgmental (Sonnet: test quality, anti-patterns), or drop judgment criteria and let code-reviewer own them.

### 4.3 Missing retries/fallbacks at the seams (MEDIUM)
Error recovery exists at the workflow level (coordinator retries an agent once; handoff retry once) — good. But nothing handles: reviewer output unparseable, planner emitting ops.json in the wrong schema (see 3.1 — the most likely failure!), `claude -p` returning empty output, or a skill file missing (agents are told to "continue without it," which silently disables golden-rule if that file is missing — a rigid rule with a soft failure mode). Mandatory skills whose absence should abort (golden-rule for implementer) need a hard-fail path.

### 4.4 Few-shot usage is good where it exists, absent where it matters (MEDIUM)
Agent frontmatter `<example>` blocks are consistently present and well-written (routing quality benefits). But the *output*-side has no exemplars: no example REVIEW REPORT filled in with a realistic plan, no example ops.json for a real multi-file change in planner.md (only the schema skeleton), no example handoff with real content. Models imitate examples far better than they follow specs; one worked end-to-end example (plan → ops.json → review → execution log) in `_shared/` would raise pipeline reliability more than any additional rule.

### 4.5 Role clarity: mostly excellent (POSITIVE)
build-error-resolver, loop-operator, refactor-cleaner, code-reviewer, and the sanitizer/packager pair have crisp single responsibilities, explicit prohibitions, and defined outputs. The kit's *role* engineering is stronger than its *consistency* engineering.

### 4.6 Hallucination risks (MEDIUM)
- planner.md requires "Content strings MUST be exact (no pseudocode)" — but Planner has no Write tool access problem writing files, yet is told to produce *exact* final code for files it plans to create, at plan time, pre-review. For non-trivial features this forces the planner to hallucinate whole file contents into JSON strings that the validator only checks structurally. Consider `code_edit` verified `find` strings (validator checks these exist — good) but allow `file_create` content to be produced at implement time from a spec.
- doc agents on Haiku "generate from code" — right principle, but the packager writes README claims (badges, examples) it never executes; add a "verify examples compile" gate (doc-updater has one; documenter doesn't).
- Coordinator's classification table keys off keywords ("add", "fix") — cheap and transparent, but "add a comma to README" → full Feature pipeline. Add a triviality escape hatch (≤2 files, no logic → direct edit with approval).

### 4.7 Token-limit vs instruction-volume irony (MEDIUM)
OUTPUT_TEMPLATE caps completion messages at 100 tokens while the input side burns 30K on skill boot. Output discipline is the cheap 5%; input discipline is the expensive 95% and gets no enforcement. The `context-budget` skill even contains the audit script that would flag this — the kit ships the diagnostic for its own disease.

---

## 5. Context Engineering Findings

### 5.1 Always-loaded weight (measured)
- Agent frontmatter descriptions: 23.4 KB ≈ **5,850 tokens**
- Skill descriptions (73): 15.9 KB ≈ **3,975 tokens**
- Command descriptions (39): 7.2 KB ≈ **1,790 tokens**
- **Total: ~11.6K tokens** of pure metadata in every session, before CLAUDE.md, session-start hook output, or MCP schemas.

That's ~6% of a 200K context on catalog listings alone. The agent `<example>` blocks inside frontmatter descriptions are the main driver (agents average ~195 tokens of description each). Two examples are useful for routing; several agents carry two long ones where one short one suffices.

### 5.2 Mandatory skill-loading stacks (HIGH)
Coordinator: 12 skills ≈ 28–35K tokens. Reviewer: 5 ≈ 12K. Implementer: 5 ≈ 10K. Planner: 6 ≈ 13K. Verifier (Haiku!): 5 ≈ 11K. Since every agent invocation is a fresh context (per CONTEXT_CLEANUP_PROTOCOL), a single Feature pipeline (coordinator + planner + reviewer + implementer + verifier + gitOps) pays **~80–100K tokens of skill text alone**, most of it motivational prose the agent will never branch on. `using-superpowers` + `golden-rule` alone are ~290 lines of rationalization tables and violation-recovery liturgy whose operative content is two sentences.
**Fix:** For each agent, inline a 3–5 line "operating rules" digest into the agent file and drop the mandatory loads to ≤2 (the ones with procedures the agent actually executes, e.g., `generate-operations-config` for planner). Keep long-form skills for on-demand human/agent reference.

### 5.3 Duplication across layers (HIGH)
The same content exists in up to four places:
- Pipelines: coordinator.md AND HANDOFF_PROTOCOL.md (verbatim).
- Handoff blocks: HANDOFF_PROTOCOL.md AND each agent's "Handoff Formats" section AND _shared/WORKFLOW_FILE_TEMPLATES.md.
- Plan template: planner.md AND WORKFLOW_FILE_TEMPLATES.md AND writing-plans skill.
- Verification gates: VERIFICATION_PROTOCOL.md AND verification-before-completion AND verification-loop AND each agent's checklist.
- Model routing table: model-router agent AND /model-route command (full rubric pasted in both).
- Explore methodology: explore agent AND /explore command AND search-first skill.
Pick one canonical home per artifact; everything else references by path. Estimated saving: 30–40% of the agent+command corpus.

### 5.4 ASCII/Unicode decoration (LOW but everywhere)
Box-drawing loop diagrams, progress bars (`████████░░`), and `====` banners cost tokens on both generation and re-reading, and progress bars invite arithmetic errors (25 chars = 4 pts/char). Replace with plain `Score: 87/100`.

### 5.5 What's done right (POSITIVE)
- CONTEXT_CLEANUP_PROTOCOL's "fresh context per agent, files cross boundaries, reasoning doesn't" is exactly correct.
- File-based handoffs (plan.md/ops.json paths, not content, in handoff blocks) — correct.
- `context-budget` skill's token heuristics (~15 tokens/line, ~500/MCP tool) are realistic.
- Session-start hook prints a compact summary and only auto-loads context <48h old — good hygiene.

---

## 6. Orchestration Findings

### 6.1 Handoff protocol: sound design, weak transport
The block format is good (task, position, constraints, expected output, return-to). But handoffs are prose conventions with a manual "validation checklist" — nothing programmatically validates a handoff, and the two-mechanism confusion (§2.2) means the transport layer itself is uncertain. The protocol also specifies "Retry once → escalate to Coordinator" for failed handoffs *from the coordinator's own dispatches* — the escalation target is the failed sender.

### 6.2 The 90% review gate: enforceable parts vs theater parts
**Enforceable (keep):** mandatory-rejection rules (missing/invalid ops.json, no rollback, hardcoded secrets) — binary, checkable, and backed by the Python validator + pre-commit hook. This is the real gate.
**Theater (fix or drop):** the numeric threshold, per §4.1. As-is, "90" mostly measures the reviewer model's mood near the boundary. With anchors + fresh-spawn + output validation it becomes meaningful; without them, replace it honestly with APPROVE/REVISE + mandatory rejection rules.

### 6.3 ops.json pipeline: high value, currently self-sabotaged
Value: reviewable diffs before execution, 29 structural/safety guards, dry-run, backups, rollback, and *hook-level enforcement* that actually blocks the bypass path. This is the kit's crown jewel — most harnesses only exhort.
Costs: (a) the schema split (§3.1) breaks it at the source; (b) exact-content-at-plan-time forces hallucination for large `file_create` ops (§4.6); (c) overhead is disproportionate for 1-line fixes — there's no fast path (a `/quick-fix` mode generating a one-op config inline would keep enforcement while killing ceremony); (d) the documented `cp/sed` bypass (§3.9).

### 6.4 Coordinator design
Classification-table + pipeline routing is simple and legible — good. Weaknesses: two conflicting routing tables (agent vs command, §2 table); 16 pipelines where ~6 would do (several "specialist pipelines" are a single agent — that's not a pipeline, that's dispatch); revision accounting is ambiguous (Reviewer counts "Revision N of 3" and Verifier counts "Retry N of 2" while Coordinator tracks a global `revision_count` ≤3 — a bug-fix pipeline can legally consume 3 plan revisions × 2 verify retries = 5 loops against a "max 3" promise).

### 6.5 Adversarial harnesses (Santa, GAN, Council): best-in-class ideas, disconnected
Anti-anchoring via parallel isolated reviewers / fresh evaluator per iteration is the correct mitigation for LLM-judge drift, and the skill docs articulate *why* (rare and commendable). But they're opt-in side quests: the default Feature pipeline uses the anchoring-prone single reviewer, and `reviewer --dual` is the only bridge. **Recommendation:** make risk-based escalation automatic — coordinator routes auth/migration/public-API plans to Santa mode without being asked; `/refine` switches to GAN mode after 2 failed iterations.

### 6.6 Autonomy: the pieces exist, the spine doesn't
loop-operator (supervisor), autonomous-loop (lifecycle), verification-loop (gates), session-continuity (state) — all present. What's missing is the connective tissue: `/loop-start` "monitors" via a second agent but nothing actually schedules the operator between iterations (no Stop-hook wiring, no iteration counter file contract — loop-operator reads `.claude/state/loop-<task-id>.json` that nothing is specified to write). Concretely: have the loop write `state/loop.json` each iteration (schema in autonomous-loops skill) and add a Stop hook that runs a 5-line stagnation check — that converts monitoring from narrative to mechanism, and is the single biggest step toward real autonomy.

### 6.7 Hooks: the strongest layer
settings.json uses official PreToolUse/PostToolUse wiring; ops-enforcement, config-protection, block-no-verify, pre-commit secret scan, pre-push validation are real controls with profiles (`ECC_HOOK_PROFILE=minimal` escape). Issues: `.claude/**` is writable by any agent (self-modification of the hooks/skills that constrain it — prompt-injection escalation path; the `config-protection.sh` hook mitigates some of this, verify it covers `.claude/hooks/*.sh` and `settings.json` itself); `hooks/config.json` is deprecated-but-load-bearing (session-start still reads `project.*` commands from it — move that block to a non-deprecated file); every Bash PreToolUse runs 3–4 subprocesses with python3 JSON parsing (measurable latency; consolidate into one dispatcher script).

### 6.8 Registry hygiene (checked programmatically)
- 73 registry entries ↔ 73 skill dirs: **in sync**, all paths valid. Good.
- `agentMapping` references `loop-start` and `opensource` — these are *commands*, not agents.
- `agentMapping.documenter` includes skill `i18n-workflow` — **does not exist on disk**.
- Stale cross-refs elsewhere: `templates/generic/CLAUDE.md` instructs `/generate-ops`, `/validate-ops`, `/execute-ops` — **none of these commands exist** (skills exist, commands don't); opensource-packager references nonexistent `opensource-forker` agent.

### 6.9 Skill overlap clusters (merge candidates)
| Cluster | Skills | Action |
|---|---|---|
| Loops | `autonomous-loop`, `autonomous-loops` | **Merge** — same lifecycle, one has convergence criteria, the other phases. Confusing near-identical names are a routing hazard. |
| Verification | `verification-before-completion`, `verification-loop` | **Merge** — "evidence before claims" + "6-phase gate" are one skill. |
| Token/context | `token-optimization`, `token-budget-advisor`, `context-budget`, `context-keeper`, `context-priming` | **Merge to 2** (budget-audit; compression). |
| Planning | `writing-plans`, `prp-plan`, `blueprint`, `spec-driven-development` | Keep `writing-plans` + `blueprint` (multi-session); fold prp/spec framing in as sections. |
| Onboarding | `codebase-onboarding`, `codebase-mapping` | Merge. |
| Dependencies | `dependency-audit`, `supply-chain-audit` | Merge. |
| Sessions | `session-continuity` vs save/resume-session commands | Keep skill as the procedure; commands invoke it. |
73 → ~60 skills, with the survivors gaining the best content of the merged ones.

---

## 7. Concrete Rewrites — Five Worst Offenders

### Offender #1 — planner.md Phase 3 (wrong schema, breaks the whole pipeline)
Replace the entire embedded ops.json format block with:

```markdown
### Phase 3: Generate Operations Config

Load skill `generate-operations-config` — it defines the ONLY valid schema
(canonical, consumed by validate-config-json.py / execute-json-ops.py):

- Top level: {"plan": "<kebab-name>", "operations": [...]}
- Operation types: "file_create" (path + full content),
  "file_delete" (path + reason ≥10 chars),
  "code_edit" (path + edits[{find, replace}]; every `find` must exist verbatim
  in the target file — verify with Read/Grep before writing it).

Do NOT invent fields. Before handoff, self-validate:
    python3 .claude/operations/scripts/validate-config-json.py <ops.json>
Exit non-zero → fix and re-run. Never hand a failing config to the Reviewer.
```
(Also delete the duplicate "ops.json format" from WORKFLOW_FILE_TEMPLATES.md.)

### Offender #2 — execute-operations-config skill (contradicts Implementer's Iron Law)
Replace Step 2 ("Read… apply… Write the modified content using Edit tool") with:

```markdown
## Step 2: Execute — script only

The ONLY permitted execution path:
    python3 .claude/operations/scripts/execute-json-ops.py <ops.json>

You MUST NOT apply operations with Edit/Write tools, even if the script fails.
Script failure → report the exact error and STOP (escalate to coordinator).
The script provides atomicity, ordering, backups, and rollback; manual edits
provide none of these and are blocked by ops-enforcement.sh anyway.
```
And change frontmatter `allowed-tools` to `Read, Bash, Grep, Glob`.

### Offender #3 — coordinator.md Mandatory Skill Loading (28–35K token boot)
Replace the 12-skill list with:

```markdown
## Operating Rules (inline — do not load skills for these)
1. Route work to agents; never plan/review/implement yourself.
2. No code reaches Implementer without Reviewer approval (or explicit user override).
3. Before spawning, estimate cost: agent def + skills + inputs ≈ tokens; prefer
   the cheapest model that can do the job (see routing table below).
4. Parallel spawns only for read-only agents; Implementer always runs alone.
5. Never claim completion without the terminal agent's verification evidence.

## Load on demand only
- multi-agent-coordination — only when spawning 2+ agents in parallel
- session-continuity — only for multi-session workflows
```
Same treatment for planner/reviewer/implementer/verifier: ≤2 loaded skills each, procedural ones only.

### Offender #4 — using-superpowers (absolutist trigger, false economics)
Replace "The Rule" with:

```markdown
## The Rule
Invoke a skill BEFORE responding when the request involves:
- modifying code or files        → golden-rule (or active approval mode)
- planning multi-step work       → writing-plans
- claiming something is done     → verification-before-completion
- debugging                      → systematic-debugging

Answer directly WITHOUT loading skills when the request is a factual/read-only
question and no process rule applies. Loading an irrelevant skill is not free:
it costs 1–4K tokens and a tool round-trip. When genuinely unsure, prefer the
skill — but "unsure" means a process rule might apply, not reflex.
```
(This also resolves the conflict with CLAUDE.md templates' "pure question → answer directly.")

### Offender #5 — reviewer.md scoring (precision without calibration)
Add anchors + machine-readable output; delete progress bars:

```markdown
## Calibration Anchors (score against these, not intuition)
- 95+: every step has exact paths/edits; ops.json validates AND dry-runs clean;
  tests specified per step; rollback executable as written. Rare.
- 90: one or two Notes-level gaps (e.g., a minor risk unlisted); zero Critical,
  zero Warnings. This is the approval bar.
- 80: steps clear but ≥1 Warning (e.g., a find-pattern not verified unique;
  test strategy generic). CONDITIONAL.
- 65: missing sections, vague steps ("update the service"), ops mismatch. REJECT.

## Output Contract (exact — parsed by machines)
=== REVIEW ===
SCORE: <integer 0-100>
DECISION: APPROVED | CONDITIONAL | REJECTED
CRITICAL_COUNT: <int>
WARNING_COUNT: <int>
ISSUES:
- [CRITICAL|WARNING|NOTE] <issue> — Location: <file/step> — Fix: <how>
=== END REVIEW ===
Rules: APPROVED requires SCORE ≥ 90 AND CRITICAL_COUNT = 0.
Your sub-scores must arithmetically produce SCORE; show the multiplication.
Do not reference or anchor on any previous review of this plan.
```
Plus a 10-line check script the caller runs on this block (regex + `sum(weights×subs)==SCORE`) before trusting the verdict.

---

## 8. Top 20 AI Improvements (ranked by impact/effort)

1. **Fix the ops.json schema split** (planner.md → canonical skill schema; §3.1). Critical-path correctness bug. *Effort: S, Impact: Critical.*
2. **Fix execute-operations-config to script-only execution** (§3.2). Removes the contradiction at the exact moment code gets written. *S/Critical.*
3. **Standardize ONE agent-invocation mechanism** (`claude -p --agent` per /refine's verified claim) and update coordinator, TASK_TOOL_SPECIFICATION, and all wrapper commands (§2.2). *M/Critical.*
4. **Cut mandatory skill loads to ≤2 per agent, inline 5-line rule digests** (§5.2, Offender #3). Saves ~60–80K tokens per feature pipeline. *M/High.*
5. **Add calibration anchors + machine-parseable output contract + arithmetic validation to reviewer and verifier** (Offender #5). Turns the 90/80 gates from theater into signal. *M/High.*
6. **Define approval modes (interactive/pipeline/autonomous) and rewrite golden-rule around them** (§3.3). Ends the deepest philosophical contradiction. *M/High.*
7. **Remove `--dangerously-skip-permissions` from /plan**; scope subprocess tools instead (§2.3). *S/High.*
8. **De-duplicate the four-layer content** (pipelines, handoffs, templates → one canonical file each, referenced by path) (§5.3). ~30–40% corpus reduction. *M/High.*
9. **Merge autonomous-loop + autonomous-loops; verification-loop + verification-before-completion**; rename survivors distinctly (§6.9). *S/High — the near-identical names are an active mis-routing hazard.*
10. **Wire loop-operator mechanically**: loop writes `state/loop.json` per iteration; Stop hook runs stagnation check (§6.6). Biggest single autonomy win. *M/High.*
11. **Merge python/typescript reviewers + silent-failure-hunter into code-reviewer** (language checklists become skills loaded by diff extension) (§1). *M/Med.*
12. **Merge documenter + doc-updater; tdd-guide → skill; model-router → skill/inline table** (§1). Three fewer routing branches. *M/Med.*
13. **Unify the two coordinator routing tables** (agent vs /coordinator command disagree on first hop) (§6.4). *S/Med.*
14. **Auto-escalate high-risk plans to Santa/GAN modes from the coordinator** instead of opt-in flags (§6.5). *S/Med.*
15. **Add one worked end-to-end few-shot example** (real plan → valid ops.json → review block → execution log) in `_shared/EXAMPLE_PIPELINE.md`, referenced by planner/reviewer/implementer (§4.4). *M/Med.*
16. **Add a `/quick-fix` fast path**: single-op ops.json generated + validated + executed in one command, preserving hook enforcement without full pipeline ceremony (§6.3). *M/Med.*
17. **Registry + stale-ref cleanup**: drop `loop-start`/`opensource` from agentMapping, fix `i18n-workflow`, fix `opensource-forker`, fix `/generate-ops` refs in templates/generic/CLAUDE.md; add a CI check (`validate-registry.py`) so drift can't recur (§6.8). *S/Med.*
18. **Remove the cp/sed bypass hint from ops-enforcement.sh** and extend the guard to obvious Bash write patterns (`sed -i`, `tee`, `>` redirects to source paths) (§3.9). *S/Med.*
19. **Harden .claude/ self-modification**: config-protection must cover hooks/*.sh and settings.json; require pipeline-mode approval for agent/skill edits (§6.7). *M/Med.*
20. **Strip decorative output** (progress bars, box diagrams, banner rules) from all agent output formats; consolidate the 3–4 Bash PreToolUse hooks into one dispatcher script (§5.4, §6.7). *S/Low-Med.*

---

## Appendix A — Severity Index of All Findings

| # | Finding | Severity |
|---|---|---|
| A1 | planner.md ops.json schema incompatible with validator (§3.1) | Critical |
| A2 | execute-operations-config contradicts Implementer Iron Law (§3.2) | Critical |
| A3 | Dual invocation mechanisms, one asserted broken (§2.2) | High |
| A4 | golden-rule vs autonomy/pipeline flows (§3.3) | High |
| A5 | 28–35K token coordinator skill boot; ~80–100K per pipeline (§5.2) | High |
| A6 | Uncalibrated 90/80 thresholds, no output validation (§4.1) | High |
| A7 | `--dangerously-skip-permissions` in /plan (§2.3) | High |
| A8 | Four-layer content duplication (§5.3) | High |
| A9 | autonomous-loop vs autonomous-loops near-duplicate names (§6.9) | High |
| A10 | Reviewer taxonomy mismatch agent vs command (§3.4) | Medium |
| A11 | Verifier judgment tasks on Haiku (§4.2) | Medium |
| A12 | No parse/retry handling for malformed scores (§4.3) | Medium |
| A13 | using-superpowers absolutism vs direct-answer rules (§3.6) | Medium |
| A14 | Nested-spawn prohibition vs --dual/GAN designs (§3.7) | Medium |
| A15 | Batch-questions vs one-question mode conflict (§3.5) | Medium |
| A16 | loop-operator monitoring not mechanically wired (§6.6) | Medium |
| A17 | Exact file content required at plan time → hallucination pressure (§4.6) | Medium |
| A18 | model-router self-contradictory overrides; agent overkill (§1) | Medium |
| A19 | opensource-forker ghost agent; /generate-ops ghost commands; agentMapping drift (§6.8) | Medium |
| A20 | ops-enforcement bypass documented in its own denial (§3.9) | Medium |
| A21 | Two routing tables disagree on first hop (§6.4) | Medium |
| A22 | Revision-budget accounting ambiguity (3× plan + 2× verify vs "max 3") (§6.4) | Low |
| A23 | golden-rule commit-approval vs gitOps auto-commit (§3.8) | Low |
| A24 | Decorative output tokens; multi-subprocess hook latency (§5.4/§6.7) | Low |
| A25 | hooks/config.json deprecated but still load-bearing for session-start (§6.7) | Low |
