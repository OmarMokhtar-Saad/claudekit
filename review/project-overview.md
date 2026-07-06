# ClaudeKit — Project Overview

**Reviewed version:** v2.0.0 (pyproject) · CLI reports 1.1.0 · CHANGELOG latest entry 1.3.0 (2026-04-11)
**Review date:** 2026-07-05
**Repository:** `/Users/omarmokhtar/IdeaProjects/claudekit` (~267 tracked files)

---

## 1. Vision & Goals

ClaudeKit is a **multi-agent orchestration layer for Claude Code**. Its thesis: raw AI coding assistants make unstructured, unauditable changes; ClaudeKit imposes a software-engineering discipline on top of them:

1. **Plans before code** — every change starts as a `plan.md` + machine-executable `ops.json`.
2. **Quality gates** — plans must score ≥90/100 (Reviewer), implementations ≥80/100 (Verifier).
3. **Safe execution** — all file mutations flow through a validated, atomic, backed-up, rollback-capable operations engine (26 validation guards, execution locks, protected-file patterns).
4. **Language-agnostic** — auto-detects 10+ languages and configures build/test/lint/coverage commands.
5. **Zero lock-in** — everything is Markdown, JSON, Bash, and stdlib Python, copied into the target project ("copy, not link").

The differentiating design bet is **file-based agent handoffs**: agents communicate via artifacts (`plan.md`, `ops.json`, `reviewer.md`, `session-context.md`) rather than shared conversational context, claimed to cut token usage ~85%.

### Target Users

| Persona | What they get |
|---|---|
| Solo developer using Claude Code heavily | Guardrails (golden rule, review gates, rollback) that prevent AI-induced damage |
| Teams adopting AI-assisted development | Auditable pipeline: every change has a plan, a review score, a backup manifest |
| Maintainers of production codebases | Constitution-driven governance (architecture/security auto-reject rules) |
| Power users / prompt engineers | 73 reusable skills, 28 agents, 39 commands, hook toolkit, autonomous-loop patterns to remix |

---

## 2. System Architecture

ClaudeKit is **not a runtime**. It is a curated tree of prompt assets (agents/commands/skills/modes), shell hooks, and three Python scripts, plus two delivery mechanisms (install.sh and a pip CLI). Claude Code itself is the execution engine; ClaudeKit programs it through its native extension points (`.claude/agents`, `.claude/commands`, `.claude/skills`, `.claude/settings.json` hooks).

### Component Diagram

```
┌──────────────────────────────  DEVELOPER MACHINE  ──────────────────────────────┐
│                                                                                  │
│  ┌──────────────────┐        delegates to        ┌──────────────────────┐       │
│  │  pip CLI          │ ─────────────────────────▶ │  install.sh          │       │
│  │  claudekit / ck   │   (init = subprocess)      │  (~470 lines bash)   │       │
│  │  src/cli/main.py  │                            │  detect lang, copy,  │       │
│  │  doctor/validate/ │                            │  render templates    │       │
│  │  execute/rollback │                            └──────────┬───────────┘       │
│  └────────┬─────────┘                                        │ copies from       │
│           │ shells out to                                    ▼                   │
│           │                     ┌────────────────────────────────────────────┐   │
│           │                     │  CLAUDEKIT REPO (source of truth)          │   │
│           │                     │  .claude/  agents(28) commands(39)         │   │
│           │                     │            skills(73) hooks(17) ops        │   │
│           │                     │  templates/ 12 langs + commands/skills/    │   │
│           │                     │             hooks/modes/mcp                │   │
│           │                     │  src/security/ (validator, path guard)     │   │
│           │                     └────────────────┬───────────────────────────┘   │
│           │                                      │ install copies into           │
│           ▼                                      ▼                               │
│  ┌────────────────────────────  TARGET PROJECT  ────────────────────────────┐   │
│  │  .claude/                                                                 │   │
│  │   ├── agents/*.md ────────┐   loaded as subagents by Claude Code          │   │
│  │   ├── commands/*.md ──────┤   slash commands (/plan, /prp-plan, ...)      │   │
│  │   ├── skills/*/SKILL.md ──┤   on-demand knowledge, skills-registry.json   │   │
│  │   ├── modes/*.md          │   behavioral modes                            │   │
│  │   ├── hooks/*.sh ◀────────┼── wired via .claude/settings.json (PreToolUse,│   │
│  │   ├── settings.json       │   PostToolUse, SessionStart, Stop, ...)       │   │
│  │   ├── operations/scripts/ │   validate-config-json.py │ execute-json-ops  │   │
│  │   │                       │   .py │ restore-backup.py │ shared.py         │   │
│  │   ├── plans/              │   plan.md + ops.json artifacts (agent I/O)    │   │
│  │   └── local/              │   CLAUDE.project.md, CONSTITUTION.md          │   │
│  │  backups/                 │   timestamped backups + manifest.json         │   │
│  └───────────────────────────┴───────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  CLAUDE CODE (runtime)                                                    │   │
│  │  reads agents/commands/skills/settings.json · fires hooks · runs the      │   │
│  │  Planner→Reviewer→Implementer→Verifier pipeline via Task/Agent tool       │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### The core workflow pipeline

```
User → Coordinator (classify) → Planner (plan.md + ops.json)
     → Reviewer (score ≥90, else re-plan, max 3 iterations; --dual = Santa Method)
     → Implementer (validate-config-json.py → execute-json-ops.py, backup + rollback)
     → Verifier (static 30% / tests 40% / coverage 30%, ≥80, else retry max 2)
     → GitOps (branch, commit, PR)
```

Enforcement is layered: prompt-level (agent "Iron Laws"), artifact-level (ops.json schema + 26 guards), and hook-level (`ops-enforcement.sh` PreToolUse hook blocks direct Edit/Write outside the pipeline; `pre-commit.sh` validates configs and scans staged secrets).

---

## 3. Directory Map

```
claudekit/
├── install.sh                 # Primary distribution: copies .claude/ into a target project,
│                              #   detects language, renders CLAUDE.md/CONSTITUTION.md, wires hooks
├── pyproject.toml             # pip package (claudekit/ck entry points) — src.* layout
├── config.schema.json         # JSON Schema for .claude/hooks/config.json (deprecated config)
├── src/
│   ├── cli/main.py            # ~396-line argparse CLI: init, doctor, validate, execute,
│   │                          #   rollback, agents, config — mostly thin wrappers/subprocess
│   └── security/              # CommandValidator (allow/blocklist + dangerous patterns),
│                              #   PathGuard (root confinement, symlink/system-path checks)
├── .claude/                   # THE PRODUCT — canonical asset tree copied to user projects
│   ├── agents/                # 28 agent .md files + _shared/ protocols (handoff, verification,
│   │                          #   output templates) + QUICK_START/HANDOFF_PROTOCOL docs
│   ├── commands/              # 39 slash commands (/plan, /implement, /prp-*, /santa, /gan-build,
│   │                          #   /loop-start, /save-session, /hookify, /opensource, ...)
│   ├── skills/                # 73 skills (dir + SKILL.md) + skills-registry.json (id → agents)
│   ├── hooks/                 # 17 bash hooks + config.json (deprecated) + README
│   ├── settings.json          # Claude Code hook wiring (PreToolUse/PostToolUse/SessionStart/Stop…)
│   ├── operations/scripts/    # The operations engine: validate (26 guards), execute (atomic,
│   │                          #   backup, lock, rollback), restore (12 guards), shared.py, schema
│   ├── local/                 # CLAUDE.template.md, CONSTITUTION.template.md ({{PLACEHOLDER}} style)
│   └── plans/                 # Working artifacts from dogfooding (plan-*.md, *.ops.json)
├── templates/
│   ├── <lang>/ ×12            # python, typescript, java, go, kotlin, swift, rust, csharp,
│   │                          #   ruby, php, generic → config.env (BUILD/TEST/LINT/COVERAGE_CMD)
│   │                          #   + optional CLAUDE.md
│   ├── commands/ (13)         # "v2" commands merged in at install (/specify, /checkpoint, /mode…)
│   ├── skills/ (14)           # "v2" skills merged at install — 13 duplicate .claude/skills/
│   ├── hooks/ (4)             # security hooks (file-guard, prompt-injection-scanner, …)
│   ├── modes/ (7)             # behavioral modes (default, brainstorm, token-efficient, …)
│   └── mcp/                   # mcp-settings.json (Context7, Sequential Thinking, Playwright,
│                              #   Memory, Filesystem) + README
├── examples/                  # python-fastapi/, typescript-nextjs/ (CLAUDE.md + CONSTITUTION.md)
├── docs/                      # ARCHITECTURE, AGENTS, SKILLS, HOOKS, CUSTOMIZATION,
│                              #   CONSTITUTION-GUIDE, cli.md (several are stale — see review)
├── i18n/                      # 6 translated READMEs (ar, es, fr, ja, ko, zh)
├── tests/                     # 14 pytest files (structure, validator, install, cli, security,
│                              #   hooks, modes, mcp, i18n, spec-driven, checkpoint, …)
└── .github/                   # ci.yml (pytest matrix, shellcheck, structure/registry checks),
                               #   release.yml, security.yml, issue/PR templates
```

---

## 4. CLI Surface (`claudekit` / `ck`)

| Command | What it actually does |
|---|---|
| `init [target] [--mode full/minimal] [--language] [--force]` | Locates the claudekit repo (`find_claudekit_root`: package dir, `~/claudekit`, `~/.claudekit`) and **subprocesses `install.sh`** |
| `doctor` | ~25 health checks: interpreter versions, asset counts, registry cross-refs, hook executability, settings.json/config.json JSON validity |
| `validate <ops.json>` | Subprocess to `.claude/operations/scripts/validate-config-json.py` |
| `execute <ops.json> [--dry-run]` | Subprocess to `execute-json-ops.py` |
| `rollback [--backup DIR] [--list]` | Subprocess to `restore-backup.py` |
| `agents` | Parses agent frontmatter by hand, prints table |
| `config [dot.key]` | Reads `.claude/hooks/config.json` |

Stdlib-only, no third-party runtime dependency. The CLI is a convenience shim; all real logic lives in install.sh and the operations scripts.

---

## 5. Workflows

### 5.1 Standard pipeline (plan → review → implement → verify)
Described in §2. Commands `/plan`, `/review`, `/implement`, `/verify` each invoke the matching agent; `/plan` shells out to a **nested `claude -p --agent planner --dangerously-skip-permissions`** process and writes to `.claude/plans/plan-<timestamp>.md`.

### 5.2 PRP (Product Requirements Process)
Four-phase lifecycle with explicit handoff contracts: `/prp-plan` (deep recon → context-rich plan a fresh agent can execute without re-exploring) → `/prp-implement` (per-step verification, 6-gate final check) → `/prp-commit` (natural-language file targeting → conventional commit) → `/prp-pr`.

### 5.3 Adversarial review patterns
- **Santa Method** (`/santa`, `reviewer --dual`): Skeptic (Opus, threshold 95) + Pragmatist (Sonnet, threshold 90) spawned in parallel with **no shared context** (anti-anchoring). Both must approve.
- **GAN harness** (`/gan-build`): Generator → fresh-spawned Evaluator (never sees prior scores) → Adjudicator convergence loop, configurable threshold/max-iter/mode.

### 5.4 Autonomous loops
`/loop-start --agent X --max-iter N --stall-after N` runs an agent iteratively while the **loop-operator** agent supervises: stagnation detection (identical outputs, no file changes, error growth), 3 intervention levels (Warn / Pause+Report / Emergency Stop on destructive commands). Backed by `autonomous-loop` and `verification-loop` skills. (Note: a near-duplicate `autonomous-loops` skill also exists.)

### 5.5 Open-source pipeline
`/opensource`: Stage 1 Sanitizer (BLOCKER/WARNING scan across secrets/infra/PII/tooling/legal/artifacts) → hard gate → Stage 2 transform in staging dir → Stage 3 Packager (README/LICENSE/CLAUDE.md/CI generation).

### 5.6 Spec-driven development
Template commands `/specify`, `/clarify`, `/analyze`, `/checklist` plus `spec-driven-development` skill.

---

## 6. Skill System

- 73 skills, each `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`, sometimes `disable-model-invocation`, `allowed-tools`).
- **`skills-registry.json`** maps skill ids → metadata + `agentMapping` (agent → skill ids). CI and `doctor` validate referential integrity (currently clean: 73 ids, 0 orphans).
- Two skills are **mandatory for all agents**: `using-superpowers` (skill-discovery protocol — check for a skill before ANY response) and `golden-rule` (no code changes without approval).
- Agents declare "Mandatory Skill Loading" lists in prose (coordinator loads 12; planner 6; reviewer 5...). This is prompt-level, duplicated from the registry rather than derived from it.
- Categories span workflow, quality, security, DevOps, git, collaboration, meta (writing-skills, constitution), and the v1.3 additions (santa-method, gan-harness, context-keeper, prp-plan, hookify, opensource-pipeline).

## 7. Agent Roster (28)

**Core pipeline:** coordinator, planner, reviewer (Opus), implementer, verifier (Haiku), debugger (Opus, read-only), documenter, gitOps, explore, tester, security-scanner (Opus), devops, database-architect.

**Specialists (v1.3 wave):** code-reviewer (5-dimension diff review), build-error-resolver ("fix the error only", max 7 iterations), loop-operator (loop supervisor), model-router (Haiku; 4-dimension rubric → haiku/sonnet/opus routing), opensource-sanitizer/-packager, silent-failure-hunter, harness-optimizer, performance-optimizer, code-simplifier, typescript-reviewer, python-reviewer, tdd-guide, refactor-cleaner, doc-updater.

Each agent file: frontmatter (name/description/examples/model/color/tools) + system prompt with responsibilities, forbidden actions, scoring rubrics, output formats, handoff rules. `_shared/` holds seven cross-agent protocol documents (handoff, verification, output, context-cleanup, task-tool spec, validation checklist, workflow file templates).

## 8. Memory & Session Continuity

Two overlapping mechanisms:

| Mechanism | File | Flow |
|---|---|---|
| `session-continuity` skill | `.claude/session-state.json` (structured JSON: task, decisions, modified files, next steps) | save at end / restore at start |
| `context-keeper` skill + `/save-session` `/resume-session` | `.claude/session-context.md` (markdown snapshot) | `session-start.sh` hook auto-loads on next session; freshness tiers (<4h trust, 4–24h verify, >72h stale) |

Additional statefulness: `.claude/plans/` (plan artifacts), `backups/` + manifests, `hooks.log`, cost-tracker log, compact-counter, checkpoint system (`/checkpoint` + auto-checkpoint hook).

## 9. Hooks (17 scripts, wired via `.claude/settings.json`)

- **PreToolUse:** ops-enforcement (block direct edits without approved ops.json), config-protection (block edits to lint/ts/py configs), security-reminder, pre-commit (on `git commit`), commit-quality, pre-push (on `git push`), block-no-verify, suggest-compact.
- **PostToolUse:** post-tool-use tracker, command-log-audit.
- **UserPromptSubmit:** pre-plan duplicate detection.
- **SessionStart:** session-start (package-manager detection, context auto-load).
- **Stop:** final checks, cost-tracker, desktop-notify, format-typecheck.
- Every hook resolves the repo root via `git rev-parse --show-toplevel` and logs to `.claude/hooks/hooks.log`. `ECC_HOOK_PROFILE` (minimal/standard/strict) gates activation.
- `.claude/hooks/config.json` is **explicitly deprecated** (self-labeled) in favor of settings.json but still stores `project.build_cmd/test_cmd/...`, which hooks and install.sh read — so it is half-deprecated, half-load-bearing.

## 10. MCP Integration

Optional (`install.sh --with-mcp`): `templates/mcp/mcp-settings.json` configures five servers — Context7 (docs), Sequential Thinking, Playwright, Memory, Filesystem — plus an `mcp-integration` skill giving per-server usage guidance. No custom MCP server is shipped; ClaudeKit only pre-configures third-party ones.

## 11. Orchestration Model

- **Hub-and-spoke:** the Coordinator classifies (Feature/Bug/Refactor/Docs/…) and routes to fixed pipelines; revision loops are bounded (plan↔review ×3, implement↔verify ×2), with human escalation on exhaustion.
- **File-based handoffs** are the contract between agents; the HANDOFF_PROTOCOL document defines the artifact each agent must leave behind.
- **Model tiering** as cost policy: Opus for judgment (reviewer, debugger, security), Sonnet for generation, Haiku for mechanical work — with the model-router agent recommending routing per task.
- **Anti-anchoring** as a first-class principle (Santa, GAN evaluators spawned context-free).

## 12. Dependency Footprint

| Layer | Dependencies |
|---|---|
| Runtime (target project) | Python 3.8+ **stdlib only**, Bash 4+, Git; optional `jsonschema` (validator degrades gracefully) |
| pip package | Zero runtime deps declared |
| Tests | `pytest`, `jsonschema` (tests/requirements.txt) |
| CI | ubuntu-latest, Python 3.8/3.10/3.12 matrix, shellcheck |

This near-zero footprint is a genuine strength and deliberate ("zero lock-in").

## 13. Distribution Model

Two parallel paths:

1. **`install.sh` (primary):** clone repo → run script against target project. Does language detection, component copying (with template merging), `sed`-based rendering of CLAUDE.md/CONSTITUTION.md, hook config injection via inline python, `.gitignore` updates. Modes: `--full` / `--minimal`; flags `--with-mcp`, `--with-i18n`, `--force`.
2. **pip (`pip install -e .` → `claudekit`/`ck`):** intended as a wrapper; `claudekit init` still requires a repo checkout because the wheel contains **only `src/**`** — none of the `.claude/` assets are packaged. (The architecture review covers why this path is currently broken.)

The "copy, not link" philosophy means installed projects are self-contained snapshots with **no update channel** other than `--force` reinstall, which overwrites local customization.

---

## 14. Summary Assessment

ClaudeKit is an ambitious, ideas-dense framework whose real product is its **prompt-asset corpus** (28 agents, 73 skills, 39 commands, 17 hooks) and its **operations engine** (the only "hard" enforcement in the system). The Python CLI and pip packaging are thin, partially broken veneers; install.sh is the true installer. The concepts — file-based handoffs, scored review gates, anti-anchoring dual review, supervised autonomous loops, ops.json as a change-transaction format — are genuinely novel and coherent. The engineering around them (packaging, versioning, deduplication, documentation freshness, update story) lags significantly behind the conceptual layer; see `architecture-review.md`.
