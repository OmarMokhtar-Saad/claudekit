# Task 008 — Consolidate Agents, Skills & Commands; One Source of Truth

## Problem
The prompt corpus has inflated past the point of diminishing returns and split into parallel truths:
- **13 skills duplicated** across `.claude/skills/` and `templates/skills/` (`autonomous-loop, codebase-mapping, command-flags, context-priming, hook-profiling, incident-response, mcp-integration, prompt-injection-defense, safe-command-approval, session-continuity, spec-driven-development, token-optimization, usage-monitoring`); `incident-response` and `spec-driven-development` have **already diverged**; install.sh copies both trees into the same destination so which version wins depends on copy order (arch F-11).
- **Near-duplicate skills sabotage routing:** `autonomous-loop` vs `autonomous-loops` (F-12); `verification-before-completion` vs `verification-loop`; token/context quintet (`token-optimization`, `token-budget-advisor`, `context-budget`, `context-keeper`, `context-priming`); `codebase-onboarding` vs `codebase-mapping`; `dependency-audit` vs `supply-chain-audit` (ai §6.9).
- **Agent overlap:** python-reviewer + typescript-reviewer are language checklists (skills in agent costume); silent-failure-hunter is one review dimension; documenter/doc-updater split confuses routing; code-simplifier ≈ refactor-cleaner; tdd-guide duplicates the `test-driven-development` skill; model-router is a static lookup table with self-contradicting overrides; harness-optimizer triplicates context-budget (ai §1).
- **Registry vs prose drift:** each agent hand-writes a "Mandatory Skill Loading" list duplicating `skills-registry.json`'s `agentMapping`; nothing syncs them. agentMapping contains `loop-start` and `opensource` (commands, not agents) and references skill `i18n-workflow` which doesn't exist; opensource-packager references a ghost `opensource-forker` agent; `templates/generic/CLAUDE.md` instructs `/generate-ops`, `/validate-ops`, `/execute-ops` — commands that don't exist (ai §6.8, arch F-13).
- **Commands restate agent specs** (13 thin wrappers duplicating "Mandatory Skills"/workflow phases), and reviewer decision taxonomy differs between reviewer.md and /review (ai §2.1, §3.4).

## Root Cause
Additive growth with no curation budget and no generated artifacts: every new capability landed as a new file, "templates/" was used as a second home for optionality, and prose lists were hand-copied from the registry once and never again.

## Files
- Delete: `templates/skills/` (after merging the 2 diverged files' best content into `.claude/skills/`), `templates/commands/`, `templates/hooks/`, `templates/modes/` → merge into `.claude/` with manifest `optional` flags (arch F-16; coordinate with task 005's manifest)
- Merge/convert agents: `.claude/agents/python-reviewer.md`, `typescript-reviewer.md`, `silent-failure-hunter.md` → `code-reviewer.md` + per-language checklist skills; `documenter.md` + `doc-updater.md` → one `docs` agent; `code-simplifier.md` → `refactor-cleaner.md`; `tdd-guide.md` → skill; `model-router.md` → inline table in `coordinator.md` + thin `/model-route`; `harness-optimizer.md` → `context-budget` skill/command
- Merge skills: `autonomous-loops` → `autonomous-loop`; `verification-loop` → `verification-before-completion`; token/context quintet → 2; onboarding pair → 1; dependency pair → 1
- `skills-registry.json` (authoritative; clean agentMapping), new `scripts/gen-agent-skills.py`
- `.claude/agents/coordinator.md` (routing table dedupe vs `/coordinator` command — two tables disagree on first hop, ai §6.4)
- `templates/generic/CLAUDE.md` (ghost command refs), `.claude/agents/opensource-packager.md` (ghost agent ref)
- All 13 thin-wrapper commands (≤40-line rule)

## Priority
**P1** (the near-identical loop-skill names are an active mis-routing hazard — ai #9 "High"); bulk consolidation P2.

## Estimated Time
1.5–2 weeks. Do it as pure relocation + deduplication — the prose corpus is the product's moat (arch §4.4).

## Risk
Medium. Merges can lose content nuances — for each merge, diff both sources and keep the union of operative rules (e.g., doc-updater's "generate from code, don't invent" survives into the merged docs agent). Users with custom commands referencing removed agents break — registry aliases old→new for one release (roadmap §4).

## Step-by-step Implementation
1. **Diverged-file reconciliation first:** three-way review of `incident-response` and `spec-driven-development` across both trees; merged versions land in `.claude/skills/`; then delete `templates/skills/` and update install.sh (or the manifest).
2. Merge the skill clusters (73 → ~60): survivor keeps the best content of each merged skill as sections; registry updated; deleted names added to a `renamed` alias map the registry serves for one release.
3. Agent merges (30 → ~20) per the ai-review verdict table: convert python/ts checklists to `skills/python-review-checklist/`, `typescript-review-checklist/` loaded by code-reviewer when the diff contains matching extensions; fold silent-failure detection in as a code-reviewer dimension; single `docs` agent with `mode: create|update`.
4. **Registry becomes law:** `scripts/gen-agent-skills.py` regenerates each agent's "Mandatory Skill Loading" section from `agentMapping`; CI diff-checks. Validate every agentMapping key is an existing `agents/*.md`; drop `loop-start`/`opensource`; fix/remove `i18n-workflow`.
5. Ghost-ref sweep: `opensource-forker` (point Stage 2 at the real pipeline or create the agent), `/generate-ops|/validate-ops|/execute-ops` in templates/generic/CLAUDE.md → real command names.
6. Command diet: each wrapper command reduced to frontmatter + arg parsing + invocation + artifact contract (≤40 lines); one reviewer decision taxonomy defined in HANDOFF_PROTOCOL.md, referenced everywhere (fixes ai §3.4); unify the two coordinator routing tables.
7. Add lint rules (feeds `ck lint`, missing-features #4): command line-budget, skills with `allowed-tools: Agent` flagged (they're agents in skill costume — F-19), duplicate trigger phrases across skill descriptions.
8. Update `install.sh`/manifest, `doctor` expected counts, gen-docs tables (task 006) — all derive from the manifest so this is automatic by now.

## Acceptance Criteria
- `templates/skills|commands|hooks|modes` no longer exist; single canonical asset tree.
- Agent count ~20, skill count ~60, zero near-duplicate names (`autonomous-loop*` count == 1).
- `git grep -l "Mandatory Skill Loading" .claude/agents` sections are byte-identical to generator output (CI-enforced).
- Registry referential integrity: every agentMapping key is an agent file; every skill id has a SKILL.md; zero ghost references repo-wide (CI job).
- No command file exceeds the line budget; reviewer taxonomy appears in exactly one file.

## Testing Strategy
- Extend `tests/test_structure.py` with the referential-integrity + line-budget + duplicate-name checks (in pytest, not just CI shell one-liners — testing-review missing test 7).
- Golden frontmatter-schema test across all agents/commands/skills (missing test 6).
- Eval framework (task 010) regression run before/after each merge batch — proves routing/behavior didn't degrade, which keyword tests can't.

## Rollback Plan
Do merges in small batches (one cluster per PR) with the eval suite as the gate. Every merge is a git revert away; the registry alias map means consumers see a rename, not a deletion, for one release — reverting restores the old name with zero consumer impact.
