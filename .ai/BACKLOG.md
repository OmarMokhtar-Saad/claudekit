# Backlog

Priority-ordered. Sources: `review/tasks/` (file-level specs — read them before starting), `review/FINAL-REPORT.md` §3 (top-100 list), AGENTS.md Known Issues. Status date: 2026-07-08.

## P0 — blocked on owner

- [ ] **Tag v2.1.0 + PyPI publish** (recipe: [PLAYBOOK.md](PLAYBOOK.md)). Everything is staged.
- [ ] Decision: plugin packaging as primary channel (task 007) — approve/defer.
- [ ] Decision: consolidation merge list sign-off (task 008).

## P1 — high value, unblocked

- [ ] **Fix `_shared/WORKFLOW_FILE_TEMPLATES.md` legacy ops schema** (AGENTS.md issue #9) — actively harmful: agents following it produce validator-rejected configs. Small, surgical.
- [ ] Fix QUICK_START table drift vs frontmatter (issue #6) and the phantom `opensource-forker` references (#8).
- [ ] Task 008 prep (no deletions yet): draft the migration table for owner review.
- [ ] Task 010 eval framework skeleton: `evals/` + one fixture repo + golden ops.json for planner + `ck eval` stub.
- [ ] Task 012: behavioral upgrades for `test_modes/test_mcp/test_checkpoint/test_spec_driven` (currently existence-flavored).

## P2 — important, larger

- [ ] Task 009 context budget: one hook dispatcher per event; ≤2 mandatory skill loads; stop registry double-loading.
- [ ] Task 007 plugin packaging (after owner yes): `.claude-plugin/plugin.json`, marketplace.json, install-path parity tests.
- [ ] Task 014 supply chain: SHA256SUMS + Sigstore on releases; pin MCP template server versions (drop `npx -y @latest`); default filesystem MCP read-only.
- [ ] Task 013 OSS health: CODE_OF_CONDUCT, CODEOWNERS, issue labels, demo GIF, MkDocs site.
- [ ] `ck update` true three-way merge (unchanged→replace, modified→keep+`.new`, removed→prompt).
- [ ] Hook-enforced autonomous-loop block-list (audit item 19) + sandbox profile presets.

## P3 — polish & smaller fixes (from AGENTS.md Known Issues + audit)

- [ ] INVOCATION.md `--allowedTools` rows for all 28 agents (only planner/reviewer covered; planner row contradicts frontmatter — issue #11).
- [ ] reviewer `--dual` cannot spawn with its toolset (#12) — fix tools or drop the flag.
- [ ] refactor-cleaner commits directly, violating "only GitOps commits" (#13).
- [ ] Coordinator routing gaps: tester/devops/database-architect/documenter unreachable by keyword (#5); skills mixed into the agent routing table.
- [ ] Missing Mandatory-Skill/handoff sections in 9 newer agents (#14); single-example frontmatter in 5 (#14).
- [ ] Model-tension pass: Haiku verifier and Sonnet language-reviewers vs model-router's own "merge verdicts → Opus" rule (#15).
- [ ] `gitOps.md` casing anomaly (#7) — decide and standardize (breaking rename; do during 008).
- [ ] Generate `docs/AGENTS.md` specialist sections from frontmatter via gen-docs.
- [ ] Example CONSTITUTION.md files for the two example projects (guide+template exist, no filled examples).
- [ ] `ck lint` for consumer-authored assets; `ck new <asset>` scaffolder.

## Icebox

Windows support · MCP server for the ops engine · `ck cost`/`ck trace` observability · team features · README translations refresh policy (i18n/ currently drifts silently — no CI check).
