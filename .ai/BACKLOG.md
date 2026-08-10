# Backlog

Priority-ordered. Sources: `review/tasks/` (file-level specs — read them before starting), `review/FINAL-REPORT.md` §3 (top-100 list), AGENTS_KNOWN_ISSUES.md. Status date: 2026-07-08.

## P0 — blocked on owner

- [ ] **Tag v2.1.0 + PyPI publish** (recipe: [PLAYBOOK.md](PLAYBOOK.md)). Everything is staged.
- [ ] Decision: plugin packaging as primary channel (task 007) — approve/defer.
- [ ] Decision: consolidation merge list sign-off (task 008).

## P1 — high value, unblocked

- [ ] Fix QUICK_START table drift vs frontmatter (issue #6) and the phantom `opensource-forker` references (#8).
- [ ] Task 008 prep (no deletions yet): draft the migration table for owner review.
- [ ] Task 010 eval framework skeleton: `evals/` + one fixture repo + golden ops.json for planner + `ck eval` stub.
- [ ] Task 012: behavioral upgrades for `test_modes/test_mcp/test_checkpoint/test_spec_driven` (currently existence-flavored).

## P2 — important, larger

- [ ] **Corpus-wide `disable-model-invocation` vs loader-instruction contradiction** — ~30 skills carry the flag while agent/command prompts instruct agents to load them (found 2026-08-09 while fixing `using-git-worktrees`; that one skill was fixed, rest untouched). Resolve together with task 009, which *prescribes* the flag for niche skills to cut the routing tax — needs a per-skill decision: un-flag it or delete the loader instruction. Note: the worktree work added +1 skill/+1 command/1 un-flagged skill to the routing surface (accepted cost, recorded in plan-worktree-multi-agent.md).
- [ ] `ck doctor`: consider adding `worktree-manager.py` to the ops-script manifest check (reviewer note, plan-worktree-multi-agent.md).

- [ ] Task 009 context budget: one hook dispatcher per event; ≤2 mandatory skill loads; stop registry double-loading.
- [ ] Task 007 plugin packaging (after owner yes): `.claude-plugin/plugin.json`, marketplace.json, install-path parity tests.
- [ ] Task 014 supply chain: SHA256SUMS + Sigstore on releases; pin MCP template server versions (drop `npx -y @latest`); default filesystem MCP read-only.
- [ ] Task 013 OSS health: CODE_OF_CONDUCT, CODEOWNERS, issue labels, demo GIF, MkDocs site.
- [ ] `ck update` true three-way merge (unchanged→replace, modified→keep+`.new`, removed→prompt).
- [ ] **`settings.local.json` must not be manifest-managed** — `ck update` overwrites per-project permission allowlists/MCP config with the kit's copy, contradicting its own "local, per-developer, never shipped" framing; the 2026-07-31 fleet rollout had to hand-preserve it in all 17 projects. Fix: exclude from the manifest (or treat as always-keep-local in update).
- [ ] Hook-enforced autonomous-loop block-list (audit item 19) + sandbox profile presets.

## P3 — polish & smaller fixes (from AGENTS_KNOWN_ISSUES.md + audit)
- [ ] **Multi-interpreter validator resolution** — the hooks' `python3 -m claudekit.security`
  fallback only works for whichever python3 wins PATH in that session; on a multi-Python
  machine (3.9 system + 3.12 python.org + 3.14 Homebrew, seen 2026-08-03) sessions hit the
  rc-127 warn path and prompt users to pip-install. Field fix applied: claude-kit user-site
  installed into all three interpreters. Kit fix candidates: `ck doctor` check for "importable
  under every python3 on PATH", or hooks probing `command -v python3 python3.12 python3.13`;
  document the PEP-668 `--user --break-system-packages` recipe for Homebrew pythons.
- [ ] **Issue-ledger hygiene** — fold `python3 .claude/operations/scripts/knowledge-ledger.py prune`
  into this same periodic sweep: it exits 1 and lists entries in `.claude/knowledge/issues/`
  whose referenced files are all gone; `--apply` moves them to `issues/archive/`. Also
  re-validate any entry older than the last large refactor. No separate mechanism, same cadence.

- [ ] Stale test-count references across 7 `.ai/*`+`CLAUDE.md` files ("516 tests"; actual 638 as of 2026-07-31 and still moving) — sweep once plan-remaining-fixes items are all landed, counts change again with each.
- [ ] Consolidate the duplicate CI shellcheck jobs (`ci.yml` `shellcheck` job vs `security.yml` "Validate shell scripts" step — byte-identical intent, run twice per push).
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

Cross-project promotion of `.claude/knowledge/issues/` entries into the global
`~/.claude/skills/learned/` tier — explicitly out of scope for ledger v1 (project-local only);
needs a redaction story and a per-project provenance field before it can be considered.

Windows support · MCP server for the ops engine · `ck cost`/`ck trace` observability · team features · README translations refresh policy (i18n/ currently drifts silently — no CI check).
