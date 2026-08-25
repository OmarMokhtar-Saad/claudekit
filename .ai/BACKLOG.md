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

- [x] **DONE (verified 2026-08-25): `hooks=19` was already fixed.** `scripts/gen-docs.py`
  defines `HOOK_GLOBS = ("*.sh", "*.py")` and reports `hooks=26`. This entry was stale, and it
  was re-quoted as current from a truncated `grep` that showed only the agents/commands/skills
  globs — the same class of error as the counts this entry was written about. Original text:
- [ ] ~~**`hooks=19` is WRONG, not stale**~~ — `scripts/gen-docs.py:55` globs `*.sh` only, so the two
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
- [x] **DIAGNOSED 2026-08-24 — it was a leading dash in the session token.** The entry
  below is kept in full, because its value is the record of five wrong or half-right
  hypotheses and two lost captures. **Cause:** `secrets.token_urlsafe` draws from the
  base64url alphabet, which contains `-`, so **~1.5% of session tokens begin with one**
  (measured: 306 of 20000 draws). Every caller passed the token as
  `--session-token <value>`, and argparse reads a leading-dash value as the **next
  option**, exiting 2 with `argument --session-token: expected one argument`. That is the
  exact signature recorded below, and it is why the failure never reproduced: the coin flip
  is **inside the secret**, so a re-run draws a different token.

  **What finally caught it was keeping the whole suite output.** The two prior captures
  were lost — once to `/dev/null`, once to `tail -4` — and this entry says as much. The run
  that diagnosed it wrote the full output to a file, and the traceback showed the token
  going onto argv followed immediately by `--inbox`.

  **Fixed at generation, not at the call site**, because the token is printed to the user at
  session start and pasted onto command lines by agents: `_new_token()` redraws until the
  token does not start with `-` (redraw, not strip — stripping would shorten the secret).
  Callers that pass a token already on disk now use `--session-token=<value>`, which
  argparse parses whatever the value starts with. `tests/test_session_token_shape.py`
  pins all of it, **including the premise** (that `token_urlsafe` really does emit leading
  dashes), so the guard cannot pass vacuously if the alphabet ever changes.

  **The earlier ruling-out was correct and still is:** `None` and `""` were checked and
  neither produces this error. The entry's own conclusion — "the observed error requires
  the token argument to have been absent or **option-shaped**" — was right, and nobody
  followed it to the alphabet.

- [ ] **UNEXPLAINED intermittent (RESOLVED above; original record retained): `test_receipt_via_json_stdin_clears_the_checkpoint`**
  **WIDENED 2026-08-22 — it is a FAMILY, not one test.** Two consecutive full-suite runs on
  `main` at the merge of `perf/token-efficiency` each failed exactly one `TestCli`
  checkpoint-clearing test, and a DIFFERENT one each time: first
  `test_receipt_via_json_stdin_clears_the_checkpoint`, then
  `test_receipt_via_cli_clears_the_checkpoint`. Both passed 3/3 standalone and the whole file
  passed 54/54 immediately after, in both cases. So the signature is not one flaky test but any
  member of the receipt-clears-checkpoint set, failing only under a full-suite run — which points
  at cross-test state (a shared ledger/checkpoint path or a session id colliding across modules)
  rather than at either test. Still NOT diagnosed; recorded as observation, not theory.
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

  **SIGHTING 2026-08-24 (second), and the evidence was LOST AGAIN — by me, in a new
  costume.** One full-suite run on `main` at the paper-trail/gate work failed exactly one
  member of the family, `test_receipt_via_cli_clears_the_checkpoint`, at
  `tests/test_reflection_ledger.py:409` (the `pending_checkpoint(SESSION) is None`
  assertion, not the argparse shape). It did **not** reproduce: the test passed standalone
  and the whole file passed 54/54 immediately after, and a full re-run was **2902 passed,
  0 failed**. Consistent with every prior sighting.
  **The `receipt_diagnostic()` capture fired and I threw it away**: the run was piped
  through `tail -4` to keep the transcript small, so only the summary line survived. This
  entry already records the identical mistake made with `/dev/null` on 2026-08-21 and says
  it "is precisely the mistake this item exists to prevent" — so the lesson is that the
  capture is not the weak link, **the harness around the run is**, and a summary-only
  invocation defeats it just as completely as a redirect to nowhere.
  **Rule for the next runner: never pipe a full-suite run through `tail`/`head` when this
  family can fire. Write the whole output to a file and summarise from the file.** No cause
  is claimed and no retry was added.

  **NEW SIGNATURE 2026-08-24** (full-suite run, worktree at `bd49c7f`, ~1 failure in 9):
  the CLI variant failed with **argparse exit 2** — `reflection.py receipt: error:
  argument --session-token: expected one argument` — not with the exit-0 /
  checkpoint-not-cleared shape every prior sighting had. Two candidate values were
  checked and BOTH ruled out: `read_session_token` returns `Optional[str]` and never
  `""`; a `None` token raises `TypeError` in the parent before `subprocess` is reached,
  and `""` parses cleanly to `rc=0`. So the observed error requires the token argument to
  have been absent or option-shaped, which neither return value explains. `record_failure`
  calling `ensure_session_token` and **discarding its return** (`reflection.py:606`) is
  noted as a place where a silent token-creation failure would go unobserved — a LEAD,
  not a diagnosis. **Capture widened accordingly**: the CLI variant had no
  `receipt_diagnostic()` at all despite being a recorded family member since the
  2026-08-22 widening, and the diagnostic recorded no argv — the one field that would
  have settled this signature. Both fixed; the next occurrence arrives with the evidence
  this one lacked. Still no cause claimed.
- [ ] **[MEDIUM] `check-plan-artifacts.py` silently skips 59% of the configs it counts.**
  Observed 2026-08-24: `check-plan-artifacts: OK (151 config(s), 363 path(s) verified)` followed
  by `NOTE: 89 config(s) resolved to no plan and were not checked`. So **62 of 151** configs are
  actually checked, and the headline number counts all 151. The script's own comment at
  `scripts/check-plan-artifacts.py:259-261` already names this failure mode — "a config count
  alone cannot tell a real pass from a gate that checked nothing" — and the NOTE is printed
  rather than failed on, so the 59% has grown quietly.

  **Cause, and it is mostly self-inflicted.** `_resolve_plan` tries `plan-<slug>.md` and
  `<slug>.md` for the config's declared `plan` key. Configs declaring a *sub-slug* — one plan
  executed through several configs, e.g. `"plan": "triage-refresh-records"` against
  `plan-triage-refresh.md` — resolve to nothing and are skipped. **Six of the 89 are mine**, from
  this period: I named each config after its step rather than its plan, and the gate skipped all
  six without failing. Two candidate fixes: declare the parent slug in every config (convention,
  no code), or have `_resolve_plan` fall back to the longest `plan-*.md` prefix of the declared
  slug (code, and it must not match across unrelated plans). **Prefer the convention fix** — a
  prefix fallback is the kind of loose matcher that `ops-dispatcher-payload.json`'s L1 lesson was
  about.

  **Do not "fix" it by making the NOTE fatal first.** 89 configs are already archived and spent;
  failing on them reddens CI for history nobody can change. Fix the resolution, watch the number
  fall, then make it fatal — in that order, or the gate gets routed around.

- [ ] **[MEDIUM] `review-record.py check` manufactures DRIFT for a plan's second ops config.**
  Diagnosed 2026-08-24 while working the three `drifted` plans `gen-plan-index.py --check`
  reports. **Two of the three warnings are the tool's, not the tree's.** When a config has no
  record under its own ops key, `resolve_ops`'s legacy fallback compares its bytes against the
  *plan-slug* record — a different file's approved hash — and reports drift:

      $ python3 .claude/operations/scripts/review-record.py check \
          .claude/plans/plan-dispatcher-payload.md \
          .claude/plans/archive/ops-dispatcher-payload-docs.json
      NOTE: no record under ops key 'dispatcher-payload-docs'; using the legacy plan-slug record 'dispatcher-payload'.
      DRIFT: ops.json changed after it was reviewed.

  `archive/README.md:57` records that config as executed with `--no-approval` (Tier 1, docs) —
  it never had a verdict, so it cannot have drifted from one. `ops-enforcement-runtime-wiring.json`
  is the same shape. Each plan's *primary* config is clean: `ops-dispatcher-payload.json`
  APPROVED 94, `ops-enforcement-runtime.json` APPROVED 93, both capability-tiers siblings 93/95.
  Because `gen-plan-index.py`'s `PRECEDENCE` puts `drifted` first, one falsely-drifted addendum
  condemns the whole plan. Fix: report *absence* (the existing rc=3 `planned`) when no record
  exists under the ops key, instead of hashing against a different file's verdict. **Owner-gated —
  it changes what the approval machinery calls approved, so it is Tier 3 and wants an adversarial
  review.** Mutation proof required both ways: the two addenda 2 → 3, the four primary configs
  unchanged at 0, and a hand-edited byte in a primary config still reporting 2.

  **`plan-capability-tiers`'s drift is genuine and is NOT covered by that fix.** Its own key's
  hash changed after the verdict. `archive/README.md:90` records it executed 8/8 with APPROVED 95,
  and `review-record.py` names the probable cause itself — `--stamp-baseline` run after the
  verdict was recorded, which rewrites the config's bytes. Probable, documented, benign, and
  still not a verdict: **no approval will be re-recorded for it.** It stays `drifted` until a real
  `/review` pass re-scores it, which is the only honest way out.

  **The handoff's prescribed remedy does not apply.** "Archive it with a README row" conflicts
  with the repo's own convention: `scripts/check-plan-artifacts.py:147-148` states that an
  executed *config* moves to `archive/` while **the plan stays at `.claude/plans/`** — moving the
  three plan documents would break the path resolution that comment exists to describe.

- [x] **Triage `review/code-review.md` — DONE. Pointer only; verdicts live in
  `review/code-review-triage.md` (40 LIVE, 62 FIXED, 5 OBSOLETE, 1 UNVERIFIABLE at `d945278`).**

  This headline used to read "30 of 75 P2/P3 findings verified ... 45 unverified", which the body
  below already corrects — and leaving the wrong number in the *headline* is how the error
  propagated in the first place, since that is the line a skim reads. A stale summary above an
  accurate body is worse than no summary.

  **The count in this entry was wrong twice, and re-deriving it is the first lesson.** It
  read "76 unfixed P2/P3 findings"; a later grep for `P2|P3` returned **88**, which is a
  count of *mentions* — it includes the severity-scale legend at `:7` and prose that merely
  names a severity. Parsed structurally (a `### P2/P3 —` heading, or a bullet opening
  `**P2**`/`**P3**`), the file holds **75** findings. Neither 76 nor 88 was ever the number
  of findings, and no verdict below should be quoted without re-checking the file it names.

  **75 is the P2/P3 count, not the file's total.** `plan-code-review-triage.md` (Workstream
  13, unexecuted) counts **103** findings across every severity, and that is the right
  number for a full triage. It also prescribes a different shape from this entry — a new
  `review/code-review-triage.md`, with `.ai/**` explicitly out of scope because the owner
  holds the BACKLOG. This pass edited the entry because the handoff asked for exactly that;
  **if the owner prefers Workstream 13's shape, the verdicts below move to that file and
  this entry goes back to a pointer.** Flagged, not decided here.

  **Verified STILL REAL (11)** — each checked against the current file, not against this
  entry:

  | Finding | Evidence today |
  | --- | --- |
  | `ExecutionLock` is not a lock on Windows, and `release()` unlinks unconditionally | `execute-json-ops.py:159-183` — no `fcntl`, so `O_CREAT\|O_TRUNC` always succeeds; `release()` unlinks whoever holds it |
  | `cmd_config` parses `config.json` unguarded | `src/claudekit/cli/main.py:1836` — a malformed file gives a traceback, not an error |
  | `subprocess.run` with no `timeout=` | `main.py:325` (`bash --version`), `:340` (`git --version`) — a wedged binary hangs `ck doctor` |
  | `cmd_rollback`'s `elif`/`else` branches are identical | `main.py:717-720` — both append `--list` |
  | ANSI colour is unconditional | `main.py:45-46` — no `NO_COLOR`, no `isatty()` |
  | `log()` is copy-pasted across hooks | **14** hooks define their own; `lib.sh` exists but does **not** define it, so the shared-library fix stopped short |
  | failure output truncated to `tail -20` | `post-implement.sh:98,130`, `pre-push.sh:150` — the root cause is usually above the last 20 lines |
  | `file-guard.sh` blocks by extension with no allowlist | `file-guard.sh:95` — `cert\|crt\|pem\|key\|p12\|pfx` still catches `public.pem` and test fixtures |
  | `config.schema.json` overpromises and documents unwired hooks | `config.schema.json:75` still claims "195+ patterns"; `file-guard`, `prompt-injection-scanner` and `check-comment-replacement` have **0** references in `.claude/settings.json` |
  | `auto-checkpoint.sh` prune math + unlocked registry | `auto-checkpoint.sh:90-91` — `checkpoints[:len-max+1]`, and read/modify/write with no lock |
  | `PM_INSTALL`/`PM_RUN` are dead | `session-start.sh:17-51` — assigned eight times, read never |

  **Verified ALREADY FIXED (19).** The large first bucket the triage predicted, and most of
  it was closed incidentally rather than by working this list: the three-place version
  contract (hard rule 7) and the dead `setuptools-scm` dependency; `license = "MIT"` plus the
  3.13 classifier and `optional-dependencies`; `install.sh`'s `curl \| bash` guard, its
  `CK_VAR_*` env substitution replacing `sed` templating, and computed `$CMD_COUNT` /
  `$SKILL_COUNT` / `$HOOK_COUNT` instead of hard-coded totals; `block-no-verify.sh`'s
  substring false positive; the `\x27`-inside-a-character-class bug (`lib.sh:79`,
  `pre-commit.sh:145`); `suggest-compact.sh`'s stale-lock recovery and its `date -r`
  portability; `auto-checkpoint.sh` recording a stash **SHA** and reporting a failed apply
  loudly; the `awk '{print $2}'` porcelain mangling; `atomic_write` preserving the target's
  mode — **this is the mode-stripping P2 that cost real damage**, now closed; an edit whose
  `find` pattern is missing failing closed instead of continuing, with ambiguous matches
  refused too; `path_guard`'s substring `PROTECTED_PATTERNS` match, its relative-symlink base
  and its magic depth constant; the dead imports in `main.py`; and `*.md` being permanently
  undeletable.

  **SUPERSEDED 2026-08-24 — this entry is now a pointer.** The verdicts live in
  **`review/code-review-triage.md`**, which triaged all 108 findings on 2026-08-20 (commit
  `8f54f55`) and was re-verified against `HEAD` on 2026-08-24: **40 LIVE, 62 FIXED, 5
  OBSOLETE, 1 UNVERIFIABLE**, still zero P0 and zero P1. Do not add verdicts here.

  **The "45 unverified" above was never true.** This entry and the triage file were two
  independent enumerations of one review — 75 P2/P3 findings here, 108 across all severities
  there, different IDs, neither pointing at the other — so "unverified by this entry" got
  read as "unverified". Every one of the 45 already had a verdict one directory over. That is
  the `duplicate-asset` class task 008 exists to close, and it cost a working period.

  **The two method lessons below are kept because they are about how to check, not what is
  currently true.**

  **Two traps this pass hit, worth inheriting.** (1) `templates/hooks/` no longer exists, so
  §6's eight findings *look* retired — but batch 1 **promoted** those hooks into
  `.claude/hooks/`, and four of the eight are still live against the promoted files. A
  finding whose path moved is not a finding that went away. (2) `lib.sh` existing looked like
  the duplicate-`log()` fix; it is not, because `lib.sh` does not define `log()`. Both errors
  came from reasoning about the fix instead of grepping for it.

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

- [ ] **`install.sh --full` ships the STALE `token-optimization` skill (measured 2026-08-23).**
  The skills install is two passes into one destination — `.claude/skills/*/` then
  `templates/skills/*/` — so the second wins. 13 names exist in both trees; three have
  diverged. For `incident-response` (180 vs 350 lines) and `spec-driven-development`
  (214 vs 221) the templates copy is the newer one, so the race is benign by luck. For
  `token-optimization` it is not: canonical is 219 lines (2026-08-19, the token-efficiency
  pass), templates is 147 (2026-04-12), and **a real `bash install.sh --full` into a temp
  dir ships the 147-line file** — verified by `diff`, not by reading the script. Every
  `--full` install since 2026-08-19 discarded the newer text, and no gate could see it:
  `gen-registry.py`, `gen-docs.py` and `check-context-floor.py` all read `.claude/skills/`,
  the copy that loses. This is arch F-11 turning from a hazard into a live regression.
  **Fix is prepared and blocked, not deferred:** `.claude/plans/plan-canonical-skill-wins.md`
  + `ops-canonical-skill-wins.json` (validator: APPROVED) make the canonical tree win, with a
  content-asserting regression test in `tests/test_install.py`. Execution is refused by the
  approval gate for want of a review record — it needs a `code-reviewer` pass, then
  `/implement`. **Second-order consequence to weigh in that review:** under the fix,
  `incident-response` and `spec-driven-development` start shipping their OLDER canonical
  bodies. Determinism first, content merge second (task 008) — but the two must land close
  together or the fix trades one silent staleness for two.

- [ ] **`review-record.py` cannot express the verdict reviewers actually give.** A reviewer
  that ends a round with "apply this one fix, then execute without a fourth round" is giving
  a CONDITIONAL — and `write` accepts `CONDITIONAL` while `check` treats it exactly like
  `REJECTED`: "Recorded CONDITIONAL (91) — does NOT authorise execution". Measured
  2026-08-23 on `ops-canonical-skill-wins.json`. The decision is in `VALID_DECISIONS`
  (`review-record.py:42`) but there is no path from it to an authorised execution, so the
  only ways forward are a round the reviewer explicitly said not to run, `--no-approval`
  (which launders the gate), or self-issuing `APPROVED` (which the review-record machinery
  exists to prevent). All three are wrong; the review had to be bounced back to the
  reviewer purely to change one word. **Options:** (a) let `check` accept CONDITIONAL when
  the ops.json hash still matches the snapshot the reviewer signed AND the record carries
  the applied conditions; (b) drop CONDITIONAL from `VALID_DECISIONS` so the taxonomy stops
  offering a verdict the gate cannot honour. Owner call — (a) widens what authorises
  execution, which is a security-adjacent surface.
- [ ] **`resolve_plan`'s prefix normalisation destroys the only match it had.**
  `ops-hardening-implementer-contract.json` declares `"plan": "ops-hardening-implementer-
  contract"`; the loop strips the `ops-` prefix, and the real file is
  `plan-ops-hardening-implementer-contract.md` — so the strip removes the very prefix that
  made it resolvable, and the config passes with every operation unchecked. Found
  2026-08-23 by fuzzy-matching all 36 configs the newly honest `check-plan-artifacts.py`
  reports as plan-less: 31 are genuinely plan-less, 4 are follow-up configs against distinct
  plans, and this 1 is a resolution bug. Pre-existing, out of scope for the change that
  measured it. Fix: try the declared value BOTH stripped and unstripped.
- [ ] **The recurrence ratchet earned a check that is not written yet:
  `comment-asserts-what-is-false` reached FIVE entries** across two review rounds of one
  change (a false `force=False` race claim, a wrong line reference, a fabricated docs
  example, a docstring whose own counter-example was false, and a retrospective artifacts
  list naming `.claude/profiles/base/profile.json` — a file that has never existed). Only
  the last shape is mechanisable, and cheaply: `check-plan-artifacts.py` today checks
  config → plan only, so add the REVERSE — every path listed in a plan's "Artifacts
  written"/"Artifacts this change writes" section must appear in some config's
  `target_paths`. That would have caught the fabricated profile path automatically. The
  other four are prose claims about code behaviour and cannot be mechanised; the durable
  mitigation is to cite symbols rather than behaviour that has not been executed.
- [ ] **The bash oracle is INERT on ubuntu, which is the platform CI runs it on.**
  `tests/test_validator_vs_bash.py::TestTheOracleBinds::test_a_validator_with_no_blocklist_is_caught_by_bash`
  holes the validator's `BLOCKLIST` and asserts the oracle catches the mutant. On ubuntu it
  reports `{'errored': 0, 'executed': 338, 'finding_count': 0, 'findings': []}` — 338 payloads
  ran, nothing errored, and the shadow functions never echoed a marker, so a validator with NO
  BLOCKLIST AT ALL passes the oracle. Measured 2026-08-23: **23 passed locally on macOS, all
  four ubuntu jobs red, and red on `main` too** (run 32560538178), so it predates
  `fix/review-loop-gaps` and is not caused by it. This is the `TestTheOracleBinds` half — the
  test whose entire job is to prove the oracle can fail. While it is red, the sibling
  `test_the_shipped_validator_allows_nothing_bash_can_use` passing means nothing: an oracle that
  cannot catch an empty blocklist cannot certify a real one. **Do not "fix" it by relaxing the
  assertion.** Likely suspects, in order: the `ulimit -v 262144` line in `PROBE`
  (`scripts/check-validator-vs-bash.py:111`), which glibc/ASLR may make unsurvivable for bash on
  Linux while macOS ignores it via `|| true`; then `export PATH=""` interacting with a
  Linux-built bash's function lookup. Tier 3 — security-relevant surface, needs a plan, a real
  review, and a proof that runs on Linux, not on the maintainer's Mac. The durable lesson is
  already earned: a security oracle must be proven to BIND on every platform its gate runs on,
  and this one was only ever proven on one.
- [ ] **Three open minors from `ops-review-truthfulness-batch.json`'s round-3 approval
  (94/100, 2026-08-23).** None blocks; all three are in `scripts/check-plan-artifacts.py`.
  (a) **`[^/]*` matches a `..` segment**, so a plan writing `src/*/x.py` names
  `src/../x.py`. Blast radius chased rather than assumed: `validate-config-json.py`
  APPROVES a `..` path and `execute-json-ops.py:258-268` confines without normalising, so
  `src/../x.py` executes as `x.py` — a different file than the pattern implies, while
  `src/../../x.py` is blocked. Not a security boundary (the gate grants nothing) but the
  same "plan names a DIFFERENT file" class one level deeper. Fix: reject any token or path
  containing a `..` segment, or `os.path.normpath` before matching.
  (b) **The docstring's reason for rejecting trailing-glob tokens is wrong for honest
  ones.** It says a token ending in `*` "is markdown emphasis, not a path pattern" — true
  of `*src/main.py*`, false of `docs/*`, which is a real pattern the matcher now rejects.
  The behaviour is the safe direction (cries wolf, never licenses) and no plan relies on
  it, but the stated reason is exactly the class this batch closed. Fix: describe the
  trade-off instead — rejected because indistinguishable from emphasis, at the cost of
  honest trailing globs. Also worth recording: the reviewer could construct NO input where
  removing the `startswith`/`endswith` guard changes the outcome, so the segment rule is
  the mechanism and the guard is defence-in-depth — do not credit it as the fix.
  (c) **Theoretical regex backtracking** at 8+ adjacent `*` in one segment (0.9s at 8,
  >8s at 12). Unreachable from real prose — the three real multi-star tokens in the corpus
  run in 0.000s because `/` literals bound each segment. Fix: `re.sub(r"\*+", "*", pattern)`.
- [ ] **Nothing archives an executed ops config, and the queued-ops gate punishes the next
  committer for it.** `execute-json-ops.py` has no archive step; `.claude/plans/archive/README.md`
  documents archiving as a manual `mv` plus a table row. So every execution leaves
  `test_queued_ops_configs_validate_against_head` red until a human remembers — measured twice
  this session, once caught by a reviewer AFTER the commit had already gone in (`7b39cb9`).
  Fix: have the executor move the config and stub the README row on success, or make the gate's
  failure message name the exact `mv` command.
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
- [ ] **Three hooks are named `-gate` but cannot block.** `file-guard-gate.sh`,
  `injection-scan-gate.sh` and `security-reminder.sh` contain neither `exit 2` nor a `deny` call,
  so nothing they detect can stop a tool call — the name promises enforcement the file does not
  implement. Found 2026-08-21 while building the dispatch registry, by re-deriving blocking
  capability from the shipped hook files rather than from their names; the same pass corrected the
  repo's own count of blocking-capable hooks from 6 to **7** (`reflection-gate.py` and
  `iron-law-gate.py` do block). They are registered `advisory` in `dispatch-registry.json`, which
  is honest about what they do today and is *not* a decision about what they should do. **If any
  of the three was ever meant to block, that is a live security gap, not a naming nit** — it means
  a guard has been reporting for an unknown length of time while enforcing nothing. Decide per
  hook: promote to blocking (with a fail-closed path and a mutation proof), or rename so the file
  stops claiming to be a gate. Owner call — silently changing enforcement behaviour is not
  something a refactor gets to do.
- [ ] **`.claude/hooks/dispatch.sh` has no per-handler timeout, and deliberately does not claim
  one.** Handlers run synchronously and unbounded; the dispatcher cannot observe a timeout, so
  exit 124 in the codec is only ever a code a handler chose to report. Not implemented because
  macOS has no `timeout(1)`, a bash-3.2 background+poll+kill wrapper cannot reliably kill a
  handler's descendants without a process group, and `pre-commit`/`pre-push` legitimately run for
  minutes, so any bound short enough to help would break them. Recorded here rather than written
  into a comment as if it existed (hard rule 6). If a bounded wait is ever wanted, it needs a
  per-handler `timeout_s` in the registry with an explicit unbounded opt-out, and a mutation proof
  that a sleeping handler yields exit 2 on a blocking event.
- [ ] **A hook can fail open by degrading to exit 0, and no codec can catch that.** Re-measured
  2026-08-21 at `5f3e322`: `echo '' | env -i PATH=/nonexistent /bin/bash
  .claude/hooks/ops-enforcement.sh` exits **0** — `dirname`, `cat` and even `lib.sh`'s `deny` are
  command-not-found, so the guard emits nothing and ends successfully, and 0 is ALLOW. (An earlier
  `PATH=/nonexistent bash ...` reading of 127 measured the *interpreter* lookup failing, so the
  hook had not run at all; 0 is the stronger and more alarming fact.) The dispatcher's codec fixes
  every failure it can *observe* — a handler that cannot start, crashes, or is signalled — but a
  handler that returns 0 while doing nothing is indistinguishable from a handler that allowed. The
  fix belongs in the hooks: `set -e`, an `EXIT` trap, and a positive "I ran" assertion per guard.
- [ ] **Footgun: never place a git worktree under the session scratchpad.** A full-suite run
  inside a worktree rooted at a scratchpad path deletes its own CWD mid-run, because a test
  `rmtree`s scratchpad paths. Symptom is a mid-suite cascade of `FileNotFoundError`/`getcwd`
  failures that looks like a test-ordering bug. Put worktrees outside the scratchpad.

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
- [ ] **Mechanical check: no DoD gate may be asserted from a prior round inside a plan's gate-evidence table.** The eight DoD gates are a fixed list, so a test can assert that no file under `.claude/plans/` contains `not re-run` / `prior round` inside a gate-evidence table. Class has recurred three times on `perf/token-efficiency`: (1) round-3 `mypy` omitted from the evidence table, which became the blocking H1-new; (2) `gen-model-policy --check` labelled `[prior round, not re-run]`; (3) `shellcheck` labelled the same — (2) and (3) were green when re-executed, so milder than (1), but the class earned a mechanical check per .ai/REVIEW_GUIDE.md. Proposed only; **not** implemented by `plan-generators-that-cannot-drift` and deliberately absent from its ops.
- [ ] **The secret self-scan has no exemption model, so documenting a pattern trips it.** `tests/test_day_one_blockers.py::TestSelfScanIsClean` greps every *tracked* file for 13 secret patterns, with no way to mark a file as legitimately describing one. Three occurrences on this branch, each a different file class: (1) an earlier revision's test module (recorded in that test's own docstring); (2) `tests/test_memory.py`, whose secret-refusal cases need a body that looks like a secret — fixed by assembling the literal from parts; (3) `.claude/plans/archive/README.md`, whose row *explaining fix (2)* quoted the literal and re-reddened the gate — caught by an adversarial reviewer, not by the author, who had claimed the gates green from a suite run predating the row. Splitting literals works but every future author must rediscover it, and the failure mode is a red branch nobody expects. Options: an explicit allowlist with a stated reason per entry; a `# selfscan: expected` marker the scan honours; or scanning only added lines in a diff. Prefer whichever keeps the scan fail-closed by default — an exemption model that is easy to apply silently is worse than the workaround.

## Closed 2026-08-23

- [x] **`ck doctor --strict` on a fresh full install was NOT registry drift.** Diagnosed
  and closed: the rc 1 came from three deliberately-blank `project.*_cmd` values, not from
  `i18n-workflow`. That skill ships from `templates/skills/`, lives outside
  `.claude/skills/` by design, and the installer's reconciliation is covered at
  `tests/test_install_receipts.py:354-386`. Filling the commands (under `project`, not the
  root — a root write fails the schema check) gives rc 0 at 26/26. Both the outcome and the
  diagnosis are now pinned by tests, so the misattribution cannot recur.
- [x] **`ops-mcp-probe.json` archived unexecuted** by owner decision. Its verdict was
  recorded under a different plan's slug before records keyed on ops identity; verified
  still `NO RECORD` after that fix, which stops the class but cannot rescue this artifact.
  Its `--probe` would execute vendor server argv on the operator's machine, unsandboxed, so
  a fresh plan and review is the right route if the capability is wanted. See the archive
  README row.

## Icebox

Cross-project promotion of `.claude/knowledge/issues/` entries into the global
`~/.claude/skills/learned/` tier — explicitly out of scope for ledger v1 (project-local only);
needs a redaction story and a per-project provenance field before it can be considered.

## Post-execution findings — dispatcher wiring + approval machinery (2026-08-22)

Filed by the adversarial diff review after lanes A and B landed. Ranked.

- [x] **[HIGH] FIXED 2026-08-22** — landed via `ops-dispatcher-payload.json`, APPROVED 94/100 bound to `726d3b9`. The resolver moved to `.claude/hooks/dispatch_resolve.py` and the payload travels on stdin. **The `ck_mktemp` fix this row proposes is WRONG and must not be retried:** it adds an `RLIMIT_FSIZE` kill surface, so the boundary emits `rc -25` (SIGXFSZ) instead of a fail-closed `rc 2`, breaking hard rule 2. Reviewed twice (82, then 61) and abandoned at `b7d1cc8`. Original row, for the record:
  **[HIGH] A tool payload over ~1 MB is blocked, with a misleading cause.** `.claude/hooks/dispatch.sh:254` passes the payload to the resolver through the ENVIRONMENT, so once it crosses `ARG_MAX` (1048576) `execve` returns `E2BIG`, the resolver fails, and the registry-resolution branch exits 2. Measured: 1000.1KB -> rc 0; 1020.1KB -> rc 2 `BLOCKED: could not resolve hook handlers for PreToolUse`. Before the wiring addendum, PreToolUse hooks received the payload on stdin and had no such limit, so this is introduced by that change. Fail-CLOSED, so not a safety hole — but a real functional regression on a realistic operation (writing a >1 MB file), and the message names neither the size nor the cause. Fix: write the payload to the already-available `ck_mktemp` file and pass the PATH in `CK_PAYLOAD_FILE`, or move the resolver body to a `.py` file beside `dispatch.sh` so stdin is free (the heredoc currently occupies it). Add a regression test asserting a 2 MB `Write` payload returns 0.
  **UPDATE 2026-08-22 — the obvious fix is WRONG; do not repeat it.** An attempt to spill the
  payload to a `ck_mktemp` file and pass `CK_PAYLOAD_FILE` was planned, reviewed twice and
  ABANDONED (scores 82 then 61, six MAJORs). Measured by the round-2 reviewer, private TMPDIR,
  `ulimit -f 100`, 2 MB payload: unpatched -> **rc 2** (fail-closed, correct); patched -> **rc -25
  (SIGXFSZ)**; patched with the cleanup removed -> **rc -25** as well. Three things that attempt
  taught, all verified by execution:
  (a) `printf '%s' "$PAYLOAD" > "$file"` is the first payload-sized write in `dispatch.sh` and
      creates a new RLIMIT_FSIZE kill surface. A signal-killed hook emits neither 0 nor 2, which
      breaks hard rule 2, and the host plausibly treats it as NON-blocking — so the cure converts
      a fail-CLOSED usability bug into a possible fail-OPEN safety bug.
  (b) The `|| { rm -f ...; }` cleanup never fires on the disk-full route at all: the shell dies
      before the `||` is evaluated, and the pre-existing EXIT trap already removes the file. The
      round-1 claim of a 102,400-byte leak did NOT reproduce.
  (c) Regression tests that force the partial write with `ulimit -f` SKIP on macOS and on Linux
      CI, because SIGXFSZ is default-fatal on both. A proof that skips binds nowhere.
  Any real fix must (1) make the write error observable rather than fatal — a subshell, or
  `trap '' XFSZ` — (2) assert rc in {0,2} under `ulimit -f`, (3) force the failure by a route
  that yields a real write error (unwritable target dir), not a fatal signal, and (4) archive its
  own spent config, or `test_queued_ops_configs_validate_against_head` turns the suite red.
- [ ] **[MEDIUM] `decisions.merge()` is dead code with zero coverage, while `dispatch.sh:48-49` claims it is parity-tested.** Mutating `worst = ALLOW` -> `worst = DENY` (making every merge return DENY) leaves the suite green; `grep -rnE "(decisions\.merge|[^_a-z]merge)\("` over src/tests/scripts returns nothing. Only `from_exit_code`, `to_exit_code` and `clamp_advisory` have shell<->Python parity tests. The live merge is the bash one and IS mutation-proven, so no live risk — but the file most likely to be trusted as canonical is the one nothing checks. Fix: add a parity test driving both merges over the 4^n decision tuples (n<=3), OR delete `merge` and narrow the dispatch.sh sentence to the three functions genuinely covered.
- [ ] **[LOW] `printf: write error: Broken pipe` leaks to hook stderr on payloads >=100 KB.** `.claude/hooks/dispatch.sh:346` — a handler that exits before draining stdin SIGPIPEs the writer. Verdict unaffected. Fix: `2>/dev/null` on that printf, or redirect into hooks.log.
- [ ] **[LOW] `stderr_preview` persists up to 512 bytes of handler stderr to disk.** `.claude/hooks/lib.sh` `ck_emit_hook_decision`. A guard that blocks a secret-bearing write and echoes the offending text would land it in `.claude/runtime/events/*.jsonl`. Mitigated: that directory is gitignored and advisory stdout is not captured. Fix: one-line note in docs/HOOKS.md that the event log may contain guard stderr.
- [ ] **[LOW] Four PreToolUse hooks are structurally unable to block.** `file-guard-gate`, `security-reminder`, `pre-commit`, `pre-push` are `tier: "advisory"` in dispatch-registry.json. Verified none has an `exit 2` path today, so no live regression — but a future `exit 2` added to a file named `*-gate.sh` would be silently clamped. Fix: a test asserting these four remain `exit 2`-free, so the clamp and the artifact cannot drift apart.

## Approval-machinery defects, found by using it (2026-08-22)

Three separate defects made the Iron Law's own enforcement path unable to service a
multi-config plan. All hit live while executing two approved Tier 3 plans.

- [x] **[HIGH] The record slug is derived from the PLAN filename, but the executor's gate derives it from the OPS filename.** FIXED 2026-08-22 (`ops-approval-machinery.json`): records key on `ops_slug()`, the same inversion `_approval_slugs()` performs, so the two sides agree by construction. **Does NOT retroactively rescue `ops-mcp-probe.json`** — its verdict was recorded under a *different plan's* slug (`generators-that-cannot-drift`), which neither the ops key nor the legacy plan-slug fallback reaches; verified still `NO RECORD` rc 3 after the fix. It needs a fresh review record, which is a review decision, not a machinery one. `review-record.py write .../plan-generators-that-cannot-drift.md .../ops-mcp-probe.json` records under slug `generators-that-cannot-drift`; `execute-json-ops.py` then refuses with `no review record for 'mcp-probe'`. So an addendum whose ops file is named differently from its plan CANNOT be approved through the sanctioned path at all. `ops-mcp-probe.json` reviewed APPROVED 93 and is still unexecuted for this reason alone. Fix: derive the slug the same way in both, or let the record carry an explicit slug.
- [x] **[HIGH] `validate-config-json.py --stamp-baseline` breaks the approval binding it coexists with.** MISDIAGNOSED — this is a SEQUENCING defect, not a code defect, and no code was changed. Measured on unmodified HEAD: stamp -> record -> execute works (`Baseline: verified`, `Successful: 1`); only record -> stamp gives DRIFT. Re-stamping after approval SHOULD force re-review, since the artifact changed. Closed 2026-08-22 by making the DRIFT refusal name `--stamp-baseline` as the likely cause and pinning both orders with tests. **A sidecar redesign was drafted and CUT after two rejections (82, then 62 with five MAJORs) — do not retry it:** requiring a `baseline_sidecar` declaration made `--stamp-baseline` reject every config the repo's own generator emits (`implementer.md:83` runs it unconditionally, non-zero = STOP); it restored tamper-evidence only against deletion (re-stamping after drift, or swapping in a baseline computed over an unrelated file, both still reported `Baseline: verified`); and `echo '{}' > <config>.baseline.json` disabled the drift gate at rc 0, the exact outcome its own docstring called "strictly worse than having no gate". Stamping writes a `baseline` key of target-file hashes INTO the ops config; the review record binds `sha256(ops.json)`; so stamping changes the hash and the gate then refuses with DRIFT. Two anti-drift mechanisms that cancel each other, and any plan whose steps say "stamp, then execute an approved config" is unrunnable by construction. Hit live on lane B; recovered by restoring the approved snapshot (verified the ONLY delta was the injected key, all 16 operations byte-identical). Fix: stamp to a sidecar file, or exclude `baseline` from the hashed bytes.
- [x] **[MEDIUM] Records key by plan slug, so a plan with a core config AND an addendum can hold only one — the second silently overwrites the first.** FIXED 2026-08-22 — same root cause as the slug HIGH above, same one-line fix; bound by a test asserting the first record survives byte-identical. Writing the probe's verdict destroyed lane B core's approved snapshot (105925 -> 10524 bytes). Recovered by re-recording the core from its archived config. Fix: key by ops identity, or store one record per config under the plan.
- [x] **[MEDIUM] Nothing in the reviewer prompt chain asks for the `=== REVIEW ===` block that `review-record.py --from-review` parses.** FIXED 2026-08-22 — and the row was slightly imprecise: `reviewer.md:242` was not silent, it deferred to the caller ("if the caller specifies such a format, it wins"), so a caller who did not spell it out still got prose. The block is now MANDATORY and specified inline, with a placeholder form that cannot parse as a real verdict, bound by a test that extracts the template from the prompt and feeds it to `parse_verdict`. A reviewer can therefore return a flawless verdict the approval gate cannot consume. Five review rounds this session produced prose; execution stalled until `/review` (which DOES specify the block) was run. Fix: put the block in the reviewer contract in `.claude/agents/reviewer.md`.
- [ ] **[MEDIUM] `subagent_type: reviewer` has no Bash, so it cannot run the mutation proofs its own prompt demands.** PARTIALLY ADDRESSED 2026-08-22: `reviewer.md` no longer demands proofs it cannot run and routes gate-binding review to `code-reviewer`. The tool grant itself is left OPEN and owner-gated — granting Bash to a plan-review agent widens a tool surface to fix a prompt inconsistency, which is the more expensive of the two options the row offers. Rounds 1-2 of both lanes scored plans without executing anything and found nothing; every finding that mattered came from `code-reviewer`. Fix: grant `reviewer` Bash, or retire it in favour of `code-reviewer` for any review that must prove a gate binds.

## Findings from Phase 1b (2026-08-22)

- [ ] **`check-context-floor.py` reports failure and returns success.** `scripts/check-context-floor.py:88` is `return 1 if (check and not ok) else 0`, so the no-flag form can never return 1 — and `CLAUDE.md`'s command block prescribes exactly that form, so the next person copies the invocation that cannot fail. CI is safe (it passes `--check`) and the floor is genuinely under budget (91233/99000), so nothing is masked today. Fix: return 1 on failure regardless of the flag, switch `CLAUDE.md` to `--check`, and mutation-prove it by forcing an over-budget state and asserting the no-flag form returns 1. **Shipping as its own commit — a DoD gate, not a backlog row.**
- [ ] **The drift matcher rejects `./`-prefixed mentions.** `scripts/check-plan-artifacts.py:70`'s lookbehind rejects a preceding `/`, which is what closes the shadowing hole but also rejects `./install.sh` and `../scripts/x.py`. Measured: 5 occurrences across 5 of 67 plan documents; nothing is red today because it only bites when the `./` form is an artifact's SOLE mention. Verified fix: permit a leading `./` or `../` run only — `r"(?:(?<![\w./-])|(?<=\.\./)|(?<=\./))"` — which keeps every closed shape closed. A leading absolute `/scripts/...` stays excluded: that names a different file.
- [ ] **`VERDICT:` vs `DECISION:` — every reviewer prompt asks for a block `review-record.py` cannot parse.** The agents emit `VERDICT: APPROVED` / `SCORE: 94/100`; `review-record.py:51-52` requires `^DECISION:` and a bare integer `^SCORE:`. Recording a real verdict today required hand-translating the block, which is exactly the manual step that lets an unrecorded verdict slip through as `NO RECORD`. Fix: accept both spellings and a trailing `/100`, or change the prompts — and add a test that feeds a reviewer-shaped block through `parse_verdict`.
- [ ] **INTERMITTENT (its own row, NOT the `TestCli` checkpoint family): `test_pipeline_e2e.py::test_sigint_mid_batch_reports_exactly_once_and_rolls_back`.** Failed once in a full suite; then passed 5/5 standalone, 11/11 whole-file, on patched and pristine trees, and a second patched full suite was clean. Flake surface is `tests/test_pipeline_e2e.py:595-599` — a 30 s poll for five files with `assert proc.poll() is None`, a load-sensitive subprocess race. Nothing in the Phase 1b delta touches its call graph: it `Popen`s `execute-json-ops.py` directly and no hook fires. **Do NOT merge this into the documented `TestCli` checkpoint-clearing family** — that mechanism is different and a shared symptom is not evidence. Contributing condition: the suite grew +22 tests in this batch.
- [ ] **Fleet-sync marker co-ownership (task-008 debt, deliberately carried).** `ck adapt` will own the `CLAUDEKIT:` marked region in `.claude/local/CLAUDE.project.md`; fleet-sync keeps the root `CLAUDE.md` region it appends today. Two writers maintaining two files. Owner decision 2026-08-22: **carry it, do not retire the fleet-sync path now.** Recorded so a later reader does not mistake it for an oversight. Consolidation is owner-gated (16 downstream repos).
- [ ] **`.claude/hooks/*.py` are outside `ruff check src/ tests/ scripts/` and mypy's scope**, so `dispatch_resolve.py` ships unlinted by the DoD gate (clean when linted by hand). Also `dispatch_resolve.py`'s `os.environ["EVENT"]` raises `KeyError` -> rc 1 rather than the module's `exit 3` vocabulary (pre-existing shape, fails closed).
- [ ] **`review-record.py:213` decodes reviewer prose in text mode.** Deliberately left alone in Phase 1b: it reads prose, not a hook payload, and a decode failure records no verdict, so `/implement` reports `NO RECORD` — fail-closed. Filed for diagnostics only.

## Findings from the approval-machinery repair (2026-08-22)

Filed by round-3 adversarial review of `ops-approval-machinery.json`, which APPROVED at
90/100. None is blocking; all three were left rather than patched, because the review
ceiling is three rounds and changing the ops.json would have invalidated the verdict bound
to its bytes.

- [ ] **[LOW] The new DRIFT text names `--stamp-baseline` unconditionally, so it misdiagnoses the legacy-fallback path.** Measured: a config resolved through the legacy plan-slug fallback, never stamped and carrying no `baseline` key, still printed `Most likely cause: --stamp-baseline was run AFTER the verdict was recorded` — the real cause was a cross-config legacy borrow. Fails closed and the trailing "Otherwise re-run /review" line still applies, but it reproduces the misdiagnosis shape the edit exists to cure, in a different branch. Fix: gate the five lines on `"baseline" in current_config`, or suppress them when the record was resolved via the fallback.
- [ ] **[LOW] `cmd_diff`'s legacy fallback resolves silently.** `cmd_check` prints `NOTE: ... using the legacy plan-slug record '<key>'` and its test asserts that line ("the operator cannot tell which key satisfied the lookup"); `cmd_diff` adopts the same fallback with no NOTE. Fix: emit the same line.
- [ ] **[MEDIUM] The executor's legacy-record path — the actual production back-compat surface — has no test.** `TestLegacyRecordFallback` drives `review-record.py check`, never `execute-json-ops.py` on the ACCEPTING path. Verified working by hand (legacy key `core`, config `ops-addendum.json` with a matching `plan` field -> `Approval: reviewed verdict verified`, `Successful: 1`; non-matching -> fails closed exit 3). So a future change to `_approval_slugs` or the fallback could detach every record already on disk with the suite green — the same verification gap that produced the two `vacuous-check` instances this plan closed. Fix: one case asserting the verdict is consumed through the executor for a legacy-keyed record.
- [ ] **[LOW] `parse_verdict` accepts a verdict with no anchored block at all.** `review-record.py:137-138` falls back to `body = text` when `_BLOCK_RE` finds nothing, so loose reviewer prose containing `SCORE: 93` and `DECISION: APPROVED` on their own lines records as a real verdict. Pre-existing; the now-mandatory block makes it less likely to be hit, never worse. Fix: require the block, or state that the bare form is intentional.
- [x] **[LOW] `reviewer.md`'s human report template omits `REVISE`.** ~~It offers `DECISION: APPROVED | CONDITIONAL | REJECTED` while `VALID_DECISIONS` accepts four.~~ **Closed by task 008 batch 4** (2026-08-24), which found this was one of FOUR contradicting definitions, not one omission, and replaced them with a single taxonomy in `HANDOFF_PROTOCOL.md` where findings gate before score.
- [ ] **[LOW] Degenerate ops filenames collide onto record key `_`.** `.json`, `.ops.json`, `plan-.json`, `ops-.json` all key as `_` under `ops_slug()` while `_approval_slugs()` returns `[]`. The disagreement direction is fail-CLOSED (NO RECORD), so it is a curiosity rather than a hole.

- [ ] **[MEDIUM] Two skills are agents in skill costume, waived in `ck lint` rather than fixed.** `gan-harness` and `opensource-pipeline` both declare `allowed-tools` containing `Agent`, so they can spawn agents while being loaded INTO an agent's context — routing around `.claude/agents/_shared/INVOCATION.md`, where spawning is scoped. Both are genuine orchestration prose (Generator → fresh Evaluator → Adjudicator; Sanitizer → Forker → Packager), so converting them is agent-corpus work that belongs with task 008 batch 3, not with batch 4 which added the rule. Waived BY NAME with a reason each in `.claude/lint-baseline.json`; `ck lint` fails on any un-waived grant. Fix: convert both to agents, or state that an orchestration skill is a deliberate category and narrow the rule's rationale.
- [ ] **[LOW] ~~`test_receipt_via_cli_clears_the_checkpoint` is flaky~~ — FOLDED into the UNEXPLAINED-intermittent entry above, where it already belonged.** Filing it separately was a duplicate: that entry was WIDENED on 2026-08-22 to cover this exact test as a member of the family. The stated cause here — `read_session_token` returning empty — was **checked and does not hold**: `read_session_token` returns `Optional[str]`, never `""`; a `None` token raises `TypeError` in the parent before `subprocess` runs, and an empty string parses fine (`rc=0`). So neither value produces the observed `--session-token: expected one argument`. **No cause is claimed.** What the 2026-08-24 observation does add is a NEW SIGNATURE, recorded on the entry above.
- [ ] **[LOW] `ck lint` is not wired into CI.** Batch 4 shipped the gate and the DoD runs it by hand; adding it to `.github/workflows/ci.yml` is a separate, owner-gated decision because it turns three advisory rules into a merge blocker.
- [ ] **[LOW] `declared_tools()` does not read five valid-YAML forms.** Multiline flow list, CRLF block list, a blank line before the first block item, a duplicate `allowed-tools` key (it reads the first, YAML takes the last), and a scoped grant like `Agent(*)`. Each verified to have 0 occurrences in the corpus, and listed in `src/claudekit/lint.py` as a measured boundary rather than an oversight. Adversarial-only: a skill author determined to hold `Agent` can take a waiver instead.

Windows support · MCP server for the ops engine · `ck cost`/`ck trace` observability · team features · README translations refresh policy (i18n/ currently drifts silently — no CI check).
