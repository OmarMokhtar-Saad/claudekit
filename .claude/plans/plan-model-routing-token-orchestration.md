# Plan: Model Routing, Token Economy, Parallel Orchestration & Trivial Fast-Path

**Date**: 2026-07-23 | **Target**: claudekit master → distribute to all installed projects
**Requested by**: Omar | **Author**: main agent (direct user approval in conversation)

## Goals
1. Per-agent model routing: planner=opus, reviewer=sonnet, implementer=haiku, explore=haiku.
2. Never stop on model limits: global fallback chain sonnet → haiku.
3. Cut web-search token burn: haiku `web-researcher` agent + context7-first + research cache.
4. Parallel orchestration: coordinator decomposes big/multi-task requests, fans out plan/review, gates execution.
5. Trivial fast-path: ≤2-line / cosmetic changes → ops.json + implement directly, skip planner/reviewer.

## Verified facts (recon)
- Master source of truth = `~/IdeaProjects/claudekit/.claude/` (`CLAUDE_SRC="$SCRIPT_DIR/.claude"` in install.sh:11). Projects hold synced COPIES + `.claudekit-manifest.json` with per-file sha256 (keys relative to `.claude/`, used by `ck update` drift detection).
- Current master models: planner=opus, reviewer=opus, implementer=sonnet, explore=sonnet, coordinator=sonnet, model-router=haiku.
- Manifest-tracked projects: AppiumLens, LeanApis, MobileUIAutomator, ai-agent-system, qa-agents, qaforge-ai.
- `~/.claude/settings.json`: `"model": "claude-fable-5[1m]"`, NO fallbackModel today.
- Claude Code facts (doc-verified): agent frontmatter `model:` = single alias/ID/inherit; `fallbackModel` array in settings.json applies to session + subagents; `CLAUDE_CODE_SUBAGENT_MODEL` env overrides all subagents; `ANTHROPIC_SMALL_FAST_MODEL` deprecated.

## Workstream A — Model routing (master agents)
| File | Change |
|---|---|
| `.claude/agents/reviewer.md` | `model: opus` → `model: sonnet` |
| `.claude/agents/implementer.md` | `model: sonnet` → `model: haiku` (safe: implementer only runs execute-json-ops.py mechanically) |
| `.claude/agents/explore.md` | `model: sonnet` → `model: haiku` (5K/10K budget fits haiku) |
| `.claude/agents/planner.md` | unchanged (opus) |

Risk: reviewer 90/100 gate quality on sonnet → mitigated by coordinator escalation rule (opus reviewer for multi-phase / architecture / security plans, via Agent-call model override).

## Workstream B — Fallback chain (user settings)
- Backup `~/.claude/settings.json` → `settings.json.bak-<date>`.
- Add `"fallbackModel": ["sonnet", "haiku"]`. On primary-model limit/overload the session AND subagents degrade instead of stopping.
- Emergency lever (documented, not configured): `CLAUDE_CODE_SUBAGENT_MODEL=haiku claude`.

## Workstream C — web-researcher agent (NEW, master)
`.claude/agents/web-researcher.md`: model haiku; tools WebSearch, WebFetch, Read, Write, Grep, Glob.
Contract: cache-check `.claude/reports/research/` first → context7-first for library docs → max 3 search rounds → one targeted WebFetch over multi-open → return ≤300-token distilled answer + source URLs → write cache file. Raw page content never leaves the agent.

## Workstream D — Coordinator Orchestration Protocol v2 (master)
Append to `.claude/agents/coordinator.md`:
- **Triage**: TRIVIAL → fast-path (no planner/reviewer); single task → standard pipeline; multi-task or plan >15 ops / >2 phases → decompose; external info → web-researcher.
- **Decompose**: sub-plans + dependency graph + file-ownership map (a file belongs to exactly one sub-plan; overlap ⇒ merge or serialize).
- **Fan out**: planners for all sub-plans in parallel (read-only, safe); reviewers in parallel; reviewer=sonnet, opus escalation rule.
- **Composition gate (barrier)**: simulate/dry-run ALL approved ops.json together before ANY execution (cross-plan anchor collisions).
- **Execute**: disjoint file sets in parallel (worktree isolation if needed); overlapping sequential in dependency order; re-validate anchors at execution time.
- **Model economy** table (planner opus only when architecture-heavy; consult model-router when unsure).
- **Verifier gate (NEW, user-ordered)**: verifier NEVER auto-runs after implementation. Flow STOPS after implementer reports; ask the user "Run verifier?" and run only on explicit approval.

## Workstream E — CLAUDE.md policy block (all projects)
Append marker-guarded block `<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v1 -->` to each target project's `CLAUDE.md` (idempotent — skip if marker present):
1. Web research only via web-researcher; context7 first; cache check.
2. **Trivial fast-path**: ≤2 lines OR purely cosmetic (color/size/spacing/label/log-level), single file, no API/architecture/security impact → create minimal ops.json → validate → execute → compile-verify. SKIP planner/reviewer. Criteria unmet or execution fails → full flow. (Constitution exception explicitly ordered by Omar, 2026-07-23.)
3. Model routing table + fallback note.
4. Many tasks / oversized plan → coordinator Orchestration Protocol v2.

## Workstream F — Distribution
For each of: AppiumLens, LeanApis, MobileUIAutomator, ai-agent-system, qa-agents, qaforge-ai:
1. `cp` changed/new agent files: reviewer.md, implementer.md, explore.md, coordinator.md, web-researcher.md → `<proj>/.claude/agents/`.
2. Refresh those 5 entries in `<proj>/.claude/.claudekit-manifest.json` (sha256, python) so `ck update` sees no drift.
3. Append CLAUDE.md policy block (marker-guarded).
Skipped (no manifest): Lean, "LeanApis ai-agent-system AppiumLens MobileUIAutomator" (stale/accidental dirs) — noted for user.

## Workstream G — Verification
- `grep ^model:` for the 5 agents across master + 6 projects == expected matrix.
- `python json.load` on `~/.claude/settings.json` and all touched manifests.
- Manifest sha256 == actual file sha256 for copied files.
- Marker block present exactly once per CLAUDE.md.

## Rollback
- claudekit master: `git diff` / `git checkout -- <file>` (repo is git; changes left uncommitted for user review).
- Settings: restore `.bak` file.
- Projects: re-copy previous versions from claudekit git history; manifest re-refresh.

## Out of scope / follow-ups
- Committing claudekit changes (user to review diff, then commit).
- Adding policy block to `templates/*/CLAUDE.md` for future fresh installs.
- New-session smoke test of agent spawning under new models.
