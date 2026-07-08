# Commands Catalog

40 slash commands in `.claude/commands/*.md` (installed into user projects), plus 13 template commands in `templates/commands/` and 7 behavioral modes in `templates/modes/`. A command file = frontmatter (`description`, sometimes `allowed-tools`) + prompt body that runs the workflow, typically by dispatching agents per `_shared/INVOCATION.md`. Syntax is uniform: `/command [arguments]`, with universal flags (`--mode`, `--depth`, `--format`, `--persona`, `--save`, `--checkpoint`) provided by the `command-flags` skill.

## Core pipeline

| Command | Does | Dispatches |
|---------|------|-----------|
| `/plan <task>` | Create implementation plan + ops.json in `.claude/plans/` | planner |
| `/review <plan>` | Score plan vs 90/100 threshold | reviewer |
| `/refine <task>` | Auto-loop planner ↔ reviewer until ≥90 with no issues | planner+reviewer |
| `/implement <plan>` | Execute approved ops.json (dry-run → execute → verify build/lint/test) | implementer |
| `/verify` | Unified quality validation vs 80/100 | verifier |
| `/coordinator <task>` | Full multi-agent orchestration for complex tasks | coordinator |
| `/git <op>` | Branch/commit/push/PR | gitOps |
| `/rollback` | Restore last applied ops config from backup | (ops engine) |

## PRP pipeline (4 phases, v2.1)

`/prp-plan` (deep recon → context-rich plan a fresh agent can execute without re-exploration) → `/prp-implement` (execute with per-step validation loops; stops only when all checks pass) → `/prp-commit` (natural-language file targeting → conventional commit) → `/prp-pr` (auto-discover PR template, generate description from commits).

## Analysis & quality

| Command | Does |
|---------|------|
| `/explore <question>` | Codebase exploration report (explore agent) |
| `/debug <bug>` | Read-only diagnosis (debugger) |
| `/audit` | Parallel fan-out: explore + silent-failure-hunter + security-scanner |
| `/code-review [path\|PR]` | Real-code review (code-reviewer agent) — distinct from `/review` (plans) |
| `/security [path]` | Security analysis (security-scanner) |
| `/performance` | Profile & optimize (performance-optimizer) |
| `/test [target]` | Generate/run/analyze tests (tester) |
| `/deps` | Dependency audit (CVEs, updates) |
| `/build-fix` | Minimal-diff build repair, max 7 iterations (build-error-resolver) |

## Adversarial & advanced workflows

| Command | Does |
|---------|------|
| `/santa <target>` | Dual independent review — Opus Skeptic + Sonnet Pragmatist, no shared context, both must approve |
| `/gan-build <task>` | Generator → fresh Evaluator → Adjudicator loop until threshold/max-iterations |
| `/blueprint <epic>` | Multi-session construction blueprint for 3+-PR objectives (blueprint skill) |
| `/loop-start <task>` | Autonomous loop supervised by loop-operator |
| `/batch <change>` | Large-scale parallel changes via worktree agents |
| `/eval` | Define/run/report evaluations (eval-harness skill) |
| `/opensource` | 3-stage hard-gated pipeline: sanitize → fork/transform → package |
| `/model-route <task>` | Model recommendation (model-router) |
| `/context-budget` | Token-consumption audit across agents/skills/hooks/MCP |

## Docs, session, meta

| Command | Does |
|---------|------|
| `/docs <target>` | Generate new docs (documenter) |
| `/doc-updater` | Sync existing docs after code changes (doc-updater) |
| `/onboard` | Analyze unfamiliar codebase → guide + starter CLAUDE.md |
| `/adapt` | Fit ClaudeKit to the current project (any language): detect install state, configure config.json/CLAUDE.md/CONSTITUTION/hook profile, verify with evidence (`--verify-only`, `--reconfigure`). Delegates recon to codebase-onboarding; distinct from `/onboard` (learns the code) — `/adapt` configures the kit itself. |
| `/learn` | Extract session patterns → save as skills |
| `/hookify <behavior>` | Generate a prevention hook from a bad-behavior description |
| `/save-session` / `/resume-session` | Serialize/restore session state via `.claude/session-context.md` |
| `/migrate` | DB migrations, API version bumps, framework upgrades |
| `/deploy` | Release prep, containerization, deployment workflows |

## Template commands (`templates/commands/`) — installed on demand, not part of the 39

`analyze`, `checklist`, `checkpoint`, `clarify`, `flags`, `index`, `load`, `mcp`, `mode`, `ship`, `spawn`, `specify`, `translate`. These are v2.0-era optional extras (spec-driven flow: `specify`/`clarify`/`checklist`; parallel: `spawn`/`ship`; context: `load`/`index`/`checkpoint`; config: `mode`/`flags`/`mcp`; i18n: `translate`).

## Behavioral modes (`templates/modes/`)

`default`, `brainstorm`, `token-efficient`, `deep-research`, `implementation`, `review`, `orchestration` — system-prompt overlays selected via `/mode` or `--mode`.

## Conventions & error handling

- Commands stay thin: classify → dispatch → relay agent output. Roadmap target ≤40 lines each (§2.4).
- Agent spawning always uses scoped `--allowedTools` per INVOCATION.md; `permission-gate` CI job rejects any `--dangerously-skip-permissions`.
- Failure paths: `/review` rejection returns a scored report with required fixes; `/implement` aborts (with rollback) if validation fails or ops.json is missing; `/refine` and `/gan-build` have max-iteration caps to prevent infinite loops.

## Known issues

- `/coordinator`, `/implement`, `/review` descriptions are terse legacy stubs compared to newer commands — style drift, not functional.
- Overlap: `/docs` vs `/doc-updater` mirrors the documenter/doc-updater agent split (merge candidate, task 008).
- Template commands duplicate concerns now in core (e.g., `checkpoint` vs auto-checkpoint hook) — consolidation candidates (task 008).
