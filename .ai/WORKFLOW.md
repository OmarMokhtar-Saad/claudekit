# Workflows

Every sanctioned way work moves through ClaudeKit. Commands in [COMMANDS.md](COMMANDS.md); agents in [AGENTS.md](AGENTS.md).

## 1. Standard feature pipeline
`/plan` → `/review` (≥90 or reject) → `/implement` (validate → backup → execute → build/lint/test) → `/verify` (≥80) → `/git` (branch/commit/PR). Orchestrated end-to-end by `/coordinator` for multi-step tasks. Auto-refinement variant: `/refine` loops planner↔reviewer until the gate passes.

## 2. PRP pipeline (context-rich, single-executor)
`/prp-plan` (deep recon; plan must be executable by a *fresh* agent with zero re-exploration) → `/prp-implement` (per-step validation loops; stops only when all checks pass) → `/prp-commit` (NL file targeting → conventional commit) → `/prp-pr` (template auto-discovery → generated description). Use when one strong agent should carry the whole change with maximal context.

## 3. Adversarial review
- **Santa** (`/santa`): Opus Skeptic + Sonnet Pragmatist review independently — no shared context — both must approve. For high-stakes changes (auth, migrations, public API).
- **GAN build** (`/gan-build`): Generator produces → *fresh* Evaluator scores (anti-anchoring) → Adjudicator decides converge/iterate; threshold + max-iteration caps.
- **Council** (skill): Architect/Skeptic/Pragmatist/Critic parallel debate for decisions rather than code.

## 4. Bug flow
`/debug` (read-only diagnosis, 4-phase RCA, confidence-rated) → then the standard pipeline for the fix (diagnosis is never implementation). Build breakage shortcut: `/build-fix` (minimal diff, ≤7 iterations).

## 5. Autonomous loops
`/loop-start` runs an iterating agent under **loop-operator** supervision: Warn → Pause+Report → Emergency Stop on stagnation/error spirals/destructive behavior. Iteration caps mandatory. (Block-list enforcement is still prompt-side — roadmap item 19.)

## 6. Audit fan-out
`/audit` = explore + silent-failure-hunter + security-scanner in parallel, merged report. Individual entry points: `/security`, `/performance`, `/deps`, `/code-review`.

## 7. Open-source pipeline
`/opensource`: Stage 1 sanitizer (secrets/PII/internal refs → PASS/FAIL) ⇒ **hard gate** ⇒ Stage 2 fork/transform ⇒ Stage 3 packager (README/CLAUDE.md/LICENSE/CONTRIBUTING/.github). Note: the "forker" stage is referenced by prompts but has no agent file (AGENTS.md issue #8).

## 8. Session continuity
`/save-session` writes `.claude/session-context.md`; `session-start.sh` auto-surfaces it; `/resume-session` restores with freshness rules (<4h trust · 4–24h verify · >72h stale-warn). Long multi-PR efforts: `/blueprint` produces a sequenced construction plan; `.claude/plans/phase-1-HANDOFF.md` is the exemplar of a phase handoff document.

## 9. Maintainer workflow (developing ClaudeKit itself)
Pick task from [BACKLOG.md](BACKLOG.md) → read the `review/tasks/0XX` spec → branch → behavioral test first → implement → run the full DoD gate ([MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) §5) → update CHANGELOG `[Unreleased]` + affected docs → conventional commit with co-author line → PR. Release recipe: [PLAYBOOK.md](PLAYBOOK.md).

## Choosing a workflow

| Situation | Use |
|-----------|-----|
| Normal feature/refactor | Standard pipeline (or PRP if exploration cost dominates) |
| High-stakes/risky change | Standard + `/santa` before merge |
| Vague requirements | `/clarify` questions → `/plan`, or brainstorm mode |
| Unknown codebase | `/onboard` or `/explore` first |
| Quality sweep | `/audit`, then plans per finding |
| Long grind (test fixing, migrations) | `/loop-start` with caps, or `/batch` for parallel worktrees |
| Epic (3+ PRs) | `/blueprint` then per-PR standard pipelines |
