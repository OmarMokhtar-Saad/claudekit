# Changelog

All notable changes to ClaudeKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Versioning correction (2026-07):** the entry previously published as `1.3.0`
> (2026-04-11) actually shipped *after* `2.0.0` (2026-03-17). It has been renumbered to
> `2.1.0` to restore monotonic order. Two agents listed under it — `dead-code-hunter` and
> `open-source-forker` — never shipped and have been removed.

## [Unreleased]

### Changed
- **Frontier-behavior corpus upgrade.** Audited all shared agent docs, 10 core agents, 14
  core commands, and the load-bearing skills against a 10-pattern operating spec (parallel
  batching, persistence, verification, adversarial self-check, evidence integrity, calibrated
  autonomy, read-before-conclude, context economy, root-cause discipline, resumable
  decomposition) so Opus/Sonnet agents operate at frontier level. Highlights:
  - "Batch independent tool calls in ONE message" is now mandated corpus-wide
    (AGENT_TEMPLATE, using-superpowers, TASK_TOOL_SPECIFICATION, coordinator, and the
    verify/debug/explore/audit/santa/plan workflows). The "3+ problems before parallelizing"
    gate is gone (2+ suffices).
  - New mandatory **Refutation Pass** before any PASS/clean/complete claim
    (VERIFICATION_PROTOCOL + verification-before-completion): what breaks it, what wasn't
    run, which claim rests on prose.
  - Evidence integrity: numbers must come from executed output; evidence is exempt from
    silent-mode token caps; templates no longer pre-print fake evidence (refine success
    banner now actually runs the validator + dry-run; loop-start gate lines quote real
    results); token-optimization can never compress verification evidence.
  - Persistence: retries must change approach (never verbatim — including coordinator error
    recovery); executing-plans' mid-plan "Continue?" permission loop removed — an approved
    plan is the permission; checkpoint to files instead.
  - Fixed unexecutable contracts: 8 commands' broken `@agents/` references (the delegated
    agent specs never loaded); reviewer `--dual` no longer tells a spawn-less agent to spawn
    (orchestrated by the command layer); planner frontmatter reconciled with INVOCATION.md
    (Write granted, Agent removed, Bash scoped to the ops validator); INVOCATION.md tool
    table extended from 2 to 10 roles.
  - Model routing: planner sonnet→**opus** (feeds the ≥90 plan gate), verifier
    haiku→**sonnet** (scores a hard ≥80 gate); coordinator stays sonnet (routing is
    table-driven). 24 anchor tests (`tests/test_behavior_spec.py`) pin all of the above.

### Added
- **Legacy-install lifecycle support.** Installs that predate the v2.1 manifest are no
  longer locked out of the lifecycle commands:
  - `claudekit diff` falls back to comparing managed assets (`agents/ commands/ skills/
    hooks/ operations/scripts/ settings.json`) against the kit source when no manifest
    exists, classifying files as `identical` / `differs` / `custom` / `not installed`.
  - With a manifest **and** kit source available, `diff` refines `modified` into
    `locally modified` / `kit-updated` / `both changed`, and lists project-added
    `custom` files.
  - `claudekit update` now works on pre-manifest installs (confirmation-gated full-mode
    reinstall that writes a manifest for next time).
  - The installer preserves project-custom assets across reinstalls: backup files not
    tracked by the old manifest (or, for pre-manifest backups, anything under
    `agents/ commands/ skills/`) are restored into the new tree instead of being
    stranded in `.claude.bak-*`. Old kit-managed files are never resurrected when a
    manifest exists.

### Security
- **Wired the security layer (was dead code).** `CommandValidator`/`PathGuard` are now
  reachable in production via a `PreToolUse` Bash guard (`.claude/hooks/command-guard.sh`)
  and the `claudekit check-command` / `check-path` CLI. Framed honestly as a **denylist
  speed bump, not a sandbox**.
  - `CommandValidator.from_config` now reads the `security` section (was `hooks` — user
    `safeMode`/`allowedCommands` were silently ignored).
  - Inspects every segment of a chained command (`; && || |`) plus `$(...)`/backtick
    substitution payloads, not just `argv[0]`. `bash`/`sh`/`env`/`xargs` removed from the
    allowlist (payload smuggling). Added `find -delete/-exec`, `${IFS}` evasion, and Python
    `os.system`/`subprocess`/`__import__` interpreter-smuggling detection.
  - `PathGuard`: relative symlinks resolved against the link's directory; protected patterns
    (`.env`, `.git/config`, …) matched per path component (`my.envelope.txt` no longer blocked).
  - Guard rollout gated by `ECC_HOOK_PROFILE`: `strict` blocks (fail-closed), `standard`
    warns (default), `minimal` off.

### Changed
- Packaging: fixed the `pyproject.toml` build backend; moved to true `src/claudekit/`
  src-layout; single version source via `importlib.metadata`.
- Prompt layer: planner ops.json schema now references the canonical
  `generate-operations-config` schema; `execute-operations-config` drives all changes through
  `execute-json-ops.py` (no manual Edit/Write).
- Docs: rewrote `docs/HOOKS.md` around `settings.json` + `ECC_HOOK_PROFILE` (the real model);
  corrected the canonical repo slug to `OmarMokhtar-Saad/claudekit` everywhere;
  `docs/ARCHITECTURE.md`/`SECURITY.md` now describe what actually runs.

### Added
- `/adapt` command + `project-adaptation` skill: adapt ClaudeKit to any project and
  language (including stacks without a dedicated template) — detect installation
  state, learn the project, configure `config.json` commands / `CLAUDE.md` /
  `CONSTITUTION.md` / hook profile / `.agentignore`, verify with evidence
  (hook block test, ops round-trip, `ck doctor`), and record adaptation decisions.
- CLI install-lifecycle commands built on the install manifest (`.claudekit-manifest.json`):
  `claudekit diff` (show locally-modified managed files), `claudekit update` (re-install over an
  existing project, warning before overwriting local edits; installer backs up first), and
  `claudekit uninstall` (remove managed files to a recoverable backup). Plus `ck init
  --full/--minimal/--yes` and `ck doctor --strict`.
- `MAX_DELETIONS` guard (max 3 `file_delete` operations per plan) in the ops validator.
- `scripts/gen-docs.py` — generates component counts from the filesystem and, with `--check`,
  fails CI when any doc hard-codes a stale count (the new `docs-drift` gate).
- CI: whole-suite test job, macOS matrix, `install.sh → doctor` integration job, coverage
  gate, `ruff`/`mypy` lint, dangling-hook-path check, and SHA-pinned actions + Dependabot.
- Wheel now bundles the runtime asset tree (`setup.py` → `<prefix>/share/claudekit`), so a
  plain `pip install` is self-contained and `ck init` works with no source checkout.

### Fixed
- Packaging: `find_claudekit_root` resolved to `src/` (not the repo root) after the src-layout
  move, breaking `ck init`; now walks up to `.claude/agents`. `CLAUDEKIT_HOME` is honored.
- `skills-registry.json`: `documenter` referenced a non-existent skill (`i18n-workflow` →
  `i18n-patterns`), which failed the validate-registry gate.
- Installer: template rendering used `sed s|{{X}}|$VAL|` — values with `&`/`|`/`\` (e.g.
  `npm run build && npm test`) corrupted output; replaced with literal Python substitution.
  C# detection now searches subdirs for `*.csproj`/`*.sln`. `set -E` so staging cleanup fires
  on a helper failure. `settings.local.json` is preserved across a reinstall.
- Hooks: `suggest-compact` daily reset was GNU-`date -r`-only (broken on macOS) — now stores the
  date in the counter file, with stale-lock cleanup. `format-typecheck` read edited files from
  the wrong log (Bash commands, not Edit/Write targets) — now uses a dedicated `edited-files.log`.
  `auto-checkpoint` stored a positional `stash@{0}` ref that pruned the wrong stash — now uses the
  stable stash SHA. Wired the dormant `file-guard`/`prompt-injection-scanner` as advisory hooks.
  Fixed the latently-red shellcheck CI job (`.shellcheckrc`).

## [2.1.0] — 2026-04-11

### Added

#### Agents (6 new — total: 28)
- **code-reviewer** (Opus) — Reviews actual code/diffs with 5 dimensions: Correctness, Security, Performance, Reliability, Code Quality; confidence-filtered findings with file:line references
- **build-error-resolver** (Sonnet) — Minimum-diff error fixer; THE ONE RULE: fix the error only; max 7 iterations; never uses `@ts-ignore`
- **loop-operator** (Sonnet) — Autonomous loop monitor with 3 intervention levels: Warn, Pause+Report, Emergency Stop; stagnation detection
- **opensource-sanitizer** (Sonnet) — Stage 1+2 of open-source pipeline; BLOCKER/WARNING classification across 6 categories (secrets, infra, PII, tooling, legal, artifacts)
- **opensource-packager** (Haiku) — Stage 3 of open-source pipeline; generates CLAUDE.md, README, LICENSE, .env.example, CONTRIBUTING.md, .github/ templates from actual code
- **model-router** (Haiku) — 4-dimension scoring rubric (reasoning depth, output complexity, error cost, domain novelty) → haiku/sonnet/opus recommendation

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
- Documented component counts corrected to match the filesystem: 28 agents / 39 commands / 73 skills / 19 hooks, now generated and CI-enforced by `scripts/gen-docs.py`

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
