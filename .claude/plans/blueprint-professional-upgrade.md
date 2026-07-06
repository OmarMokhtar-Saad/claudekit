# Blueprint: ClaudeKit Professional Upgrade
**Created:** 2026-04-10  
**Scope:** EPIC — 6 PRs, ~12 implementation sessions  
**Objective:** Close all high-value gaps vs. everything-claude-code, add missing hooks, agents, and meta-systems to make ClaudeKit the most complete Claude Code harness available.

---

## Current State
- 22 agents, 67 skills, 9 hooks, 23 commands
- Missing: 13 high-value hooks, 6 core agents, 4 meta-system patterns
- Bugs: security-reminder hook blocks legitimate security discussions in docs

---

## Dependency Graph

```
PR 1: Critical Hooks (no deps)
PR 2: Core Missing Agents (no deps, parallel with PR 1)
PR 3: Santa Method + Dual Review (depends on PR 2: needs code-reviewer agent)
PR 4: Meta-Systems — Hookify + Session (depends on PR 1: hooks foundation)
PR 5: PRP Lifecycle + Build Resolvers (depends on PR 2 + PR 3)
PR 6: GAN Harness + Open-Source Pipeline (depends on PR 2 + PR 3 + PR 5)
```

**Parallel groups:**
- Group 1 (parallel): PR 1, PR 2
- Group 2 (sequential): PR 3 (after PR 2)
- Group 3 (sequential): PR 4 (after PR 1)
- Group 4 (parallel): PR 5 (after PR 2 + PR 3)
- Group 5 (sequential): PR 6 (after PR 4 + PR 5)

---

## Steps

### PR 1 — Critical Hooks (5 new hooks + 3 hook upgrades)
**No dependencies. Implement first.**

#### What to build:
1. **`config-protection.sh`** (PreToolUse / Write)  
   Blocks edits to linter/formatter/type-checker config files. Forces agent to fix code, not weaken rules.  
   Block patterns: `.eslintrc*`, `eslint.config.*`, `.prettierrc*`, `tsconfig*.json`, `biome.json`, `pyproject.toml [tool.ruff]`, `.flake8`  
   Exit 1 with: "Config protection: modifying linter/type-checker configs is blocked. Fix the code to comply instead."

2. **`suggest-compact.sh`** (PreToolUse)  
   Count tool calls in today's session log. Every 50 tool calls, print suggestion to run `/compact`.  
   Runs async — never blocks. Counter stored in `.claude/hooks/compact-counter.txt`.

3. **`session-start.sh`** (SessionStart)  
   Auto-detect package manager (check `bun.lockb`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`).  
   Print detected PM and key project commands from `config.json`.  
   Load `.claude/session-context.md` if it exists (last saved session summary).

4. **`format-typecheck.sh`** (Stop)  
   Batch formatter + type-checker across ALL JS/TS files edited in the session (NOT after every edit).  
   Read edited files from `bash-commands.log`, extract unique .ts/.tsx/.js paths.  
   Run: `npx biome format --write` (or prettier if no biome), then `npx tsc --noEmit`.  
   Only runs if any JS/TS files were edited. Async, non-blocking.

5. **`commit-quality.sh`** (PreToolUse / Bash — intercepts `git commit`)  
   Intercepts `git commit` commands. Checks:  
   - Staged files contain no `console.log`, `debugger`, `TODO: FIXME` patterns  
   - Commit message is ≥ 10 chars and not generic ("fix", "update", "wip")  
   - No staged `.env` or secret files  
   Prints warnings (not blocks) for quality issues. Blocks only for staged secrets.

#### Upgrades to existing hooks:
6. **`security-reminder.sh` fix** — current hook blocks legitimate security docs. Fix: only trigger on Write tool with destination in source dirs (not `.claude/skills/`, `docs/`, `*.md` files).

7. **`pre-commit.sh` upgrade** — add check: if staged files include any `.ts`/`.js`, run `tsc --noEmit` before committing.

8. **`settings.json` wiring** — add all new hooks to correct lifecycle events.

#### Files to create/modify:
- `.claude/hooks/config-protection.sh` (new)
- `.claude/hooks/suggest-compact.sh` (new)
- `.claude/hooks/session-start.sh` (new)
- `.claude/hooks/format-typecheck.sh` (new)
- `.claude/hooks/commit-quality.sh` (new)
- `.claude/hooks/security-reminder.sh` (fix trigger condition)
- `.claude/hooks/pre-commit.sh` (upgrade)
- `.claude/settings.json` (wire new hooks)

#### Verification:
```bash
# Config protection blocks tsconfig edit
echo '{"test":1}' | bash .claude/hooks/config-protection.sh  # should pass
printf '{"tool":"str_replace_based_edit_tool","input":{"path":"tsconfig.json"}}' | bash .claude/hooks/config-protection.sh  # should exit 1

# Session start prints package manager
bash .claude/hooks/session-start.sh

# All hooks are executable
ls -la .claude/hooks/*.sh | awk '{print $1, $9}' | grep -v "^-rwx" && echo "FAIL: non-executable hooks" || echo "PASS: all executable"
```

#### Exit criteria:
- [ ] 5 new hook files created and executable
- [ ] 2 existing hooks fixed/upgraded
- [ ] settings.json wired correctly
- [ ] config-protection blocks tsconfig/eslint edits
- [ ] security-reminder no longer blocks .claude/skills/ writes

---

### PR 2 — Core Missing Agents (6 agents)
**No dependencies. Can run parallel with PR 1.**

#### What to build:

1. **`code-reviewer.md`** — Reviews actual code diffs (not plans).  
   Model: opus. Tools: Read, Grep, Glob, Bash.  
   Input: file paths or PR diff. Output: structured review with severity-ranked findings.  
   Distinct from `reviewer.md` which only scores plans.  
   Checks: logic errors, security issues, performance anti-patterns, code style.  
   Format: file:line → severity → description → suggested fix.

2. **`build-error-resolver.md`** — Fixes build/type errors with minimal diffs.  
   Model: sonnet. Tools: Read, Grep, Glob, Bash, Edit.  
   Protocol: read error → find source → apply smallest fix → re-run build → repeat max 5x.  
   Hard rule: NEVER change architecture, NEVER refactor, ONLY fix the error.  
   Supports: TypeScript tsc errors, ESLint errors, import resolution failures.

3. **`loop-operator.md`** — Monitors and safely intervenes in autonomous agent loops.  
   Model: sonnet. Tools: Read, Bash, Agent.  
   Detects: stagnation (same output 2+ iterations), loop exceeding max_iterations, error spirals.  
   Actions: pause loop → report state → ask human for guidance.

4. **`opensource-sanitizer.md`** — Verifies a codebase is safe to open-source.  
   Model: sonnet. Tools: Read, Grep, Glob, Bash.  
   Scans: 20+ regex patterns for secrets, internal URLs, employee names, internal tooling refs.  
   Output: PASS/FAIL report with specific file:line findings.

5. **`opensource-packager.md`** — Generates complete open-source packaging.  
   Model: haiku. Tools: Read, Write, Glob.  
   Produces: CLAUDE.md (project-specific), setup.sh, README.md, LICENSE, CONTRIBUTING.md, .github/ templates.  
   Input: sanitized codebase. Output: all packaging files.

6. **`model-router.md`** — Routes tasks to optimal model based on complexity scoring.  
   Model: haiku. Tools: Read.  
   Scoring rubric: token estimate + task type + required reasoning depth → haiku/sonnet/opus recommendation.  
   Output: recommended model + justification + estimated token cost.

#### Update coordinator.md:
- Add `code-reviewer`, `build-error-resolver`, `loop-operator` to routing table
- Add `opensource-sanitizer`, `opensource-packager` to specialist pipelines
- Add new pipeline: `OpenSource Pipeline → Sanitizer → Packager`

#### Files to create/modify:
- `.claude/agents/code-reviewer.md` (new)
- `.claude/agents/build-error-resolver.md` (new)
- `.claude/agents/loop-operator.md` (new)
- `.claude/agents/opensource-sanitizer.md` (new)
- `.claude/agents/opensource-packager.md` (new)
- `.claude/agents/model-router.md` (new)
- `.claude/agents/coordinator.md` (update routing table)
- `.claude/agents/QUICK_START.md` (update agent table)
- `.claude/agents/HANDOFF_PROTOCOL.md` (add new handoff formats)

#### Verification:
```bash
# All agents have required frontmatter
for f in code-reviewer build-error-resolver loop-operator opensource-sanitizer opensource-packager model-router; do
  head -10 .claude/agents/$f.md | grep -q "^name:" && echo "OK: $f" || echo "MISSING name: $f"
done

# Coordinator references new agents
grep -c "code-reviewer\|build-error-resolver\|opensource" .claude/agents/coordinator.md
```

#### Exit criteria:
- [ ] 6 new agent files with correct frontmatter (name, description, model, tools)
- [ ] Each agent has: skill loading section, workflow phases, output format, anti-patterns
- [ ] Coordinator routing table updated
- [ ] QUICK_START and HANDOFF_PROTOCOL updated

---

### PR 3 — Santa Method + Dual Review System
**Depends on PR 2 (needs code-reviewer agent).**

#### What to build:

1. **`santa-method` skill** (`.claude/skills/santa-method/SKILL.md`)  
   Two independent model reviewers both must approve before code ships.  
   Reviewer A: opus (correctness focus)  
   Reviewer B: sonnet (pragmatism + shipping speed focus)  
   Neither reviewer sees the other's output (anti-anchoring).  
   Decision: BOTH approve → ship. ONE rejects → revision. BOTH reject → escalate.  
   Format: structured verdict with APPROVE/REJECT + specific issues.

2. **`/santa` command** (`.claude/commands/santa.md`)  
   Invokes santa-method on a target (file, PR diff, or plan).  
   Args: `[file-or-diff] [--strict|--normal]`  
   Spawns 2 parallel code-reviewer agents with no shared context.  
   Synthesizes results: shows agreement, disagreement, final verdict.

3. **`/model-route` command** (`.claude/commands/model-route.md`)  
   Invokes model-router agent. Routes any task to optimal model.  
   Args: `<task-description>`  
   Output: recommended model, cost estimate, reasoning.

4. **Update `reviewer.md`** — add dual-review option: flag `--dual` triggers santa-method for high-stakes plan reviews (score ≥ 95 required for dual approval).

#### Files to create/modify:
- `.claude/skills/santa-method/SKILL.md` (new)
- `.claude/commands/santa.md` (new)
- `.claude/commands/model-route.md` (new)
- `.claude/agents/reviewer.md` (add --dual flag documentation)
- `.claude/skills/skills-registry.json` (add santa-method)

#### Verification:
```bash
# Skill has correct frontmatter
head -5 .claude/skills/santa-method/SKILL.md

# Commands exist
ls .claude/commands/santa.md .claude/commands/model-route.md

# Registry updated
python3 -c "import json; d=json.load(open('.claude/skills/skills-registry.json')); ids=[s['id'] for s in d['skills']]; print('santa-method' in ids)"
```

#### Exit criteria:
- [ ] santa-method SKILL.md with anti-anchoring protocol
- [ ] /santa command with 2-parallel-agent invocation
- [ ] /model-route command
- [ ] skills-registry.json updated

---

### PR 4 — Meta-Systems: Hookify + Session + Compact
**Depends on PR 1 (hooks foundation).**

#### What to build:

1. **`hookify` skill** (`.claude/skills/hookify/SKILL.md`)  
   Analyze conversation transcripts → identify recurring bad behaviors → auto-generate prevention hooks.  
   5-phase: Load transcript → Identify problematic patterns → Classify by hook type → Draft hook code → Register in settings.json.  
   Pattern categories: "agent did X when it shouldn't", "agent forgot Y repeatedly", "agent used wrong tool for Z".

2. **`/hookify` command** (`.claude/commands/hookify.md`)  
   Invokes hookify skill on a conversation or description.  
   Args: `[--from-session|--from-description "<behavior to prevent>"]`  
   Output: ready-to-use hook file + settings.json diff.

3. **`context-keeper` skill** (`.claude/skills/context-keeper/SKILL.md`)  
   Structured save/resume for session context.  
   Save: serialize current task state to `.claude/session-context.md` (project, files touched, next steps, decisions made).  
   Resume: load context file, reconstruct working state, continue without re-exploration.  
   Hook integration: session-start.sh auto-loads if present.

4. **`/save-session` command** (`.claude/commands/save-session.md`)  
   Serializes current session to `.claude/session-context.md`.  
   Captures: current task, files modified, decisions made, pending steps, open questions.

5. **`/resume-session` command** (`.claude/commands/resume-session.md`)  
   Loads `.claude/session-context.md` and prints structured context for the new session.

6. **ECC Hook Profile env var system**  
   Add profile checking to all hooks: read `$ECC_HOOK_PROFILE` (minimal|standard|strict).  
   - `minimal`: only security-critical hooks run  
   - `standard`: all hooks run except format/typecheck (default)  
   - `strict`: all hooks including format-typecheck and commit-quality  
   Add 5-line profile check header to each hook file.

#### Files to create/modify:
- `.claude/skills/hookify/SKILL.md` (new)
- `.claude/skills/context-keeper/SKILL.md` (new)
- `.claude/commands/hookify.md` (new)
- `.claude/commands/save-session.md` (new)
- `.claude/commands/resume-session.md` (new)
- All hook `.sh` files (add ECC_HOOK_PROFILE check header)
- `.claude/hooks/README.md` (document profile system)

#### Verification:
```bash
# Skills exist with content
wc -l .claude/skills/hookify/SKILL.md .claude/skills/context-keeper/SKILL.md

# Commands exist
ls .claude/commands/hookify.md .claude/commands/save-session.md .claude/commands/resume-session.md

# All hooks check ECC_HOOK_PROFILE
grep -l "ECC_HOOK_PROFILE" .claude/hooks/*.sh | wc -l  # should equal total hook count
```

#### Exit criteria:
- [ ] hookify skill with 5-phase transcript-to-hook pipeline
- [ ] context-keeper skill with save/load protocol
- [ ] 3 new commands
- [ ] All hooks respect ECC_HOOK_PROFILE env var

---

### PR 5 — PRP Lifecycle + Build Resolver Commands
**Depends on PR 2 + PR 3.**

#### What to build:

1. **`prp-plan` skill** (`.claude/skills/prp-plan/SKILL.md`)  
   Product Requirements Process — plan phase.  
   Deep codebase analysis → pattern extraction → implementation blueprint with context for a fresh agent.  
   Output: `.claude/plans/prp-<feature>.md` with: existing patterns, files to touch, step sequence, test requirements.

2. **`/prp-plan` command** (`.claude/commands/prp-plan.md`)  
   Args: `<feature-description>`  
   Runs: Explore → extract patterns → generate PRP plan file.

3. **`/prp-implement` command** (`.claude/commands/prp-implement.md`)  
   Args: `<prp-plan-file>`  
   Runs: load plan → implement with validation loop → stop only when all checks pass.

4. **`/prp-commit` command** (`.claude/commands/prp-commit.md`)  
   Args: natural language file targeting ("commit the auth changes")  
   Runs: find relevant files via Grep → stage → commit with generated message.

5. **`/prp-pr` command** (`.claude/commands/prp-pr.md`)  
   Creates GitHub PR from current branch with auto-discovered PR template.  
   Runs: `gh pr create` with body from `.github/pull_request_template.md` if exists.

6. **`/build-fix` command** (`.claude/commands/build-fix.md`)  
   Invokes build-error-resolver agent on current build errors.  
   Args: `[--ts|--eslint|--go|--rust] [--max-iterations N]`  
   Protocol: run build → pass errors to resolver → apply fix → repeat until clean or max-iterations.

7. **`/code-review` command** (`.claude/commands/code-review.md`)  
   Invokes code-reviewer agent on a file, directory, or PR number.  
   Args: `[<path>|<pr-number>] [--severity critical|high|all]`

#### Files to create/modify:
- `.claude/skills/prp-plan/SKILL.md` (new)
- `.claude/commands/prp-plan.md` (new)
- `.claude/commands/prp-implement.md` (new)
- `.claude/commands/prp-commit.md` (new)
- `.claude/commands/prp-pr.md` (new)
- `.claude/commands/build-fix.md` (new)
- `.claude/commands/code-review.md` (new)
- `.claude/skills/skills-registry.json` (add prp-plan)

#### Verification:
```bash
# All commands exist
for cmd in prp-plan prp-implement prp-commit prp-pr build-fix code-review; do
  ls .claude/commands/$cmd.md && echo "OK: $cmd" || echo "MISSING: $cmd"
done

# PRP skill has required sections
grep -c "Phase\|Output\|Exit criteria" .claude/skills/prp-plan/SKILL.md
```

#### Exit criteria:
- [ ] prp-plan skill with codebase-analysis-first protocol
- [ ] 6 new commands covering full PRP + build-fix + code-review lifecycle
- [ ] skills-registry.json updated
- [ ] /build-fix wired to build-error-resolver agent

---

### PR 6 — GAN Harness + Open-Source Pipeline
**Depends on PR 2 (agents: opensource-sanitizer, opensource-packager, loop-operator), PR 3 (santa-method for quality gate), PR 5 (prp-plan for initial planning).**

#### What to build:

1. **`gan-harness` skill** (`.claude/skills/gan-harness/SKILL.md`)  
   Generate-Evaluate-Iterate loop for quality-critical features.  
   3 fixed roles: Generator (implements), Evaluator (scores against rubric, never sees generator prompt), Adjudicator (resolves disagreement).  
   Protocol: Planner writes rubric → Generator implements → Evaluator scores → if score < threshold, Generator revises → repeat max 5x.  
   Anti-anchoring: Evaluator spawned fresh per iteration with no prior context.  
   Quality threshold: configurable (default 85/100).

2. **`/gan-build` command** (`.claude/commands/gan-build.md`)  
   Invokes GAN harness on a feature.  
   Args: `<feature-description> [--threshold N] [--max-iter N]`  
   Step 1: generate rubric  
   Step 2: spawn Generator + Evaluator in generate-evaluate loop  
   Step 3: report convergence or failure

3. **`opensource-pipeline` skill** (`.claude/skills/opensource-pipeline/SKILL.md`)  
   3-agent staged pipeline for releasing internal projects as open source.  
   Stage 1 (Sanitizer): scan for secrets, internal refs, employee names → PASS/FAIL  
   Stage 2 (Forker): strip secrets, replace internal refs, generate .env.example  
   Stage 3 (Packager): generate CLAUDE.md, setup.sh, README, LICENSE, CONTRIBUTING, .github/ templates  
   Hard gate: Stage 2 only runs if Stage 1 PASSES.

4. **`/opensource` command** (`.claude/commands/opensource.md`)  
   Invokes open-source pipeline on current repo or a target directory.  
   Args: `[<target-dir>] [--sanitize-only|--package-only|--full]`  
   Default: full 3-stage pipeline.

5. **`/loop-start` command** (`.claude/commands/loop-start.md`)  
   Start an autonomous agent loop with loop-operator monitoring.  
   Args: `<task-description> [--max-iter N] [--agent <agent-name>]`

6. **Update `install.sh`** final summary to show accurate counts after all PRs.

7. **Update `CHANGELOG.md`** with v1.3.0 entry covering all additions.

#### Files to create/modify:
- `.claude/skills/gan-harness/SKILL.md` (new)
- `.claude/skills/opensource-pipeline/SKILL.md` (new)
- `.claude/commands/gan-build.md` (new)
- `.claude/commands/opensource.md` (new)
- `.claude/commands/loop-start.md` (new)
- `install.sh` (update final counts)
- `CHANGELOG.md` (v1.3.0 entry)
- `.claude/skills/skills-registry.json` (add gan-harness, opensource-pipeline)

#### Verification:
```bash
# GAN skill has 3-role structure
grep -c "Generator\|Evaluator\|Adjudicator" .claude/skills/gan-harness/SKILL.md  # expect ≥ 6

# OpenSource pipeline has 3 stages
grep -c "Stage [123]\|Sanitizer\|Forker\|Packager" .claude/skills/opensource-pipeline/SKILL.md

# Commands exist
ls .claude/commands/gan-build.md .claude/commands/opensource.md .claude/commands/loop-start.md

# CHANGELOG has v1.3.0
grep "v1.3.0\|1\.3\.0" CHANGELOG.md
```

#### Exit criteria:
- [ ] GAN harness skill with anti-anchoring evaluator protocol
- [ ] Open-source pipeline skill with hard gate between stages
- [ ] 3 new commands
- [ ] CHANGELOG.md updated with v1.3.0
- [ ] install.sh final counts accurate

---

## Summary

| PR | Effort | Value | Deps |
|----|--------|-------|------|
| PR 1: Critical Hooks | Medium | Very High — immediate quality enforcement | None |
| PR 2: Core Agents | Medium | Very High — fills biggest capability gaps | None |
| PR 3: Santa Method | Low | High — adversarial review for correctness | PR 2 |
| PR 4: Meta-Systems | Medium | High — hookify + session persistence | PR 1 |
| PR 5: PRP + Commands | Low | High — structured feature lifecycle | PR 2 + 3 |
| PR 6: GAN + OpenSource | Medium | Medium-High — advanced harness patterns | PR 2 + 3 + 5 |

**Total additions after all PRs:**
- Agents: 22 → 28 (+6)
- Hooks: 9 → 14 (+5 new, 2 upgraded)
- Commands: 23 → 37 (+14)
- Skills: 67 → 74 (+7)

**To start:** Implement PR 1 and PR 2 in parallel (no deps).  
`/implement .claude/plans/blueprint-professional-upgrade.md --step 1`  
`/implement .claude/plans/blueprint-professional-upgrade.md --step 2`
