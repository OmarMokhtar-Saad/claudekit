# ClaudeKit — Product & Engineering Roadmap

**Synthesized from:** 11 completed reviews in `review/` (2026-07-05)
**Current state:** v2.0.0 (pyproject) · CLI reports 1.1.0 · CHANGELOG tops out at 1.3.0 · zero git tags
**Overall Repository Score: 49/100** (weighted; see `FINAL-REPORT.md` for the full score table)

**One-line thesis:** the ideas (ops.json transaction engine, scored review gates, anti-anchoring dual review, file-based handoffs) are top-decile; the execution (packaging, hook wiring, versioning, deduplication, CI honesty) is bottom-decile. v2.1 fixes what's broken; v3.0 makes it a real product.

---

## 1. Next Release — v2.1 "Fix What's Broken" (target: 4–6 weeks)

Everything in this release is a defect in something already advertised. No new features.

### 1.1 Packaging & release (task 001)
- Fix `build-backend = "setuptools.backends._legacy:_Backend"` → `setuptools.build_meta` (pyproject.toml:3). The package has **never been installable**.
- Rename top-level `src` package → proper src-layout `src/claudekit/`; entry points `claudekit.cli.main:main`.
- Single version source of truth (pyproject → `importlib.metadata`); kill the 4-value drift (2.0.0 / 1.1.0 / 1.3.0 / 3.1.0).
- Tag `v2.1.0`, exercise `release.yml` for the first time, publish to PyPI (resolve the npm `claudekit` name-collision question first).

### 1.2 Hooks actually fire and actually block (tasks 002, 003)
- `install.sh` never copies `.claude/settings.json` → every fresh install ships 17+ inert hook scripts. Install/merge it.
- All "blocking" hooks use `exit 1` + stdout; Claude Code only blocks on `exit 2` + stderr. **No enforcement hook has ever blocked anything.** Fix all four (block-no-verify.sh:46, ops-enforcement.sh:96, config-protection.sh:91, commit-quality.sh:133).
- `post-tool-use.sh` reads env vars (`$CLAUDE_TOOL_NAME`…) Claude Code never sets — tool tracking, ops revalidation, and cost-tracker are dead. Read stdin JSON.
- Ops filename split-brain: hooks search `ops-*.json`, repo ships `*.ops.json` — pre-commit ops validation has matched zero files forever. One shared pattern in `.claude/hooks/lib.sh`.
- Blocking guards must **fail closed** on JSON-parse mismatch (today they `exit 0` on drift).
- Fix `\x27` secret-regex bug (pre-commit.sh:115-128 — single-quoted secrets never caught), bash-4 `${VAR,,}` on macOS (commit-quality.sh:60), empty-`ROOT` fallback.
- Wire the shipped-but-dormant `file-guard.sh` and `prompt-injection-scanner.sh` into settings.json.

### 1.3 Kill the permission bypass (task 004)
- Remove `--dangerously-skip-permissions` from `/plan` (plan.md:30), `/review` (review.md:55), `/refine` (refine.md:96,112,150). A safety product must not ship a default that disables the platform's primary safety mechanism.
- Standardize ONE agent-invocation mechanism kit-wide (resolve the `claude -p --agent` vs Task-tool contradiction, ai-review §2.2).

### 1.4 Installer stops destroying data (task 005)
- ERR trap `rm -rf "$DEST"` (install.sh:94-101) can delete a user's customized `.claude/` on any mid-install failure. Staging-dir install + backup + atomic swap.
- `curl | bash` guard, `--yes` for non-interactive, sed-delimiter escaping (:306-337), computed (not hardcoded, lying) summary counts (:399-413).
- Write `.claude/.claudekit-manifest.json` (version + per-file sha256) at install time — the foundation for `ck update`.

### 1.5 Version & docs reconciliation (task 006)
- Renumber CHANGELOG (the 1.3.0-after-2.0.0 entry is really 2.1.0); add `[Unreleased]`; remove phantom agents (`dead-code-hunter`, `open-source-forker`).
- One canonical repo slug (`omarmokhtar/claudekit` vs `OmarMokhtar-Saad/claudekit` — one of them 404s) across README, badges, pyproject, schema `$id`.
- Regenerate all counts (README says 13 agents/17 commands/~45 skills; reality 28/39+13/73) via `scripts/gen-docs.py` + docs-drift CI job.
- SECURITY.md supported versions `1.x` → `2.x`; disclose skip-permissions history, inert security layer, MCP `npx @latest`.
- Rewrite docs/HOOKS.md around settings.json (it documents the pre-1.1 architecture).

### 1.6 Critical prompt-layer fixes (subset of task 008/010 groundwork)
- Fix planner.md's embedded ops.json schema — it **fails the kit's own validator** (ai-review §3.1). Reference `generate-operations-config` as the single schema source.
- Fix `execute-operations-config` skill — it instructs Edit-tool usage that the implementer's Iron Law and ops-enforcement hook forbid (ai-review §3.2).
- Add `MAX_DELETIONS` guard to `validate-config-json.py` (fixes the currently-red `test_max_deletions_exceeded` and a real unbounded-delete gap).

### 1.7 CI becomes honest (task 011)
- Remove `|| true` from cli-tests and security jobs; run all 14 test files; add macOS to the matrix; add `pip install . && claudekit doctor` smoke job; add `install.sh → doctor --strict` integration job.

**v2.1 exit criteria:** `pip install claudekit && ck init && ck doctor` works from a clean machine with zero warnings; every enforcement hook demonstrably blocks in a self-test; no doc/version number disagrees with the tree; CI cannot pass with a failing test.

---

## 2. Next Major Release — v3.0 "Real Product" (target: 1–2 quarters)

### 2.1 Claude Code plugin packaging (task 007) — the strategic bet
- `.claude-plugin/plugin.json` + `marketplace.json`; the `.claude/` tree is already plugin-shaped. `/plugin install` becomes the primary channel and outsources install/update/discovery.
- Optional split: fat `claudekit` plugin + `claudekit-security`, `claudekit-prp`, `claudekit-opensource` sub-plugins.

### 2.2 Manifest-driven install + real update mechanism (tasks 005, 007)
- `claudekit.manifest.json` at repo root drives install.sh, `ck doctor`, CI counts, and generated docs (architecture-review F-17). One truth, four consumers.
- `ck update`: three-way merge (unchanged→replace, user-modified→keep + `.new`, removed→prompt) against the install manifest; `ck uninstall`; `ck diff`.
- Managed vs user split on disk: `.claude/claudekit/` (overwritable) vs `.claude/local/` (never touched).

### 2.3 Eval framework (task 010)
- `evals/` with fixture repos + golden ops.json snapshots for the 5 core agents; `ck eval` runner via `claude -p --output-format json`; nightly CI job with score trends.
- Structured `review.json`/`verify.json` verdicts with schemas; a hook mechanically gates `/implement` on `score ≥ threshold` — the 90/100 gate stops being prompt theater.
- Calibration anchors + machine-parseable output contract in reviewer/verifier prompts; benchmark and publish the "85% token reduction" claim.

### 2.4 Corpus consolidation (tasks 008, 009)
- Agents 30 → ~20 (merge python/ts-reviewer + silent-failure-hunter → code-reviewer; documenter + doc-updater; code-simplifier → refactor-cleaner; tdd-guide, model-router → skills; harness-optimizer → context-budget).
- Skills 73 → ~60 (merge autonomous-loop/-loops, verification pair, token/context trio, onboarding pair, dependency pair); delete `templates/skills/` (13 duplicates, 2 already diverged).
- Commands ≤40 lines each; registry is authoritative — agent "Mandatory Skill Loading" sections generated from `agentMapping`.
- Context budget: mandatory skill loads ≤2 per agent with inline 5-line digests (saves ~60–80K tokens per feature pipeline); stop double-loading skills-registry.json + frontmatter (~7K tokens/session); one hook dispatcher per event (~100 ms/tool-call saved).

### 2.5 Security layer becomes real (task 002 completion, 014)
- `src/claudekit/security/` imported by ops scripts and exposed as `claudekit check-command`, wired as a fail-closed PreToolUse guard — after fixing the allowlist bypasses (`bash -c`, `&&` chaining, wrong config section read).
- Sandbox profile pack: devcontainer + `interactive`/`gated`/`autonomous` settings presets; doctor warns when autonomous loops run unsandboxed.
- Supply chain: SHA-pinned actions, Dependabot, pinned MCP server versions, signed releases + SHA256SUMS + PyPI attestations.

### 2.6 DX & ecosystem
- CLI v2 tree: `ck init|update|uninstall|doctor --fix|ops validate/execute/rollback|list|config get/set|version|lint|eval` — with `--json`, `NO_COLOR`, examples in help.
- `ck lint` for consumer-authored assets; `ck new skill|agent|command` scaffolder; language detection via per-language `detect` keys.
- Consumer GitHub Action (`claudekit-action@v1`); MkDocs docs site; runnable examples with checked-in workflow transcripts; demo GIF.

---

## 3. Future Vision (12–24 months)

1. **Marketplace-first distribution.** ClaudeKit as the reference "constitutional AI-coding workflow" plugin; install.sh legacy-only. Sub-plugin ecosystem with third-party contributions gated by `ck lint` + eval CI.
2. **Provable quality gates.** Published nightly eval dashboards per agent; reviewer/verifier scores backed by calibration corpora; regression alerts on prompt changes — the first prompt-asset kit with real CI for prompts.
3. **ClaudeKit MCP server.** ops engine (validate/execute/rollback/list-backups/lint) exposed as MCP tools — stable contract, usable from Claude Desktop and other MCP clients; kills path-brittleness.
4. **Real observability.** `ck cost` from Claude Code OTEL/transcript data (not log-line guessing); `ck trace` timeline rendering of plan→review→implement→verify handoffs; static HTML status report.
5. **Cross-platform.** Python installer absorbs bash duties; Windows-native support; hooks as a single Python dispatcher (one interpreter spawn per event).
6. **Autonomy with containment.** loop-operator mechanically wired (state/loop.json + Stop-hook stagnation check); autonomous mode requires the sandbox profile; risk-based auto-escalation to Santa/GAN review for auth/migration/public-API changes.
7. **Team features.** Shared constitution templates, org-level marketplaces, review-score history as a team quality metric.

---

## 4. Breaking Changes (v3.0)

| Change | Who breaks | Mitigation |
|---|---|---|
| Package rename `src.*` → `claudekit.*` | Anyone importing `src.security`/`src.cli` (nothing found in the wild — F-7) | Deprecation shim for one release |
| Installed layout: `.claude/claudekit/` (managed) vs `.claude/local/` (user) | Every existing install; paths in settings.json/hooks change | `ck update` migration moves files, rewrites settings.json |
| ops filename standardized to `*.ops.json` | Hooks/scripts using `ops-*.json` | Migration accepts both for one release, warns |
| `templates/skills|commands|hooks|modes` deleted; `.claude/` canonical | Forks referencing `templates/` paths | Documented in migration guide; manifest lists optional bundles |
| Merged agents removed (python-reviewer, typescript-reviewer, silent-failure-hunter, tdd-guide, model-router, doc-updater, code-simplifier, harness-optimizer) | Custom commands/registry entries referencing them | Registry aliases old→new names for one release |
| Merged skills removed (autonomous-loops, verification-loop, token-budget-advisor, context-keeper duplicates, etc.) | Agent prose lists | Generated from registry, so updated automatically |
| `hooks/config.json` retired; `project.*` commands move to `.claude/claudekit.json` (schema-validated) | Hooks/install.sh reading config.json | Shim reads both for one release |
| Reviewer/Verifier output becomes machine-parseable contract (`review.json`) | Anything grepping the old markdown format (`/refine`) | `/refine` updated in the same release |
| CLI: `validate/execute/rollback` move under `ck ops` | Scripts calling old subcommands | Top-level aliases kept for one deprecation cycle |
| `--dangerously-skip-permissions` removed from shipped commands | Workflows relying on unattended sub-agent spawns | Explicit opt-in flag on `/loop-start` + sandbox profile |

---

## 5. Migration Guide (1.x / 2.0 → 3.0)

1. **Back up:** `cp -r .claude .claude.bak-$(date +%s)` (do this yourself; 2.0 installers can destroy `.claude/` on failure).
2. **Install the new CLI:** `pipx install claudekit` (works from v2.1 onward).
3. **Adopt the manifest:** `ck doctor` on a 2.0 install detects "unmanaged legacy install" and offers `ck update --adopt`, which hashes your tree against the 2.0 release manifest to classify files as pristine vs user-modified.
4. **Run the migration:** `ck update` — moves managed assets to `.claude/claudekit/`, preserves `.claude/local/` and any user-modified file (written as `.new` alongside for diffing), renames ops files to `*.ops.json`, rewrites settings.json hook paths, migrates `hooks/config.json` `project.*` keys to `.claude/claudekit.json`.
5. **Re-map removed agents/skills:** the migration prints a table (e.g. "python-reviewer → code-reviewer (auto-loads python-review-checklist skill)"). Update any custom commands referencing old names.
6. **Verify:** `ck doctor --strict` must exit 0; run one ops.json round-trip (`ck ops validate && ck ops execute --dry-run`).
7. **Optional:** switch to plugin distribution — `claude /plugin marketplace add <slug>` then `ck uninstall --keep-local` to remove the copied tree.
8. **Rollback:** `ck rollback --backup <dir>` or restore `.claude.bak-*`. Manifests make downgrade a supported operation.

---

## 6. Technical Debt Inventory

| Debt item | Source | Interest paid |
|---|---|---|
| No manifest driving install/doctor/CI/docs — 470 lines of imperative bash with hardcoded component knowledge | arch F-17 | Directly caused F-6 (settings.json forgotten), F-11 (double-copy), F-14 (stale counts) |
| 13 skills duplicated across `.claude/skills/` and `templates/skills/`, 2 diverged | arch F-11 | Which copy wins depends on copy order; divergence already happened |
| Four-layer prompt duplication (pipelines/handoffs/templates ×4 homes) | ai §5.3 | 30–40% corpus bloat; every edit is a drift opportunity |
| Registry vs prose skill lists — two parallel truths; agentMapping keys that are commands, refs to nonexistent skills | arch F-13, ai §6.8 | Routing errors, dead references |
| `src/security/` dead code + 3 parallel security implementations (bash hooks, ops scripts, Python modules) | arch F-7, sec §1 | False security guarantee in docs |
| CodeManifest fossils: `shared.py` v3.1.0, `.codemanifest.lock`, gitignored `.claude-core.lock` nothing creates | arch F-8 | Confusion, lock-file mismatch |
| config.schema.json validates a deprecated file; nothing runs validation; shipped config violates the schema | arch F-15, code §10 | Users' security settings silently ignored (command_validator.py:94 reads wrong section) |
| Copy-pasted `log()`/`get_project_config()`/JSON extractors across 10+ hooks, already diverged | code §5 | ~10 interpreter spawns per tool call; inconsistent log paths |
| Structure-theater test suite (~85% file-existence assertions), CLI at 0% in-process coverage, red test shipped | testing | False confidence; the settings.json bug was invisible to tests |
| Hardcoded doctor thresholds (≥9/≥8/≥27) and CI floors (≥13/≥17) that can never catch regressions | code §9, arch F-23 | Decorative gates |
| Dogfooding debris: committed hooks.log (159KB), cost-tracker.log, compact-counter.txt, stray `.claude/operations/scripts/.claude/hooks/` dir, 20+ plan artifacts | arch F-18, sec §5.1 | Leaks usernames/paths; signals hygiene problems |
| `.claude/plans` naming split-brain (`*.ops.json` vs `ops-*.json`) | code §4 | Ops validation silently validated nothing, forever |
| Prompt-count inflation: 73 skills/30 agents past diminishing returns, near-synonymous names | arch F-20, ai §6.9 | Mis-routing hazard, 12.4K-token routing tax |
| i18n READMEs stale at 2.0.0 structure, unlinked, no sync marker | docs §6 | Dead weight pretending to be a feature |

---

## 7. Quick Wins (≤1 day each)

1. Fix build backend (one line, pyproject.toml:3) + CI `pip install .` smoke job.
2. Copy `settings.json` in install.sh (turns on every hook for every new user).
3. `exit 1` → `exit 2` + stderr in the four blocking hooks (turns on enforcement).
4. Delete `--dangerously-skip-permissions` from plan/review/refine commands.
5. One canonical repo slug, grep-replaced everywhere + CI grep-check.
6. SECURITY.md supported-versions `1.x` → `2.x` + threat-model paragraph.
7. `git rm --cached` committed logs/counters; fix .gitignore; delete stray nested `.claude` dir.
8. Remove `|| true` from ci.yml; wire all 14 test files into the matrix job.
9. Add `MAX_DELETIONS` cap in validate-config-json.py (fixes the red test + real gap).
10. Fix `\x27` secret-grep bug in pre-commit.sh (single-quoted secrets currently invisible).
11. Honor `CLAUDEKIT_HOME` in `find_claudekit_root()` (the error message already promises it).
12. Replace planner.md's embedded (wrong) ops.json schema with a pointer to the canonical skill.
13. Rewrite `execute-operations-config` Step 2 to script-only execution; fix its `allowed-tools`.
14. Pin GitHub Actions to commit SHAs + add dependabot.yml.
15. Pin MCP server versions in templates/mcp/mcp-settings.json (drop `npx -y @latest`).
16. install.sh summary prints computed counts only (delete the hardcoded lying banner).
17. Add CODE_OF_CONDUCT, SUPPORT.md, CODEOWNERS, FUNDING.yml, YAML issue forms, labels.
18. Merge `autonomous-loop` + `autonomous-loops` skills (active mis-routing hazard).
19. Registry cleanup: drop `loop-start`/`opensource` from agentMapping, fix `i18n-workflow` and `opensource-forker` ghosts, fix `/generate-ops` refs in templates/generic/CLAUDE.md.
20. Renumber CHANGELOG, add `[Unreleased]`, remove phantom agents; tag first release.

## 8. High Impact Changes (ordered by leverage)

1. **Claude Code plugin packaging** — replaces the entire broken install/update story with the native channel (missing-features #1).
2. **`claudekit.manifest.json` as single source of truth** — makes the whole class of drift bugs (counts, double-copies, forgotten files) structurally impossible (arch F-17).
3. **Eval framework + golden tests for prompts** — the kit's only unverifiable layer is its actual product; this converts marketing claims into data (missing-features #3).
4. **`ck update` with hash manifest** — unfreezes every installed project from its install-day fork (arch F-21).
5. **Hook dispatcher consolidation + fail-closed semantics** — one python spawn per event, correct exit codes, shared lib; fixes latency, correctness, and maintainability at once (code §12.7, perf §3).
6. **Mandatory-skill diet (≤2 per agent + inline digests)** — saves ~60–80K tokens per feature pipeline; directly serves the product's own token-economy pitch (ai §5.2).
7. **Structured review.json verdicts + calibration anchors** — the 90/100 gate becomes mechanical instead of a mood (ai §4.1, missing-features #8).
8. **Wire or delete `src/security/`** — ends the false-guarantee problem either way (sec §1).
9. **Agent/skill consolidation (30→20, 73→60)** — better routing accuracy, smaller tax, less drift (ai §1, §6.9).
10. **CI that proves the product** — build wheel → install → init fixture → doctor --strict → ops round-trip (arch §4.2.6).

---

## 9. Consolidated Priority Table

Effort: **S** ≤1 day · **M** ≤1 week · **L** >1 week. Impact: business (adoption/trust) / developer (maintainer velocity, user safety).

### P0 — broken or user-harming now

| # | Finding | Files | Effort | Business impact | Developer impact |
|---|---|---|---|---|---|
| P0-1 | pip build backend invalid; package never installable | pyproject.toml:3 | S | Entire pip channel + PyPI + `ck` fictional | Blocks all packaging work |
| P0-2 | `settings.json` never installed → all hooks inert in every fresh install | install.sh (absent ref) | S | Flagship safety features don't exist for users | Silent; tests never caught it |
| P0-3 | Blocking hooks `exit 1`+stdout; Claude Code blocks only on `exit 2`+stderr — enforcement never enforced | block-no-verify.sh:46, ops-enforcement.sh:96, config-protection.sh:91, commit-quality.sh:133 | S | Core promise false | One-line fix ×4 |
| P0-4 | Top-level `src` package name / entry points | pyproject.toml:29-40 | S | Namespace collision on install | Do with P0-1 |
| P0-5 | `--dangerously-skip-permissions` in shipped commands | plan.md:30, review.md:55, refine.md:96,112,150 | S | Safety product disables platform safety; injection amplifier | Rework invocation |
| P0-6 | planner.md embeds ops.json schema its own validator rejects | .claude/agents/planner.md Phase 3 | S | Pipeline nondeterministically broken at source | Delete schema, point at skill |
| P0-7 | execute-operations-config skill contradicts Implementer Iron Law (Edit-tool instructions) | .claude/skills/execute-operations-config/SKILL.md | S | Execution-path coin flip | Rewrite Step 2 |
| P0-8 | install.sh ERR trap `rm -rf .claude` destroys user data on failure | install.sh:94-101 | S | Data loss; reputational | Staging + backup |
| P0-9 | No Claude Code plugin packaging | (missing) `.claude-plugin/` | M | Missing THE native distribution channel | Manifest work |
| P0-10 | No update mechanism; `--force` = data loss by design | install.sh:104-112; docs/CUSTOMIZATION.md:179-187 | M | Every install forks forever | Needs manifest |
| P0-11 | No eval/golden tests for the 30 agents/73 skills (the actual product) | tests/, .claude/evals/ (prompt-only) | M–L | Claims unprovable; regressions invisible | Runner + CI |

### P1 — structural defects, fix this quarter

| # | Finding | Files | Effort | Business impact | Developer impact |
|---|---|---|---|---|---|
| P1-1 | Version chaos: 2.0.0 / 1.1.0 / 1.3.0-after-2.0.0 / 3.1.0 / "2.0" | pyproject.toml:7, src/cli/main.py:13, CHANGELOG.md:8,64, shared.py:3, skills-registry.json | S | Corrosive for an "auditability" product | Single source + CI check |
| P1-2 | `src/security/` dead code; 3 parallel security impls; validator reads wrong config section; bash/sh allowlisted; chaining-blind | command_validator.py:79-94, path_guard.py:64,70 | M | Advertised control doesn't run (false guarantee) | Wire fail-closed or delete |
| P1-3 | Ops filename split-brain (`*.ops.json` vs `ops-*.json`) — validation matched zero files forever | pre-commit.sh:91, ops-enforcement.sh:56, settings.json Stop hook | S | Silent non-protection | Shared lib pattern |
| P1-4 | post-tool-use.sh fed env vars never set → tracking/cost/revalidation dead | settings.json PostToolUse; post-tool-use.sh:14; cost-tracker.sh:26 | S | Two features dead | stdin JSON |
| P1-5 | 13 skills duplicated in two trees, 2 diverged; install copies both | .claude/skills/ vs templates/skills/ | S | Nondeterministic installs | Delete templates/skills |
| P1-6 | No manifest drives install/doctor/CI/docs | install.sh, src/cli/main.py:124-138, ci.yml | M | Root cause of drift-bug class | claudekit.manifest.json |
| P1-7 | Blocking hooks fail open on JSON-shape drift | config-protection.sh, ops-enforcement.sh, security-reminder.sh | S | Advertised guard silently allows | fail-closed + self-test |
| P1-8 | file-guard.sh + prompt-injection-scanner.sh shipped but never wired | templates/hooks/, settings.json | S | Strongest defenses are inert files | Add matchers |
| P1-9 | auto-checkpoint stash handling can wipe uncommitted work; stash@{0} refs drift; prunes wrong stash | templates/hooks/auto-checkpoint.sh:144-153,101 | S | Data loss | Record SHAs, verify apply |
| P1-10 | CI `|| true` on cli/security jobs; 9 of 14 test files never run in CI; no coverage; stale count floors | .github/workflows/ci.yml | S | Quality-gates product with fake gates | Remove, expand matrix |
| P1-11 | Red test + real gap: no MAX_DELETIONS cap | validate-config-json.py; tests/test_validator.py | S | Unbounded delete in one config | Add guard |
| P1-12 | Invocation mechanism split (`claude -p --agent` vs Task tool) — half the orchestration docs may route wrong | /refine vs /implement, coordinator.md, TASK_TOOL_SPECIFICATION.md | M | Orchestration reliability | Pick one, update all |
| P1-13 | golden-rule vs autonomy contradiction (loop-start violates it on iteration 2) | golden-rule skill, planner.md, loop-start.md | M | Unpredictable agent behavior | Approval modes |
| P1-14 | 28–35K-token coordinator boot; ~80–100K skill text per pipeline | coordinator.md + 12 mandatory skills | M | Contradicts 85%-reduction pitch; cost | ≤2 loads + digests |
| P1-15 | Uncalibrated 90/80 gates; no output validation; Goodhart loop in /refine | reviewer.md, verifier.md, refine.md | M | Gate is theater near threshold | Anchors + parser |
| P1-16 | Repo slug mismatch (one URL 404s); supply-chain squat risk | README.md:6,46 vs pyproject.toml:34 | S | Credibility + security | Canonicalize |
| P1-17 | config.schema.json dead; deprecated config.json load-bearing; shipped config violates own schema | config.schema.json:138, .claude/hooks/config.json | M | Users' settings silently ignored | Split concerns |
| P1-18 | CLAUDEKIT_HOME advertised in error text, never read | src/cli/main.py:31-53 | S | Broken promise | 3 lines |
| P1-19 | doctor thresholds stale (≥9/≥8/≥27 vs 28/52/73); doesn't check settings.json wiring | src/cli/main.py:124-189 | S | Half-broken installs "pass" | Manifest-driven |
| P1-20 | Documentation counts wrong everywhere; changelog phantom agents; SECURITY.md covers only 1.x; HOOKS.md describes previous architecture | README, docs/AGENTS.md, docs/HOOKS.md, SECURITY.md, CHANGELOG.md:19-20 | M | Docs can't be trusted | gen-docs.py + drift CI |
| P1-21 | curl\|bash path guaranteed to fail, then triggers destructive trap | install.sh:9,82,107,160 | S | New-user disaster path | Guard + --yes |
| P1-22 | No asset linting or versioning (`ck lint`, frontmatter `version:`) | (missing) | S–M | Consumer-authored assets unvalidated | Extract CI check |

### P2 — real debt, fix opportunistically

| # | Finding | Files | Effort | Business impact | Developer impact |
|---|---|---|---|---|---|
| P2-1 | Four-layer prompt duplication (pipelines/handoffs/templates/routing tables) | coordinator.md, HANDOFF_PROTOCOL.md, _shared/* | M | 30–40% corpus bloat, drift | Canonical homes |
| P2-2 | Agent/skill/command inflation: 30/73/39 with heavy overlap clusters | .claude/agents/, skills/ | M | Routing accuracy degrades | Consolidate to ~20/~60/~28 |
| P2-3 | Hook latency: ~9–15 spawns, 150–300 ms per tool call | settings.json, all hooks | M | Tens of seconds/session | One dispatcher/event |
| P2-4 | Routing-surface tax ~12.4K tokens; registry JSON duplicates frontmatter (~7K) | skills-registry.json | S–M | Dominant per-session cost | Single truth, tiering |
| P2-5 | sed templating breaks on `\|`/`&` in commands → triggers destructive trap | install.sh:306-337 | S | Mid-install corruption | Escape or python |
| P2-6 | `--force` not idempotent (stale files survive); no uninstall | install.sh | S | Zombie hooks across versions | Fresh-dir install |
| P2-7 | atomic_write flips file perms to 0600; Windows lock not exclusive; TOCTOU between review and execute | execute-json-ops.py:68-101, validate-config-json.py | M | Subtle corruption vectors | copystat, O_EXCL, content hashes |
| P2-8 | commit-msg extraction regex misses common forms; console.error flagged as debug | commit-quality.sh:44,77 | S | Checks silently skip | shlex parse |
| P2-9 | config-protection blocks creating new pyproject.toml; substring pattern false-positives | config-protection.sh:19-30,77 | S | Legit work blocked | Anchor patterns |
| P2-10 | suggest-compact: stale-lock freeze; GNU-only `date -r` → daily reset never fires on macOS | suggest-compact.sh:23-34 | S | Feature silently dead on macOS | Age check + stat branch |
| P2-11 | format-typecheck scrapes bash log to find edited files — wrong data source | format-typecheck.sh:29-42 | S | Feature fires on wrong files | Track PostToolUse |
| P2-12 | MCP template `npx -y @latest` ×5 + filesystem `--allow-write .` | templates/mcp/mcp-settings.json | S | RCE-by-design on --with-mcp | Pin versions |
| P2-13 | Unpinned actions (@v4 tags), no dependabot, no lockfile/hashes, no signed releases | .github/workflows/* | S | CI supply chain exposure | SHA pins |
| P2-14 | Structure-theater tests (~85%); CLI 0% in-process coverage; no adversarial hook tests; no macOS/Windows CI | tests/, ci.yml | M | False confidence | Behavioral rewrite |
| P2-15 | model-router agent for a static table; verifier judgment on Haiku; taxonomy mismatches | model-router.md, verifier.md, /review | S–M | Cost/latency waste; coin-flip outputs | Convert/split |
| P2-16 | `templates/` conflates languages with verbatim assets; extension = edit-the-framework | templates/, install.sh detect_language() | M | Contribution friction | languages/ + scaffolder |
| P2-17 | Structured verdicts missing (review.json); memory storage contract missing; sandbox profiles missing; SAST not wired; cost tracking heuristic | multiple | M each | Product depth gaps | See missing-features |
| P2-18 | committed runtime logs w/ usernames+paths; .pyc in tree | .claude/hooks/hooks.log (159KB) etc. | S | Info leak, hygiene | rm --cached |
| P2-19 | loop-operator monitoring not mechanically wired (reads state file nothing writes) | loop-operator.md, loop-start.md | M | Autonomy is narrative | state/loop.json + Stop hook |
| P2-20 | ops-enforcement documents its own bypass; Bash writes ungated | ops-enforcement.sh:94 | S | Enforcement advisory in practice | Remove hint, gate sed -i/tee |

### P3 — polish

| # | Finding | Files | Effort | Impact |
|---|---|---|---|---|
| P3-1 | Decorative output (progress bars, box diagrams) wastes tokens, invites arithmetic errors | reviewer.md et al. | S | Token hygiene |
| P3-2 | ANSI colors unconditional; no NO_COLOR/isatty; dead imports; duplicate rollback branches | src/cli/main.py:7,10,16-28,262-265 | S | CLI polish |
| P3-3 | Guard-numbering fiction (26 vs 29; guards 15/27/28 don't exist) | validate-config-json.py:5 | S | Maintainer confusion |
| P3-4 | CodeManifest fossils, `.codemanifest.lock` vs gitignored `.claude-core.lock` | shared.py, install.sh | S | Naming hygiene |
| P3-5 | Bash/git hard dependency; hooks break silently in non-git dirs | settings.json wrappers | S | `[ -n "$ROOT" ] \|\| exit 0` |
| P3-6 | i18n stale + unlinked; examples oversold ("complete projects" = 2 config files); no logo/GIF/site | i18n/, examples/, README | S–M | Adoption optics |
| P3-7 | OTEL presets, agent trace viewer, HTML status report, Homebrew/npm shims | (missing) | M | Post-PMF niceties |
| P3-8 | security-reminder fires on docs; 3000-char truncation = silent partial scan | security-reminder.sh | S | Noise/coverage |
