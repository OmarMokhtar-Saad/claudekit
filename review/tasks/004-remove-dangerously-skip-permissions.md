# Task 004 — Remove `--dangerously-skip-permissions` & Standardize Agent Invocation

## Problem
ClaudeKit's own core commands disable Claude Code's primary safety mechanism. `/plan` (`.claude/commands/plan.md:30`), `/review` (`review.md:55`), and `/refine` (`refine.md:96,112,150`) spawn nested `claude -p --agent <name> --dangerously-skip-permissions` processes. These sub-agents read repo files and untrusted plan text, so any prompt injection in source content drives an agent explicitly stripped of permission gating — the security review's highest-impact design flaw (§4.1), and the worst possible pairing with the kit's autonomous-loop features (§4.2).

Compounding it: the kit is split-brained about **how** agents are invoked at all. `/refine` asserts the Agent tool's `subagent_type` does NOT resolve local agents and `claude -p --agent` is "the only verified mechanism," while `/implement`, `/coordinator`, `/docs`, `coordinator.md`, and `_shared/TASK_TOOL_SPECIFICATION.md` describe Task/Agent-tool spawning. If `/refine` is right, half the orchestration docs silently route to the wrong agent (ai-review §2.2, finding A3). Nested `claude -p` also doubles token cost, loses context, and couples to an undocumented CLI surface (architecture-review F-10).

## Root Cause
The nested-CLI pattern was adopted to guarantee agent-file loading when the native mechanism was unverified, and `--dangerously-skip-permissions` was added to stop the subprocess from stalling on permission prompts in headless mode. Nobody reconciled the two invocation stories afterward, and no security review gated the flag's inclusion.

## Files
- `.claude/commands/plan.md:30`
- `.claude/commands/review.md:55`
- `.claude/commands/refine.md:96,112,150`
- `.claude/commands/loop-start.md` (autonomous loops — flag becomes explicit opt-in here only)
- `.claude/agents/coordinator.md`, `.claude/agents/_shared/TASK_TOOL_SPECIFICATION.md`, `.claude/agents/_shared/HANDOFF_PROTOCOL.md` (invocation mechanism docs)
- Wrapper commands `/implement`, `/coordinator`, `/docs`, `/debug`, `/verify`, `/git` (whichever mechanism loses)
- `SECURITY.md` (disclose the change and residual risk)

## Priority
**P0** (security High). The invocation standardization is P1 but done in the same pass.

## Estimated Time
2–3 days including verification of the native subagent mechanism against the current Claude Code release.

## Risk
Medium. Removing the flag may reintroduce permission prompts inside `/plan` flows, changing UX (prompts are the point, but users accustomed to unattended planning will notice). If the native Task mechanism genuinely cannot load `.claude/agents/*.md` in the current Claude Code version, the fallback is scoped headless invocation — never a blanket permission bypass.

## Step-by-step Implementation
1. **Verify the transport empirically** (this decides everything): in a fixture project, test (a) Task-tool invocation of a local agent, (b) `claude -p --agent <name>` *without* the flag but with `--allowedTools "Read,Grep,Glob,Write"` scoping. Record results in `_shared/INVOCATION.md` — the new single source of truth.
2. Remove `--dangerously-skip-permissions` from plan.md, review.md, refine.md (all five occurrences).
3. If native Task works: rewrite the three commands (and coordinator.md) to use it; delete the nested-CLI instructions; reserve headless `claude -p` for `/loop-start` only.
4. If nested CLI must stay: scope every invocation with `--allowedTools` appropriate to the agent (planner/reviewer are read-only + plan-file writes; never unrestricted Bash), and document why.
5. `/loop-start`: permission bypass becomes an explicit opt-in flag (`--unsafe-skip-permissions`) that (a) defaults off, (b) prints a red warning, (c) requires the sandbox profile once task 010/sandbox work lands; loop block-list enforcement moves into the PreToolUse hook (task 002) instead of narration.
6. Update `TASK_TOOL_SPECIFICATION.md`, `HANDOFF_PROTOCOL.md`, and every wrapper command to reference `_shared/INVOCATION.md`; delete contradictory prose (the "no nested spawning" rule vs `--dual`/GAN designs — ai finding A14 — gets an explicit exception list here).
7. Add a CI grep gate: `grep -rn "dangerously-skip-permissions" .claude/ templates/` fails unless the only match is loop-start's documented opt-in.
8. SECURITY.md: note the historical exposure and the new posture.

## Acceptance Criteria
- Zero occurrences of `--dangerously-skip-permissions` in shipped commands/agents/skills except the documented `/loop-start` opt-in.
- `/plan → /review → /refine` completes end-to-end in a fixture project using the standardized mechanism, with permission gating active.
- Exactly one document (`_shared/INVOCATION.md`) defines the invocation mechanism; all commands/agents reference it; no file contradicts it.
- CI grep gate green.

## Testing Strategy
- Manual pipeline run in the fixture repo (recorded transcript checked into `examples/` — doubles as the missing example content, docs-review §6).
- CI grep gate (step 7).
- Eval-framework smoke (task 010): planner invoked via the standardized mechanism produces a validator-passing ops.json.

## Rollback Plan
Command files are prompt assets — revert the commits and the previous behavior returns instantly (no binary/compat concerns). If the native mechanism proves flaky post-release, fall back to scoped `claude -p --allowedTools` (step 4) — under no circumstances restore the blanket flag.
