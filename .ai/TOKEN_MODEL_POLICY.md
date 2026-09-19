# Token & Model Policy — full text (v5, 2026-09-19)

The block in `CLAUDE.md` is the short form every session boots with. This file carries the rules in
full plus the evidence. Maintainers only.

## Why v5 (measured 2026-09-17..19, both accounts, deduplicated on message.id)

| Fact | Value |
|---|---|
| Input tokens in 2 days | 1.88 B (97 % cache re-reads), 8,728 API turns |
| Boot context per turn, qa-agents / claudekit | 66 K / 58 K tokens before any work |
| A 4-op Tier 1 task | 47 turns, 4.0 M tokens; ~15 turns spent scripting an ops.json with exact anchors |
| Planner runs | avg 98 turns; `maxTurns` in frontmatter never bound |
| Reflection Stop gate | 4 extra full-context turns per stop; 135 issue files, 164 proposals, 0 reads |
| Skills | 83 shipped, 3 ever invoked in qa-agents, 0 in claudekit |
| Agents | 28 shipped, 13 ever spawned fleet-wide |

## Rules

1. **Blast-radius tiers.** Tier 1: one file, no public API / security / schema / architecture surface
   -> the parent applies it directly where the hook profile allows, otherwise one single-op ops.json;
   no planner, no reviewer. Tier 2: several files, no security or schema surface -> the parent writes
   plan.md + ops.json itself and executes; spawn the planner only above 5 files. Tier 3:
   security-relevant, DB migrations, >15 ops or >2 phases -> planner -> reviewer -> implementer. The
   Iron Law binds the implementer agent (it never holds Edit/Write).
2. **Review and verification are on request.** No agent, command, skill or phase runs reviewer,
   code-reviewer or verifier on its own. When asked: fresh instance, never the author, told to refute;
   stop at the first round with zero blocking findings; 3 rounds is a hook-enforced ceiling.
3. **Turn hygiene.** Batch every independent command into one Bash call. Read files in windows
   (`sed -n`, `grep -n -C3`), never whole. Do not pause for "OK" on Tier 1: the executor and git keep
   backups. One task per session, then `/clear`; a day-long session re-reads its whole history every
   turn. Never bridge peer sessions: every peer message is a full-context turn on the receiver.
4. **Boot context.** Every skill, agent, hook line and CLAUDE.md paragraph is paid on every turn of
   every session. Hide never-invoked skills with `skillOverrides`, move never-spawned agents out of
   `.claude/agents/`, keep SessionStart output under 1.5 K chars, keep CLAUDE.md under the context
   floor budget, and turn off per project the plugins and MCP servers a project does not use.
5. **Models.** Roles map to capability tiers in `.claude/model-policy.json`, never to vendor names.
   the most-capable tier for implementation and review, the fast tier for transcript scans, probes and
   formatting. Effort high, not xhigh, for implementation. On limits, degrade one tier, never stop.
6. **Web research.** Main agent and planner never call WebSearch/WebFetch; check
   `.claude/reports/research/` first, call context7 yourself for library docs, else `web-researcher`.
7. **Parallel work.** Many tasks or a plan >15 ops -> `coordinator` with a file-ownership map and
   disjoint-set execution; never a shared tree for parallel builds.

## Previous block (v3, verbatim, retired 2026-09-19)

<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 START -->
## Token & Model Policy (ClaudeKit, 2026-07-23)

- **Web research**: main agent and planner MUST NOT call WebSearch/WebFetch directly. Check `.claude/reports/research/` first. Library/API docs -> call context7 YOURSELF (`web-researcher` has no MCP access, so delegating wastes a search); else delegate to `web-researcher`.
- **Blast-radius tiering** (route by risk surface, not line count):
  - **Tier 1** — single file, no public API/security/schema/architecture surface (any size: docs, tests, prompts, cosmetic, internal logic) -> create minimal ops.json -> validate -> execute -> compile-verify. SKIP planner/reviewer. Execution fails -> escalate to Tier 2.
  - **Tier 2** — multi-file, no security/schema surface -> planner + ops.json; reviewer ONLY if architecture is touched (new module boundaries, public API, cross-layer changes).
  - **Tier 3** — security-relevant, DB migrations, >15 ops, or >2 phases -> full pipeline (planner -> reviewer -> implementer), unchanged.
  - **Review floor (all tiers)**: every PR gets >=1 adversarial diff review before it merges — fresh `code-reviewer` instance, never the author, prompted to REFUTE not approve. Stop at the first round with zero blocking findings; ceiling 3 rounds; rounds 2+ read only the diff since the last verdict.
  - **Review routing**: plans -> `reviewer`; code + mutation proofs -> `code-reviewer`. See .ai/REVIEW_GUIDE.md
- **Verifier gate**: the verifier agent NEVER auto-runs after implementation. Stop, ask the user, run only on explicit approval.
- **Model routing**: policy names **capability tiers** (`most-capable`/`balanced`/`fast`), never vendor model names. `.claude/model-policy.json` is the one table — role -> accountability + tier (+`escalate_to`/`escalate_when`), tier -> model — and `scripts/gen-model-policy.py --check` gates the agent frontmatter against it. Changing a model is a one-line edit there. Role and capability are chosen **separately**. On limits, degrade one tier, never stop.
- **Turn hygiene**: `/compact` at 150K, never 300K; `py_compile` patch scripts before running; no re-reads; 3 review rounds is a hard stop (hook-enforced).
- **Parallel orchestration**: many tasks or plan >15 ops / >2 phases -> `coordinator` agent Orchestration Protocol v2 (decompose with file-ownership map, parallel plan/review, composition gate before execution, disjoint-set parallel execution).
<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 END -->
