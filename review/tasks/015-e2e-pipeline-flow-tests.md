# Task 015 — End-to-End Pipeline Flow Tests

## Problem
Every stage of the pipeline is tested in isolation and the *flow* is tested nowhere. `tests/` proves a hook exits 2 for a crafted payload, that `validate-config-json.py` rejects a 4th delete, that the wheel installs — but nothing proves that **plan -> review -> implement -> verify** holds together as one enforced sequence. Concretely:

1. **No composed-flow coverage.** `review-record.py` binds a verdict to `sha256(ops.json)` and `execute-json-ops.py` applies operations, but no test drives plan -> record -> execute -> rollback as a single transaction over a fixture repo. Every integration seam (plan file naming, `extract-json-from-plan.py` handoff, record resolution from a plan path, backup manifest -> `restore-backup.py --post`) is covered only by the stage that owns one end of it.
2. **Zero dogfood signal on the enforcement layer.** This repo develops with `ECC_HOOK_PROFILE=minimal` in a gitignored `.claude/settings.local.json` (CLAUDE.md "Session setup gotcha"), so the hooks that define the product — `ops-enforcement.sh`, `file-guard-gate.sh`, `config-protection.sh` — are *off* for every maintainer session. `test_hooks_behavioral.py` runs individual hooks with forced env; nothing asserts the wired `.claude/settings.json` matcher set actually engages under `standard` and is genuinely inert under `minimal`.
3. **The Iron Law is asserted in prose, not in a test of the pair.** No test shows the same edit being *blocked* on the Edit path and *succeeding* on the ops path. The `.md` and `.claude/**` exemptions in `ops-enforcement.sh` (lines ~45–50) are unasserted in either direction, and whether those exemptions are right for THIS repo — where prompts and skills *are* the product — is an open owner decision (WS-5 decision memo). Untested + undecided is the worst combination: a future "fix" changes behavior with nothing to notice.
4. **Approval gating is advisory.** `/implement` says "review score >= 90 or explicit user override" in prose; `review-record.py` has the exit codes (2 drift / 3 no record / 4 unauthorised verdict) but is not proven to be on the execution path. The WS-1 workstream moves this gate *into* `execute-json-ops.py`; that enforced behavior needs a matrix, not a smoke test.
5. **Failure/recovery is single-shot.** Rollback is tested as a function call; not as "SIGINT lands mid-batch, the tree is consistent, forward recovery from the post/ snapshot works."
6. **The delivery contract has no regression guard.** The measured 80.3M-token burn (`.claude/plans/plan-token-waste-workflow-fixes.md`) came from handoffs reprinting plan/ops payloads. INVOCATION.md now forbids it; nothing tests it.

## Root Cause
Testing followed the module boundaries instead of the product's control flow. Each artifact had an owner who tested their unit; the pipeline itself is an emergent property of prompts + hooks + scripts and has no owner, so it got no suite. Compounding it: the only end-to-end evidence on record is the single manual 2026-07-08 run logged in INVOCATION.md (~$1.86, one task, one path) — an anecdote treated as coverage.

## Relationship to tasks 010 and 012 (do not duplicate)
- **Task 010 (eval framework)** asserts *one agent's* behavior per eval — does the planner emit a valid ops.json, does the reviewer refute. It owns `evals/definitions/*.json` and `scripts/run-evals.py`. This task owns the *composition*: multi-stage flows where the artifact of stage N is the input and the gate of stage N+1. Task 015 extends the existing harness with a `flow` eval kind rather than building a second runner.
- **Task 012 (behavioral upgrade)** upgrades per-unit tests inside `tests/`. This task adds exactly one new pytest module family (`tests/test_pipeline_e2e.py` + fixtures) for the deterministic lane and never edits task 012's files.
- Rule of thumb: if a case can be decided without a model, it belongs here in pytest; if it needs a model to *produce* the artifact, it belongs here as a `run-evals.py` flow definition; if it judges a single agent's prompt quality, it is task 010's.

## Files
- New: `tests/test_pipeline_e2e.py` — the deterministic lane (LANE A cases below).
- New: `tests/fixtures/pipeline/` — a minimal fixture repo (source file with a stable anchor, a passing pytest, `.claude/` with settings.json + hooks + operations scripts copied from the tree, a seeded plan.md + ops.json pair, a pre-built review record).
- New: `tests/conftest.py` additions (fixture-repo factory: tempdir copy, `ECC_HOOK_PROFILE` parametrization, git init so worktree cases work).
- New: `evals/definitions/flow-*.json` (LANE B cases) + `evals/fixtures/pipeline/` — reuses `scripts/run-evals.py`.
- `scripts/run-evals.py` — add a `flow` kind: ordered multi-spawn definitions (stages array), stage-scoped `allowed_tools`, per-stage checks, plus check types `exit_code`, `file_absent`, `record_state`, `payload_absent`.
- New: `.github/workflows/e2e.yml` — LANE A only, per-PR (no API key). LANE B stays opt-in/manual + nightly with a budget cap.
- `.ai/TESTING_GUIDE.md` — test-map row + the lane distinction.
- `docs/` + CHANGELOG `[Unreleased]` on landing.

## Dependencies (blocking, name them in the PR)
- **WS-1** (approval gate moved into `execute-json-ops.py`): LANE A group B is written against the *enforced* behavior. Until WS-1 lands, group B cases must be marked `xfail(strict=True)` with the WS-1 reference — never skipped, never `|| true`.
- **WS-2** (lifecycle gates: reflection checkpoint, Stop-hook interrupt-once, PreCompact duty survival): group E has no subject until WS-2 lands; same `xfail(strict=True)` discipline.
- **WS-5** decision memo (are the `.md` / `.claude/**` ops-enforcement exemptions correct for this repo): group D's exemption cases are **characterization tests** — they record what the hook does today and say so in the docstring. They must not be read as endorsement, and the memo's outcome will rewrite them.
- Task 010's harness exists (it does: `scripts/run-evals.py`, 4 definitions) — LANE B extends it, does not fork it.

## Priority
**P1.** Nothing else in the queue can prove a change to the enforcement layer did not break the product's central promise. Prerequisite for the consolidation work (008) that will move hook and agent files around.

## Estimated Time
LANE A: 4–6 days (fixture factory is the bulk). LANE B: 2–3 days on top, plus a first budgeted run. `flow` kind in the runner: 1 day.

## Risk
Medium.
- *Fixture drift:* a fixture `.claude/` copied from the tree goes stale. Mitigation: build the fixture by *copying the live tree's* hooks/operations at test time (not a vendored snapshot), and assert the copy's file count against the manifest.
- *Hook tests are environment-sensitive:* macOS bash 3.2 vs CI ubuntu. Mitigation: subprocess with explicit `env=`, never inherit; the macOS CI lane is the referee (TESTING_GUIDE rule 4).
- *LANE B cost and nondeterminism:* ~$1.5–3 per flow (the 2026-07-08 run was $1.86 for one pass). Mitigation: per-run budget cap in the runner, N-of-M pass thresholds, assertions on machine-checkable properties only (exit codes, file existence, record state, schema validity) — never on model prose.
- *False confidence:* an E2E suite that mocks the model is not an E2E suite. The lane split is the mitigation; a LANE A case must never claim to cover agent behavior.

---

## Test case catalogue

**Lane legend.** **A = deterministic** (pytest, no model, no network, runs per-PR in CI). **B = live** (real `claude -p` spawns, real API spend, opt-in/nightly lane, budget-capped, N-of-M thresholds).

Every case states: **Pre** (preconditions) · **Cmd** (exact command) · **Assert** (observable outcome) · **Fails as** (the failure signature the case is designed to catch).

### Group A — Pipeline happy path

**E2E-01 — plan artifacts land and validate (A)**
- Pre: fixture repo; a seeded `plan.md` + matching `ops.json` (fixture, not model-produced).
- Cmd: `python3 .claude/operations/scripts/extract-json-from-plan.py .claude/plans/plan-fixture.md` then `python3 .claude/operations/scripts/validate-config-json.py <extracted>`.
- Assert: extractor exit 0 and writes the ops file; validator exit 0.
- Fails as: extractor/validator schema drift (the schema-split class of bug) — non-zero exit, or an ops file the validator rejects.

**E2E-02 — review record binds the verdict to the exact ops.json (A)**
- Pre: E2E-01 artifacts.
- Cmd: `review-record.py write plan-fixture.md ops.json --score 95 --decision APPROVED` then `review-record.py check plan-fixture.md ops.json`.
- Assert: write exit 0, record file under `.claude/reports/reviews/`; check exit 0; the record contains `sha256(ops.json)` equal to the file's real digest (computed in the test).
- Fails as: record written against a path/name rather than content — digest mismatch, or check passes on a mutated file.

**E2E-03 — implement applies the ops and verify observes the result (A)**
- Pre: E2E-02 approved record.
- Cmd: `execute-json-ops.py ops.json` then the fixture's own `python3 -m pytest -q`.
- Assert: executor exit 0; target file contains the post-state text; backup dir created with a manifest listing modified + created files; fixture suite exits 0.
- Fails as: silent partial application (executor exit 0 with unchanged target), or missing backup manifest.

**E2E-04 — full live pipeline over a fixture task (B)**
- Pre: API key; `evals/fixtures/pipeline`; budget cap set.
- Cmd: `python3 scripts/run-evals.py --only flow-full-pipeline`.
- Assert (per stage, machine-checkable only): planner stage produces a `plan-*.md` and an ops file that passes the validator; reviewer stage emits a parseable `=== REVIEW ===` block whose `SCORE:`/`DECISION:` `review-record.py write --from-review` accepts; implementer stage's transcript contains **no** `Edit`/`Write` tool call and the target file changed; verifier stage's verdict matches seeded ground truth (fixture seeded to fail -> verdict must not be a pass).
- Fails as: any stage returning an artifact the next stage cannot consume — the integration failure class no per-agent eval can see.

### Group B — Approval-gate matrix (WS-1 dependency)

All cases: Pre includes a valid ops.json and a fixture repo; Cmd is `python3 .claude/operations/scripts/execute-json-ops.py <ops.json>` unless stated.

**E2E-05 — no approval record blocks execution (A)**
- Pre: no file under `.claude/reports/reviews/` for this plan.
- Assert: exit non-zero (the executor's gate code), stderr names the missing record, **target file byte-identical to pre-state**.
- Fails as: executor runs unreviewed ops (the gate is advisory again).

**E2E-06 — drift after approval blocks execution (A)**
- Pre: APPROVED record for digest D; then one byte appended to `ops.json`.
- Assert: exit 2 from `review-record.py check` and a blocking non-zero from the executor; stderr says drift; no file mutated.
- Fails as: gate keyed on plan path or timestamp instead of content digest.

**E2E-07 — CONDITIONAL does not authorise unattended execution (A)**
- Pre: record written with `--decision CONDITIONAL --score 88`.
- Assert: `review-record.py check` exit 4; executor refuses; stderr distinguishes "verdict does not authorise" from "no record".
- Fails as: CONDITIONAL treated as APPROVED, or collapsed into the exit-3 no-record path (operator cannot tell why).

**E2E-08 — REJECTED blocks (A)**
- Pre: record `--decision REJECTED --score 40`.
- Assert: check exit 4; executor refuses; no mutation.
- Fails as: any execution at all.

**E2E-09 — APPROVED below threshold blocks (A)**
- Pre: record `--decision APPROVED --score 89` (threshold 90 in `review-record.py`).
- Assert: check exit 4 — decision/score consistency is enforced, not just the enum.
- Fails as: enum-only gating; a self-declared APPROVED at any score executes.

**E2E-10 — APPROVED at/above threshold executes (A)**
- Pre: record `--decision APPROVED --score 90`.
- Assert: check exit 0; executor exit 0; target mutated; record untouched.
- Fails as: the gate over-blocks (false negative), which is how gates get disabled in practice.

**E2E-11 — escape hatch is explicit, loud, and audited (A)**
- Pre: no record; the WS-1 override mechanism engaged exactly as WS-1 defines it (env var or flag — the test asserts WS-1's chosen surface, not an invented one).
- Assert: execution proceeds; stderr carries an unmissable warning; the override is recorded (hooks.log or the run's report) so it is auditable after the fact; **the same run without the override still blocks** (paired assertion).
- Fails as: a silent bypass, a bypass that leaves no trace, or an env var that is on by default.

**E2E-12 — the gate cannot be satisfied by a hand-written record (A)**
- Pre: a syntactically valid record JSON hand-authored in the test with an APPROVED verdict and a *wrong* digest.
- Assert: check exit 2 (drift), executor refuses.
- Fails as: the record is trusted as a token rather than verified against the artifact.

**E2E-41 — CONDITIONAL -> revise -> re-approve -> execute round trip (A)**
- Pre: E2E-07 state (CONDITIONAL record, execution refused).
- Cmd: (1) confirm the executor refuses; (2) edit `ops.json` to address the finding (changes its digest); (3) confirm it *still* refuses — the stale CONDITIONAL record now also drifts (exit 2), so the revision cannot be smuggled through the old verdict; (4) `review-record.py write <plan> <ops.json> --score 92 --decision APPROVED`; (5) `review-record.py check`; (6) `execute-json-ops.py`.
- Assert: steps 1 and 3 non-zero (with *different* stderr reasons — verdict vs drift); step 5 exit 0 with the record digest equal to the **revised** file's digest; step 6 exit 0 and the target carries the revised post-state; the superseded record is retained (auditable history), not silently overwritten in place with no trace.
- Fails as: the daily workflow breaking in either direction — a revision that can never be re-approved (the gate has no forward path), or a re-approval that does not re-bind to the new digest (approval laundering: get a CONDITIONAL, edit freely, execute).

### Group C — Hook profile matrix

**E2E-13 — `standard` engages the wired enforcement set (A)**
- Pre: fixture repo with the tree's real `.claude/settings.json` and hooks.
- Cmd: for each PreToolUse Edit/Write matcher hook, run it as a subprocess with `env={"ECC_HOOK_PROFILE": "standard"}` and a payload targeting `src/app.py`.
- Assert: `ops-enforcement.sh` exits 2 with non-empty stderr; the assertion iterates the matcher list parsed **from settings.json**, so a hook silently unwired from settings fails the test.
- Fails as: the missing-hook-wiring class of P0 (hook file present, never invoked).

**E2E-14 — `minimal` is genuinely inert (A)**
- Pre: same payload.
- Cmd: same hooks with `env={"ECC_HOOK_PROFILE": "minimal"}`.
- Assert: every blocking hook exits 0 and writes nothing to stderr; and — the part that matters — a real `execute-json-ops.py` run and a direct file write both succeed.
- Fails as: partial bypass (some hook ignores the profile), which would make maintainer sessions behave unlike documented.

**E2E-15 — profile default is fail-safe (A)**
- Pre: env with `ECC_HOOK_PROFILE` **unset**.
- Assert: hooks behave as `standard` (the code's documented default `${ECC_HOOK_PROFILE:-standard}`) — a source-file payload is blocked.
- Fails as: an unset env silently disabling enforcement for anyone who did not read the setup gotcha.

**E2E-16 — dogfood signal: this repo's own local override is visible, not invisible (A)**
- Pre: none (runs against the repo itself).
- Assert: if `.claude/settings.local.json` sets `ECC_HOOK_PROFILE=minimal`, the test passes but emits a warning line naming it, and asserts the file is gitignored and never present in a built wheel/installed tree (`ck doctor` fixture install has no minimal override).
- Fails as: a maintainer-only bypass leaking into a shipped artifact.

### Group D — Iron Law (block direct edits, allow the ops path)

**E2E-17 — direct Edit of a source file is blocked (A)**
- Pre: `standard` profile; fixture `src/app.py`.
- Cmd: `echo '<Edit payload for src/app.py>' | .claude/hooks/ops-enforcement.sh` with forced env.
- Assert: exit **2**, stderr non-empty and mentions the ops path; exit is not 1, output is not on stdout (hard rule 2).
- Fails as: exit 1 / stdout, which Claude Code does not treat as a block.

**E2E-18 — the same change via ops succeeds (A)**
- Pre: same file, same intended edit, approved record.
- Cmd: `execute-json-ops.py` with a `code_edit` op carrying the identical change.
- Assert: exit 0; file contains the new text. Paired with E2E-17 in one test so "blocked" can never be satisfied by "nothing works."
- Fails as: an over-broad guard that blocks the sanctioned path too.

**E2E-19 — malformed payload fails closed (A)**
- Cmd: feed `ops-enforcement.sh` truncated JSON, empty stdin, and a payload with a null `file_path`.
- Assert: exit 2 for the unparseable cases (never 0); no traceback text in stderr.
- Fails as: fail-open on garbage — the single highest-value hook bug class.

**E2E-20 — CHARACTERIZATION: `.md` files are exempt today (A)**
- Pre: `standard`; payload targeting `docs/guide.md` and `README.md`.
- Assert: exit 0 (allowed). Docstring states verbatim: *this records current behavior; whether the exemption is correct for this repo is an open owner decision (WS-5 memo). Do not cite this test as endorsement.*
- Fails as: behavior changed without a decision — the test goes red and forces the memo to be resolved before merge.

**E2E-21 — CHARACTERIZATION: `.claude/**` in-project files are exempt today (A)**
- Pre: `standard`; payload targeting `<root>/.claude/agents/planner.md` and `<root>/.claude/hooks/lib.sh`.
- Assert: exit 0 (allowed). Same characterization docstring. Note explicitly that under this exemption a `.sh` hook inside `.claude/` is directly editable — the widest surface the exemption grants, and the concrete thing the WS-5 memo must rule on.
- Fails as: same as E2E-20.

### Group E — Lifecycle gates (WS-2 dependency)

**E2E-22 — reflection checkpoint blocks mutation after repeated failures (A)**
- Pre: WS-2's failure counter seeded past its threshold in the fixture state file.
- Cmd: attempt an ops execution / mutating tool call through the wired hook.
- Assert: exit 2; stderr instructs reflection; no file mutated.
- Fails as: the counter is decorative and the agent grinds on a failing loop.

**E2E-23 — a valid reflection receipt releases the gate (A)**
- Pre: E2E-22 state + a receipt produced by WS-2's own writer.
- Assert: the same command now exits 0 and mutates; the counter resets.
- Fails as: a gate with no exit — agents get permanently wedged.

**E2E-24 — a forged receipt does not release the gate (A)**
- Pre: a receipt hand-written in the test (wrong signature/digest/session id, per WS-2's binding).
- Assert: still exit 2; stderr names the invalid receipt distinctly from "no receipt".
- Fails as: a checkpoint satisfiable by `touch`.

**E2E-25 — Stop hook interrupts once, then yields (A)**
- Cmd: invoke the Stop hook twice: payload with `stop_hook_active: false`, then `true`.
- Assert: first invocation interrupts (its blocking exit code + stderr); second exits 0.
- Fails as: an infinite stop loop (honouring `stop_hook_active` is the only thing preventing it).

**E2E-26 — duties survive PreCompact (A)**
- Pre: fixture session with pending duties recorded.
- Cmd: run the PreCompact hook, then assert the post-compact injection content.
- Assert: the duty text is present in what the hook emits for re-injection; the duty store is not truncated by the compact.
- Fails as: the agent forgets its obligations exactly when the context is smallest.

### Group F — Failure and recovery

**E2E-27 — mid-batch failure rolls the tree back (A)**
- Pre: ops.json of 3 edits where op 2's `find` anchor is absent.
- Cmd: `execute-json-ops.py`.
- Assert: non-zero exit; **all three targets byte-identical to pre-state** (hash compared); backup dir present; stderr names the failing op index.
- Fails as: op 1 applied and left behind — a half-applied plan is worse than a failed one.

**E2E-28 — SIGINT during execution leaves a consistent tree (A)**
- Cmd: launch the executor on a slow fixture batch (many ops), send SIGINT mid-run, wait.
- Assert: every target is either fully pre-state or fully post-state — no file contains a truncated/partial write; the backup dir is usable by `restore-backup.py`.
- Fails as: torn writes (the crash class no unit test reaches).

**E2E-29 — forward recovery from the post-state snapshot (A)**
- Pre: a completed run with a `post/` snapshot; then the tree clobbered (files reverted by hand).
- Cmd: `restore-backup.py --backup <dir> --post`.
- Assert: exit 0; modified **and created** files restored to post-state; a run without a `post/` snapshot exits with the documented "older run" message rather than silently restoring pre-state.
- Fails as: forward recovery silently degrading into a rollback (data loss dressed as success).

**E2E-30 — dry-run mutates nothing (A)**
- Cmd: `restore-backup.py --dry-run` and the executor's dry-run/simulate path.
- Assert: exit 0; tree hash unchanged; the preview lists the same file set the real run touches.
- Fails as: a "preview" with side effects.

**E2E-31 — a crash before any write leaves no partial artifacts (A)**
- Pre: ops.json whose first op targets a path outside the project root (guard trips immediately).
- Assert: non-zero exit; **no backup dir created or an empty-but-valid one**; no target created; no stale lock left behind that blocks the next run (run the executor again on a good config and assert exit 0).
- Fails as: a failed run poisoning subsequent runs.

### Group G — Isolation

**E2E-32 — worktree-per-implementer isolates writes (A)**
- Pre: fixture repo is a git repo.
- Cmd: `worktree-manager.py create ws-a --json`; run the executor with cwd = the emitted `root`.
- Assert: files change under the worktree root only; the main tree is byte-identical; `worktree-manager.py remove` cleans up with no residue; a 6th concurrent create is refused (max 5).
- Fails as: parallel implementers stomping the main tree.

**E2E-33 — disjoint-set parallel execution does not interleave (A)**
- Pre: two ops configs with strictly disjoint file sets, two worktrees.
- Cmd: run both executors concurrently; join.
- Assert: both exit 0; each target has exactly its own plan's post-state; backup dirs are distinct (no manifest overwrite).
- Fails as: shared backup/lock paths colliding under parallelism.

**E2E-34 — cross-project edit is blocked (A)**
- Pre: two sibling fixture projects, cwd in project A; `standard`.
- Cmd: Edit payload targeting `../projectB/src/app.py`, plus an ops config with the same escape (`../`, an absolute path, and a symlink pointing out of the root).
- Assert: hook exits 2 ("cross-project"); executor's path guard refuses all three escape forms; scratchpad/temp paths remain allowed (the documented exemption).
- Fails as: path-guard bypass by traversal or symlink.

### Group H — Delivery contract (token-burn regression)

**E2E-35 — command wrappers redirect agent stdout to disk, never echo it (A)**
- Pre: none — static+behavioral check over the shipped command/agent corpus.
- Cmd: run the wrapper snippets in the `/plan` and `/refine` command files against a stub `claude` on PATH that prints a large marker payload.
- Assert: the marker string lands in the target file and appears **zero times** on the wrapper's own stdout; wrapper stdout is a short scoreboard (path + verdict + counts), under a fixed line budget.
- Fails as: the exact 80.3M-token mechanism — `tee`/`echo` of a captured artifact.

**E2E-36 — no shipped agent/command instructs a payload reprint (A)**
- Cmd: lint the corpus for the forbidden instruction family ("return the complete plan", "print the full ops.json", "output the entire file") with an allowlist for the sanctioned headless-stdout carve-out in INVOCATION.md.
- Assert: zero unallowlisted hits; a seeded violation turns it red.
- Fails as: contract erosion by prompt drift.

**E2E-37 — live handoffs return paths, not payloads (B)**
- Pre: the flow eval of E2E-04.
- Assert: each stage's returned message is under a token/char budget and does **not** contain the ops.json body (checked by substring of a distinctive fixture-only literal planted in the ops content).
- Fails as: an agent that obeys the contract in prose and violates it in practice — only observable with a real spawn.

### Group I — Spawn mechanisms

**E2E-38 — headless `claude -p --agent` completes a scoped read-only task (B)**
- Cmd: `claude -p --agent explore --model haiku --allowedTools "Read,Grep,Glob"` on the fixture, prompt on stdin.
- Assert: exit 0 within a generous timeout; non-empty stdout; **no** `--dangerously-skip-permissions` anywhere in the invocation; records the cold-boot duration into the eval results so the documented ~13–14s figure stays honest.
- Fails as: the "agent not found" frontmatter regression, or a hang on a permission prompt.

**E2E-39 — CHARACTERIZATION: headless `.claude/**` write gate (B)**
- Cmd: headless agent with `--allowedTools "Read,Write"` instructed to write `.claude/plans/probe.md`.
- Assert: the file is **not** created (the platform sensitive-path gate holds) and the run does not hang the harness; docstring records that this is a platform behavior we depend on, re-verified per Claude Code upgrade (INVOCATION.md "Verification spike").
- Fails as: the gate changing under us — which would invalidate the stdout delivery design and must be noticed loudly, in either direction.

**E2E-40 — Task-tool spawn path stays registered (A for registration, B for execution)**
- Assert (A): every `.claude/agents/*.md` parses as valid frontmatter with a `description` block scalar and no bare `<example>` between YAML fields — the exact regression that made every agent invisible to *both* mechanisms.
- Assert (B): a Task-tool spawn of `explore` in a live session returns a result (recorded manually per release; not automatable from headless CI — state this rather than fake it).
- Fails as: silent de-registration of the whole agent corpus.

**Totals: 41 cases — 36 LANE A (deterministic, CI) · 4 LANE B (live model spawns: E2E-04, E2E-37, E2E-38, E2E-39; budgeted opt-in lane) · 1 hybrid (E2E-40: its registration half is LANE A, its Task-tool spawn half is a manually recorded live check). Counted by the (A)/(B) marker on each case id above; the numbers reconcile with the catalogue — if you edit a case, re-derive this line rather than adjusting it.**

---

## Step-by-step Implementation
1. **Fixture factory first** (`tests/conftest.py`): a `pipeline_repo` fixture that builds a tempdir git repo containing `src/app.py` (stable anchors), a passing `tests/test_app.py`, and a `.claude/` assembled by copying the live tree's `hooks/`, `operations/scripts/`, and `settings.json`. Parametrized on `ECC_HOOK_PROFILE`. Everything else depends on this; get it right before writing cases.
2. **Group A + D** (happy path + Iron Law) — the spine. These need no WS dependency and prove the fixture factory works.
3. **Group C + F** (profiles, failure/recovery) — pure script/hook behavior, highest value per hour.
4. **Group B** behind `xfail(strict=True)` referencing WS-1; flip to expected-pass in the WS-1 PR (that flip is WS-1's acceptance evidence).
5. **Group E** behind `xfail(strict=True)` referencing WS-2; same flip discipline.
6. **Group G + H(A-lane)** — worktree isolation and the delivery-contract lint/wrapper tests.
7. **`flow` kind in `scripts/run-evals.py`**: a definition gains `stages: [{agent, model, allowed_tools, prompt, checks}]` executed in order, with a `carry` map so stage N+1's prompt can reference stage N's produced paths; add the four new check types; `--dry-run` must validate flow definitions without spending. Add `--budget-usd` with a hard stop.
8. **LANE B definitions** (`flow-full-pipeline`, `flow-delivery-contract`, `flow-headless-gates`) + `evals/fixtures/pipeline`.
9. **CI**: `e2e.yml` runs LANE A on ubuntu+macos per PR alongside the existing suite; LANE B is `workflow_dispatch` + nightly, skipped on forks, budget-capped, results committed as trend JSON (reusing task 010's results convention).
10. **Docs**: TESTING_GUIDE test-map row, the lane distinction stated in one sentence ("LANE A proves the machinery; LANE B proves the agents; neither substitutes for the other"), CHANGELOG `[Unreleased]`.

## Acceptance Criteria
- `python3 -m pytest tests/test_pipeline_e2e.py -q` green on ubuntu and macOS, offline, in under 90 s, with zero flakes across 20 consecutive runs.
- **Counts are re-derived, never restated.** Any statement of case totals (the Totals line, the
  Files section, this task's own metadata, and any downstream summary) must be produced by counting
  the `(A)`/`(B)` markers in the catalogue at the time of writing — not copied forward from a
  previous revision. Adding or removing a case therefore requires re-deriving every total in the
  document, and the PR must show the count command's output. Rationale, recorded because it has now
  happened twice during this spec's own review: a total that drifts from the body is the exact
  defect class this suite exists to catch, and a suite whose spec miscounts itself has no standing
  to enforce anything. Prefer a mechanical count over a prose number wherever one will do.
- **Mutation proof for every one of the nine groups.** Each is a stash-the-guard / run / confirm-red exercise, recorded in the PR with pasted output. No group ships without one:
  - **A (happy path):** make `execute-json-ops.py` return 0 without applying its edits (comment out the write) -> E2E-03 red (target unchanged, backup manifest absent). Second mutation: break `extract-json-from-plan.py`'s fenced-block regex -> E2E-01 red.
  - **B (approval gate):** make `review-record.py check` return 0 unconditionally -> E2E-05..09, E2E-12, E2E-41 red. Second mutation: compare the record's *path* instead of its digest -> E2E-06 and E2E-12 red while the others stay green (proves the digest binding specifically).
  - **C (hook profiles):** delete the `[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0` line from `ops-enforcement.sh` -> E2E-14 red; change the default from `standard` to `minimal` in the same expansion -> E2E-15 red.
  - **D (Iron Law):** change `ops-enforcement.sh`'s block from `exit 2` to `exit 1` -> E2E-17 red (exit-code assertion is the point, per hard rule 2). Second mutation: drop the `.md` allow branch -> E2E-20 red, which is the characterization test doing its job (a behavior change forces the WS-5 memo).
  - **E (lifecycle gates):** make WS-2's receipt validator accept any file that exists (skip the digest/session binding) -> E2E-24 red. Second mutation: make the Stop hook ignore `stop_hook_active` -> E2E-25 red (second invocation no longer exits 0).
  - **F (failure/recovery):** delete the rollback branch on anchor failure in the executor -> E2E-27 red (op 1 left applied). Second mutation: make `restore-backup.py --post` fall through to the pre-state snapshot when `post/` is missing instead of erroring -> E2E-29 red.
  - **G (isolation):** remove the `..`/absolute-path rejection from the executor's path guard -> E2E-34 red. Second mutation: hardcode a single shared backup dir name instead of a per-run one -> E2E-33 red under concurrency (manifest overwrite).
  - **H (delivery contract):** add `echo "$out"` to the `/plan` wrapper -> E2E-35 red (marker appears on stdout). Second mutation: seed "return the complete plan" into a scratch agent file -> E2E-36 red.
  - **I (spawn mechanisms):** insert a bare `<example>` block between YAML frontmatter fields in one agent file -> E2E-40's LANE A registration assertion red (the exact 2026-07-08 regression). The LANE B half of I (E2E-38/39) is **not mutation-provable by us**: it exercises platform behavior (cold-boot spawn, the `.claude/**` sensitive-path gate) that we do not control and cannot deliberately break — stated here rather than papered over. Its guard is re-verification per Claude Code upgrade (INVOCATION.md "Verification spike"), not mutation.
- Every WS-dependent case is `xfail(strict=True)` with a named reference — zero unconditional skips, zero `|| true` (task 011 culture rule).
- Characterization tests (E2E-20/21/39) carry the "records current behavior, not an endorsement" docstring and are cross-linked from the WS-5 memo.
- `python3 scripts/run-evals.py --dry-run` validates the new `flow` definitions with zero API calls and exits 0.
- One budgeted LANE B run recorded: per-stage pass/fail, total cost, wall time — published next to the 2026-07-08 anecdote so the anecdote stops being the evidence.
- `.ai/TESTING_GUIDE.md` updated; component counts untouched by hand (gen-docs).

## Testing Strategy
(Meta) The suite's own falsifiability is the deliverable: each case ships with its mutation proof (stash the guard, run, confirm red) as required by task 012's discipline. LANE A must run with `env=` explicitly set on every subprocess — never inheriting the maintainer's `minimal` profile, which would make the whole suite vacuously green (that is precisely the failure this task exists to prevent, so `tests/conftest.py` asserts `ECC_HOOK_PROFILE` is explicitly set in every subprocess call it constructs). LANE B assertions are restricted to machine-checkable properties (exit codes, file existence, digest match, schema validity, substring absence) with N-of-M thresholds; no assertion may depend on model prose.

## Rollback Plan
Entirely additive: one new test module, one fixtures dir, new eval definitions, one new workflow. Revert the workflow file alone to stop CI cost/noise; revert the test module to drop the gate. The one shared-file change is the `flow` kind in `scripts/run-evals.py` — additive and gated by the presence of a `stages` key, so existing single-agent definitions keep running unchanged; revert that commit independently if the runner regresses. No production code changes in this task, so nothing here can break a user install.
