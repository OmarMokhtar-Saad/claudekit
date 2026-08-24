# Technical Debt Register

Live register — remove entries when paid. Severity: H/M/L. Historical context: `review/` (audit) fixed items are *not* listed here.

| # | Debt | Sev | Where | Notes / exit |
|---|------|-----|-------|--------------|
| 2 | Prompt-corpus duplication (4 layers: command↔agent↔skill↔registry) | H | corpus-wide | ~60–80K tokens/pipeline waste; exit = tasks 008+009. |
| 3 | Near-duplicate assets | H | agents (10 merge candidates), skills (5 pairs/trios), `templates/skills/` (14 dupes, 2 diverged) | Exit = task 008 with migration table. |
| 4 | Gates are prompt-enforced only | H | reviewer/verifier prompts | 90/80 thresholds have no mechanical enforcement or calibration. Exit = task 010. |
| 5 | 9–15 hook spawns per tool call | M | `.claude/settings.json` | ~150–300 ms/call. Exit = single dispatcher per event (009). |
| 6 | `ck update` overwrite-with-backup, not merge | M | `cli/main.py` cmd_update | Roadmap §2.2 design (three-way vs manifest). |
| 7 | `hooks/config.json` dual role | M | `.claude/hooks/config.json` | "Deprecated" header but `project.*` is load-bearing. Exit = split project commands into their own file or fold into settings env. |
| 8 | QUICK_START / INVOCATION / frontmatter disagreements | M | `.claude/agents/` | Cataloged in AGENTS.md #6/#11; tables should be generated, not hand-written. |
| 9 | Coordinator routing gaps + skills-in-agent-table | M | `coordinator.md` | AGENTS.md #5; also phantom `opensource-forker` (#8). |
| 10 | Loop block-list narration-enforced | M | loop-operator / hooks | Audit item 19; needs a hook + sandbox preset. |
| 11 | MCP templates unpinned (`npx -y @latest`) | M | `templates/mcp/mcp-settings.json` | Task 014. |
| 12 | v2.0 asset test suites are existence-flavored | M | tests/test_{modes,mcp,checkpoint,spec_driven}.py | Task 012. |
| 13 | Release pipeline never exercised | M | release.yml | Risk retires on first successful tag publish. |
| 14 | i18n READMEs drift silently | L | `i18n/` | No CI check that translations track README; decide policy. |
| 15 | `gitOps.md` camelCase filename | L | `.claude/agents/` | Standardize during 008 (breaking rename). |
| 16 | refactor-cleaner self-commits | L | `refactor-cleaner.md` | Violates only-GitOps-commits rule (AGENTS_KNOWN_ISSUES.md #13). |
| 17 | docs/AGENTS.md depth gap (13 deep / 15 shallow) | L | docs/ | Generate specialist sections from frontmatter. |
| 18 | No example CONSTITUTION.md in examples/ | L | examples/ | Guide + template exist; add filled examples. |
| 19 | Local artifacts in tree (.coverage, cache dirs, hook logs) | L | repo root, .claude/hooks/ | Verify .gitignore coverage; never commit logs (historic leak). |
| 20 | model-tension: Haiku verifier / Sonnet merge-verdict reviewers | L | frontmatter vs model-router rules | Decide and align (AGENTS_KNOWN_ISSUES.md #15). |
| 21 | Five commands over 200 lines | L | `.claude/commands/` | `refine` 464, `ship` 228, `gan-build` 227, `opensource` 222, `loop-start` 220 (`wc -l`, 2026-08-24; 7318 total). **Not a context win** — command *bodies* are outside the always-on floor; `check-context-floor.py` budgets only descriptions, at **4753/6000** chars. So the exit is readability + per-invocation cost, and framing it as context savings would breach hard rule 6. **`refine.md` is not extractable:** its bash blocks are fragments carrying `<TASK>`/`<N>`/`$iteration` with no loop wrapper (stated in `tests/test_delivery_contract_smoke.py`'s module docstring), so "extract the script" means *writing* one on a CI-facing path — a feature, not a refactor. Any cut to a shipped command is user-visible and owner-gated. |

**Adding debt:** every consciously-deferred fix gets a row here with an exit condition — that's the price of deferring.
