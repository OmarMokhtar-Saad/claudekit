# ClaudeKit — Missing Features & Gap Analysis

**Reviewer role:** Product Manager + OSS reviewer
**Date:** 2026-07-05
**Scope caveat:** ClaudeKit is a *Claude Code asset kit* (markdown agents/commands/skills + shell hooks + Python ops scripts + installer). It is **not** an SDK or runtime framework. Gaps are judged against that identity: comparisons to LangChain/CrewAI/Vercel AI SDK are only relevant where the capability translates to "kit + installer + CI" form. "Multi-provider support" (OpenAI, Gemini, etc.) is explicitly **out of scope** and is not counted against the project.

**What the kit already does well (baseline):** 30 agents, 39 commands, 73 skills, 21 hooks, an ops.json validate/execute/rollback engine with a JSON Schema, 11 language templates, a Python CLI (`claudekit`/`ck` with init/doctor/validate/execute/rollback/agents/config), i18n READMEs in 6 languages, and 14 test files. This is far more substantive than typical "awesome-prompts" repos. The gaps below are what separates it from a distributable product.

---

## 1. Gap Matrix

| # | Capability | Status | In scope? | Priority | Effort | Evidence / Notes |
|---|-----------|--------|-----------|----------|--------|------------------|
| 1 | **Claude Code plugin/marketplace packaging** (`.claude-plugin/plugin.json`, `marketplace.json`) | **Missing** | **Core** — this is *the* native distribution channel for exactly this artifact type | **P0** | S–M | Zero hits for `plugin.json`/`marketplace` anywhere in repo. Claude Code's plugin system (GA since Oct 2025) packages agents+commands+skills+hooks+MCP config — ClaudeKit's exact contents — with `/plugin install`, central updates, and marketplace discovery. Shipping only `install.sh` copy-in is the single biggest strategic omission. |
| 2 | **Update/sync mechanism for installed kits** | **Missing** | Core | **P0** | M | `install.sh` supports `--force` (blind overwrite) only. No `ck update`, no installed-version manifest, no diff of local customizations vs upstream, no changelog-aware upgrade. Users who customized `.claude/` are stranded on their install version. Plugin packaging (#1) solves most of this for free. |
| 3 | **Evaluation framework for prompts/skills (regression + golden tests)** | **Partial** | Core | **P0–P1** | M | `/eval` command + `eval-harness` skill define a nice YAML eval format in `.claude/evals/`, but it is *prompt-side only*: no runner script, no golden transcripts, no CI job that evals the kit's own 30 agents/73 skills. `tests/` validates structure, not behavior. The kit that enforces "80% coverage" on user code has 0% behavioral coverage of its own prompts. |
| 4 | **Prompt/asset linting** | **Partial** | Core | P1 | S | `tests/test_structure.py`, `test_new_skills.py` check frontmatter in CI, but there's no `ck lint` for end users authoring their own agents/skills, no style rules (description trigger quality, token-size budget per asset, dead skill references). CI's registry check (`ci.yml` validate-registry job) is a good seed. |
| 5 | **Prompt versioning** | **Missing** | Core | P1 | S | No `version:` in agent/skill frontmatter; kit-level CHANGELOG only. Installed copies can't be traced to a kit version; no per-asset diffability. Also: repo itself has version chaos — README badge v2.0.0, pyproject 2.0.0, CHANGELOG tops out at 1.3.0, zero git tags. |
| 6 | **CI/CD & GitHub Actions for consumers** | **Missing** | Core | P1 | M | `.github/workflows/` covers the kit repo only. No reusable `claudekit-action` (validate ops.json, lint `.claude/`, run evals in consumer CI), no workflow templates shipped by the installer. The `ci-cd-pipeline` skill is prose guidance, not tooling. |
| 7 | **Versioned asset migrations** | **Missing** | Core | P2 | M | Commit `6d444e2` ("close ops.json schema mismatch") shows the schema already drifted once with no migration path. No `migrations/` registry, no `ck migrate-config`. |
| 8 | **Cost/token analytics** | **Partial** | In scope (bounded) | P2 | M | `cost-tracker.sh` Stop hook exists but *estimates* cost from hook-log line counts — not real token data. `usage-monitoring`, `token-budget-advisor`, `context-budget` skills are advisory prose. Claude Code natively exports OTEL metrics incl. real token counts; the kit should consume those instead of guessing. |
| 9 | **Telemetry / OpenTelemetry** | **Missing** | Marginal | P3 | S | Nothing wires `CLAUDE_CODE_ENABLE_TELEMETRY`/OTEL env config. Right-sized scope: ship an opt-in `templates/telemetry/` with OTEL env presets + a local collector docker-compose, not a telemetry stack. Kit-usage phone-home telemetry: out of scope, keep it that way. |
| 10 | **MCP server integrations** | **Partial** | In scope | P2 | S–M | `templates/mcp/mcp-settings.json` curates 5 servers (context7, sequential-thinking, playwright, memory, filesystem) + `mcp-integration` skill + `test_mcp.py`. Gaps: installer doesn't merge into project `.mcp.json`; no ClaudeKit MCP server exposing the ops engine (validate/execute/rollback) as tools; the `filesystem` server template with `--allow-write .` is a questionable default. |
| 11 | **Structured outputs** | **Partial** | In scope | P2 | S | ops.json + `operations-schema.json` is genuinely good structured output for edits. But Reviewer (90/100) and Verifier (80/100) verdicts are free-form markdown — thresholds are "enforced" by prompt discipline. No `review.json` schema, so hooks/CI can't gate on scores mechanically. |
| 12 | **Memory system** | **Partial** | In scope (bounded) | P2 | S | `save-session`/`resume-session` commands, `context-keeper` + `session-continuity` skills (with freshness validation — nice), memory MCP server in template. Missing: a durable project-memory convention (decisions/, learned-patterns/) that agents write to automatically; `continuous-learning` skill exists but has no storage contract. |
| 13 | **Sandbox execution** | **Missing** | Partially in scope | P2 | S | No devcontainer, no permission-profile presets, no `--dangerously-skip-permissions`-in-container recipe. Claude Code itself provides sandboxing/permissions; the in-scope move is shipping a `templates/sandbox/` devcontainer + hardened `settings.json` permission profiles (deny-by-default for autonomous-loop mode, which the kit ships and therefore should sandbox). |
| 14 | **Security scanner** | **Partial (strong)** | In scope | P2 | M | Best-covered area: security-scanner agent (Opus), `/security`, `/audit`, secret scan in pre-commit, `prompt-injection-defense` + `supply-chain-audit` + `insecure-defaults` skills, `src/security/{path_guard,command_validator}.py`, `security.yml` workflow. Gap: scanning is prompt-driven; no wired deterministic SAST (semgrep/gitleaks configs) that hooks call, so results aren't reproducible. |
| 15 | **Context optimizer** | **Partial** | In scope | P2 | M | `token-optimization`, `context-budget`, `suggest-compact.sh` hook, `token-efficient` mode, "85% token reduction" claim via file-based handoffs. All advisory/unmeasured. No tool that measures actual context composition or prunes CLAUDE.md/skills by measured relevance. The "85%" claim is unbenchmarked (see eval gap #3). |
| 16 | **Agent debugger** | **Missing** | Marginal | P3 | M | No transcript replay/inspection of agent handoffs. Hooks write `hooks.log` but nothing consumes it. Right-sized: `ck trace` that renders the plan→review→implement→verify handoff files + hook log as a timeline. A full step debugger is out of scope (that's the harness's job). |
| 17 | **Visual dashboard / workflow visualizer** | **Missing** | Marginal | P3 | M–L | Nothing beyond ASCII diagrams. Right-sized: `ck status --html` static report (installed assets, last runs, backup inventory, eval pass rate). A live web dashboard is out of scope for a zero-dependency kit and would betray the "no runtime deps" principle. |
| 18 | **RAG / knowledge base** | **Missing** | Mostly out of scope | P3 | L | Claude Code has native code search; MCP covers external retrieval; `codebase-mapping` skill approximates a codebase KB. Building embeddings/vector infra contradicts the stdlib-only stance. Verdict: document MCP-based RAG patterns, don't build. |
| 19 | Multi-provider (OpenAI/Gemini) support | Missing | **Out of scope** | — | — | ClaudeKit is definitionally Claude Code-native. Noted only to state it deliberately. |
| 20 | Windows-native support | Missing | In scope (adjacent) | P2 | M | Bash-only installer + 21 bash hooks; README says "use WSL". Claude Code runs natively on Windows since late 2025; the Python CLI could absorb installer/hook duties cross-platform. Not on the required list but a real adoption gap. |

**Scorecard:** of the 18 in/partially-in-scope capabilities: 4 solid-partial, 6 weak-partial, 8 missing. The pattern: *prompt-side coverage is excellent; deterministic tooling behind the prompts is thin.* Almost every gap is "the skill describes the practice, but no script/CI/schema enforces it."

---

## 2. Design Sketches — Top 10

### 1. Plugin & marketplace packaging (P0, S–M)
- Add `.claude-plugin/plugin.json` (name, version, description, author) at repo root; the existing `.claude/agents|commands|skills|hooks` layout is already plugin-shaped — mostly a manifest + metadata task.
- Add `.claude-plugin/marketplace.json` so the repo doubles as a single-plugin marketplace: `claude /plugin marketplace add omarmokhtar/claudekit`.
- Split decision: ship one fat `claudekit` plugin + optional `claudekit-security`, `claudekit-prp`, `claudekit-opensource` sub-plugins (the command namespaces already cluster this way).
- Keep `install.sh` for the copy-in/self-contained audience; document plugin install as the primary path. Hooks map to plugin `hooks/hooks.json`; `templates/mcp/mcp-settings.json` maps to plugin `.mcp.json`.
- CI: add a job validating `plugin.json` against the official schema and that every command/agent referenced exists.

### 2. `ck update` with install manifest (P0, M)
- On `ck init`/`install.sh`, write `.claude/.claudekit-manifest.json`: kit version, ISO timestamp, and `{path: sha256}` for every installed file.
- `ck update`: fetch target version → three-way classify each file: *unchanged-by-user* (hash matches manifest → replace), *user-modified* (write `.new` alongside + report), *new/removed upstream* (add/prompt).
- `ck diff` shows drift before updating. Store per-version manifests so downgrades work via existing backup machinery (`restore-backup.py` already exists — reuse it).

### 3. Eval runner + golden asset tests (P0–P1, M)
- `evals/` in the kit repo with regression suites for the 5 core agents: fixture repo (reuse `examples/python-fastapi`) + task prompt + assertions ("planner output contains valid ops.json that passes validate-config-json.py", "reviewer rejects a plan violating Constitution Art. I").
- Runner: `ck eval` shelling to `claude -p --output-format json` headless mode; assertions in Python (stdlib + the YAML format already specified in the eval-harness skill).
- CI: nightly workflow (paid API key via secret; skip on forks) + score-trend JSON committed to `evals/results/`. Golden tests = snapshot the ops.json produced for fixed tasks; fail on structural drift.
- This also finally substantiates the README's "85% token reduction" and "90/100 gate" claims with data.

### 4. `ck lint` for assets (P1, S)
- Deterministic checks over `.claude/`: frontmatter schema per asset type (name/description/model/allowed-tools), description-trigger quality ("Use when..." pattern), token budget per file (warn >2K tokens for a skill), registry consistency (extract the CI inline-Python registry check into `src/cli/lint.py`), broken cross-references between agents/skills/commands, duplicate trigger phrases across skills (73 skills — collision risk is real).
- Ships to consumers: they author their own skills; lint them in their pre-commit hook (the kit already installs pre-commit hooks — wire it in).

### 5. Asset version frontmatter + migration registry (P1, S)
- Add `version:` + `kit: 2.1.0` to every asset's frontmatter (scripted one-time pass; enforced by `ck lint`).
- `migrations/` dir with `<from>-<to>.py` steps for breaking changes (ops.json schema, hook config keys). `ck update` runs applicable migrations in order; each is idempotent and logs to the manifest.

### 6. Reusable GitHub Action for consumers (P1, M)
- `omarmokhtar/claudekit-action@v1` (composite action, no Docker): inputs `mode: lint|validate-ops|eval`, runs `ck lint`, validates any `operations/**/ops.json` in the PR, optionally runs smoke evals.
- `ck init` drops `.github/workflows/claudekit.yml` into consumer repos (behind a `--ci` flag). This turns the kit's "quality gates" from prompt promises into CI reality for users.

### 7. Real cost/token analytics (P2, M)
- Replace heuristic `cost-tracker.sh` estimation: parse Claude Code's session transcript JSONL (`~/.claude/projects/...`) or consume its OTEL metrics for actual input/output/cache token counts per session.
- `ck cost [--since 7d] [--by agent|command]`: attribute usage to workflow phases via the hook log timeline (Stop/SubagentStop events already fire). Output table + optional JSON. Keep it local-only, stdlib-only.

### 8. Structured JSON verdicts for Reviewer/Verifier (P2, S)
- Define `review-schema.json` / `verify-schema.json` (score, per-dimension breakdown, violations[] with article + severity, verdict enum). Reviewer/verifier agents required to emit `reviewer.json` next to `reviewer.md`.
- `validate-config-json.py`-style validator + a hook that blocks `/implement` unless `reviewer.json` exists, validates, and `score >= threshold` — the 90/100 gate becomes mechanically enforced instead of prompt-enforced. Threshold read from CONSTITUTION front-matter, not hardcoded.

### 9. Sandbox profile pack (P2, S)
- `templates/sandbox/`: `.devcontainer/devcontainer.json` (network-restricted, Claude Code preinstalled) + three `settings.json` permission presets: `interactive` (current behavior), `gated` (deny Bash write outside repo), `autonomous` (for `/loop-start`: deny-all-except-allowlist — the kit ships autonomous loops today with no containment story, which is the riskiest current gap).
- `ck init --sandbox <profile>` merges the preset; `doctor` warns when autonomous-loop skills are installed without a restrictive profile.

### 10. ClaudeKit MCP server (P2, M)
- Small stdio MCP server (stdlib + the existing ops scripts) exposing: `validate_ops_config`, `execute_ops_config(dry_run)`, `rollback`, `list_backups`, `lint_assets`.
- Why: subagents currently shell out to python scripts by path — brittle across CWD drift (two commits already fixed CWD bugs). MCP tools give a stable contract, and make the ops engine usable from Claude Desktop/other MCP clients, widening the audience beyond Claude Code.

---

## 3. Priority Summary

| Priority | Items |
|----------|-------|
| **P0** | Plugin/marketplace packaging · Update/sync mechanism · Eval runner + golden tests |
| **P1** | Asset linting (`ck lint`) · Prompt/asset versioning · Consumer GitHub Action |
| **P2** | Migrations · Cost analytics · MCP hardening + ClaudeKit MCP server · Structured verdicts · Memory contract · Sandbox profiles · SAST wiring · Context measurement · Windows |
| **P3** | OTEL presets · Agent trace viewer · Static HTML status report · RAG (document-only) |

**Strategic read:** ClaudeKit's differentiation is the *ops.json safety engine + constitutional gates* — no comparable Claude Code kit (superpowers-style skill repos, awesome-claude-code lists) has deterministic, rollback-capable execution. The P0 items all serve one thesis: package that differentiator in the native channel (plugins), keep installs current (update), and prove it works (evals). Everything else is compounding.
