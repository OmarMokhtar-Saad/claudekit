# Plan: token-spend remediation (umbrella / handoff)

Written 2026-09-19 from a transcript scan of both accounts (`~/.claude`, `~/.claude-acct-b`),
2026-09-17 → 2026-09-19. Scan scripts: session scratchpad `usage.py`, `subs.py`, `deep.py`,
`hooks.py`, `rest.py`, `pipeline.py`, `stages.py`, `guards.py`, `stops.py`.
Memory: `token-spend-root-causes-2026-09-19`.

## Measured

| Fact | Value |
|---|---|
| API input tokens, 2 days | 1.88 B deduplicated on message.id (1.82 B cache reads, 56 M cache writes, 4.5 M output), 8,728 turns. First scan said 3.33 B / 16,057: it counted records, not messages; ratios below unchanged |
| Share | qa-agents 84 %, claudekit 13 %; main sessions 2.26 B, subagents 1.07 B |
| Sessions at 500–966 K context | 7; compactions in 2 days: 9 |
| Planner | 33 runs, 646 M (19 %), avg 98 turns, worst 572 turns / 895 K; `maxTurns: 40` did not bind |
| Reviewer | 35 runs, 2.5 M avg, 33 turns avg, 56/56 APPROVED at 95–96 |
| Implementer | 44 turns / 1.4 M avg to run three scripts |
| One simple task (plan→review→plan→review→implement) | 7.9 M, 32 parent turns |
| Peer-bridged main sessions | peak 8 per account, 305 peer messages |
| Guard blocks (2 days) | 235 PreToolUse + 24 Stop blocks → 149 forced turns; ~35 M re-sent |
| Reflection loop | 436 write calls, 134 issues, 162 proposals, 1 promoted, **0 reads** |
| Memory | qa-agents 289 files / 772 KB, 135 write calls, 14 reads in 2 days |
| After the 09-19 03:38–04:04 fixes (7.6 h) | 33 M ctx-tokens/h vs 58 M/h before; main avg ctx 165 K vs 303 K |

## Work items

### A. Account settings (both `~/.claude/settings.json` and `~/.claude-acct-b/settings.json`) — DONE in-session
- `model`: drop the `[1m]` suffix (200 K hard window).
- `autoCompactWindow`: 350000 → 150000.
- `enabledPlugins["warp@claude-code-warp"]`: true → false (7,551 PostToolUse injections in 2 days).
- Operator: run implementation sessions on Opus (`/model opus`), effort high not xhigh; stop bridging
  parallel sessions — one orchestrator, short-lived subagents.

### B. claudekit repo — DONE via `.claude/plans/ops-token-remediation-ck.json` (planner-authored, 10 ops) + `.claude/plans/ops-token-remediation-ck-followup.json` (test constant `MEMORY_AGENTS` and `agent-memory/README.md` list trimmed to code-reviewer + planner). Follow-up prose: the `## Durable memory` body sections in explore, debugger, verifier, security-scanner are now stale.
1. `.claude/agents/planner.md`: tools → Read, Grep, Glob, Write (no Bash); `maxTurns: 15`.
2. `.claude/agents/reviewer.md`: `maxTurns: 8`; body: read plan.md + ops.json only, no codebase exploration.
3. `.claude/agents/implementer.md`: `maxTurns: 12`.
4. Remove `memory: project` from reviewer, explore, debugger, verifier, security-scanner (never written to).
5. `.claude/settings.json`: drop reflection-gate on Stop, SubagentStop, PreCompact, PostToolUse; drop
   `command-log-audit.sh` (3,137 parse failures, never worked). Keep reflection-gate SessionStart +
   PostToolUseFailure (append-only ledger, no gate).
6. `.claude/hooks/dispatch-registry.json`: remove the reflection-gate PreToolUse row.
7. `CHANGELOG.md` `[Unreleased]` entry.
Validation: `python3 -m pytest tests/ -q`, `ruff check ...`, `python3 scripts/gen-docs.py --check`,
`python3 scripts/gen-model-policy.py --check`, `python3 scripts/check-plan-artifacts.py --check`.

### C. qa-agents repo — DONE 2026-09-19 (C.1–C.5 applied by session qa-agents-20260919-1245; spent configs archived in qa-agents `.claude/plans/archive/ops-token-remediation/` with README rows: `…-frontmatter.json` 7 ops, `…-c1-c3.json` 4 ops, `…-c3doc-c4.json` 2 ops). Superseded note on item 1: claudekit `command_validator.py` now carries `_SAFE_ENV_ASSIGN_NAMES` too; the copies differ only on bare assignments (`FOO=bar echo hi`: claudekit allows since 558ed14, the qa-agents vendored copy refuses), which is the open `vendorparity` finding.
1. `.claude/hooks/vendor/claudekit_security/cli.py`: resolve `.claude/hooks/config.json` via
   `CLAUDE_PROJECT_DIR`, then walk up from cwd (port `_find_config` from claudekit
   `src/claudekit/security/cli.py`). Root cause of "Command not in allowlist: adb" and the
   `ImportError`/`ModuleNotFoundError` phantom blocks. Do NOT overwrite `command_validator.py`:
   the qa-agents copy carries `_SAFE_ENV_ASSIGN_NAMES` / steering hardening claudekit lacks.
2. Same frontmatter edits as B.1–B.4.
3. Same hook unwiring as B.5–B.6.
4. `.claude/agents/_shared/INVOCATION.md`: planner rows still document a Bash grant; trim to
   `Read, Grep, Glob, Write` (claudekit did this in `ops-tests-docs.json`; drift test exists there).
5. After executing, move the spent `ops-token-remediation-qa-agents-frontmatter.json` and the new config
   into `.claude/plans/archive/<name>/` with a README row, or the queued-ops gate fails on the next full run.
Validation: qa-agents `pytest -q` (full suite once), guard probe from a subdirectory cwd.
Note: `command-log-audit.sh` is identical in both repos and has never recorded a payload in either
(claudekit hooks.log: 5,012 parse failures / 0 recorded) while its stdin test stayed green — the test
exercised a sandbox payload, not a production one. Removing the hook is correct in both repos.

### D. Memory prune — DONE in-session (reversible: moved, not deleted)
`project`-type auto-memory files older than 30 days moved to `memory/_archive/` in both accounts'
qa-agents memory dirs; MEMORY.md lines pointing at them removed.

### E. Follow-ups for a fresh Opus session (owner decisions / new features)
- `ck implement <ops.json>`: validate → dry-run → execute → plan's validation commands → one RESULT
  line. Replaces the implementer agent for Tier 1/2. (`src/claudekit/cli/`, Tier 2)
- `/plan` defaults to inline plan+ops written by the parent; `--deep` spawns the planner.
- `security.projectTools` in `.claude/hooks/config.json`: heads exempt from allowlist and host-pattern
  matching (adb, emulator, gradle, ./gradlew, xcrun). Test: `adb shell rm -rf /sdcard/x` allowed.
- iron-law-gate: parent creates the branch; implementer never runs git.
- qa-agents `CLAUDE.md` 22 KB → ~8 KB (owner review; every subagent boots with it).
- Deletions (owner sign-off, MAX_DELETIONS=3/plan): `/refine`, `/gan-build`, `/santa`, `/xpipe`
  commands + skills; 162 unpromoted `.claude/knowledge/proposals`; 22 of 25 `.claude.bak-*` dirs.
- Review round: B and C touch hooks (Tier 3 by policy). Reviewer skipped on owner's cost mandate;
  run `/review` on the two ops files if wanted.
