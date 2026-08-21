# Backlog

Priority-ordered. Sources: `review/tasks/` (file-level specs — read them before starting), `review/FINAL-REPORT.md` §3 (top-100 list), AGENTS_KNOWN_ISSUES.md. Status date: 2026-07-08.

## P0 — blocked on owner

- [ ] **Tag v2.1.0 + PyPI publish** (recipe: [PLAYBOOK.md](PLAYBOOK.md)). Everything is staged.
- [ ] Decision: plugin packaging as primary channel (task 007) — approve/defer.
- [ ] Decision: consolidation merge list sign-off (task 008).
- [ ] **Decision 21 second half — do maintainers stop defaulting to `ECC_HOOK_PROFILE=minimal`?**
  Option A shipped 2026-08-19 (`.ai/DECISIONS.md` entry 21, commit `d878496`): `.ops-source-globs`
  makes `.claude/{agents,commands,skills,hooks,operations}/*` count as SOURCE in this checkout,
  provably inert for user projects. But it is **dormant under `minimal`**, which `CLAUDE.md:11`
  still tells maintainers to keep set, so the repo gets no dogfood signal yet. Flipping it means
  every prompt edit needs an ops.json — real friction on the highest-churn files, and the velocity
  cost lands on the owner. Pinned dormant by a test, so nothing flips by accident.
- [ ] **Fleet-sync the `TOKEN-MODEL-POLICY` v3 block to the 16 kitted projects.** The block now
  states routing in capability tiers instead of vendor model names (2026-08-21). The marker was
  bumped v2 → v3 precisely so the sync is not skipped as "already present"; until the sync runs,
  downstream copies still read vendor names. Owner decides when.
- [ ] **Push `perf/token-efficiency`?** 13 commits. The `TOKEN-MODEL-POLICY` marker went v1 → v2,
  so the per-PR review floor propagates to all 16 fleet-synced projects on their next sync.

## P0.7 — wave-2 adoption, blocked on the enforcement-runtime lane (2026-08-21)

Verdicts and reasoning: [RESEARCH.md](RESEARCH.md). These are **Retained — blocked**: both need a
durable typed event log and a single hook dispatcher per event, which the concurrent
enforcement-runtime lane owns. Do not start either before those land.

- [ ] **Mechanical Definition-of-Done at the `Stop` hook** (ChaosEngine `guard.py`, ~470 lines of
  stdlib Python). Block session end until verification, independent review, delivery status, and
  the learning loop are complete. Closes the gap `CLAUDE.md` currently admits ("Prompt-enforced
  until task 010 makes them mechanical"). **Depends on:** durable receipts to check against.
- [ ] **Failure-fingerprint circuit breaker** (ChaosEngine `reflection-checkpoints.md`). Two
  failures with *different* fingerprints → task reflection; two with the *same* fingerprint → deep
  reflection. Today `loop-operator` does this by prompt judgement, which is neither deterministic
  nor testable. **Depends on:** the hook dispatcher.
- [ ] **Record the first eval cassettes — BLOCKED ON QUOTA, not on a decision.** Attempted
  2026-08-21; the `claude` CLI here routes through `xpipe` and the available account had hit its
  weekly limit, so no recording was possible. The mechanism is complete and waiting: run
  `python3 scripts/run-evals.py --record` from a session with quota (4 evals, ~$0.2–1.5 each),
  then wire `--replay` into `.github/workflows/ci.yml` in the same change. `--inject` already gives
  CI-safe value with no recordings. Cassettes go stale if the corpus changes first, so record
  close to when CI is wired.
- [x] **Skill-description budget lowered 14000 → 9000 — CONFIRMED 2026-08-21.** A tightening
  alongside the fix that stopped charging for model-invisible skills. Real value 7,719 of 9,000.
- [ ] **Command invocation sites are the remaining vendor-name surface — 8 literals in 6 files**,
  not the 2 first recorded here: `review.md:89`, `refine.md:161,180`, `plan.md:67`,
  `gan-build.md:85`, `santa.md:64,68` (and `model-router.md:103`, since rewritten into a tier
  lookup). The three `--agent planner --model opus` sites auto-resolve against the planner's tier;
  the rest are recorded overrides. `santa.md`'s pair is legitimate and should stay — the
  santa-method deliberately uses two different models so neither reviewer anchors on the other.
  Not an oversight:
  `install.sh:203` copies only `.claude/operations/scripts/*.py` into user projects, so repo-root
  `scripts/gen-model-policy.py` does not exist where those commands run and cannot resolve a tier.
  Pinned against drift by `test_plan_command_spawns_planner_on_the_planner_tier`, which derives the
  expected literal from the table. **Decision needed:** either ship a resolver under
  `.claude/operations/scripts/` (installed, so callable downstream) or accept the literal and keep
  the pin. Do not "fix" it by hand-editing the command files.
- [ ] **`CLAUDE.md` headroom is improved but not solved: 30,508 of 31,000** (was 30,992 of 31,000).
  Bought 2026-08-21 by deleting stale hand-written counts, which was a drift surface hard rule 8
  forbids anyway. That is ~123 chars of future text. **The budget was deliberately not raised** —
  `check-context-floor.py` offers that escape with owner sign-off, but raising a ceiling because a
  file is near it is how a gate stops meaning anything. The structural fix is the one the script's
  own comment names: move content into the agents that consume it, since CLAUDE.md is charged ×4
  (main context + 3 pipeline subagent injections). Candidates: the blast-radius tiering block and
  parts of "How to work" that only the pipeline agents act on.
- [ ] **Add `gen-model-policy.py` to `iron-law-gate.py`'s `_CHECK_ONLY_SCRIPTS`** (one line, at
  `.claude/hooks/iron-law-gate.py:265`). Until then the implementer agent cannot run the new DoD
  gate — maintainers and CI can. Deliberately left to the lane that owns `.claude/hooks/**`.

## P0.5 — landed 2026-08-19, follow-ups from the reflection/review-discipline batch

Seven workstreams (21 ops) landed with 13 review rounds; every plan failed its first review.
These are the findings that were **ticketed rather than carried** at the stopping rule, plus
defects discovered during execution. See CHANGELOG `[Unreleased]` and the plans in
`.claude/plans/archive/`.

- [ ] **`hooks=19` is WRONG, not stale** — `scripts/gen-docs.py:55` globs `*.sh` only, so the two
  new `.claude/hooks/*.py` (`reflection.py`, `reflection-gate.py`) are invisible to the counter.
  The repo ships 21 hooks and documents 19. Fix: extend the glob to `*.py` (preferred), or render
  "19 shell hooks". Must go through the generator — hard rule 8 forbids hand-editing counts.
- [ ] **`ledger_dir()` falls back to a host-shared temp dir** (`.claude/hooks/reflection.py:189-195`).
  When `CLAUDEKIT_REFLECTION_DIR` is unset or non-absolute it uses `$TMPDIR/claudekit-reflection`,
  shared across every session and every project on the machine. Test-side isolation landed (each test
  gets its own ledger root), but that is containment, not a cure — the product still defaults to a
  shared location keyed only by `sha256(session_id)[:32]`. Fix in the hook: use a per-invocation
  subdirectory, or refuse to operate without an explicit ledger root. Note this fallback is the most
  likely origin of a "flaky CLI test" reported 2026-08-19 that no in-process reproduction could
  produce — an ambient `CLAUDEKIT_REFLECTION_DIR` in a live session, misattributed to the test.
- [ ] **UNEXPLAINED intermittent: `test_receipt_via_json_stdin_clears_the_checkpoint`**
  (`tests/test_reflection_ledger.py:388`). Observed 2026-08-21 on `perf/token-efficiency` at
  `7f25746`: one full-suite run failed at `:399` — `assert ref.pending_checkpoint(SESSION) is None`
  — with the CLI itself exiting 0. It did **not** reproduce standalone, running the whole file,
  pairing with `test_pipeline_e2e.py` or `test_reflection_gate.py`, or on an immediate second full
  run (1,646 passed). **No cause is claimed.** The obvious hypothesis — that this test's
  `dict(os.environ)` picks up an ambient ledger — was checked and **ruled out**: `TestCli.run`
  documents at `:341` that `os.environ` already carries the per-test ledger from the
  `reflection_env` fixture, `ref` depends on that fixture, and propagating the scoped values into
  the child is deliberate. The env is scoped; a live session's hook should not be able to reach
  that ledger. Do not close this by asserting the entry above is the explanation — that link is
  unproven. THIRD sighting 2026-08-21 at `64088a5`: one failure in a fresh process at the same
  assertion, then two consecutive clean full runs (1,646 passed each). That run's output was
  redirected to /dev/null and the evidence was LOST - precisely the mistake this item exists
  to prevent. **Capture is now in place** (`receipt_diagnostic()`,
  `tests/test_reflection_ledger.py`): on failure the assertion message carries the ledger
  dir, the resolved ledger path and its raw bytes, the `CLAUDEKIT_REFLECTION_DIR` the CHILD
  process received, the inbox path, the derived active entries, the returned checkpoint, and
  the CLI's returncode/stdout/stderr. Note there is no separate checkpoint file: the
  checkpoint is a pure reduction over the ledger JSONL, so the ledger bytes ARE the
  "checkpoint contents" this entry asked for. **Still no cause is claimed**; no retry was
  added and the assertion itself is unchanged. Do not close this until a CAPTURED failure
  explains it.
- [ ] **Triage `review/code-review.md` — 76 unfixed P2/P3 findings, and one of them just cost real
  damage.** The ops engine's mode-stripping bug was documented there at `:286` as a P2 **with its fix
  already written out** ("Copy the original mode … before replace"), and left unfixed until it
  silently shipped `.claude/hooks/ops-enforcement.sh` and `scripts/gen-docs.py` as 100755 => 100644 in
  `d878496` and took `install.sh` to 0600 in `749e34d`. It was caught only by an incidental
  `git log --diff-filter=M --summary` audit. Two more from the same block are live: `ExecutionLock`
  is not a real lock on Windows (`O_CREAT|O_TRUNC` always succeeds) and `release()` unlinks the lock
  file even if another process now holds it; and the validator checks `find` patterns against the
  ORIGINAL file while the executor applies edits sequentially. That last one is a **second confirmed
  instance** of the class below — two entries, one short of the ratchet's three-entry threshold.
  A stack of known defects with known fixes is worth more attention than the next feature.
- [ ] **The validator does not bind the executor.** `operations-schema.json` sets
  `additionalProperties: false`, but `execute-json-ops.py` silently IGNORES unknown edit fields.
  A config `validate-config-json.py` REJECTS still executes — and if the unknown field carried
  intended semantics, the executor quietly does something else. Observed live 2026-08-19.
  This undermines the reviewer instruction "do not re-derive what the validator proves".
- [ ] **`add_after` does not guarantee a line break.** A `code_edit` `add_after` whose content
  lacks a leading `\n` is concatenated onto the anchor line. Hit live on `CLAUDE.md` (line grew to
  442 chars, the inserted bullet would have rendered inside the Tier 3 bullet). Dry-run cannot
  detect it. Fix: normalise in the executor, or add a validator GUARD.
- [x] **Iron Law hook (option b) — DONE 2026-08-20**, `.claude/hooks/iron-law-gate.py`. The
  interactive Iron Law is now harness-enforced, not prompt-enforced. Took five review rounds,
  each finding a distinct live bypass, and one owner-authorised architectural rework: flags are
  **default-deny** rather than denylisted, because enumerating forbidden flags never converged
  (`pytest --log-file/-o/-c/--override-ini`, then `ruff --add-noqa`/`pytest --debug`, then
  `mypy --install-types`/`@argfile`). Positionals are checked too — `git remote add origin <url>`
  mutates through arguments and survived three rounds of flag auditing. Residual, stated in R7
  and the hook header: the SAFE tables are audited enumerations of permitted arguments, and
  `pytest` executes `conftest.py`.
- [ ] **Two follow-ups from the hook's final review** — `redact()` inherits
  `reflection.looks_like_credential`'s disclosed blind spot (single-case non-hex secrets of
  20–31 chars, or ones containing `_`, passed as a positional or under a non-keyword flag, reach
  stderr but not the log); and relative positionals are checked textually (`..`, `~`, `isabs`)
  rather than realpath'd, so a relative symlink inside the repo pointing outside it is readable
  via an inert verb. Both read-only, and the implementer already holds `Read`.
- [ ] **Frontmatter/INVOCATION grant drift is only partly gated** — the new drift test covers the
  10 agents in the `--allowedTools` table; 19 others are ungated, several declaring `Write`+`Edit`+
  `Bash` (`tester`, `devops`, `database-architect`, `refactor-cleaner`, `tdd-guide`, `doc-updater`;
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

## P0.75 — harness findings, 2026-08-20 (from the plan-doctor-gate batch)

Two findings about the harness rather than the product. Neither is fixed; both imply owner-gated
asset changes, so they are recorded as options with trade-offs.

- [ ] **The `reviewer` agent cannot execute, so plan reviews are structurally static.**
  `.claude/agents/reviewer.md` grants Read, Grep, Glob — no Bash. Across three review rounds of
  plan-doctor-gate the reviewer was twice asked to clone the repo, run `execute-json-ops.py` and
  run the six DoD commands; it correctly reported it could not, and verified by reading instead.
  Consequence: no test in that plan was executed by any reviewer, the plan's "pre-verified during
  planning" claims were planner self-reports, and the post-execution DoD run was the first real
  execution. Why it matters: in that same batch **three of the four defects found were introduced
  by fixes to earlier findings** — round 1's fix leaked this repo's commands onto the installer's
  failure path; round 2's fix for that added an `exit 1` that skipped `_cleanup_on_failure` and
  would have littered `.claude.staging.<pid>` into user projects; round 3 found a `jsonschema` test
  stub that was inert in CI and fake-green exactly where `test_gate_scope.py` skips. And
  `.ai/REVIEW_GUIDE.md` asks reviewers to prove a check binds by MUTATING the shipped artifact and
  reading the failure — which a Read/Grep/Glob agent cannot do, so the guide asks for something its
  addressee cannot perform. Options, undecided: **(a)** grant the reviewer scoped Bash — this
  collides with the Iron Law / tool-grant work, and `tests/test_agent_tool_grant_drift.py`
  established that a frontmatter-declared `Bash(...)` specifier is NOT applied on the interactive
  path, so a "scoped" grant may silently become unscoped Bash on the review agent, which is the
  security tension and the reason this is not a free win; **(b)** keep the reviewer read-only and
  add a separate execute-capable verification step that applies ops in a throwaway clone;
  **(c)** leave as-is and require the orchestrator to run mutants, documenting in the guide that
  plan reviews are static.
- [ ] **`ops-enforcement.sh:43`'s exemption list is broad and worth revisiting.** It exempts
  `/private/tmp/claude-*`, `/tmp/claude-*`, `/private/var/folders/*` and `/var/folders/*`; anything
  placed under those prefixes — a fixture, a scratch file, or an entire repo clone — has
  enforcement silently disabled. Recorded, not proposed: narrowing it is owner-gated and could
  break the AppiumLens field fix the comment at `ops-enforcement.sh:38-41` cites as the reason the
  exemption exists. The reviewing lesson (verify clone/fixture location; expected exit 2 arriving
  as exit 0 is the tell) is generalised in `.ai/REVIEW_GUIDE.md` beside the hook checklist.
- [ ] **CI lints a narrower surface than the DoD command claims.** `CLAUDE.md:17` documents the gate
  as `ruff check src/ tests/ scripts/`, but `.github/workflows/ci.yml:63` runs
  `ruff check src/claudekit scripts` — `tests/` is never linted in CI. Measured 2026-08-20. A style
  defect in a test file is caught only if a maintainer runs the DoD command locally. Decide whether
  CI should widen to match the documented gate, or the doc should narrow to match CI; they should
  not disagree silently.
- [ ] **`E302`/`W391` are preview-gated, so they enforce nothing.** Under this repo's
  `select = ["E","F","W","I"]` (`pyproject.toml:51`), ruff reports *"Selection `E302` has no effect
  because preview is not enabled"* and passes. Measured 2026-08-20 while reviewing a plan whose
  `add_after` payload produced one blank line before a class instead of two: the defect was real,
  the mechanism that was supposed to catch it does not exist. `W292` (missing final newline) IS
  non-preview and does bind, so the gap is specific to the blank-line rules.

## P1 — high value, unblocked

- [ ] **`AGENTS.md` is a mechanical `.claude` -> `.Codex` sed of `CLAUDE.md`, and most of it is
  wrong.** Found 2026-08-21 by the reviewer of `plan-remove-codex-mirror` (my own grep missed
  it: I searched case-sensitively for `.codex` and the file writes `.Codex`). The sed also
  rewrote prose it should not have: PyPI name reads **`Codex-kit`** (it is `claude-kit`),
  the tagline reads "orchestration kit for Codex", and `.Codex/local/Codex.template.md`
  should be `CLAUDE.template.md`. Counts are stale too: it claims `29 agents · 42 commands · 75 skills` and
  `19 hooks`, against `python3 scripts/gen-docs.py --check` measured 2026-08-21 ->
  `Counts: agents=29 commands=42 skills=76 hooks=21`. Skills and hooks are both wrong;
  AGENTS.md is not generator-owned, which is why nothing caught it. **Three of its four `.Codex/` paths already did not exist**
  before the `.codex/` removal (`settings.local.json`, `agents/_shared/INVOCATION.md`,
  `operations/scripts/shared.py`); only `.Codex/hooks/*.sh` resolved, and only because
  macOS is case-insensitive. That one line was fixed in the removal batch because the
  deletion would have made its shellcheck glob silently match zero files; the rest is
  pre-existing decay in the file other tools read as their instruction standard, and it
  needs its own pass. Same class applies to `.agents/skills/*/SKILL.md`, which carry ~100
  `.Codex/...` paths pointing at a layout that never fully existed.

- [x] **RESOLVED 2026-08-21 by removing `.codex/` entirely (owner-approved; DECISIONS.md 22).**
  Filed the same day as a P1 drift item, then resolved by deletion rather than by the gate the
  entry proposed — investigating it found the mirror was unshipped, unreferenced, self-disabled
  and machine-specific, so gating it would have bought maintenance of a copy nobody consumed.
  **One correction I owe on the original entry: I called the drift "security-relevant", and that
  was wrong.** `.codex/config.toml` set `ECC_HOOK_PROFILE=minimal`, under which the enforcement
  hooks it wired stood down entirely — and the specific file I cited, `format-typecheck.sh`, is
  strict-only, so it could not have run there under any profile. I wrote the claim without
  checking the config next to the file. The drift was real; the security framing was mine and
  unfounded, and hard rule 6 applies to my own findings, not just the product's docs.
  **The durable lesson, which survives the deletion:** a hand-maintained mirror with no gate
  drifts silently — measured at 8 stale shell hooks and three weeks — and the right question was
  "should this exist" before "how do we gate it".

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

- [x] **Corpus-wide `disable-model-invocation` vs loader-instruction contradiction — RESOLVED
  2026-08-21** (`plan-skill-loading-contract`). Measured, not estimated: 15 of the 33 flagged
  skills were declared loads (8 mandatory, 7 on-demand), all un-flagged after a per-skill decision;
  `tests/test_skill_loading_contract.py` prevents recurrence. The 18 flagged-but-never-declared
  skills are correctly left alone. Superseded description below.
- [ ] ~~**Corpus-wide `disable-model-invocation` vs loader-instruction contradiction**~~ — ~30 skills carry the flag while agent/command prompts instruct agents to load them (found 2026-08-09 while fixing `using-git-worktrees`; that one skill was fixed, rest untouched). Resolve together with task 009, which *prescribes* the flag for niche skills to cut the routing tax — needs a per-skill decision: un-flag it or delete the loader instruction. Note: the worktree work added +1 skill/+1 command/1 un-flagged skill to the routing surface (accepted cost, recorded in plan-worktree-multi-agent.md).
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
