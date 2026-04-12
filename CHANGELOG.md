# Changelog

All notable changes to ClaudeKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — 2026-04-11

### Added

#### Agents (8 new — total: 30)
- **code-reviewer** (Opus) — Reviews actual code/diffs with 5 dimensions: Correctness, Security, Performance, Reliability, Code Quality; confidence-filtered findings with file:line references
- **build-error-resolver** (Sonnet) — Minimum-diff error fixer; THE ONE RULE: fix the error only; max 7 iterations; never uses `@ts-ignore`
- **loop-operator** (Sonnet) — Autonomous loop monitor with 3 intervention levels: Warn, Pause+Report, Emergency Stop; stagnation detection
- **opensource-sanitizer** (Sonnet) — Stage 1+2 of open-source pipeline; BLOCKER/WARNING classification across 6 categories (secrets, infra, PII, tooling, legal, artifacts)
- **opensource-packager** (Haiku) — Stage 3 of open-source pipeline; generates CLAUDE.md, README, LICENSE, .env.example, CONTRIBUTING.md, .github/ templates from actual code
- **model-router** (Haiku) — 4-dimension scoring rubric (reasoning depth, output complexity, error cost, domain novelty) → haiku/sonnet/opus recommendation
- **dead-code-hunter** — Detects unreachable code, unused exports, dead feature flags, zombie dependencies
- **open-source-forker** — Transforms private code to public-safe version in staging directory

#### Skills (6 new — total: 73)
- **santa-method** — Adversarial dual-review: Skeptic (Opus) + Pragmatist (Sonnet) spawned simultaneously with no shared context (anti-anchoring)
- **hookify** — Analyzes behavior patterns → classifies tool call → generates prevention hook → settings.json diff → verification tests
- **context-keeper** — Structured save/resume: required fields, freshness validation (<4h full trust, 4-24h verify, >72h warn stale)
- **prp-plan** — Product Requirements Process plan phase: "A fresh agent with this plan should implement correctly without re-exploring"
- **gan-harness** — GAN-style generate-evaluate-iterate loop; anti-anchoring Evaluator spawned fresh each iteration; configurable threshold and max iterations
- **opensource-pipeline** — 3-stage hard-gated pipeline; Stage 2 only runs if Stage 1 PASSES; never modifies original source

#### Commands (13 new — total: 37)
- **/santa** — Dual adversarial review with anti-anchoring; `--strict` raises threshold to 95/100
- **/hookify** — Generate hook from behavior description or session transcript
- **/save-session** — Serialize session state to `.claude/session-context.md`
- **/resume-session** — Load and validate saved session context with freshness check
- **/model-route** — Route a task description to optimal model with scoring breakdown
- **/prp-plan** — Phase 1: deep recon → context-rich plan document (the "contract")
- **/prp-implement** — Phase 2: execute plan with per-step verification and 6-gate final check
- **/prp-commit** — Phase 3: natural-language file targeting → smart conventional commit
- **/prp-pr** — Phase 4: auto-discover PR template, generate description from commits and plan
- **/build-fix** — Fix build/type errors with minimum diff; max 7 iterations; never suppresses
- **/code-review** — Review files, directories, or GitHub PRs with ranked findings report
- **/gan-build** — GAN harness command: `--mode fast|standard|quality|strict`, `--threshold N`, `--max-iter N`
- **/opensource** — Full 3-stage open-source pipeline: `--sanitize-only`, `--package-only`, `--license MIT|Apache|GPL`
- **/loop-start** — Start monitored autonomous loop: `--agent <name>`, `--max-iter N`, `--stall-after N`

#### Hooks (6 new — total: 15)
- **config-protection.sh** (PreToolUse) — Blocks edits to ESLint, tsconfig, Prettier, Biome, pyproject and 15 other config files; respects `ECC_HOOK_PROFILE`
- **commit-quality.sh** (PreToolUse/Bash) — Warns on generic messages, debug artifacts; BLOCKS on staged secrets (`.env`, `.pem`, `.key`)
- **security-reminder.sh** (PreToolUse/Write) — Non-blocking warnings for `shell=True`, SQL concat, `innerHTML`, TLS disabled, weak crypto, permissive CORS
- **suggest-compact.sh** (PostToolUse, async) — Suggests `/compact` every 50 tool calls; daily counter reset
- **session-start.sh** (SessionStart) — Detects package manager, loads config commands, prints startup summary, auto-loads recent session context
- **format-typecheck.sh** (Stop, async) — Runs Biome/Prettier + `tsc --noEmit` on all JS/TS files edited in session; strict mode only

#### System
- **ECC_HOOK_PROFILE** env var — `minimal|standard|strict` controls hook activation without file edits
- **Anti-anchoring protocol** — Both Santa reviewers and GAN Evaluators spawned with no shared context or prior conversation history
- **PRP lifecycle** — 4-phase workflow (plan→implement→commit→PR) where each phase is a dedicated command with explicit handoff contract

### Fixed
- `pre-commit.sh` path: `find operations/ -name "ops.json"` → `find .claude/plans/ -name "ops-*.json"` (planner writes to `.claude/plans/`)
- `skills-registry.json` `agentMapping` structure: confirmed as dict (agent_name → list of skill IDs), not a list
- Install counts updated from 22 agents/27 commands/55 skills/9 hooks to accurate 30/37/74/15

## [2.0.0] — 2026-03-17

### Added
- **7 Behavioral Modes**: default, brainstorm, token-efficient, deep-research, implementation, review, orchestration
- **5 MCP Server Configurations**: Context7, Sequential Thinking, Playwright, Memory, Filesystem
- **Universal Command Flags**: --mode, --depth, --format, --persona, --save, --checkpoint
- **Spec-Driven Development Workflow**: /specify, /clarify, /analyze, /checklist commands
- **Security Hooks**: file-guard (195+ patterns), check-comment-replacement, prompt-injection-scanner
- **Checkpoint System**: /checkpoint create/restore/list with auto-checkpoint hook
- **Parallel Execution**: /spawn, /batch, /ship commands for parallel agent work
- **International Support**: READMEs in Arabic, Chinese, Spanish, French, Japanese, Korean
- **10 Advanced Skills**: token-optimization, codebase-mapping, session-continuity, autonomous-loop, context-priming, hook-profiling, safe-command-approval, usage-monitoring, prompt-injection-defense, incident-response
- **/translate command**: Multi-language documentation translation
- **/mode command**: Switch behavioral modes per session
- **/index command**: Generate project structure index
- **/load command**: Context loader for project components
- **/flags command**: Universal flags reference
- **.agentignore template**: Gitignore-style file for AI agent access control
- **i18n-workflow skill**: Internationalization patterns and RTL support
- **mcp-integration skill**: MCP server usage guidelines
- **spec-driven-development skill**: Specification-first workflow patterns
- **command-flags skill**: Universal flag parsing system

### Changed
- Bumped version to 2.0.0
- Expanded skill count from 45 to 55+
- Expanded command count from 17 to 27+
- Added modes directory to template structure
- Added mcp directory to template structure
- Added i18n directory with 6 language translations

## [1.1.0] - 2026-03-16

### Added
- 4 new agents: tester, security-scanner, devops, database-architect (total: 13)
- 9 new commands: /explore, /security, /deps, /rollback, /test, /deploy, /performance, /migrate, /batch (total: 17)
- 18 new skills including Trail of Bits-inspired security skills, enterprise patterns, and i18n/a11y (total: 45)
- 4 new language templates: Rust, C#, Ruby, PHP (total: 11)
- Official Claude Code hooks via .claude/settings.json (7 event types)
- Professional README with shields.io badges and comprehensive documentation

### Fixed
- 43+ bugs fixed across security, cross-references, and compliance
- All agent frontmatter updated with tools and example blocks per Claude Code official docs
- All skill frontmatter updated with disable-model-invocation, user-invocable, allowed-tools
- Hooks format migrated from custom config.json to official Claude Code settings.json
- Kotlin language detection now works correctly (moved before Java check)
- Template {{PROJECT_NAME}} substitution now works for all language templates
- Command injection vulnerabilities fixed in all hook scripts
- install.sh config.env sourcing security hardened

## [1.0.0] - 2026-03-16

### Added
- 9 specialized agents: coordinator, planner, reviewer, implementer, verifier, debugger, documenter, gitOps, explore
- 8 slash commands: /plan, /review, /implement, /verify, /debug, /docs, /git, /coordinator
- 27 generic skills covering planning, review, implementation, testing, debugging, git, and more
- 5 workflow hooks: pre-commit, post-implement, pre-plan, pre-push, post-tool-use
- Operations system with validate, execute, and restore scripts (CodeManifest v3.1.0)
- One-command installer (`install.sh`) with language detection
- 7 language templates: Python, TypeScript, Java, Go, Kotlin, Swift, Generic
- 2 complete examples: Python/FastAPI and TypeScript/Next.js
- CLAUDE.template.md and CONSTITUTION.template.md for project customization
- Shared agent templates and protocols
- Skills registry for agent-skill mapping
- Comprehensive documentation (Architecture, Customization, Agents, Skills, Hooks, Constitution Guide)
- CI/CD pipeline with GitHub Actions
- Issue and PR templates
