# Task 009 — Context Budget Reduction & Hook Consolidation

## Problem
The kit sells "85% token reduction" while imposing measured, unmanaged overhead:
- **Routing-surface tax ~12,400 tokens/session** before any work: agent frontmatter descriptions ~6,500 tokens (30 agents), skill descriptions ~4,076 (73/74 skills), command descriptions ~1,848 (39 commands) (performance §1, ai §5.1).
- **Registry duplication:** `skills-registry.json` (~7,076 tokens) is a near-duplicate of the skill frontmatter — if both are visible, ~11K tokens describe the same skills twice (performance §2).
- **Mandatory-skill boot stacks:** coordinator loads 12 skills ≈ 28–35K tokens; a single Feature pipeline (coordinator+planner+reviewer+implementer+verifier+gitOps) pays **~80–100K tokens of skill text alone**, most of it motivational prose (ai §5.2). `using-superpowers` + `golden-rule` are ~290 lines whose operative content is two sentences.
- **Four-layer duplication:** pipelines exist in coordinator.md AND HANDOFF_PROTOCOL.md; handoff blocks in three homes; plan templates in three; verification gates in four; model routing table in two; explore methodology in three (ai §5.3). Estimated 30–40% of the agent+command corpus is duplicate.
- **Hook latency:** every Edit fires 3 hooks ≈ 9–12 process spawns; every Bash fires 4–5 ≈ 12–15 spawns; measured ~150–300 ms per tool call, dominated by repeated python3 cold starts (~12 ms each) and per-hook `git rev-parse` (~14 separate invocations in settings.json) (performance §3).
- **Decorative output:** Unicode progress bars/box diagrams cost tokens both ways and invite arithmetic errors (ai §5.4).

## Root Cause
No corpus budget is tracked (the kit ships `context-budget`, the diagnostic for its own disease — ai §4.7), and content was duplicated for author convenience because nothing generates from canonical sources. Hooks grew one-script-per-concern with copy-pasted plumbing.

## Files
- `.claude/agents/coordinator.md` (12-skill list → 5-line inline digest, ai Offender #3), `planner.md`, `reviewer.md`, `implementer.md`, `verifier.md` (≤2 mandatory loads each)
- `.claude/skills/using-superpowers/SKILL.md` (rewrite trigger rule, ai Offender #4), `golden-rule/SKILL.md` (approval-modes rewrite feeds ai §3.3)
- `.claude/agents/_shared/HANDOFF_PROTOCOL.md`, `WORKFLOW_FILE_TEMPLATES.md`, `VERIFICATION_PROTOCOL.md` (become the single canonical homes; duplicates deleted from agents/commands)
- `skills-registry.json` (drop from the model-visible path; keep as build-time source)
- `.claude/settings.json` + all hooks → new `hooks/dispatch.sh` per event (or single python dispatcher), builds on task 003's `lib.sh`
- `session-start.sh` (export `CK_ROOT` once)
- Agent output-format sections (strip progress bars/banners)

## Priority
**P1** for skill-boot diet + registry dedup (biggest single savings); **P2** for the rest.

## Estimated Time
1–1.5 weeks (content surgery is careful work; dispatcher is 1–2 days on top of task 003).

## Risk
Medium. Cutting "motivational prose" can remove rules an agent actually branched on — mitigate with before/after eval runs (task 010) per agent edit. Dispatcher consolidation changes hook ordering semantics; preserve the current sequence (enforcement → protection → reminder) and blocking behavior exactly.

## Step-by-step Implementation
1. **Measure first:** commit a `scripts/context-audit.py` (adapt the heuristics from the `context-budget` skill: ~15 tokens/line) emitting per-asset token estimates + totals; record the baseline (~12.4K routing, ~208K corpus) in the repo so regressions are visible.
2. **Skill-boot diet:** per agent, inline a 3–5 line "Operating Rules" digest (ai Offender #3 gives the coordinator text) and cut mandatory loads to ≤2 procedural skills (e.g., planner keeps `generate-operations-config`; implementer keeps `execute-operations-config` — post-task-003 rewrite). Long-form skills remain for on-demand reference.
3. Rewrite `using-superpowers` per ai Offender #4 (trigger-condition table replaces absolutism; acknowledges the 1–4K token cost of gratuitous loads) — also resolves the conflict with CLAUDE.md templates' "pure question → answer directly."
4. **Canonical homes:** pipelines live only in HANDOFF_PROTOCOL.md; handoff block format only there; plan template only in `writing-plans`; verification gates only in VERIFICATION_PROTOCOL.md; routing table only in coordinator.md. Everything else references by path. Delete the duplicated blocks (~30–40% corpus reduction target).
5. **Registry out of the context path:** skill routing relies on frontmatter only; `skills-registry.json` becomes a build-time artifact consumed by generators/doctor/CI (tasks 006/008), never loaded by the model. Est. ~7K tokens/session saved.
6. **Skill catalog tiering:** keep ~20 core skills in the routing surface; niche skills (`insecure-defaults`, `property-based-testing`, `static-analysis-integration`…) get `disable-model-invocation` or minimal descriptions, invoked explicitly. Est. 2–4K tokens/session.
7. **Hook dispatcher:** one entry per event in settings.json → `dispatch.sh <event>`; reads stdin once, one python3 parse extracting all fields, runs checks in-process, first block wins (exit 2). `CK_ROOT` exported by session-start and trusted by all hooks. Target: ≤2 process spawns per tool call (from 9–15), ~60–120 ms saved per call.
8. Strip decorative output from agent output formats (`Score: 87/100` replaces bars).
9. Re-run the context audit; publish before/after in the README perf section (feeds oss-excellence #12 benchmark work).

## Acceptance Criteria
- Context audit shows: routing surface ≤ ~8K tokens; coordinator boot ≤ 5K (from 28–35K); feature-pipeline skill text ≤ 25K (from 80–100K).
- `time` of a simulated Edit hook chain ≤ 80 ms (from ~150–250 ms); ≤2 python spawns per tool call (count via a wrapper).
- No content block >20 lines appears verbatim in two files (`scripts/dup-check.py` in CI).
- Eval suite (task 010) shows no regression on the core-agent fixtures after each content cut.
- `scripts/context-audit.py` runs in CI and fails on >10% unexplained growth (the "corpus budget" from arch F-20).

## Testing Strategy
- Task 003's behavioral hook tests re-pointed at the dispatcher (same payloads, same expected exits — proves semantic preservation).
- Timing micro-benchmark in CI (soft threshold, warn-only, to avoid runner variance flakes).
- Eval regression runs per PR touching `.claude/agents/` or `skills/`.

## Rollback Plan
Dispatcher: settings.json can be reverted to the per-hook entries (keep the old hook scripts in place until one release after the dispatcher stabilizes). Content cuts: batched PRs, each revertible; the canonical-home refactor moves text rather than deleting it, so restoration is a copy-back.
