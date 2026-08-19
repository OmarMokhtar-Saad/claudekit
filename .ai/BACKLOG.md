# Backlog

Priority-ordered. Sources: `review/tasks/` (file-level specs — read them before starting), `review/FINAL-REPORT.md` §3 (top-100 list), AGENTS_KNOWN_ISSUES.md. Status date: 2026-07-08.

## P0 — blocked on owner

- [ ] **Tag v2.1.0 + PyPI publish** (recipe: [PLAYBOOK.md](PLAYBOOK.md)). Everything is staged.
- [ ] Decision: plugin packaging as primary channel (task 007) — approve/defer.
- [ ] Decision: consolidation merge list sign-off (task 008).
- [ ] **Decision 21 — Iron Law scope vs. this repo's own product** (`.ai/DECISIONS.md`, status OPEN).
  `ops-enforcement.sh:47` exempts `.claude/**` and `:50` exempts every `.md`, so the agent +
  command + skill corpus — this repo's actual deliverable — is outside the Iron Law; `:13`
  disables the hook entirely under `ECC_HOOK_PROFILE=minimal`, which `CLAUDE.md:11` instructs
  maintainers to keep set. Three options steelmanned in the memo.

## P0.5 — landed 2026-08-19, follow-ups from the reflection/review-discipline batch

Seven workstreams (21 ops) landed with 13 review rounds; every plan failed its first review.
These are the findings that were **ticketed rather than carried** at the stopping rule, plus
defects discovered during execution. See CHANGELOG `[Unreleased]` and the plans in
`.claude/plans/archive/`.

- [ ] **`hooks=19` is WRONG, not stale** — `scripts/gen-docs.py:55` globs `*.sh` only, so the two
  new `.claude/hooks/*.py` (`reflection.py`, `reflection-gate.py`) are invisible to the counter.
  The repo ships 21 hooks and documents 19. Fix: extend the glob to `*.py` (preferred), or render
  "19 shell hooks". Must go through the generator — hard rule 8 forbids hand-editing counts.
- [ ] **The validator does not bind the executor.** `operations-schema.json` sets
  `additionalProperties: false`, but `execute-json-ops.py` silently IGNORES unknown edit fields.
  A config `validate-config-json.py` REJECTS still executes — and if the unknown field carried
  intended semantics, the executor quietly does something else. Observed live 2026-08-19.
  This undermines the reviewer instruction "do not re-derive what the validator proves".
- [ ] **`add_after` does not guarantee a line break.** A `code_edit` `add_after` whose content
  lacks a leading `\n` is concatenated onto the anchor line. Hit live on `CLAUDE.md` (line grew to
  442 chars, the inserted bullet would have rendered inside the Tier 3 bullet). Dry-run cannot
  detect it. Fix: normalise in the executor, or add a validator GUARD.
- [ ] **Iron Law hook (option b)** — `agent_type` IS present in the `PreToolUse` payload on both
  the `--agent` and Task-tool paths (measured). Build the ALLOWLIST hook: permit
  `execute-json-ops.py` + a named read-only verb set for the implementer, reject everything else;
  reject shell metacharacters/wrappers before matching; match tokenised argv, not a prefix; reject
  `sed` if any token starts with `-i`; pass through when `agent_type` is absent. Spec in
  `plan-agent-tool-grants.md` Risks. This is what actually closes the interactive Iron Law hole.
- [ ] **Frontmatter/INVOCATION grant drift is only partly gated** — the new drift test covers the
  10 agents in the `--allowedTools` table; 19 others are ungated, several declaring `Write`+`Edit`+
  `Bash` (`tester`, `devops`, `database-architect`, `refactor-cleaner`, `tdd-guide`, `doc-updater`;
  `harness-optimizer`, `code-simplifier`, `build-error-resolver` declare `Edit`). `explore`,
  `security-scanner`, `silent-failure-hunter` declare `Bash` against documented read-only rows, and
  `planner` declares bare `Bash` against a validator-scoped row. INVOCATION.md's own "add a row
  before wiring a new agent" rule is already violated repo-wide.
- [ ] **Unseparated experiment arm** — whether the interactive path STRIPS a frontmatter tool
  specifier (H1) or ignores allow-rules for subagents entirely (H2) was not separated. Falsify by
  declaring bare `tools: ["Read","Bash"]` and re-running the same write probe. The shipped
  conclusion holds under both; only the mechanism is unresolved.
- [ ] **Approval-gate residuals** (`execute-json-ops.py`): `check_approval()` computes `recorded`
  before `_gate_applies()`, so a transient lookup fault refuses even ungated ad-hoc configs; the
  refusal message can name `slugs[0]` when the plan-document branch triggered gating, pointing at a
  slug with no plan; and the `ECC_OPS_GATE_ALL=1` default-flip migration exists only as prose with
  no test and no CI job, so nothing fails if it is forgotten and the gate stays heuristic forever.
- [ ] **Reflection residuals**: the credential guard still passes single-case 20–31 char chunks and
  underscore-bearing secrets (disclosed in its docstring); `_MUTATING_SHELL` does not match output
  redirection (`cat > f`, `> f`), `python3 -c "open(...,'w')"`, or `dd`; and
  `knowledge-ledger.py:271`'s write gate still fires only at the Verifier PASS checkpoint, which
  the token policy says never auto-runs — so the learning store is unreachable in the common path.
- [ ] **Review-discipline residuals**: `_shared/VERIFICATION_PROTOCOL.md:56` and
  `skills/verification-before-completion/SKILL.md:86` carry an identical copy of the refutation
  paragraph (pre-existing); and the finding-class ratchet has no cross-session counter, so it only
  binds once task 010 consumes it.
- [ ] **Seed the recurrence table with the classes this batch proved** (`.ai/REVIEW_GUIDE.md`):
  `fix-introduces-larger-hole` (WS-3 Phase 0 refuse-all → blind-to-new-files; WS-2 hook-conflict fix
  → symlink source-write bypass), `guard-cannot-express-guarded-case` (WS-3 `CANNOT REVIEW` absent
  from the verdict enum; path (d) absent from the `Revision:` header), and `count-asserted-not-derived`
  (WS-6 lane totals, twice). Each is at or past the three-entry threshold that earns a mechanical check.

## P1 — high value, unblocked

- [ ] Fix QUICK_START table drift vs frontmatter (issue #6) and the phantom `opensource-forker` references (#8).
- [ ] Task 008 prep (no deletions yet): draft the migration table for owner review.
- [ ] Task 010 eval framework skeleton: `evals/` + one fixture repo + golden ops.json for planner + `ck eval` stub.
- [ ] **Task 015 E2E pipeline flow tests** (`review/tasks/015-e2e-pipeline-flow-tests.md`, written
  2026-08-19): 41 cases in 9 groups covering plan→review→implement→verify end to end — approval-gate
  matrix, hook-profile matrix, Iron Law characterization, lifecycle gates, failure/recovery,
  isolation, delivery contract, both spawn mechanisms. Lane split is explicit: 36 deterministic
  (CI, no API) · 4 live-spawn (budget-capped opt-in via a new `flow` kind in `scripts/run-evals.py`)
  · 1 hybrid. Mutation proof enumerated for all 9 groups. Sits above 010 (per-agent evals) and 012
  (per-unit tests) as the composition layer; its implementation session additively touches
  `scripts/run-evals.py` and `evals/`, which task 010 also owns.
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
