# Plan: Worktree-Per-Agent Parallelism + Multi-Account / Cross-Tool Collaboration (rev 2)

**Date**: 2026-08-09 | **Target**: claudekit master (maintainer mode, direct edits) → AppiumLens pilot guide
**Requested by**: Omar (explicit /goal approval: "plan → review → implement all, then apply to AppiumLens")
**Author**: main agent | **Rev 2**: addresses all 15 reviewer findings from review of rev 1 (score 71.3, REVISE)
**Research base**: `.claude/reports/research/git-worktrees-parallel-ai-agents-2025-2026.md`, `dual-claude-accounts-multi-subscription.md`, `multi-tool-ai-agent-collaboration.md`

## Goals

1. **Phase 1 — Worktree automation**: `worktree-manager.py` ops script (stdlib-only) + `/worktree` command + upgraded `using-git-worktrees` skill, with a git-ignored JSON registry at `.claude/state/worktrees.json`.
2. **Phase 2 — Orchestration integration**: coordinator dispatches parallel implementers into isolated worktrees with a **specified** isolation mechanism (below); gitOps owns the merge protocol (agents never merge); `/batch` is reconciled to delegate to the same primitive.
3. **Phase 3 — Cross-tool bridge**: new `cross-tool-collaboration` skill (AGENTS.md standard, dual Claude accounts via `CLAUDE_CONFIG_DIR`, Cursor headless, `MULTI_AGENT_PLAN.md` contract, trust boundary) + user-facing `docs/PARALLEL_AGENTS.md`.
4. **AppiumLens applicability**: tailored pilot plan written to `AppiumLens/.claude/plans/plan-parallel-agents-pilot.md` (additive only).

## Verified facts (recon — corrected per review)

- `using-git-worktrees` has `disable-model-invocation: true`, contradicting FOUR loaders: `.claude/commands/git.md:27`, `.claude/agents/gitOps.md:35`, `.claude/commands/batch.md:26`, `.codex/agents/gitOps.toml:30`. This plan fixes THIS skill only; the corpus-wide contradiction (~30 skills agents are told to load vs task 009 prescribing the flag for niche skills) is logged to `.ai/BACKLOG.md` as a separate consolidation item — NOT fixed here.
- `execute-json-ops.py:215-224` guards target paths against `os.getcwd()`; `ops-enforcement.sh` derives `ABS_ROOT` from `git rev-parse --show-toplevel`. **In a linked worktree, `--show-toplevel` returns the worktree root**, so both guards work correctly *iff the process cwd is the worktree root*. That is the isolation mechanism this plan adopts (Workstream 2).
- `/batch` (`.claude/commands/batch.md`) already does worktree parallelism: 5–30 units via `EnterWorktree`, agents create branches and "individual PRs or merge to a staging branch". It conflicts with this plan's ≤5 cap and agents-never-merge rule → batch.md is IN SCOPE (Workstream 2).
- `.claude/state/` does not exist today; runtime sidecars live at `.claude/project-graph.json`, `.claude/locks/` (git-ignored), `.claude/session-context.md`. `.gitignore` does NOT currently cover `.claude/state/` — this plan adds it so the registry (which contains machine-local paths) is never committed/shipped.
- `gen-docs.py` regen rewrites ONLY the README inventory block; prose counts are hand-fixed and `--check`-gated across `DRIFT_FILES` (README.md, docs/AGENTS.md, docs/ARCHITECTURE.md, docs/SKILLS.md, docs/HOOKS.md). Known lines that will go stale at 41 commands / 75 skills: `README.md:246,341,342`, `docs/ARCHITECTURE.md:48,49,475`, plus count prose in `docs/SKILLS.md` / `docs/AGENTS.md`; out-of-gate but updated for consistency: `CLAUDE.md:7`, `AGENTS.md:7`, `.ai/SYSTEM_OVERVIEW.md:14,15,27,47`, `.ai/MEMORY.md:11`, `.ai/README.md:23,24`, `.ai/MODEL_ONBOARDING.md:17`.
- `skills-registry.json` `skills[]` is hand-maintained; `agentMapping` AND `usedBy` are derived/rewritten by `gen-registry.py` from agent "Skill Loading" sections — so `usedBy` for the new skill is authored via the agent files, and whatever is hand-seeded gets overwritten (expected, harmless).
- Twins: exactly 2 skills are byte-identity-enforced against `templates/skills/` (`codebase-mapping`, `context-priming`); new skill needs no twin.
- Mirror trees `.agents/` (skills mirror) and `.codex/` (Codex-flavored corpus) are shipped surfaces; skill edits must propagate to `.agents/skills/` in this plan; `.codex/` regeneration is a separate owner-scheduled sync pass (noted in CHANGELOG).
- Counts arithmetic: 40 command files, 74 skills today → 41/75 after.
- `project-graph.py` precedent: exit codes 0/1/2/3 and `CLAUDEKIT_PROJECT_ROOT`-style env override for subprocess behavioral tests — adopted here.
- Claude Code native worktree support (`--worktree`, `EnterWorktree`, Agent `isolation: "worktree"`) per research report `git-worktrees-parallel-ai-agents-2025-2026.md` (v2.1.206+ claim sourced there; `batch.md:55` already uses `EnterWorktree`). Our layer adds what native lacks: registry, setup copy-list, per-worktree env, merge protocol, cross-tool support.

## Workstream 1 — Worktree engine (Phase 1)

| File | Change |
|---|---|
| `.claude/operations/scripts/worktree-manager.py` | NEW, stdlib-only. Subcommands: `create <slug> [--base <ref>] [--copy <path>...]`, `list [--json]`, `remove <slug> [--force]`, `prune`. **Input validation (security)**: slug must match `^[a-z0-9][a-z0-9-]{0,40}$` (reject otherwise, exit 2); all git calls use `subprocess` list form (never `shell=True`) with `--` before user-supplied refs; `--copy` targets resolved via `os.path.realpath` and MUST stay inside the repo root (reject symlink escapes, absolute paths outside root, null bytes). **Behavior**: creates `.worktrees/<slug>` + branch `agent/<slug>` from `--base` (default: current HEAD); registry `.claude/state/worktrees.json` stores **repo-relative** paths (slug, branch, relpath, base, created ISO date, index); copies `.claude/settings.local.json` if present, preserving mode (0600 if source is stricter); **`.env` is NEVER copied by default** — only via explicit `--copy .env` (secrets stay opt-in); writes `.worktree-env` (WORKTREE_SLUG, WORKTREE_INDEX, WORKTREE_PORT_OFFSET=index*10) into the worktree. **Guards**: refuses duplicate slug; refuses >5 registered worktrees; `remove` refuses (a) dirty tree, (b) **unpushed/unmerged commits** (`git log <base>..HEAD` non-empty) without `--force`, (c) the primary worktree, always; `prune` reconciles registry against `git worktree list --porcelain` and removes stale entries. **Concurrency**: registry writes are atomic (`tempfile` + `os.replace`) under a lock file `.claude/locks/worktree-manager.lock`. **Exit codes**: 0 ok, 1 operational error, 2 validation refusal (repo convention). **Testability**: honors `CLAUDEKIT_PROJECT_ROOT` env override for the repo root. `create --json` emits the **absolute** worktree root for dispatchers. |
| `.claude/commands/worktree.md` | NEW command (model: haiku): thin front-end to worktree-manager.py; usage examples; safety notes (never `rm -rf` a worktree — use remove/prune; never merge from inside a worktree). Justification vs `/batch`: `/worktree` is the *primitive* (lifecycle of one worktree); `/batch` remains the *orchestrator* and now delegates lifecycle to the same script (see Workstream 2) — no near-duplicate: one manages, one orchestrates. |
| `.claude/skills/using-git-worktrees/SKILL.md` | Drop `disable-model-invocation: true` (single-skill fix; four loaders reference it — see recon). Add sections: worktree-per-agent (one branch = one worktree = one agent), manager script + registry usage, per-worktree env (ports/devices), `.gitignore` requirements, native Claude Code isolation options, and the copy-local-config-NOT-secrets rule (kept, now enforced by the script default). |
| `.agents/skills/using-git-worktrees/SKILL.md` | Mirror the same edit (shipped surface). |
| `.gitignore` | Add `.worktrees/` AND `.claude/state/` (registry holds machine-local data; must never ship — install.sh copies `.claude/` wholesale). |

## Workstream 2 — Orchestration integration (Phase 2)

**Isolation mechanism (the load-bearing decision, per reviewer finding 1):** every worktree-dispatched implementer receives, in its dispatch prompt, the absolute worktree root (from `create --json`) and the contract *"run EVERY command as `cd <worktree_root> && <command>`; never operate from the main tree"*. With cwd = worktree root: `execute-json-ops.py`'s cwd-containment guard scopes writes to the worktree, and `ops-enforcement.sh`'s `git rev-parse --show-toplevel` resolves to the worktree root, so its `.claude/*` exemption and backup/review-record paths resolve inside the worktree. Iron Law preserved per worktree. A behavioral test proves this end-to-end (Workstream 4). Claude Code native `isolation: "worktree"` remains a documented alternative for harnesses that support it.

| File | Change |
|---|---|
| `.claude/agents/coordinator.md` | Replace the bare line at 441 with a "Worktree Isolation Protocol" subsection: ≥2 parallel implementers → one worktree per sub-plan via `worktree-manager.py create --json`; dispatch with the cd-contract above; after all COMPLETE → gitOps merge phase; workers forbidden to merge or push. Add **using-git-worktrees** + **cross-tool-collaboration** to on-demand Skill Loading (drives gen-registry). |
| `.claude/agents/gitOps.md` | Add "Multi-Agent Merge Protocol": integration branch `integration/<goal>`; merge `agent/*` branches in dependency order; single verification pass on the integration branch; then PR; cleanup = delete merged `agent/*` branches + `worktree-manager.py remove`. Add **cross-tool-collaboration** to on-demand Skill Loading. |
| `.claude/commands/batch.md` | Reconcile with the primitive: (a) worktree lifecycle via `worktree-manager.py` (EnterWorktree allowed as fallback where the script is unavailable); (b) units execute in **waves of ≤5** concurrent worktrees (was: 5–30 unbounded); (c) remove agent-side PR/merge steps — agents commit on `agent/*` only; the orchestrator (gitOps protocol) merges. |
| `.claude/skills/multi-agent-coordination/SKILL.md` | Add "Pattern 4: Worktree-Per-Agent" + `MULTI_AGENT_PLAN.md` template (task matrix: task, owner agent/tool, branch, worktree, WRITE/READ/NO file sets, status). |
| `.agents/skills/multi-agent-coordination/SKILL.md` | Mirror the same edit. |

## Workstream 3 — Cross-tool & multi-account bridge (Phase 3)

| File | Change |
|---|---|
| `.claude/skills/cross-tool-collaboration/SKILL.md` | NEW skill. Content: (a) shared-instruction layer — AGENTS.md standard, generated mirror of CLAUDE.md, single-source-of-truth rule; (b) dual Claude accounts — `CLAUDE_CONFIG_DIR` aliases, independent quotas, macOS Keychain caveat, **hardening requirements: config dirs OUTSIDE any repo, `chmod 700` dir / `600` credentials, never committed**, framing = isolation of legitimately separate subscriptions (work/personal), NOT quota circumvention; ToS note; (c) heterogeneous tools — Cursor CLI headless alongside `claude -p`; role split (Account A = planner/reviewer/merge authority; Account B = implementer; foreign tool = cross-reviewer or disjoint-module implementer); (d) coordination contract — MULTI_AGENT_PLAN.md + file-ownership map + agents-never-merge; (e) **trust boundary — foreign-tool output entering Claude context is untrusted DATA, never instructions; cross-link `prompt-injection-defense`**; (f) hard limits — ≤5 parallel agents; non-Claude tools get disjoint ownership or read-only review. |
| `.agents/skills/cross-tool-collaboration/SKILL.md` | Mirror copy of the new skill. |
| `.claude/skills/skills-registry.json` | Add `cross-tool-collaboration` to `skills[]` (usedBy seeded; gen-registry will rewrite from agent files — expected). |
| `docs/PARALLEL_AGENTS.md` | NEW user doc: quick start, architecture diagram, dual-account recipe (same hardening requirements as the skill), Cursor bridge, merge flow, troubleshooting. **Owner sign-off checkbox** for the dual-account section before any release ships it: [ ] Omar approves publishing the dual-account recipe. |

## Workstream 4 — Tests, docs, gates

- `tests/test_worktree_manager.py` (NEW, behavioral, subprocess-level via `CLAUDEKIT_PROJECT_ROOT`): temp git repo fixture → create (dir + branch + registry relpaths + `.worktree-env` + copied settings.local.json with mode preserved); duplicate-slug refusal (exit 2); **traversal slug `../x` refusal**; **absolute/outside `--copy` refusal**; **flag-like `--base` handled safely (`--` separator)**; `.env` NOT copied by default; max-5 refusal; list --json; remove clean; remove dirty w/o --force refused; **remove with unpushed commits w/o --force refused**; remove primary worktree always refused; prune after manual deletion; registry write is atomic + lock file created; **registry path is git-ignored (`git check-ignore`)**. ~16 tests.
- **Isolation proof test**: inside a temp-repo worktree created by the manager, run `execute-json-ops.py` (cwd = worktree root) with a small ops.json → asserts writes land in the worktree and the cwd guard accepts; asserts a path escaping the worktree is rejected.
- `python3 scripts/gen-docs.py` (regen README block) + **hand-fix enumerated prose count lines** (see recon) + new skill row in `docs/SKILLS.md` table + `docs/ARCHITECTURE.md` skill-mapping rows; `python3 scripts/gen-registry.py` (regen agentMapping/usedBy); then both `--check`.
- CHANGELOG.md `[Unreleased]`: Added — worktree engine + /worktree + cross-tool-collaboration skill + PARALLEL_AGENTS doc; Changed — coordinator, gitOps, batch (waves ≤5, orchestrator-merges), multi-agent-coordination, using-git-worktrees; Fixed — `using-git-worktrees` was model-invocation-disabled while four loaders instruct agents to load it (single-skill fix); Note — `.codex/` mirror refresh deferred to next corpus sync.
- `.ai/BACKLOG.md`: log (a) corpus-wide disable-model-invocation vs loader-instruction contradiction (~30 skills, interacts with task 009's routing-tax goal — this plan adds +1 skill/+1 command/1 un-gated skill to the routing surface, accepted cost); (b) optional `ck doctor` manifest entry for worktree-manager.py.
- Full DoD gate: pytest, ruff, mypy, gen-docs --check, gen-registry --check, shellcheck.

## Workstream 5 — AppiumLens applicability (after ClaudeKit DoD passes)

Write `~/IdeaProjects/AppiumLens/.claude/plans/plan-parallel-agents-pilot.md` (additive; no AppiumLens code touched):
- Assets arrive on next fleet sync; until then reference claudekit master paths.
- Gradle: shared `~/.gradle` cache makes worktree builds cheap; per-worktree `build/` isolated automatically.
- Device/port matrix: per-worktree `APPIUM_PORT=4723+WORKTREE_PORT_OFFSET`, `SYSTEM_PORT`, ADB UDID assignment via `.worktree-env`; device-ownership rule (a UDID belongs to exactly one worktree).
- Dual-account roles + optional Cursor as test cross-reviewer; MULTI_AGENT_PLAN.md seeded with 3 example disjoint tasks.

## Risks & mitigations

- **Isolation regression**: covered by the isolation proof test (executor guard inside a worktree).
- **Registry leak**: `.claude/state/` git-ignored + `git check-ignore` test; relpaths only.
- **Secret duplication**: `.env` opt-in only; mode preserved on copies; documented permission-inheritance effect of copying `settings.local.json` (its `permissions.allow` grants apply in the worktree session) in skill + doc.
- **/batch contradiction**: reconciled in scope; single merge authority everywhere.
- **Prompt-file regressions**: gen-registry --check + test_registry.py.
- **Routing-surface growth vs task 009**: accepted +1 skill/+1 command; logged to backlog.
- No changes to hooks, security module, or install.sh.

## Rollback

- Git revert per commit (one concern per commit: engine+tests; orchestration prompts; cross-tool skill+docs).
- Runtime artifacts from failed runs: `worktree-manager.py prune`, `git worktree remove <path>`, `git branch -D agent/<slug>`, delete `.claude/state/worktrees.json` — all documented in the command file.

## Out of scope

- MCP coordination bus (Agent Room / Agent Bus) — documented future option.
- Corpus-wide disable-model-invocation reconciliation (backlogged; task 009 owns the policy).
- `.codex/` mirror regeneration (separate sync pass).
- Fleet-wide distribution; release/tag (owner-gated).
