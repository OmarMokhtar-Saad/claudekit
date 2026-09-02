# AI Session Changelog

Reverse-chronological log of AI working sessions on this repository. Append an entry per significant session: date, model, scope, changes, follow-ups. (Product changes go in `CHANGELOG.md` — this file tracks the *work sessions* themselves.)
## 2026-09-01 — graph `verify`/`render`/`diff`/`impact`, and what parallel planning costs

Two independent reviews **REJECTED at 59 and 60**, then **all gates green** after one
repair round. Suite unchanged from baseline.

**What landed.** Four subcommands on `project-graph.py` (573 -> 1312 lines). The graph was
already an agent-emitted JSON IR behind a deterministic validator — `build`/`query`/`hubs`/
`path`/`stale` shipped long ago — so the gap was never the IR, it was that nothing checked
the agent's *claims* against disk and nothing could draw the result. `verify` rejects
missing nodes, dangling endpoints and `extracted` edges whose source file never mentions
the target. `render` emits mermaid or a self-contained HTML page and refuses to draw an
unverified graph. `diff --against` gives before/after on architecture. `impact --ops`
turns "does this plan touch architecture?" into an exit code, and the planner now runs it.

**The expensive lesson: parallel planning against one file.** Four planners each produced a
plan that applied cleanly *alone* and validated APPROVED. Applied in sequence, three of four
failed — p1 duplicated a print string two others used as a unique anchor, rewrote a docstring
line a third anchored on, and inserted a subparser inside a fourth's anchor. Two agents
independently extracted the same `fan_counts` helper (ruff F811, mypy no-redef); two more
independently implemented the same god-node rule under different names. None of it was
visible to any single planner, and none of it was visible to the validator.

**The finding worth more than the feature.** `validate-config-json.py` approved all four
plans the executor then refused. It checks that an anchor *exists*; the executor requires
it to be *unique*, evaluated against the post-predecessor file. A gate that green-lights
what the engine rejects is why a broken sequence reached review at all. **Follow-up, not
yet done:** assert `count(find) == 1`, and add a mode that validates a sequence against its
projected post-state.

**Security.** `--ops` and `--against` confined their input with `normpath` + `startswith` —
textual, so a symlink inside the root pointing outside it passed while the error text
claimed containment held. Both now `realpath` before the check; verified by exploit and
re-test. The pre-existing `build --input` path shared the weakness.

**Open.** `render`'s HTML/SVG layer ships inside `project-graph.py`; both reviewers flagged
the god-file risk, which is ironic given `impact` exists to detect exactly that. Recorded,
not resolved — a split is the obvious follow-up. Also: the pipeline agent bodies are at
their context ceiling (42930/43000 after this change), so the routing lines had to be
compressed and the explanation pushed into the skill.

## 2026-09-01 — `/ask` + `request-shaping`, and three gates that outlived two approvals

Plan review **62 REJECTED → 91 APPROVED**. Suite **7057 passed / 4 failed → 7060 passed
/ 1 failed**, that one being an unrelated pre-existing flake (see below).

**What landed.** A `request-shaping` skill and an `/ask` command: input-side request
normalization. Every prompt asset in the corpus was output-side — `writing-plans`,
`writing-skills`, `prompt-evaluation`, `token-optimization` all improve text *we* emit —
so nothing normalized the incoming request, and the blast-radius tier was picked from an
unstructured sentence while `planner` re-derived scope every run. `/ask` extracts the six
dimensions the pipeline actually routes on (task verb, scope, constraints, success
criteria, derived tier, evidence to read), asks at most three questions and only for
Blocking gaps, emits a fixed Shaped Request block, then names the next command **without
running it** — which is what keeps it outside the Golden Rule's approval gate.

**Provenance.** Idea adapted from the MIT-licensed `nidhinjs/prompt-master`; **no code
vendored**, so no attribution row is owed. Deliberately left out: its 13-framework router
(RTF/CO-STAR/RISEN/CRISPE — ceremony the planner does not consume), its 30+ foreign-tool
profiles (Midjourney, Zapier, Cursor — this kit's only target is its own pipeline), and
its model-spec verification step, because `claude-api` already owns model facts and a
second model table is a staleness liability.

**The finding worth keeping: review approval is not suite evidence.** Two plan reviews
cleared this change and the full suite then failed four tests, none of which a reviewer
could have seen without executing. Round 1's own catch was already of that class — a bare
`file_create` registers nothing, so `gen-registry.py --check` would have failed — and it
could not be fixed with a `run_command` op, because `ALLOWED_RUN_COMMANDS` holds only
formatters and `python3` is absent; widening that allowlist is a security-surface change,
so the generator run stayed out-of-band with `test_skill_is_registered` to red if it is
skipped. Then **four more** fired after both approvals. Three at full-suite time: **`ck lint`'s
command-budget** (a *new* command must fit 40 lines; `ask.md` shipped at 83 and was
compressed to 40, the detail moved into the skill where it belongs), the **`.agents/`
Codex mirror** membership gate, and the **queued-ops gate** — an ops config fails
validation the moment it succeeds, its `file_create` anchors consumed by the files it
creates, so executing is not the last step; archiving with a README row is.

**The fifth is the one worth remembering, because the suite could not see it either.**
The adversarial code review (75 REVISE) found `scripts/gen-plan-index.py --check` red on
`.claude/plans/INDEX.md`: adding a plan file left the index stale, which turns **CI**
(`.github/workflows/ci.yml:144`) red while all 7061 tests pass. Four gate assertions had
been added to `tests/test_request_shaping.py` and the index gate was not among them —
the docstring enumerated the gates the author thought of, which is exactly the failure
mode. Now asserted. **Five gates, one change, none of them logic.**

The same review killed a **vacuous test**: `test_command_and_skill_agree_on_the_block`
was `delegates or restates_fully`, and `delegates` only checked that two strings appear
in `ask.md` — both appear permanently, so the right side never evaluated and the test
could not fail for the reason its own message gave. Mutation-proved by the reviewer with
a four-field block renaming `DONE WHEN` to `SUCCESS`. Rewritten to check every fenced
block that mentions `TASK:` against the full field set, and re-proved against that same
mutation. Three further content defects, all in `ask.md`: it routed Tier 1 to
`/validate-ops`, **a command that exists nowhere in the corpus**; it documented
`--depth=quick` when `command-flags` defines `--depth=[1-5]`; and it specified
`--format=json` over "six field names" when the block has **seven** — six *dimensions*,
seven *fields* — so the JSON path silently dropped `ASSUMED`, the record that exists so
Risky/Minor gaps do not become questions.

**One flake, not ours, worth fixing separately.**
`test_validator_vs_bash.py::TestContainment::test_the_sandbox_is_removed` failed in the
rerun and passes in isolation, on a stashed clean tree, and on the whole file. It
snapshots the **shared** system temp dir for `validator-oracle-*` before and after
(`tests/test_validator_vs_bash.py:279-283`) rather than using `tmp_path`, so any
concurrent process running the oracle makes `after != before`. A code-review agent was
running against the tree at the time. Pre-existing and independent of this change; left
alone rather than folded in, but it will keep firing whenever the suite runs beside
anything else.

**Floor cost: zero.** The skill carries `disable-model-invocation: true`, so
`context_floor.model_invisible` excludes it — skill descriptions stayed at **8817/9000**
across the change while only command descriptions moved (4851 → 4942). That mattered:
there were 183 chars of headroom, and a model-visible description would have breached the
gate in a commit that looked unrelated to it.

**Fleet.** Distributed to the 13 kitted projects (26 files + a registry entry each).
`fleet-sync.py` could not do it — it is a one-shot script hardcoded to the old
skill-enhancement plan — so an additive distributor was used: dry-run default,
skip-never-overwrite, nothing committed downstream. Downstream ships
`skills-registry.json` but **not** `gen-registry.py`, so the entry is appended once by
hand; `ck doctor` would not have complained (it only resolves `agentMapping` references),
but a registry that omits an installed skill is the silent divergence `skills.py` exists
to prevent. The repo-local test file is not distributed — it imports
`claudekit.context_floor` from `src/`, which no downstream project has.

**Follow-ups.** The distributor lives in the session scratchpad, not the repo: the
approved plan's Files table does not include it, and widening approved scope unasked is
the thing the plan gate exists to stop. If fleet distribution of single assets recurs, it
deserves a real `.claude/operations/scripts/` home with its own tests.

## 2026-08-25 (fourth period) — the rejection retro loop, and four rounds spent on one root cause

Commits `74e5fed`, `b355a4f`, `648cef5`. Plan review **85 → 89 → 93 → 92 → 88 → 87 → 93**
across seven rounds; the completion batch **60 → 75 → 92**. Suite 3026 → **4412 passed**.

**What landed.** Reviewers emit the anchored verdict block on every round and rejecting
rounds are recorded, so `rounds[]` finally accumulates. `review-record.py` writes a durable
brief on the 2nd non-approving round with an `INDEX.jsonl` sidecar, fail-soft — it runs after
the verdict is on disk and cannot fail `cmd_write`. Plus `transcript-miner.py`, `flow-analyst`
+ `/flow-retro`, `rejections search|stats|classify|backfill`, a 14-fixture held-out set with
`scripts/heldout-check.py`, and `planner.md` Phase 0 searching prior rejections. Design follows
ExpeL (arXiv:2308.10144), NOT Reflexion — evidence in
`.claude/reports/research/self-learning-agent-loops.md`.

**Four of seven rounds found the same root cause one layer further out**, and each round's
TEST had manufactured the precondition production lacked: shell filter and parser read
different blocks (a code-reviewer APPROVE of a diff could have authorised execution of an
ops.json it never scored) → `$PLAN_FILE`/`$review_output` bound nowhere, injected by `env` →
the report file the fence reads written by nothing, written by the fixture → producer ordered
after consumer in the shipped document. Fixed structurally, not per-instance: the shell no
longer parses verdicts at all, and the harness now DISCOVERS step order from the shipped
headings instead of asserting one.

**`--write` would have committed two other repositories into this one.** `rejections backfill`
globbed `~/.claude*/projects/*` — 99 roots, 2019 transcripts — and 9 of the 17 rows its dry run
proposed came from AppiumLens and shsmartassistant-qa. Because the whole fleet is kitted, the
`ops-<slug>` filter scoped nothing. Caught by running the real dry run, not by reading the
glob. Now scoped to this project's transcript root, fail-closed: 9 foreign rows → 0.

**Lessons this period paid for.**

1. **One definition, two scopes — three times in one feature.** Shell regex vs `parse_verdict`;
   `valid_session` vs `_SESSION_ID_RE`; a slug derived by regex vs `ops_slug()`. Each time two
   pieces of code answered the same question differently and the disagreement was invisible
   until something crossed the boundary. Now pinned by a test.
2. **"Newest transcript = my session" is false exactly where this ships.** 21 transcripts
   touched in 2h, the newest belonging to a SUBAGENT, two sessions writing concurrently. A
   wrong session id is strictly worse than `unknown` because nothing downstream detects it —
   so resolution refuses rather than guesses, verified across 11 crafted corpora.
3. **A gate whose condition cannot be satisfied is worse than no gate.** A reviewer issued
   CONDITIONAL, but `cmd_check` requires the literal `APPROVED` and the condition
   (`heldout-check.py --freeze`) can only run AFTER the execution the token forbids. Named
   rather than routed around; the reviewer called it its own defect and converted.
4. **Concurrent sessions share a working tree AND a git index.** Another session ran `git add`
   while this one ran `git commit`; the commit swept their staged files in. Repaired by
   rewriting the unpushed commit with an explicit pathspec, which ignores the index. Use
   `git commit -- <paths>` when any other session may be live.
5. **A clean sample is not a clean property.** The miner read "0 leaks" on a real transcript;
   once credential scrubbing was added, the SAME transcript yielded 19 redactions. The first
   measurement was of paths only.

**Follow-ups.** `/flow-retro` cannot run until the corpus has >=3 sessions. The held-out set is
one-directional by construction — all baselines APPROVED, so it detects a harsher reviewer and
never a laxer one; stated in the manifest, README, analyst prompt and script output. Three
command budgets sit at exactly 100% (`code-review.md` 140/140, `refine.md` 466/466,
`review.md` 125/125) and the context floor at 99.6%, so the next added line breaks a gate.

## 2026-08-25 (third period) — §A2b + D1 + D3, and a licensing chain the plan got wrong twice

Skills 75 → 79. Plan review **84 → 93**; code review **75 → 75 → 93**. Owner approved §8
items 4 (D1) and 5 (D3) in session; §8 is annotated accordingly.

**What landed.** The §A2b testing trio — `whitebox-invariant-testing` (build the invariant
table from the SUT's own source, attack each promise through harness knobs, never edit the
SUT), `defect-pinning` (RED pins quarantined so the gate stays green, re-run live on every SUT
change and restored verbatim, five-state coverage map), `ai-agent-testing` (two-suite doctrine
plus the agent-invariant catalog) — harvested from the shsmartassistant-qa pass. Plus D3's
`prompt-evaluation` and D1's Trail of Bits methodology in `differential-security-review`.

**The plan review's value was two gaps that would have shipped.** `allowed-tools` was missing
on **two** of three A2b skills, not one — it corrected my own framing of the question. And
§A2b had no description budget at all: §7's "Both ≤160 chars" textually covers only A1/A2. The
contested baseline resolved by arithmetic rather than by re-measuring and hoping — §2.2's 7934
was pre-Phase-A, plus 299 for the two checklist descriptions = the live 8233. Four new
descriptions at ≤150 land the row at 8817/9000.

**The code review's value was entirely the licensing chain, and it took two rounds because my
first fix was incomplete rather than wrong.** Adding ToB content makes
`differential-security-review/SKILL.md` a **CC BY-SA 4.0 derivative inside an MIT
distribution** — and the precedent the plan cited (`verification-gap-lens`) is MIT→MIT, so not
precedent at all. Round 1 caught the missing notice. Round 2 caught that the notice **never
entered the sdist** (`MANIFEST.in` has an explicit include list), so `LICENSE` would have
pointed at a file the artifact did not contain; that prose inserted into `LICENSE` drops
automated MIT detection below the ~98% dice threshold licensee/ScanCode use, making the
remediation worse than the ambiguity; and that `README.md` still told users "No restrictions."
Fixed by keeping `LICENSE` byte-exact, adding `THIRD-PARTY-LICENSES.md` to both `MANIFEST.in`
and `license-files`, and correcting the README. **Verified by building the sdist and looking
inside it**, not by reading the config. Two smaller ones in the same family:
`token-optimization` carried an unlisted MIT attribution, and the 46ki75 row asserted
"unstated" when the research note had only said "not stated in SKILL.md — go check the repo".

**Three shell defects, all `bash -n`-clean, all caught by executing.** `src/test/**/` matched
nothing under real bash 3.2.57 (macOS default has no globstar) so the pin-check block was
silently a no-op; unquoted `$PINS` word-split on a path containing a space; `grep -P` is
GNU-only and BSD grep exits 2. Proven fixed against scratch trees, including one with a space
in the path.

**An allowlist can only re-confirm what you already listed.** The cross-link test intersected
`referenced` with a fixed seven-name set — so the pointer that actually breaks, a typo or a
later rename, was skipped rather than caught, which is the opposite of its docstring. Inverted
to the superset direction with a declared `NOT_SKILL_IDS` set, and mutation-proven against
both `prompt-evalution` and a renamed `eval-harness`.

**My own prior commit was red.** `fleet-sync.py` shipped in `521f4b9` with three mypy
annotation errors: the DoD sweep had been run over `src/` only, and `.claude/operations/scripts/`
is in mypy's scope. Fixed, and §A7 now says to run mypy over both — along with the archival
step, which was the other undocumented out-of-band task (a config fails the staleness gate the
moment it succeeds).

## 2026-08-25 (second period) — Phase B: the fleet sync, and the guard the plan did not have

12 kitted repos received Phase A. 20 skill directories copied, 20 files edited, 36
superseded directories deleted, everything left **uncommitted** in every downstream repo.
Report: `.claude/reports/fleet-sync-2026-08-25.md`. Tooling:
`.claude/operations/scripts/fleet-sync.py` — the thing BACKLOG §9 said did not exist.

**The finding: the approved dedupe would have broken 84 files.** B3 was approved for six
superseded skills, guarded on *local customisation*. That guard passed — all six are
byte-identical fleet-wide. It is the wrong guard. Three of the six are named in 84 real
`## Skill Loading` directives (`coordinator.md`, `devops.md`, `security-scanner.md`,
`gan-build.md`, `loop-start.md`, `prp-implement.md`), and downstream registries have no
`renamed` alias map to resolve a name whose directory is gone. Deleted the three nothing
references; **held** `session-continuity`, `dependency-audit`, `verification-loop`.
Closing it needs 48 renames + 36 line *removals* (those files already name the successor,
so renaming would make them load it twice), or a downstream alias map. Owner's call.

**The plan's stack matrix was wrong in three places**, and it mattered — AppiumLens would
have received a Kotlin checklist for a 2054-file Java codebase. The "~34 `.py`" that made
every Java project look dual-stack was ClaudeKit's own `operations/scripts/` plus
`.claude.bak-*` copies. Census now measures tracked files with `.claude/` excluded.

**Three bugs, all found by running rather than reading.**

1. **The peer survey cached directory PATHS.** The real run deleted the modal copy while
   processing project 1, then crashed comparing project 2 against a directory that no
   longer existed. It had passed every dry run, because a dry run deletes nothing. Now it
   snapshots modal *content* up front — a snapshot cannot be invalidated by the deletes
   it exists to authorise. Recovery was surgical: ApiForge's three directories restored
   from a byte-identical peer, verified by digest, and NOT via `git checkout -- .claude/`
   — every one of these repos carries pre-existing uncommitted work that would have
   destroyed.
2. **The registry update was gated on `L["added"]`** — on what *this run* copied. AppiumLens's
   skills had landed in the crashed partial run, so the re-run skipped the copy as
   "already present" and skipped the registry rows with it, leaving a registry naming
   none of its three new skills. Reconciliation is state-based now: what is on disk, not
   what this run happened to do.
3. **zsh does not word-split unquoted variables.** Two survey loops silently reported
   `0/6 duplicates` and `no checklists anywhere` for the entire fleet. Both were false.
   Caught only because the claim contradicted a plain `ls`. Surveys moved to Python.

The lesson common to 1 and 2: **a dry run cannot exercise a code path whose precondition
is a completed mutation.** Both bugs live in exactly that gap, and it is the same gap the
rejection-retro loop's four rounds kept finding.

## 2026-08-25 — the JVM half of per-language review, and three skills that did not do their job

**Phase A of `plan-fleet-skill-enhancement.md`.** Phases B (fleet distribution) and C/D
(stragglers, external adoptions) are owner-gated and NOT executed; the owner's decisions this
session were: **B3 dedupe approved with the diff-guard**, **C1 rest-framework refresh deferred
to its own session**, **C2 qa-agent-pro skipped**, and the context-floor failure to be fixed in
session — which turned out to need no action (see below).

**What shipped.** Two new skills (`java-review-checklist`, `kotlin-review-checklist`) plus
`code-reviewer` routing for `.java`/`.kt`, and repairs to `using-superpowers`,
`mcp-integration` and `security-checklist`. 7 operations, zero errors, backup at
`backups/fleet-skill-enhancement-phaseA-20260825-060931-011120/`. Full suite 3645 passed after
the archive fix; ruff, mypy, shellcheck, gen-docs, gen-registry, gen-model-policy and
check-context-floor all green.

**Three review rounds: 78 REJECTED → 82 REVISE → 91 APPROVED**, recorded with `rounds[]`
history. Both non-approving rounds found the SAME defect class one layer apart: *a plan step
with no operation behind it*. R1 — A9 promised behavioral tests and no operation created any.
R2 — the test that got added then asserted registry rows that **no ops.json can produce**,
because `allowed_run_commands()` is allowlisted to formatters (`black`, `ruff`, `prettier`, …)
so an operations config cannot invoke a generator at all, and regen is out-of-band by design.
Resolved by asserting the **invariant** (`gen-registry.py --check` exits 0) rather than the
post-state — which also catches a hand-edited registry, where asserting the two rows would not.

**The finding that mattered was the MINOR one, and execution found it, not review.** R3
objected that the Detect-block test's docstring claimed `bash -n` guards against a silently
wrong regex, which it cannot. Correct — and the real bug had already been caught by *running*
the blocks: `grep: repetition-operator operand invalid`, from `yaml\.load\((?!.*SafeLoader)`,
a PCRE negative lookahead in an ERE pattern. bash parsed it happily. **Python's `re` accepts it
too**, so a `re.compile` check would have passed the exact bug it was meant to catch. The test
now hands all 25 extracted patterns to `grep` against `/dev/null` and fails on exit 2;
mutation-proven against the original pattern.

**Two things found while executing that are worth knowing next time.**

1. **`gen-registry.py` cannot auto-register a skill that an agent already declares.** It has a
   `skill_entry_from_disk` path for unregistered skills, but its unknown-skill guard (`ERROR:
   <agent> loads skills missing from the registry`) returns 1 *before* that path runs. So
   create-then-route order matters: `ck skill new` registers as it creates, and a skill created
   any other way must be bootstrapped into the registry before the agent routes to it.
2. **The context-floor failure was already gone.** It read 44186/43000 at session start and
   42816 at the end without this work touching a pipeline agent — a concurrent session executed
   `ops-retro-fixups.json` at 08:58, which reclaimed the floor by moving RATIONALE out of
   `planner.md`/`reviewer.md`. This repo has a documented history of concurrent sessions on one
   tree; **measure the floor at the moment you need the number, not at session start.**

**Open / not done.** `.agents/skills/` is a tracked 71-skill mirror of `.claude/skills/` (75),
already missing `python-review-checklist`, `typescript-review-checklist` and
`verification-gap-lens`. No generator writes it, nothing in `scripts/`, `src/` or `install.sh`
references it, and it is documented nowhere. It is now 4 behind. Either give it a generator or
delete it — but that is an owner call, not a side effect of this plan.

## 2026-08-24 (fourth period) — one record instead of two, and all six jobs closed

Two halves. The first was docs and records only; the second executed the three owner-gated
plans after the owner approved each in session. **Two new CI gates landed.**

**Second half — the three approved plans.**

- **`plan-enforcement-trio.md`, and the order is the point.** The new
  `scripts/check-fileguard-differential.py` landed and was proven against a real baseline
  *before* the file-guard allowlist was written; the allowlist then **failed the gate on all ten
  paths as undisclosed**; each was then disclosed with its reason. That is the sequence the owner
  chose over the faster one. **The gate's first run SKIPPED** — at `origin/main` there is no
  `.claude/hooks/file-guard.sh`, because batch 1 promoted it out of `templates/hooks/`, so
  `git show` failed and the script returned 0. A renamed subject is not an absent one, and a gate
  that skips passes forever; fixed with a legacy-path fallback. Also: `ExecutionLock.release()`
  stopped unlinking the lock file (the unlink *was* the race it appeared to prevent), and
  `config.schema.json`'s "195+ patterns" became a description with **no count at all**.
- **`plan-command-bash-parse-gate.md`.** 682 lines of command bash, never linted, now gated on
  parse errors only. **The near-miss:** the first hand-run mutation targeted `ship.md`, which has
  zero ```bash fences, so nothing landed and the gate said GREEN — caught by `grep`, not by the
  gate. The in-suite mutation test builds its own fixture for that reason.
- **`plan-hook-log-dedup.md`, scoped down on purpose.** Item 3 only: the three hooks writing to a
  **cwd-relative** log path. The other 11 `log()` definitions were left alone — delegating them
  widens `lib.sh`'s blast radius from 11 hooks to 23 across 16 downstream repos with no defect
  behind it. **My first behavioural test was vacuous**, and only the mutation proof showed it:
  the old code appended with `2>/dev/null`, so with no directory in the foreign cwd the write
  failed silently and "no stray log" was trivially true.

**No independent review for any of the second half.** No `code-reviewer` was spawned; each plan
records that rather than implying a verdict.

**First half — docs and records only.**

- **The commissioning premise was false, and finding that out was the period's main result.**
  The handoff said 45 of `review/code-review.md`'s findings were "unchecked, not probably
  fine", and asked where new verdicts should live. `review/code-review-triage.md` already held
  all 108 findings with verdicts, committed at `8f54f55` — an ancestor of `HEAD`. The "45" came
  from `.ai/BACKLOG.md`'s *separate* 75-finding P2/P3 enumeration of the same review, with
  different IDs and different totals. **Two triages of one file, neither pointing at the
  other.** Every one of the 45 already had a verdict one directory over. `.ai/BACKLOG.md` is now
  a pointer; the triage file is the single record.
- **Re-verified all 53 LIVE rows against `HEAD`, 78 commits after they were recorded.**
  **13 are now FIXED** — F37, F47, F57, F59, F70, F80, F91, F92, F93, F95, F98, F99, F100 — F68
  is half-fixed, and 40 are still live. Appended as a dated section rather than rewritten, so
  the 2026-08-20 evidence survives.
- **§6's paths had moved wholesale.** Its eight rows cite `templates/hooks/`, which no longer
  exists — those hooks were *promoted* into `.claude/hooks/`. Their findings did not retire,
  and F61/F63/F65 **lost** the "template-only, unwired, so contained" mitigation, so they went
  up in priority, not away.
- **Diagnosed the three `drifted` plans, and two of the three warnings are the tool's.**
  `review-record.py`'s legacy plan-slug fallback compares a second ops config's bytes against a
  *different* config's approved hash, so an addendum that never had a verdict is reported as
  having drifted from one. Each plan's primary config is clean (94, 93, 93/95).
  `plan-capability-tiers`'s drift is **genuine** and no approval was re-recorded for it. Filed
  as a `[MEDIUM]` backlog row; the fix touches the approval machinery and is owner-gated.
  **The handoff's prescribed remedy does not apply** — `check-plan-artifacts.py:147-148` states
  plans stay at `.claude/plans/` while only configs move to `archive/`, so moving the three plan
  documents would break the resolution that comment exists to describe.
- **The command diet, measured and deliberately not sold as a context win.** `refine` 464,
  `ship` 228, `gan-build` 227, `opensource` 222, `loop-start` 220. Command *bodies* are outside
  the always-on floor — `check-context-floor.py` budgets only descriptions, at 4753/6000 — so
  the exit is readability and per-invocation cost. Filed as TECH_DEBT row 21. `refine.md` is not
  extractable: its bash blocks are fragments with no loop wrapper, so "extract the script" means
  writing one on a CI-facing path.
- **Three defects of my own, recorded where the next reader hits them.** (1) I accepted the
  handoff's framing before running `ls review/`, which would have shown the triage file
  immediately. (2) The `.ai/TECH_DEBT.md` row landed as a second `| 16 |` because I read only
  the head of that file before picking an ID — renumbered by its own ops config, not by hand.
  (3) My first mutation proof for the command-bash gate targeted `ship.md`, which has **zero**
  ```bash fences, so nothing was inserted and the gate reported GREEN; a `grep` for the
  mutation caught it, not the gate.

## 2026-08-24 (third period) — eight live findings fixed, and a three-week mystery solved

Two commits. 2932 tests pass, 0 failures.

- **`7aa0e45` — four `cli/main.py` findings.** Colour was unconditional (ANSI into every
  pipe, file and CI log); `ck doctor` hung forever on a wedged `bash`/`git`; `ck config`
  raised a traceback on a malformed `config.json`; `cmd_rollback` had two byte-identical
  branches. **One existing test had to change and that was itself the finding:**
  `test_gate_scope.py` asserted raw ANSI in output captured through a pipe, so it *required*
  the defect — and was the only thing in the repo that would have "caught" the fix.
- **`0e35e91` — three hook findings.** The checkpoint cap was exceeded on every other run
  (the shell guard pruned at `count >= max` while the pruner skipped at `count == max`;
  measured as a 3→4→3→4 oscillation, each overshoot a retained git stash); the registry was
  read-modify-written twice with no mutex; failure output was cut to `tail -20`, i.e. the
  summary rather than the cause. **The review named three truncation sites — asserting the
  property found six**, including the lint and build gates that block `git push`.
- **THE `UNEXPLAINED` INTERMITTENT IS DIAGNOSED.** `secrets.token_urlsafe` draws from the
  base64url alphabet, so **1.53% of session tokens begin with `-`** (306 of 20 000), and
  every caller passed `--session-token <value>` — argparse read the token as the next flag
  and exited 2 with the exact recorded signature. Unreproducible for three weeks because
  **the coin flip is inside the secret**. Fixed at generation (redraw, not strip — stripping
  shortens the secret), with `--session-token=` at the call sites for tokens already on disk.
  Tests pin the behaviour, the length, both CLI forms, **and the premise**, so the guard
  cannot go vacuous if the alphabet changes.
  **What caught it was the rule adopted one commit earlier: keep the whole suite output in
  a file.** `receipt_diagnostic()` had fired twice before and the harness discarded it both
  times — `/dev/null` once, `tail -4` once, the second of those mine, earlier the same day.
- **Four defects of my own, and they are the useful part.** Markdown backticks inside a
  `python3 -c "..."` shell string, where the shell would have *executed* them — shellcheck
  caught it, which is the argument for the command-bash gate still unlanded. A test that
  forbade the bare string it was documenting. A fake wedged `bash` that forked a `sleep`
  and orphaned it, proving `timeout=` does **not** bound the wall clock when the probe forks
  — **the limit is now recorded at `PROBE_TIMEOUT` rather than claimed away**. And
  `git checkout --` to undo a mutation, which also reverted a not-yet-committed fix.
- **One mutation proof reported GREEN for the wrong reason.** BSD `sed` silently ignores the
  `0,/re/` address, so the mutant never applied. A mutation proof is only evidence if the
  mutation landed — the same lesson as a gate that cannot fail, one level up.
- **Deferred with numbers, not a shrug:** the `log()` dedup across 14 hooks. Four distinct
  implementations, and only 2 of the 14 source `lib.sh` at all, so it is a 12-file change to
  the hook layer for deduplication with no user-visible defect behind it.

## 2026-08-24 (second period) — task 008's paper trail, a gate that scanned nothing, and 688 lines of unlinted bash

Three commits, all documentation or test surface. Suite green throughout — the last
commit bundles three plans that share three files, with a `Plan-Id:` trailer for each.

- **The paper trail was a DoD violation on `main`.** `CHANGELOG.md` documented batches 1, 2
  and 4 and said nothing about batch 3 — nine agent names users invoke, removed. Written
  now for users, with the routing risk in consumer terms rather than left in
  `.claude/plans/`. `SESSION_STATE.md` and `TASK-008-SIGNOFF.md` brought to task 008
  complete, the sign-off recording **the five places it was measurably wrong**.
- **`test_queued_ops_configs_validate_against_head` was decoration.** It listed top-level
  `.claude/plans/*.json`, of which this repo has **zero** — every config lives in an
  `ops-<slug>/` subdirectory. 50 configs there, **35 already failing validation**: the
  exact condition the gate reports, accumulated underneath it. **Probed, not reasoned
  about** — an invalid config in a subdirectory leaves the test green, the same bytes at
  top level turn it red. Widened to a walk that prunes `archive/` by name, with the
  widening proven on a *constructed* tree, because coverage that depends on the repo
  containing a violation is the failure being fixed. **Fourth vacuous gate found here in a
  month.**
  - Archive-first, widen-second, one commit: widening first reddens the suite on 35
    pre-existing failures, which is how a gate gets reverted instead of fixed.
  - **The widened gate then caught this plan's own configs twice.** Working on first run.
- **`review/code-review.md` triage, partial and honest about it.** The BACKLOG count was
  wrong twice (76, then 88 — both counts of *mentions*, including the severity legend);
  structurally the file holds **75** findings. 30 verified: **19 already fixed** (mostly
  incidentally, including the `atomic_write` mode-stripping P2 that had already cost real
  damage), **11 still real** with a current file:line each. **45 recorded as UNVERIFIED,
  not implied fine.** Two near-miss verdicts recorded: §6's findings look retired because
  `templates/hooks/` is gone, but batch 1 *promoted* those hooks and four are still live;
  and `lib.sh` existing is not the duplicate-`log()` fix, because `lib.sh` does not define
  `log()` and 14 hooks still do. Both came from reasoning about a fix instead of grepping.
- **688 lines of command bash, never linted, six parse errors.** Job 5's assigned framing
  was not achievable — there is no `refine.md` script to extract, only fragments with
  `<TASK>`/`<N>` and no loop wrapper, which the test module's own docstring already said —
  so the goal was reached the other way: lint the bash where it lives. **An angle-bracket
  placeholder in a shell command position is an input redirection, not a placeholder.**
  `git branch -D agent/<slug>` deletes branch `agent/`. Six sites fixed, two usage synopses
  re-fenced as `text`, **0 parse errors left across 25 files**. Fixing one exposed a second
  in the same file: shellcheck stops at the first, so the class hides behind itself.
- **One decision left open rather than taken:** the parse-error gate that would keep the
  last item closed is small and currently green, and **not landed**, because enabling a new
  CI gate is owner-gated and the pytest suite is CI.
- **No independent review.** `CLAUDE.md`'s review floor asks for a fresh `code-reviewer` on
  every diff; this session was instructed not to spawn agents. Every plan says so.

## 2026-08-24 — task 008 batch 3 EXECUTED (seven clusters) + its paper trail

Nine agents removed, **29 → 21**, one plan and one commit per cluster. 2901 tests pass,
0 failures. Task 008 is complete; this session also closed the DoD hole the seven cluster
commits left behind.

- **The paper trail was a DoD violation sitting on `main`.** `CHANGELOG.md` documented
  batches 1, 2 and 4 and said **nothing** about batch 3 — the most user-visible change in
  the task, since the names users invoke changed. Seven commits each claimed DoD-green
  while missing it. Written now for users: the rename table, the fact that
  `/doc-updater`, `/docs` and `/model-route` all still exist as commands with the agents
  behind them moved, and the routing risk in consumer terms.
- **The routing risk is disclosed where it will actually be read.** All seven cluster
  plans carried "routing is not demonstrated unchanged", and no user reads
  `.claude/plans/`. Content and names are verified by token diff and by a dangling-
  reference scan; **behaviour is not verified at all**, because the eval cassettes that
  would prove it do not exist.
- **`renamedAgents` had to be built before anything could be deleted.** `gen-registry.py`
  resolved every alias target against `.claude/skills/`, so `renamed: 'python-reviewer' ->
  'code-reviewer'` was a hard error — an agent name could not be aliased at all. The map
  takes `{to, kind}` because four of batch 3's destinations are skills, and a bare name
  cannot say which namespace to validate against.
- **`.ai/TASK-008-SIGNOFF.md` now records the five places it was wrong**, not softened
  into "learnings". Three of them would have destroyed content if followed: the
  "duplicate" `templates/commands|hooks|modes` tree was 24 unique components; three skills
  marked DIVERGED differed by one `description:` line; and the session pair's survivor was
  backwards — `context-keeper` owns the file `session-start.sh:133` reads, while
  `session-continuity`'s state file had no reader or writer anywhere in the repo. The
  sheet and the filesystem disagreed three times and the filesystem was right every time.
- **Executed Tier 1 with `--no-approval`, disclosed.** Three documentation configs, no
  code / schema / API / security surface. Reason recorded in the commit and in the archive
  README row.

## 2026-08-24 — task 008 batch 4 + batch 3 phase 0 EXECUTED

Seven ops configs, zero errors. Batch 4 ships `ck lint`; batch 3 phase 0 ships only its
blocker. 2492 tests pass, 0 failures.

- **The spec's command budget was unreachable, and the ratchet is the honest answer.**
  0 of 55 commands meet ≤40 lines (min 47, median 129, max 466); complying is a
  5138-of-7338-line rewrite. ≤40 now binds NEW commands with a no-growth ratchet on the
  rest. **The gate immediately caught batch 4's own edits growing three commands** —
  and the fix was to tighten those edits to net −9 lines, not to re-baseline, because
  re-baselining would have demonstrated the escape hatch on day one.
- **The reviewer taxonomy had FOUR contradicting definitions, not duplication.**
  `review.md:88` mapped score <70 to REVISE; `reviewer.md:346` mapped it to REJECTED;
  `reviewer.md` declared four decisions in its anchored block and three in its template
  with no REVISE band; `refine.md:276` had a fourth. **Batch 2's own round-1 verdict —
  REVISE at 84 — matched none of them.** One definition now, where findings gate before
  score, so a high score cannot approve past an open blocker. Closes a filed BACKLOG item.
- **The round-1 CRITICAL was mine, and it is the lesson of the session.** The
  `skill-agent-costume` rule read `allowed-tools` only as a same-line value. Two skills
  declare it as a YAML block list containing `Agent` — `gan-harness` and
  `opensource-pipeline` — so the rule silently skipped the exact grant it existed to
  catch, and its "the shipped corpus is clean" test passed over both. I had written that
  false claim into the module docstring, the plan, and the CHANGELOG. **Third gate in
  this repo to pass against a mutant, in the batch whose stated purpose is preventing
  that.** Fixed, then I PROBED the parser instead of reasoning about it and found four
  more evasions review never reported (inline flow list, quoted scalar, quoted block
  item, trailing comment). 13 spellings now swept with a negative case; round 3 invented
  30 more and found none.
- **Waived, not hidden.** The two real violations are waived BY NAME with a reason each
  — never by pattern, which would cover the next skill added — and `--update-baseline`
  cannot silently drop a waiver. Both filed to BACKLOG as conversion candidates.
- **A class earned its second entry: `claim-not-corrected-everywhere-it-was-made`.**
  The same false claim was fixed in the module, found again in the plan, then found
  again in a test docstring one round later. A third instance should earn a grep gate.
- **Batch 3's blocker is gone.** `renamed` resolved targets against `.claude/skills/`
  only, so `renamed: 'python-reviewer' -> 'code-reviewer'` was a hard error and no agent
  could be deleted. `renamedAgents` maps to `{to, kind}` because three of batch 3's
  clusters move agents INTO the skill namespace. **Its tests caught a real bug in my
  first draft** — `fs_agents_set` referenced before assignment, invisible while the map
  was empty and fatal the moment a merge filled it.
- **Review found a verbatim copy and it was right.** The new doctor agent-alias scan
  duplicated the skill-alias scan; both now share one helper, rewritten in the same
  config so there is never a moment with two copies.

**Follow-ups filed:** the two waived orchestration skills; a genuine pre-existing flake
in `test_reflection_ledger.py` (~1 in 9, unrelated to any batch); wiring `ck lint` into
CI (owner-gated — it turns three advisory rules into a merge blocker); five valid-YAML
forms `declared_tools()` does not read, each with 0 corpus occurrences.

**Batch 3 is unblocked, not started.** Seven clusters, one plan and PR each, 29 → ~20
agents. The accepted risk is unchanged: routing cannot be demonstrated unchanged
without the eval cassettes, and every cluster PR must say so.

## 2026-08-24 — task 008 batch 2 EXECUTED (76 → 71 skills)

17 ops configs executed on the real tree (16 planned + `008-b2-17-seam-fixes`, a
disclosed Tier-1 follow-up for two prose defects introduced by the batch itself — see
below). Zero errors. Archived to `.claude/plans/archive/ops-008-batch2/` with a
README row; plan at `.claude/plans/archive/plan-008-batch2-skill-merges.md`. Two
adversarial `reviewer` rounds ran first (84/100 REVISE → 93/100 APPROVED), each
recorded via `review-record.py` against every config's own sha256 — the full batch
was simulated end-to-end in a throwaway worktree before either round, and re-simulated
after round 1's fixes.

- **The sign-off sheet was wrong in two more places, and measurement caught both.**
  `token-budget-advisor` shares no section with either token skill (it is a
  response-depth menu); `codebase-mapping` is the authoring contract for
  `project-graph.py` with test coverage, not near-duplicate prose. And the session
  pair's survivor was **backwards**: `context-keeper` owns the file
  `.claude/hooks/session-start.sh:133` reads, while `session-continuity`'s
  `.claude/session-state.json` has no reader or writer in the repo. Following the sheet
  would have deleted the wired skill and kept the dead one. Owner re-scoped to five
  removals, 76 → 71.
- **A second skills tree nobody had counted.** `.agents/skills/` is tracked, 76
  directories, 42 of them divergent from `.claude/skills/`, and carries a skill name
  the canonical tree does not have. Unshipped, so it is hygiene rather than consumer
  exposure — but it doubles the deletion count, and batch 1's "one canonical tree"
  claim does not cover it. Owner decision: mirror the deletions, carry the divergence.
- **Simulation caught two failures that 16 clean validations missed.** `ck doctor
  --strict` went red *because the merges were documented*: batch 1's alias scan warns
  when a file still names a removed skill, `--strict` fails on any warning, and every
  union survivor names what it absorbed in its seam. Fixed by exempting exactly one
  file — the alias target's own `SKILL.md` — with a test that fails against a blanket
  exemption. Second miss: `test_new_skills.py::test_total_skill_count` asserted `>= 76`
  and names no skill, so no grep for a removed name would have found it. Same class as
  batch 1's `TEMPLATE_DIR` constant.
- **The merges are unions, so the survivors grew.** 200→452, 190→459, 179→334,
  169→489 lines. The corpus loses 5 names and roughly zero tokens; the payoff is the
  mis-routing fix, not size. Union proven by token diff — every backtick span and
  dotted identifier from each deleted file present in its survivor, derived rather
  than spot-checked, and the 127 test fragments were generated from those token sets.
- **Both new gates were mutation-proven before being offered.** Deleting one grafted
  section turns 2 tests red; widening the doctor exemption turns the second alias test
  red while the first still passes.
- **Batch 4 measured, not started.** 0 of 55 commands meet the spec's ≤40 lines (min
  47, median 129, max 466); meeting it is a 5138-line rewrite. Put to the owner with
  options rather than assumed. The other three batch-4 items are confirmed real,
  including that `.claude/agents/_shared/HANDOFF_PROTOCOL.md` does not exist.

**Round 1 found three things I had wrong, all in the plan's own claims,
none in the underlying re-scope evidence:**
- **[CRITICAL]** `.claude/plans/plan-skill-loading-contract.md` was named as a
  consumer to update and no config touched it. Fixed by scoping it out explicitly —
  it's a spent, archived plan (`plans/archive/plan-skill-loading-contract.ops.json`
  confirms it), and editing a dated record falsifies it. The gap was real; the fix is
  disclosure, not a retroactive edit.
- **[MAJOR]** The consumer-acceptance test scanned 3 directories while the plan's own
  proof-table claim promised 6 + `README.md` — the exact "test asserts a property it
  does not exercise" shape this repo keeps re-deriving. Widened to `LIVE_ROOTS` (8
  locations + README), with a test that asserts the scope itself so a future narrowing
  goes red on its own.
- **[MAJOR]** The token-diff union proof (backtick spans + dotted identifiers) had a
  blind spot: prose carrying neither, like `NEVER save secrets, credentials, or API
  keys in the state file` or `One dependency at a time. One version bump at a time.
  Tests after every change.`, was invisible to it. Widened to bold spans and ALL-CAPS
  imperative bullets — 127 → 163 asserted fragments — which also surfaced 5 seam
  labels I had paraphrased instead of carrying verbatim (`Use when:`, `Run this
  skill:`, etc.), now exact.

**Two round-1 MINORs, both fixed:** an intra-operation edit-ordering dependency in
`008-b2-01` (reordered so the graft no longer depends on the rename having already
run); a sentence implying `docs/SKILLS.md`/`docs/ARCHITECTURE.md` might be
generator-owned (they aren't — the only generated block in either file is
`README.md:315-322`; measured and stated with line numbers).

**On the real tree: 2420 passed, 0 failed** (better than the worktree simulation's 17
pre-existing failures, which were worktree/untracked-file artifacts). `ck doctor
--strict` exits 0. Both new gates are mutation-proven: deleting a grafted section
reddens 2 of 165 tests; widening the doctor exemption from one file to every file
reddens its own guard test while the paired test stays green.

**`008-b2-17-seam-fixes` (disclosed `--no-approval`, Tier 1 docs-only):** a duplicated
`e.g.` from an earlier fix to the same graft, and three missing blank lines before a
`---` rule — `add_after` does not append a newline (CLAUDE.md already warns of this
class), so three grafts landed directly against a table row with no separating blank
line. Cosmetic; caught by re-reading the applied diffs, not by any test.

**Follow-ups.** Batch 4, then batch 3 LAST. Batch 4's command-line-budget question is
still owner-gated (0 of 55 commands meet ≤40; meeting it is a 5138-line rewrite); its
other three items are confirmed real and unblocked. Batch 3's stated blocker — the
`renamed` alias map is skills-only, `gen-registry.py` refuses aliasing an agent name —
is still unsolved.

## 2026-08-23 — task 008 batch 1 executed: one canonical tree

Batch 1 is done. 21 ops configs, 79 operations, zero errors, executed in INDEX order
after two adversarial review rounds and a full end-to-end simulation.

- **The sign-off sheet was wrong and re-measuring caught it.** It called
  `templates/commands|hooks|modes` duplicates. They were 24 unique components with zero
  name overlap in `.claude/`. Executing batch 1 as written would have deleted them. The
  three "DIVERGED" skills needing a "three-way merge" differed by exactly one line each
  — the `description:` frontmatter. **A document can be evidence-shaped, full of
  measurements, and still wrong. Re-measure.**
- **Validation is not the gate on a batch.** All 19 configs returned `-> APPROVED`
  while the applied result left 110 tests red and one module that would not parse:
  `validate-config-json.py` checks an anchor is present and unique, not that the text
  it produces is syntactically whole. Two anchors stopped one line short. The plan now
  mandates applying the whole sequence into a scratch worktree first. Simulation went
  110 → 36 → 20 → 17, where 17 is the worktree's own baseline.
- **The simulation found what grep could not.** Seven test files reached the old tree
  through a `TEMPLATE_DIR` constant, not a literal path, so the original six-file list
  was wrong. It also surfaced a promoted `0755` hook landing `0644`, a latent SC2155
  that `templates/` never linted, and my own invariant tests asserting on directory
  existence — which git does not track when empty, so they answered differently in a
  fresh clone than in the tree that ran the batch.
- **Prerequisite:** the ops engine could not delete a markdown file at all (`*.md` in
  `PROTECTED_PATTERNS`, no override; zero `file_delete` ops across 97 archived configs).
  Narrowed to 14 named identity documents, case-insensitively, with a widen-only
  `CLAUDEKIT_EXTRA_PROTECTED`. Reviewed 80 → 93.
- **New gate:** `scripts/check-protected-differential.py`. CI's "no REJECT → ALLOW"
  gate was pinned to the command validator, so the repo's other deny-decision had none
  and this branch's own widening passed CI green.

**Follow-ups.** Batches 2, 4 then 3, in that order. Batch 3 still lands last and still
has no eval-suite gate — that risk is accepted, not resolved.
## 2026-08-23 — the ops engine could not delete a markdown file, and the corpus is all markdown

Task 008 (consolidation) was picked up from a handoff. Nothing of task 008 itself has
been executed; the session went entirely into the prerequisite it uncovered, plus the
plan for batch 1.

- **The handoff's premise was wrong in two places, and re-measuring found it.**
  The three skills the sign-off sheet called DIVERGED and slated for a three-way merge
  differ by exactly ONE line each — the `description:` frontmatter — with `.claude/` a
  strict superset of the body. And `templates/commands|hooks|modes` are not duplicates
  at all: 24 uniquely-shipped components with ZERO name overlap in `.claude/`, so
  "delete the duplicate tree" as written would have deleted real content. Owner chose
  promotion. Lesson worth keeping: the sign-off sheet was itself evidence-shaped, with a
  table of measurements, and was still wrong — re-measure anyway.
- **The blocker: `PROTECTED_PATTERNS` contained `*.md`, matched by basename anywhere,
  with no override.** The kit's corpus is entirely markdown and the ops engine is the
  only sanctioned path for a change (Iron Law), so no component could ever be retired.
  Measured: across 97 archived ops configs there are ZERO `file_delete` operations of any
  kind. Task 008 is not the first plan to hit this — it is the first to notice.
- **Guard narrowed, 80 CONDITIONAL → 93 APPROVED.** Round 1 caught two REAL defects, not
  style: (a) narrowing `*.md` to literal names silently unprotected `readme.md` on
  case-sensitive filesystems, since `fnmatch` normalises case only on Windows — the guard
  had been answering differently on Linux CI and macOS all along, and the glob concealed
  it; (b) `test_the_non_markdown_patterns_are_untouched` used `>=`, so it passed against
  exactly the mutant the plan said it guarded against. Both fixed; matching is now
  case-insensitive (a widening), the list is pinned by equality, and
  `CLAUDEKIT_EXTRA_PROTECTED` lets a consumer widen its own set without forking the file.
- **Gate proven by mutation.** Dropping `CLAUDE.md` from the shipped list goes red in
  three independent tests; restoring the old `fnmatch` call goes red in the casing test.
  Output pasted in the archive README rather than claimed.
- **Batch 1 planned but NOT executed.** `plan-008-batch1-one-tree.md` + 19 ops configs in
  `.claude/plans/ops-008-batch1/` + an INDEX. All 19 validate (they were 3/19 before the
  guard change — that delta is the proof the prerequisite was load-bearing).
  `MAX_DELETIONS = 3` is what makes it 19 configs for 38 deletions; the cap was not raised.

**Follow-ups.** Batch 1 awaits owner go-ahead. Batches 2–4 unchanged. The `.md` guard
narrowing is a real reduction in protection for 16 downstream repos — named plainly in
`CHANGELOG.md`, not buried.
## 2026-08-23 — PR #20 review round: four rejections, four fixes, one queued

Every change this session was rejected on its first adversarial round, and every rejection
was correct. Recorded because the pattern is the finding.

- **Composed-diff review of PR #20: REJECTED 82/100.** Eight commits each carried its own
  verdict; nothing had reviewed the eight together. The composition broke: `ck uninstall`
  dead-ended on the edit `install.sh` instructs every user to make, `--force` promised a
  deletion it would not perform, a fresh `--minimal` install outscored the `--full` superset
  of it, `cmd_adapt`'s docstring asserted the opposite of its own branch, and
  `check-plan-artifacts.py` verified zero paths in the CI run that gates the merge.
- **Uninstall fix: 74 REJECTED → 93 APPROVED.** Round 1 caught the fix BREAKING a test by
  renaming a string it asserts, a `--dry-run` regression, the confirmation prompt as a fourth
  instance of the change's own bug class, and a second test that was vacuous — whose mutation
  proof I had claimed in the plan without running. `deletion-question-answered-with-the-
  provenance-set` hit three entries and earned a ratchet, taken structurally (`modified` →
  `modified_for_receipt`) rather than as a brittle source-introspection test.
- **Skill copy-order fix: 62 → 88 → 91 → 95.** The mechanism was never broken; the PAYLOAD
  was. Making canonical win would have shipped a `spec-driven-development` body contradicting
  four commands `install.sh` ships unconditionally, and stripped the rollback procedures out
  of `incident-response`. Promoting both bodies fixed it, and then rounds 2-3 caught that my
  union silently dropped three canonical sections while the plan claimed "nothing lost" —
  including a role table the appended war-room rules reference by name.
- **Truthfulness batch: 68 → 84 → no verdict.** My fix for a vacuous gate was itself vacuous:
  the test asserted the substring `"path(s) verified"`, which `0 path(s) verified` satisfies.
  Making the gate honest surfaced 27 real findings; triage showed 4 were mine, 19 were one
  false-positive shape (a plan naming 15 files as `.claude/skills/<name>/SKILL.md` is a
  complete description), and 4 were genuine. Round 2 then found my glob matcher used
  `fnmatch`, whose `*` crosses `/` — reopening a class the same file's docstring records as
  closed. Still queued; the reviewer died on an account session limit mid-round 3.
- **CI found two defects the local suite structurally could not.** ShellCheck 0.11.0 here is
  silent on two findings the version CI apt-installs emits, and `tests/test_shell_lint.py`
  shells out to the binary — so the invocation CLAUDE.md prescribes cannot reproduce the gate
  enforcing it. And a test added on this branch asserted `doctor --strict` rc 0, which is a
  claim about whether the runner ships shellcheck: green here and on ubuntu, red on all four
  macOS jobs.
- **Process failures worth not repeating.** I wrote a probe script into the shared scratchpad
  while a reviewer was mid-review and clobbered its applier; only the reviewer's distrust of
  the resulting grep kept a fabricated BLOCKING finding out of its report. I used
  `--no-approval` on enforcement-layer hook files, which exceeds its documented docs-only
  use, because no verdict was obtainable — a reason, not a justification. And
  `review-record.py` cannot express CONDITIONAL: the taxonomy offers a verdict the gate
  treats as REJECTED, so a reviewer saying "apply this one fix then ship" has to be bounced
  back to change one word.

## 2026-08-22 — Claude (Opus 5) — Phase 1b: the >1 MB payload refusal, and four gates that could not fail

**Scope.** The ranked `[HIGH]` in `.ai/BACKLOG.md`: a tool payload over ~1 MB was blocked
with a misleading cause. One config, `ops-dispatcher-payload.json` (18 ops / 25 edits),
APPROVED 94/100 bound to `726d3b9`, across eight review rounds (79, 80, 85, 91, 94, 90, 85,
94).

**What shipped.** The handler-resolver left its `<<'PY'` heredoc for
`.claude/hooks/dispatch_resolve.py` so the payload travels on stdin — a pipe has no
`ARG_MAX` and writes nothing to disk. The temp-file alternative was measured WRONG and must
not be retried: it adds an `RLIMIT_FSIZE` kill surface, so the boundary emits `rc -25`
(SIGXFSZ) instead of a fail-closed `rc 2`, breaking hard rule 2. Two hook fixes travelled
with it — `reflection-gate.py`'s `rc 1` traceback (a hard-rule-2 violation read as
non-blocking) and `iron-law-gate.py`'s undecodable-payload passthrough past the implementer
allowlist. `ck doctor` learned to check helper scripts a hook invokes by path, derived from
the installed hooks themselves rather than a hard-coded name.

**The finding worth keeping.** Three of the four defects I introduced while fixing the
plan/config drift class were the same shape: the check passed because it wasn't checking.
Tightening one branch of a matcher while a green test certified the whole class closed; a
declared `plan` value escaping its directory via `../` so the gate could be aimed at any
file; one of two prefixes stripped, so a config resolved to nothing and passed. The fourth
was the mirror — over-tightening that rejected ordinary sentence-final prose used by 17
occurrences across 12 of 67 plan documents. All four surfaced under mutation, none under
review-by-reading.

**Process note.** The plan/config floor was implemented twice on the same day by two
sessions from the same three-round recurrence. Ours was dropped and folded into theirs
(`scripts/check-plan-artifacts.py`), which is now wired into CI and the DoD; two
implementations of one gate is exactly task 008's class. Local `main` moved mid-session
(`54f82c8` -> `726d3b9`), so the record binds to the later commit.

**Follow-ups filed.** `check-context-floor.py:88` returns 1 only under `--check`, so the
no-flag form CLAUDE.md prescribes can never fail (its own commit, same day). The drift
matcher rejects `./`-prefixed mentions (5 occurrences across 5 documents). A
`VERDICT:`/`DECISION:` contract mismatch between every reviewer prompt and
`review-record.py`. The `test_pipeline_e2e.py` SIGINT intermittent, as its own row. The
fleet-sync marker co-ownership debt.

## 2026-08-22 — Claude (Opus 5) — Phase 1a: repairing the approval path, and cutting a redesign that was worse than the bug

**Scope.** The `## Approval-machinery defects` section of `.ai/BACKLOG.md`, lifted ahead of
the ranked ARG_MAX row because every later plan has to execute through the path it repairs.
One config, `ops-approval-machinery.json` (3 ops / 9 edits), APPROVED 90/100 on round 3.

**The finding that mattered.** Three of the five filed defects were one bug: records keyed
by plan slug, gate resolving by ops filename. One change fixed all three. The second
`[HIGH]` was misdiagnosed in the backlog — `--stamp-baseline` vs the approval hash is a
SEQUENCING problem, not a code defect. Measured on unmodified HEAD: stamp -> record ->
execute works; only record -> stamp drifts.

**What went wrong, and is worth remembering.** Between rounds 1 and 2 the score went DOWN,
82 -> 62. A sidecar redesign for the stamping collision introduced three defects worse than
the one it fixed: it made `--stamp-baseline` reject every config the repo's own generator
emits (`implementer.md:83` runs it unconditionally and treats non-zero as STOP), it restored
tamper-evidence only against deletion, and an empty-object sidecar disabled the drift gate
at rc 0 — while the new code's own docstring said "fail LOUD". The whole of C2 was then cut
and replaced with five lines of refusal text plus tests pinning both orders. **Testing the
premise, not the patch, was what closed it**: one command sequence on unmodified HEAD showed
there was nothing to fix in code.

**Three self-inflicted verification failures, all caught before shipping.** (1) A draft T1
passed against unfixed HEAD because it used `--dry-run`, and the executor skips the approval
gate when nothing will be written. (2) A draft asserted "the run was not refused", which a
gate that stopped *applying* would also satisfy; it now asserts the gate's own success
string. (3) The T4 extractor took the FIRST `=== REVIEW ===` match while `parse_verdict`
documents that only the LAST block counts, so the test read a different span from the parser.
Each is the "gate that reports PASS against a mutant" shape `.ai/REVIEW_GUIDE.md` records as
having shipped twice here.

**Reviews.** Round 1 CONDITIONAL 82 (four MAJORs, including a fail-open *introduced by the
fix*), round 2 REJECTED 62 (five MAJORs), round 3 APPROVED 90. Rounds 1 and 2 each found
defects no amount of re-reading would have: both were run with Bash and executed the
artifact. Round 1's F6 was itself wrong (it asserted no ops schema exists;
`operations-schema.json` is the ops schema, and its `additionalProperties: false` was what
rejected the new key), which is a reminder that a reviewer's prose is evidence, not a ruling.

**Follow-ups.** Six rows filed under `## Findings from the approval-machinery repair`, the
most substantive being that the executor's legacy-record path — the real production
back-compat surface — is still untested. The `reviewer` Bash grant stays open and
owner-gated. `ops-mcp-probe.json` is still stranded: the fix prevents the class going
forward but cannot rescue a verdict recorded under a different plan's slug.
## 2026-08-21 — Claude (Opus 5) — Enforcement runtime: the lane that was written up but never built

**Scope.** Agent A, Phase 0 (0.1 event log, 0.2 dispatcher + merge, 0.3 spill + pruning, 0.4
advisory tier), executed as one ops config (`plan-enforcement-runtime.ops.json`, 18 ops) on
`perf/token-efficiency`. New: `src/claudekit/enforcement/` (`decisions.py`, `eventlog.py`,
`spill.py`), `.claude/hooks/dispatch.sh`, `.claude/hooks/dispatch-registry.json`,
`tests/test_dispatch_merge.py`, `tests/test_event_log.py`, `tests/test_spill.py`; plus the
`gen-docs.py` count regeneration (21 -> 22 hooks) with README/HOOKS.md prose reworded so a hook
that is PRESENT is not described as WIRED, and a BACKLOG entry for the three `-gate`-named hooks
that cannot block.

**The brief said re-verify, so it was.** `git show --stat caa96f7` is two files, both docs —
`.ai/REVIEW_GUIDE.md` and `CHANGELOG.md`. No dispatcher, event log, spill or merge rule existed.
Two of the brief's numbers were wrong in the safe direction and are corrected here: **7**
blocking-capable hooks, not 6, and **26** `settings.json` registrations across 8 events, not
"~20 hooks".

**The defect was measured, and then RE-measured, because the first measurement was wrong.**
`PATH=/nonexistent bash ops-enforcement.sh` reporting 127 was the *interpreter* not being found;
the hook had never run. In a clean environment — `echo '' | env -i PATH=/nonexistent /bin/bash
ops-enforcement.sh` — it exits **0**, and 0 is ALLOW, which is stronger and worse than the number
originally claimed. Lesson recorded rather than buried: a "measured" figure taken through the
outer shell measures the outer shell. The codec's catch-all (`anything that is not 0 or 2 ->
ERROR -> exit 2`) fixes every failure the dispatcher can observe, including the handler that
cannot start (127); a hook that degrades to 0 on its own is not observable and is filed in
`.ai/BACKLOG.md`.

**Round-2 adversarial review (76/100, REJECTED) found a live hang, by executing.** With the
tool-name matcher disabled on an unreadable payload, `echo 'not json' | dispatch.sh PreToolUse`
against the SHIPPED registry started `pre-push.sh`, which runs the full test suite — a multi-minute
stall, and a guard executing outside its contract (`settings.json` had only ever started it behind
`grep -qE "^\\s*git\\s+push"`). Every sandbox test used a synthetic registry, so none could see
it. Fixed at the cause: a handler that declares a `command_matcher` has no command text to match
on an unreadable payload and is therefore NOT APPLICABLE, while handlers without one still run
(fail-closed unchanged; both `command_matcher` handlers are advisory and cannot block anyway). Now
bound by a test that drives the real registry and by a mutant that reproduces the hang on demand.
Also from round 2: there is **no per-handler timeout**, and the comment that implied one is gone
rather than the control being invented (hard rule 6).

**Every gate was proven by mutation before the plan was written.** Each of the three contract
proofs is paired with a mutant test that copies the shipped artifact, applies one mutation
(reverse the merge comparison; make the codec catch-all return ALLOW; disable the advisory clamp)
and asserts the outcome flips. All three flipped. Proof 4 is parametrised over every required
field, and pins the field tuple as a literal in the test file so the schema cannot be narrowed to
silence a failure. One real bug surfaced from executing rather than reasoning: re-exporting the
`spill` function from the package `__init__` shadows the `spill` module and broke 13 tests.

**Deliberately not done.** `.claude/settings.json` is **not** rewired onto the dispatcher — that
is Phase 0b, owner-gated, kept apart because the file is shared with Agent B and because holding
it back keeps this commit a zero-behaviour-change revert. `hooks.log` keeps its prose shape (a
test pins it). Stop-hook DoD gate and the failure-fingerprint breaker remain the next phase.

**Round-3 adversarial review (81/100, REJECTED) found the fix refuting itself.** Round 2's fix was
right, but the test that had asserted the OPPOSITE was left in the tree, red (`assert 0 == 2`), and
the invariant the fix leans on -- a handler with a precondition cannot block -- was enforced
nowhere: adding a `command_matcher` to the shipped **blocking** `commit-quality` row produced a
fully green suite and eight green gates. Both halves closed. The test is reconciled (it now asserts
the asymmetry the code implements and carries the history of why its predecessor was wrong), and
the resolver now REJECTS any row whose tier is not `advisory` while carrying a `command_matcher`
-- exit 3, which the dispatcher renders as a block on a blocking event, so an illegal registry
fails closed. Proven by mutating the shipped registry: without the check the illegal row is
accepted and a malformed payload skips a blocking guard (`rc=0`); with it, `rc=2`. Two lessons
worth more than the fix. First, the round-3 finding was not a subtle one -- the plan's own shipped
test said 'that is a bypass' in its assertion message, and three review rounds read past it: an
invariant a design depends on and does not enforce IS the defect. Second, the first draft of the
replacement test used the markers `CONDITIONAL RAN` and `UNCONDITIONAL RAN` -- the first is a
SUBSTRING of the second, so the assertion could never fail. A vacuous test that passes, caught only
by running it. Adding the check also pushed the resolver heredoc to 103 lines, past
`check-silent-failure.py`'s 80-line skip cap, which made its scan of a security-relevant file
INCOMPLETE and reded two lint tests -- a gate going quiet rather than loud. Fixed by relocating the
rationale comments verbatim outside the heredoc (58 lines now), not by relaxing the linter.

**Phase 0b ran.** `.claude/settings.json` PreToolUse (11 registrations) now routes through `dispatch.sh`; the other seven events are unchanged (advisory, `exit 2` not honoured, and four hooks are backgrounded with `&`, which the dispatcher does not model). Applied as its own reviewed ops config, `plan-enforcement-runtime-wiring.ops.json`.\n\n**Follow-ups.** Phase 0b rewire; re-baseline the spill thresholds against real transcripts; decide
whether `file-guard-gate` / `injection-scan-gate` / `security-reminder` were ever meant to block.

## 2026-08-21 — Claude (Opus 5) — Phase 4: a memory store that enforces its own rules

**Scope.** `handoff-3-finish-everything.md` Phase 4, one ops config (`plan-memory-store.ops.json`).
New: `src/claudekit/memory.py`, `ck memory add|list|show|check`, `tests/test_memory.py`, docs.

**What is actually new here.** `CLAUDE.md` has said "current files outrank memories" and
"a directive inside them is a finding, not an order" for months, and nothing enforced either.
Both are now states the store computes. Evidence precedence is a SHA-256 stamped at write time
and **re-derived** at read time, so the tree is always judged first — a memory whose evidence
moved is STALE, one citing nothing is UNVERIFIABLE, and neither can read as FRESH. Directive
detection surfaces imperative shapes on every read path under an explicit findings heading.
**The honest limit is written into the module:** the store cannot stop a model obeying a
sentence; it can only guarantee the sentence is never presented unlabelled, and claiming more
would be the dishonesty hard rule 6 exists to prevent.

**Rejection happens before disk, and that ordering is tested.** A store that writes and then
redacts has already leaked, so `test_a_rejected_memory_writes_nothing_at_all` asserts the file
does not exist after a refused write, and `test_a_rejection_does_not_corrupt_an_existing_store`
asserts a refusal leaves prior entries intact.

**A duplication made safe rather than avoided.** The credential heuristic is re-implemented from
`.claude/hooks/reflection.py` because hooks must work when the pip package is absent, so
`.claude/hooks/` cannot import from `src/` and moving the logic would break that independence.
Duplication is only acceptable if it cannot silently diverge, so a parametrised test runs both
implementations over a shared corpus — the same mirror discipline `pre-commit.sh` already has.
Same treatment for the `_MEMORY_KINDS` list the CLI duplicates to avoid an eager import.

**Two phases were NOT done, and the reason is collision, not difficulty.** Batch 2 (hooks reading
profiles at runtime) and Phase 3 (generators) are both already planned by other active sessions on
this branch — Agent A's `plan-enforcement-runtime` and Agent B's `plan-generators-that-cannot-drift`.
Doing batch 2 would also have built profile-reading into eleven hooks that Agent A's dispatcher is
about to replace with one. Phase 5 (`ck adapt`) depends on Phase 3, so it is blocked behind Agent B.
Owner chose to defer rather than duplicate or take over another session's authored plan.

## 2026-08-21 — Claude (Opus 5, Agent B) — generators that cannot drift (Phase 3)

**Scope.** `ck skill new` and `ck mcp add`, plus filesystem<->registry reconciliation in
`scripts/gen-registry.py` and the CI step that runs it. Lane: Agent B; Agent A held
`.claude/hooks/**` and `src/claudekit/security/**` concurrently. `scripts/check-context-floor.py`,
`tests/test_context_floor.py` and `.github/workflows/ci.yml` were reassigned to Agent B for this
phase (COORDINATION.md's table did not cover them).

**What binds.** Four mutation proofs, each executed rather than asserted: a skill whose
description would breach the always-on floor is refused with current/added/projected/budget; a
hand-created skill or agent now fails `gen-registry.py --check` (it passed silently before, exit 0
with two mutants planted); `mcp add` past `max_servers`/`max_tools` is refused with current vs
limit; and the generator's own output passes the repo's gates.

**Two things that were wrong in the first draft and are recorded rather than quietly fixed.**
(1) Moving the floor measurement into the package would have broken the three tests that copy
`check-context-floor.py` alone into a temp tree — under CI's editable install the import would have
resolved back to the real repo and kept everything green while measuring the wrong tree. The script
now loads the module from this tree only (`src/claudekit/` or beside itself) and fails closed;
the tests plant it. (2) `check_budget()` counted only our ledger, so servers hand-added to
`.mcp.json` counted as zero — a budget that failed OPEN. It counts the union now, and refuses to
evaluate `max_tools` when a configured server has no recorded count.

**`--probe` was cut.** Measuring a server's tool count by spawning it means downloading and running
third-party code from a `ck` verb, and the denylist allowlists `npx`, `node` and `docker` — it is a
speed bump, not a sandbox (hard rule 6). `--tools N` is required instead. The probe survives as a
separate, owner-gated addendum: `.claude/plans/ops-mcp-probe.json`.

**Round-2 review, two Highs, both design defects rather than typos.** (1) `ck skill new`
left `gen-docs.py --check` red: component counts are generator-owned (hard rule 8), so a
new skill invalidates them by design and the only honest remedy is re-running the
generator. That is now pinned by a test that watches the gate go red and then green, the
CLI names `gen-docs.py` on success (guarded on the script existing, since installed
projects have no `scripts/`), and the DoD carries the follow-up run instead of leaving a
gate quietly failing. (2) The C3 fail-closed fix had no escape: a server in `.mcp.json`
with no ledger row blocked every `ck mcp add`, and the remedy the refusal printed was
itself refused ("already registered"), with no `ck mcp remove` to fall back on. Such a
call now ADOPTS the existing entry — records the count, touches no configuration, adds no
verb — and the budget cannot refuse a cost already being paid. Also: `ck mcp list` shows
the union it enforces on, and the floor gate refuses only on the skill-description
category so an oversized CLAUDE.md no longer makes skills uncreatable.

**Follow-ups.** `.ai/SESSION_STATE.md` is updated by hand after execution (its header is a rewrite,
not an append, and COORDINATION.md forbids reflowing a contended file). Version bump for two new
public verbs stays owner-gated.

## 2026-08-21 — Claude (Opus 5) — `.codex/` removed, and a finding of mine corrected

**Scope.** Investigated the P1 mirror-drift item filed hours earlier in `f5eb927`, and resolved it by
deleting `.codex/` (53 files) rather than by building the gate that entry proposed. Owner approved the
removal against a costed keep-and-gate alternative.

**Every premise for keeping it failed a check.** Nothing installs or packages it (`grep -c codex
install.sh` → 0). Its own `config.toml` set `ECC_HOOK_PROFILE=minimal`, standing down every
enforcement hook it wired. Its `hooks.json` carried 20 hardcoded `/Users/omarmokhtar/...` paths where
`.claude/settings.json` has zero. Eight shell hooks were stale since 2026-07-30 and every diff was
`.claude` being ahead. Its README was byte-identical to `.claude`'s, including `chmod +x
.claude/hooks/*.sh` — it had never been adapted for Codex; the hooks still wrote into `.claude/`.

**A correction I owe.** The original entry called the drift "security-relevant". That was wrong, and I
wrote it without reading the config file sitting next to the drifted hook: under the `minimal` that
`.codex` forced, those hooks never ran, and the file I cited is strict-only besides. The drift was
real; the security framing was mine and unfounded. Hard rule 6 is about the honesty of security
claims, and it binds my own findings, not only the product's docs. Rewritten in place rather than
deleted along with the directory.

**The MAX_DELETIONS tension, named rather than routed around.** DECISIONS 7 caps deletions at 3/plan
and says large removals need multiple reviewed plans; 53 files is 18 plans, which honours the letter
and defeats the purpose. Done as one `git rm -r` under owner sign-off, recorded as DECISIONS 22.
**No flag was added and the cap is unchanged** — what got recorded is the real gap: the ops engine
models per-file deletes and has no directory-removal operation.

**An honest mutant that does not flip.** Removing `.codex` from `SCAN_ROOTS` was needed for accuracy,
but *not* removing it would have failed nothing: the secrets self-scan iterates `git ls-files -- <root>`
and an empty root yields no files. `SCAN_ROOTS` has no missing-root guard. Written into the test's own
comment instead of being left as a silent property.

## 2026-08-21 — Claude (Opus 5) — Layered profiles: `ck profile`, and one guard that was wrong

**Scope.** `handoff-4-profiles.md` Phase 2, executed as one ops config
(`plan-hook-profiles.ops.json`, 17 ops) on `perf/token-efficiency`. New: `src/claudekit/profiles.py`,
`.claude/profiles/` (4 profiles + README), `ck profile list|show`, one `ck doctor` check,
`tests/test_profiles.py`, `.ai/PROFILES.md`.

**The handoff's ground truth was wrong, and the correction mattered.** It described
`ECC_HOOK_PROFILE` as "one env var with two effective values (`minimal` / full)". Measured at
`1a15f36`: **three** values (`minimal`, `standard`, `strict` — `full` is an *install mode*), read by
**eleven** hooks in **four** guard forms, and `reflection-gate` under `minimal` is neither on nor off
but advisory (it runs; it cannot block). Deliverable 4 asked for behaviour-preserving mappings of
what the variable does today — which two profiles cannot express. Four ship, and the deviation is
declared in `.ai/PROFILES.md` rather than quietly absorbed.

**What the gate found on its first run.** `format-typecheck.sh` guarded with a positive list
(`= minimal`, `= standard`) directly beneath a comment reading `runs in strict only`, so every other
value fell through and ran an expensive Stop-time hook — while both sibling strict-only gates use
the negative form. Three review rounds of the hook batch had read that file and found nothing,
because neither line is wrong in isolation. Writing down what the profiles were *supposed* to be and
checking it mechanically surfaced it immediately. Normalised to `!= strict`: identical on all three
real values.

**What was deliberately not built, and is said out loud.** Hooks do not read profiles — that is
eleven fail-closed enforcement scripts and needs its own plan, and *not* touching them is precisely
why `ECC_HOOK_PROFILE=minimal` keeps working by construction. The `agents`/`commands`/`mcp`/`stack`
sections are declarative only; no shipped profile claims a selector that does not exist. Net
asset-count delta: **zero**.

**The binding, and why `unrecognised` is the load-bearing half.** `scan_hook_guards()` re-derives
each hook's per-profile mode from the hook's own text (regex for shell, `ast` for Python, so
docstrings that merely name the variable cannot be mistaken for guards) and **reports** any guard
shape it does not model instead of ignoring it. That is the added-clause recurrence class from
`REVIEW_GUIDE.md` applied before it could bite: a mirror that only notices a CHANGED clause goes
quietly wrong the first time someone ADDS one. Two tests mutate the shipped artifact — flip a
declared row, add an unmodelled guard — and require the failure.

**The review caught the binding lying about itself.** Round 1 (88.7/100, REJECTED) found that the shell candidate test was a substring check for `${ECC_HOOK_PROFILE`, so a brace-less `[ "$ECC_HOOK_PROFILE" = ... ]` guard was skipped *without* being recorded as unknown — neither recognised nor reported, in the one mechanism whose entire purpose is that nothing slips through. The M2 mutant passed because it exercised one unmodelled *shape* rather than the *class*. Fixed to a regex, plus M7/M8. Round 2 (88.8/100, REJECTED) then found the SAME hole one alternative to the right — the alias pattern demanded quotes, so an unquoted `$PROFILE` was skipped just as silently. M9 covers it, and neither alternative requires quotes now. Two instances of one class in two rounds is the real lesson: a candidate filter and a recogniser are different jobs, and both bugs were the filter quietly doing the recogniser's. Worth recording as its own instance of `unreviewed-expansion`: the source line read correctly, and only what it actually matched was wrong.

**Follow-ups.** `.codex/hooks/` has drifted from `.claude/hooks/` with nothing gating it (P1, filed);
hooks reading profiles at runtime; Phases 3–5 of the handoff.

## 2026-08-21 — Claude (Opus 5) — Validator security batch: three bypasses, two CI gates

**Scope.** Executed the queued `plan-validator-segmentation` and everything its reviews forced:
six ops configs, three commits (`ecb3b2b`, `0b97efc`, `4cf1e42`), all on `perf/token-efficiency`.

**What was actually broken.** `ls\nrm -rf /` was **ALLOW in the shipped product**: `_SEPARATORS`
listed `"\n"` but shlex swallowed a bare newline as whitespace, so only the first line's base
command was ever checked. Two more shapes hid a blocked command from the blocklist — a leading
file-descriptor digit (`2>/dev/null rm -rf /` → base `2`) and an empty expansion glued to the
name (`` ``rm ``, `rm$()`, `$''rm`) — both falsifying `BLOCKLIST`'s own docstring ("never
allowed, even in unsafe mode"). Also: `eval`/`exec` matched as bare words anywhere, which is what
rejected `bundle exec rspec`; env-assignment prefixes rejected wholesale; eight build tools
missing from the allowlist. The 18-entry `STILL_BLOCKED` ratchet is now empty.

**Method, and the number that matters.** Nine review rounds across the batch (three plan reviews,
six adversarial diff reviews), and **reading the diff found nothing** — every defect that
mattered was found by executing payloads. Twice a *fix for a finding* opened a hole bigger than
the one it closed: suppressing a backslash escape inside a comment changed quote parity so
`echo # don\'t` swallowed the newline (21 exploitable regressions over a 48k fuzz), and a guard
added to close a false PASS in the new CI gate made every push to `main` permanently red.

**A suite can prove a property it never tested.** All four `COMMENT_ESCAPED_NEWLINE` payloads
rejected on line 1's *trailing backslash*, so line 2's blocklist was never reached — and a mutant
carrying the **byte-identical unfixed splitter** passed every assertion about them. `assert not
ok` was vacuous. Tests now bind the split itself and the reason string.

**Two gates, and the honest boundary between them.**
`scripts/check-validator-differential.py` fails any change that moves a payload REJECT → ALLOW,
with widenings **declared** rather than forbidden. Its own review found the corpus reached 3 of
27 blocklisted commands and 1 of 17 dangerous patterns — so a mutant deleting 46 protections
reported clean. Seeded now, with tests that fail when the seed falls behind the module.
`scripts/check-validator-vs-bash.py` covers what the first structurally cannot: it compares the
validator against *itself*, so a payload both versions wrongly allow is invisible. The oracle
executes what the validator allows, with dangerous commands shadowed. Six rounds, five
rejections, every one a containment defect — including one where **I claimed `unshare --mount`
was a filesystem boundary and it was not**. Claim withdrawn; execution is opt-in locally.

**Ratchet.** `fix-introduces-larger-hole` gained its fourth instance and now has a partial
mechanical check. `validator-executor-divergence` has its first real oracle, scoped honestly to
one seam — the other two still have nothing. `unsafe-mode-matrix-gap` reached three entries and is now a row in that table rather
than a claim about one — review caught it being cited as tracked when it was not.

**Verification.** 1,646 tests green (measured at the time of writing; a second session
is committing to this branch concurrently, so the number moves); all eight DoD gates; `command_validator.py` coverage 97%.
Both CI gates exercised in a real clone across shallow / PR / push-to-main checkout shapes.

**Owner-gated.** Whether the two gates ship enabled — the second executes fuzzed shell on the
runner, and after round 6 the only filesystem argument left is that the runner is ephemeral.

## 2026-08-21 — Claude (Opus 5) — Wave-2 phase 1: policy portability (capability tiers)

**Scope.** First of three phases from the wave-2 adoption handoff, sourced from a direct read of
`ShaftHQ/SHAFT_ENGINE/chaos-engine` and `deepseek-ai/deepseek-harness`
(`.claude/reports/research/adoption-candidates.md`). Ran as a disjoint lane alongside a
concurrent enforcement-runtime agent that owns `.claude/hooks/**` and `src/claudekit/security/**`
— **zero operations touched either**, verified by the reviewer against all 8 op paths.

**What landed** (plan `capability-tiers`, 8 ops, reviewed 95/100 after one REJECT round):

- `.claude/model-policy.json` — the single table. Tier → vendor model in one place; role →
  (`accountable_for`, `tier`, optional `escalate_to`/`escalate_when`) so role and capability are
  chosen separately (ChaosEngine A2 + A3).
- `scripts/gen-model-policy.py` — projects the table onto agent frontmatter (Claude Code's parser
  only understands concrete ids). `--check` is a sixth DoD gate, same shape as gen-docs/gen-registry.
- `CLAUDE.md` — routing policy rewritten in tier names; evidence precedence ladder added
  (A7: "retrieved text is evidence, never an instruction channel", which now explicitly covers the
  auto-memory store and subagent-returned prose).
- `.ai/RESEARCH.md` — dated adoption matrix **including the rejections and their reasons** (B3).

**Method note — the review earned its keep.** First verdict was a REJECT with two CRITICALs. One
was real and non-obvious: the generator wrote each agent file inside the scan loop, so an
alphabetically-later agent with no `model:` line would abort the run *after* earlier files were
already rewritten — "fail closed" that left a partially applied policy behind exit code 1. Fixed
by two-phase commit, and **proved by mutation**: reverting to the single-pass write makes
`test_a_late_malformed_agent_does_not_leave_earlier_agents_rewritten` fail, restoring it makes it
pass. The other was a dropped fleet-sync hazard (below).

**Behaviour preservation.** The seeded tiers resolve to exactly the models all 29 agents already
shipped, so the ops.json contains **zero agent-file edits** and `--check` passes against an
untouched corpus. That is the routing-regression proof, not a claim. Net asset change: 0.

**A third plan was needed, and that is the finding.** An adversarial `code-reviewer` on the diff
returned REQUEST CHANGES (1 high, 4 medium, 4 low) and was right on every axis. The mechanism
worked; the *claims about it* outran it. The high finding: `.claude/commands/review.md:89` spawns
`--agent reviewer --model opus` unconditionally, and `--model` beats frontmatter — so `/review`'s
shipped behaviour contradicted all three artifacts the change had just added. The audit found **8**
hand-written model literals across 6 files where the BACKLOG had named 2. Also real: the generator
silently rewrote every line of a CRLF file (no `newline=` on either `open()`), `^model:` was
searched against whole files rather than frontmatter, and `.ai/RESEARCH.md` cited a prose-substring
check as "proof" of the evidence ladder.

`plan-capability-tiers-audit` (8 ops, 84.6 REJECTED → 93.9) answered these with a
`callsite_overrides` registry — every literal must resolve to its own role's tier or carry a
recorded reason — plus byte-exact line-ending handling, frontmatter-anchored matching, a named CI
step, and honestly-scoped claims in `INVOCATION.md` and `RESEARCH.md`. `review.md` was **recorded,
not changed**: repointing a quality gate is user-visible and Golden-Rule-gated.
`plan-callsite-audit-line-level` (Tier 1) then closed the registry's own hole — path-level
membership made any registered file a permanent allowlist.

**Two rejections caught a plan invalidating itself.** The audit plan's op 1 registered
`model-router.md:103` as a surviving override while its own op 5 rewrote that exact line away, so
the new registry-decay test would have gone red on the first CI run. The registry catching its own
author before execution is the strongest evidence it works — and the reason the evidence in this
entry is mutation output rather than assertion.

## Wave-2 phase 2 (same session)

**2.1 — the eval engine.** `run-evals.py` gains record-once/replay-many cassettes and four
injectable faults, so the suite can run keyless. Caching was easy; **invalidation was the design**:
`prompt_surface()` fingerprints everything the model saw — the agent's own `.md`, the skills the
registry maps to it, the operations-scripts tree, resolved model, tool grants, prompt, fixture tree,
setup files — and replay refuses on mismatch, naming what moved. `--inject` is mutation testing for
the eval suite with an **inverted exit code**; verified live with no API key, all 4 evals reject all
4 faults. Two of the four evals were also found to be running the wrong agent entirely
(implementer on sonnet, reviewer on opus). Review 83.5 → 92. **Round 1 caught a live false-PASS
path:** the operations scripts were outside the fingerprint, yet two evals grant Bash on them and
instruct the agent to self-validate — so they run during generation and their stdout shapes the
answer.

**2.2 — a sentence in the entrypoint is not a load.** 15 skill-load instructions could never
execute. Review 65.5 → 90.2, and **round 1 refuted the plan's central factual claim**: I asserted
all 15 were mandatory; 7 were on-demand. The cause is the transferable lesson — the classifier
matched `On-demand` with a hyphen while the corpus writes `On demand` with a space, so the header
never matched and everything defaulted into the mandatory bucket. A parser that cannot fail loudly
produced a confident wrong answer, and it reached a plan as fact. The shipped gate now asserts both
classes are observed, so the same silent miss fails loudly.

**Method note.** Across both phases, three of four plans were rejected on first review, and in every
case the finding was one static reading caught that execution would not have: a false-PASS path, a
false premise, a self-invalidating registry entry. Also worth recording: one of my own mutation
checks appeared to show a guard was unnecessary, and that was a `-k` filter selecting the wrong
test. Re-running by hand showed `0/0 passed` with exit 0. Verify the verification.

## Wave-2 phase 3 + open issues (same session)

**Phase 3 — the manifest is an ownership receipt, not an inventory.** `ck uninstall` deleted every
path the manifest *listed* without comparing a single sha256, while `_classify_manifest()` — which
returns exactly the split needed — already existed and was used by `ck update` and `ck diff` but not
here. Uninstall now acts only on receipt-owned files and fails closed on mixed ownership.
Also closed the standing `settings.local.json` defect, reproduced against the pre-fix installer.
Review 93/100, one round.

**On handoff 3.2, the mechanism was rejected and the invariant adopted.** There is no downloader to
commit-pin — `install.sh:13-17` refuses `curl|bash` — and adding a fetcher would add the network
surface this repo has avoided. So the manifest records `source: {commit, pinned, dirty}` instead,
and the sibling invariant ("a failed install leaves the last verified one unchanged") was **verified
rather than reimplemented**: the installer already stages and swaps atomically under an ERR trap.

**A mutation that failed to bind was the most useful result of the phase.** Restoring
`settings.local.json` to the manifest changed nothing, because the tests created it after a *fresh*
install where it does not exist at manifest time. The defect only appears on the **second** install,
once the preserve step has restored it. Same lesson as the phase-2 `-k` misread, from the other
direction: a mutation that does not turn a test red is a finding about the test.

**Open issues closed.** `/review` no longer contradicts the policy it was shipped alongside — and
the fix that matters is deleting its `callsite_overrides` entry, so the audit test binds the literal
to the table. CLAUDE.md headroom went 8 → 492 by deleting stale hand-written counts (a hard-rule-8
violation that was also the space), and the file gained a documented gate while getting smaller.
**The budget was deliberately not raised**, though the script offers that escape.

**Two regressions, both found by running the suite rather than reading the diff.** A non-git source
aborted the install (rc=128, no manifest): provenance uses two git calls, and while `rev-parse` was
guarded, `git status --porcelain | head -1` is a PIPELINE — under `pipefail` a failing upstream
fails it, and under `set -e` that killed the installer. **The review probed exactly this case and
cleared it**, having checked the other line. And `ck uninstall` raised `AttributeError` for any
caller building its own `Namespace`, which `tests/test_cli.py` does. The transferable point: static
review is excellent at finding what a diff *says* and blind to what an environment *does* — the
kit-copy fixture that exposed defect 1 already existed and had to be executed to matter.

**Still blocked, not dropped:** recording the first eval cassettes. Attempted; the CLI here routes
through `xpipe` and the available account had hit its weekly limit. The mechanism is complete.

**Follow-ups.**
- `TOKEN-MODEL-POLICY` marker bumped **v2 → v3** so the 16 kitted projects do not skip the new
  block as "already present". The precedent is `CHANGELOG.md:328` (v1 → v2). **Owner decides when
  to run the sync**; tracked in `.ai/BACKLOG.md`.
- `gen-model-policy.py` is not in `iron-law-gate.py`'s `_CHECK_ONLY_SCRIPTS`, so the implementer
  agent cannot run the new gate (maintainers and CI can). That file belongs to the concurrent
  lane — deliberately not edited. One-line follow-up in `.ai/BACKLOG.md`.
- Wave-2 phases 2 (eval replay engine) and 3 (install receipts) are **not started**.
- A1/A4 (mechanical DoD at `Stop`, failure-fingerprint circuit breaker) stay blocked on the
  enforcement-runtime lane's event log and dispatcher.

## 2026-08-19 — Claude (Opus 5) — Reflection/review-discipline batch (7 workstreams, owner-approved)

**Scope.** Read the `chaos-engine` subtree of ShaftHQ/SHAFT_ENGINE (MIT) in full — README,
RESEARCH.md, 3 SKILL.md, ~20 `references/*.md`, `hooks/guard.py` (449 lines), `hooks/reflection.py`
(557 lines) — and traced it against our flow (settings.json hook graph, 19 hooks, the 5 pipeline
agents, INVOCATION.md, VERIFICATION_PROTOCOL.md, execute-json-ops.py, review-record.py,
knowledge-ledger.py, check-context-floor.py). Produced a gap analysis (G1–G7), then executed
everything the owner approved.

**Method.** Orchestration Protocol v2: one decomposition into 7 workstreams with a disjoint
file-ownership map (21 ops, 19 files, **zero collisions** — verified mechanically), planners
fanned out in parallel on opus, reviewers per workstream (opus for security/architecture, sonnet
otherwise), every verdict hash-bound with `review-record.py`, composition gate = ownership check +
six sequential dry-runs, execution in dependency order with the approval-gate workstream LAST
because its own gate closes on every sibling config.

**Outcome.** 945 tests green; ruff, mypy, gen-docs `--check`, gen-registry `--check`,
check-context-floor `--check`, shellcheck all pass; `ck doctor --strict` 22/25 with 3 pre-existing
warnings. Product detail in `CHANGELOG.md` `[Unreleased]`.

**What the process actually bought (the honest accounting).** 13 review rounds produced 1 CRITICAL
and 12 MAJOR. **Every plan failed its first review**; only the smallest cleared 90 on round 1.
Defects that would otherwise have shipped looking correct: a code-reviewer that refuses every
review in this repo (no PR/ref exists for a local diff); after that fix, one that reports clean
while blind to newly added files; an approval gate keyed on directory name (caller-controlled);
a reflection escape hatch permitting an arbitrary source write past two guards via a symlinked
inbox; a secrets sanitizer letting bare high-entropy tokens onto disk; "cannot be forged" claimed
for a token the model can read; mutation proofs asserted for 9 groups and supplied for 4; and an
invented rationale citing repo vocabulary that does not exist.

**Two fixes introduced worse holes than the finding they closed** (WS-3 Phase 0, WS-2 inbox
allowance). Both were caught only because each delta re-review was a FRESH instance told to attack
the fix rather than confirm the finding was addressed. Recorded as the finding class
`fix-introduces-larger-hole`; with `guard-cannot-express-guarded-case` (2×) and
`count-asserted-not-derived` (2×), all three are at or past the ratchet's three-entry threshold.

**Found by execution, not by review** (dry-run cannot see these): `add_after` with no leading
newline concatenates onto the anchor line (hit live on CLAUDE.md, 442-char line); and the validator
does not bind the executor — `additionalProperties: false` in the schema vs. unknown edit fields
silently ignored at execution, so a REJECTED config still runs.

**Measured, not inferred:** a frontmatter-declared `Bash(...)` specifier is not applied on the
interactive path (differential probe, permission mode `default`, empty allow list, both arms via
`--agent`), so the implementer holds unscoped Bash and the interactive Iron Law is prompt-enforced
only. Privacy of the reflection ledger verified live: a payload carrying a 40-char token, an
absolute path and raw stderr produced zero leaks across 5,327 bytes of real ledger data.

**Follow-ups:** `.ai/BACKLOG.md` §P0.5 (10 items) + decision 21 raised to P0.

## 2026-08-17 — Claude (Fable 5) — Token-efficiency pass (measured, owner-approved)

- Measured the token floors empirically (always-on ~12k tok; per-pipeline ~15k tok; ops.json
  payload paid 3×; 737 KB of avoidable full Reads across archived plans) and verified a
  6-approach proposal against the filesystem — plan + evidence in
  `.claude/plans/plan-token-efficiency.md`, research cache in
  `.claude/reports/research/multi-agent-token-efficiency-2026.md`.
- Implemented steps 1–5: planner grep-anchor discipline, `<example>` strip from 29 agent
  descriptions (−14,393 chars; kept 1 each for reviewer/code-reviewer +
  doc-updater/documenter), reviewer manifest-first ops review (>15 KB configs),
  CLAUDE.md blast-radius tiering (replaces the ≤2-line fast-path), and
  `scripts/check-context-floor.py --check` CI-style gate + `tests/test_context_floor.py`.
- All DoD gates green (828 tests, ruff, mypy, gen-docs, gen-registry, shellcheck).
- Follow-ups: (a) `run_command` op type needs its own plan — Iron Law surface (validator
  allows only file_create/file_delete/code_edit, forcing opus to hand-transcribe lockfiles;
  58% of ops-task-014.json was a pip lockfile); (b) fleet-sync steps 1–2 to the 16 kitted
  projects **surgically** — owner directive: never remove/overwrite downstream files with
  project-specific content; (c) wire check-context-floor into CI workflow.

## 2026-08-09 — Claude (Sonnet 5) — Fixed AGENTS_KNOWN_ISSUES.md #9 (legacy ops.json schema in shared template)

- Executed the approved plan `plan-workflow-file-templates-ops-schema.md` / ops config
  `ops-workflow-file-templates-ops-schema.json` in worktree
  `agent/workflow-file-templates-ops-schema`, via `execute-json-ops.py` (7 operations: 1
  `file_create`, 6 `code_edit`, all succeeded, 0 errors).
- `_shared/WORKFLOW_FILE_TEMPLATES.md`'s Operations Config Template swapped from the
  legacy schema (`version`/`plan_ref`/`file`/`changes`/`type: create|modify|delete|move|rename`)
  — which `validate-config-json.py` rejects outright — to the canonical modern schema
  (`plan` + `operations`; `file_create`/`file_delete`/`code_edit`; `path`/`edits`;
  `additionalProperties: false`), with a validator-clean worked example and a rules table.
  Schema ownership pinned to `generate-operations-config` SKILL.md + `operations-schema.json`.
- New `tests/test_agent_doc_ops_examples.py`: materializes every ops-config-shaped JSON
  fence in `.claude/agents/**` + `.claude/skills/**` into a throwaway project and runs the
  real validator against it (10 tests, all pass) — regression guard so the legacy-schema
  bug class cannot silently return.
- Retired the issue: `.ai/AGENTS_KNOWN_ISSUES.md` #9 marked FIXED, `.ai/AGENTS_PROTOCOLS.md`
  warning replaced, `.ai/TECH_DEBT.md` row 1 removed, `.ai/BACKLOG.md` P1 item removed,
  `CHANGELOG.md [Unreleased] → Fixed` entry added.
- DoD gate: 779 tests pass, ruff/mypy/shellcheck clean, gen-docs/gen-registry `--check`
  green (counts unchanged: 29/42/75/19). Plan/ops artifacts could not be written to
  `.claude/plans/` (sensitive-path gate blocks direct Edit/Write there even with
  `ECC_HOOK_PROFILE=minimal`, distinct from the ops-enforcement hook) — they were kept at
  the worktree root instead, same accommodation the plan's own artifact-location note
  describes for planning-time writes.

## 2026-08-09 — Claude (Fable 5) — Worktree-per-agent + multi-account/cross-tool collaboration

- Owner /goal directive: research → plan → review → implement worktree parallelism +
  dual-Claude-account + cross-tool (Cursor) collaboration in claudekit, then apply to
  AppiumLens. Research (3 web-researcher agents, cached to `.claude/reports/research/`):
  worktree-per-agent is the 2026-converged pattern; `CLAUDE_CONFIG_DIR` is the dual-account
  mechanism; AGENTS.md standard + file-based contract is the cross-tool layer.
- Pipeline run on the repo's own conventions: `plan-worktree-multi-agent.md` rev 1 scored
  **71.3 REVISE** by opus reviewer (15 findings — isolation mechanism unverified vs
  executor cwd guard, /batch collision, registry path leak, missing input validation,
  gen-docs prose lines); rev 2 scored **93.3 APPROVED**. All 7 non-blocking suggestions
  folded into implementation.
- Landed: `worktree-manager.py` (validated slugs, git-ignored registry, atomic+locked
  writes, max 5, safe remove, base pinned to SHA at create) + 20 behavioral tests incl.
  isolation proof (execute-json-ops.py cwd-scoped inside a worktree, escape rejected);
  `/worktree` command; coordinator Worktree Isolation Protocol; gitOps Multi-Agent Merge
  Protocol; /batch reconciled (waves ≤5, workers never merge); `cross-tool-collaboration`
  skill; `docs/PARALLEL_AGENTS.md`; counts 41/75 across gated + maintainer docs;
  `.agents/` mirrors synced (.codex deferred, noted in CHANGELOG).
- AppiumLens applicability delivered: `AppiumLens/.claude/plans/plan-parallel-agents-pilot.md`
  (device/port matrix per worktree — APPIUM_PORT/SYSTEM_PORT/WDA via WORKTREE_PORT_OFFSET,
  one UDID per worktree; 3-task disjoint pilot; success criteria).
- 753 tests green; all six gates pass. Follow-ups backlogged: corpus-wide
  disable-model-invocation contradiction (~30 skills, ties into task 009), ck doctor
  manifest entry for the manager script.

## 2026-08-02 (later) — Claude (Fable 5) — Work-loss protection + fleet rollout ×3

- Incident-driven (concurrent session's git checkout wiped 5 rounds of accumulated work on
  one file in a kitted project): landed `46d437c feat(safety)` — destructive-git screening
  in CommandValidator (reset --hard/clean -f/checkout --/worktree restore/stash drop;
  benign forms allowed), `--stamp-baseline` drift gate (executor aborts pre-write on sha256
  mismatch, /implement stamps by default), post-state checkpoints + `restore-backup.py
  --post` forward recovery, concurrent-session warning in session-start (.claude/locks/).
  15 tests in test_work_loss_protection.py; 730 total green.
- Found + fixed a silent screening hole: user projects had NO command screening (validator
  rc-127 permissive path — no console script on PATH, no src/ tree). pip-installed
  claude-kit locally and added a third hook fallback `python3 -m claudekit.security`
  (commit `fix(hooks)`); verified the guard now blocks `git reset --hard` (rc 2) from
  inside AppiumLens.
- Graph-sidecar automation landed earlier today (`38e246c`): session-start graph status
  line + explore record-back. Fleet rolled out 3× today (graph, safety, hook-fallback) to
  all 16 kitted projects; settings.local.json intact each time (installer preservation
  held — no hand-restores needed).

## 2026-08-02 — Claude (Fable 5) — Project graph sidecar (Graphify-inspired)

- Researched Graphify-Labs/graphify (tree-sitter/NetworkX codebase→knowledge-graph tool)
  on owner request; vendoring ruled out (hard rule 8). Borrowed three patterns stdlib-only
  instead, landed as `2ae85c8 feat(graph)`: `.claude/operations/scripts/project-graph.py`
  (build/query/hubs/path/stale over `.claude/project-graph.json`), confidence tiers
  (extracted/inferred/ambiguous) on every edge, GOD-NODE fan-in/out ranking, sha256
  staleness detection. codebase-mapping skill gained Step 7 (emit sidecar) + stale→merge
  refresh; explore/planner/refactor-cleaner go graph-first with exit-3→grep fallback.
  34 behavioral tests in `tests/test_project_graph.py` incl. byte-identity guard on the
  skills/templates twins. All gates green (706 tests).
- Design decisions: no Skill Loading/registry coupling (agents call the script directly);
  build refuses overwrite without --force (ledger convention); god-node thresholds are
  flags, not config keys. AppiumLens exploration grounded the design (TestingDetailPanel
  3,953 LOC etc. as the target god-node class).
- Follow-up (approved plan, not yet executed): pilot `ck update` on AppiumLens + smoke
  test (hubs must surface TestingDetailPanel), then fleet fan-out — remember the
  settings.local.json clobber caveat from the 2026-07-31 rollout.

## 2026-07-31 — Claude (Fable 5) — Full fleet rollout

- On explicit owner instruction ("all projects"), rolled the kit out across the entire
  ~/IdeaProjects folder: 6 managed projects `ck update`d (AppiumLens hold lifted by
  owner) + 11 fresh installs (qa-agent-pro, ApiForge, AutomationApp, Eatizaz, SehhatyApp,
  appium-lens-public, Lean, codemanifest, CodeManifest-1/2/new; `--force` over old
  hand-copied `.claude/` fragments, backed up first). All 17 validated: doctor --strict
  22/22 each + per-project asset checks (review-record.py, new review.md/plan.md,
  scratchpad hook allowance).
- Upstreamed AppiumLens' field fix into the kit before overwriting it (`354f905`:
  ops-enforcement.sh allows session-scratchpad/OS-temp targets — false cross-project
  denials), then re-synced the 5 projects updated before the fix landed.
- Kit bug filed (BACKLOG P2): settings.local.json is manifest-managed and gets clobbered
  by `ck update`; hand-preserved in every project this rollout.
- Deleted the accidental "LeanApis ai-agent-system AppiumLens MobileUIAutomator" dir
  (unquoted-spaces artifact, owner-approved). Skipped non-projects: backups, report
  outputs, scratch dirs.

## 2026-07-31 (later) — Claude (Fable 5) — Remaining-fixes implementation

- Implemented `.claude/plans/plan-remaining-fixes-2026-07-31.md` end to end — 9 commits:
  ops-hardening landed as 4 conventional commits (post-approval 2-edit delta identified
  and recorded as prose-only; rejected finally-reset confirmed absent); approval-binding
  rebased against HEAD and executed via the ops engine itself (review-record.py, 20
  tests, delta review mode) with a same-session `fix(security)` follow-up closing 2
  background-review findings (slug sanitization, symlink-chain check); shellcheck gate
  surfaced (`ck doctor` warn + tests/test_shell_lint.py, 21 visible per-script results);
  100KB `.ai/AGENTS.md` split into 13 byte-preserving files each <10KB.
- Fleet rollout deliberately NOT executed: all 6 projects at manifest 2.1.0 but every
  tree dirty (54–535 files) — blocked on owners per the plan's own step-2 rule.
- Suite: 638 (595 → +20 review-record, +2 write-safety, +21 shell-lint). All DoD gates
  green including shellcheck for the first time.

## 2026-07-31 — Claude (Sonnet 5) — Token-waste workflow fixes

- Origin: transcript analysis of a 2026-07-30/31 session that burned 80.3M billed context
  tokens over 381 API calls, root-caused to full plan/ops.json payloads leaking into the
  main session context via `tee`, re-typed Writes, non-persisting shell variables, and
  `cat`'d heredoc interpolation. Plan: `.claude/plans/plan-token-waste-workflow-fixes.md`.
  New governing contract: subagent handoffs pass file paths, never file bodies.
- 6 commits (`51db588`..`3546f1e`): `suggest-compact.sh` fixed (was a no-op — PreToolUse
  stdout is never shown to the model, plus doubly backgrounded; now PostToolUse,
  foreground, cadence 40); `/plan` scripted+interactive paths stop leaking; `/refine`
  restructured around fixed `PLAN_FILE`/`OPS_FILE` paths instead of a shell variable that
  doesn't persist across Bash calls; the path-not-payload rule codified into
  `INVOCATION.md`/`HANDOFF_PROTOCOL.md`/`planner.md`; `/review` audited and found to have
  the identical leak (`cat`'d the whole plan into a prompt) — fixed, then a follow-up
  commit corrected an over-narrow ops-file-naming assumption in that fix (this repo
  intentionally supports both `*.ops.json` and `ops-*.json`, per `.ai/FAQ.md`).
- Added `tests/test_delivery_contract_smoke.py`: zero-LLM-cost regression test running
  `/plan`'s actual scripted bash block (extracted from the command file, not hand-copied)
  and an assembled `/refine` 2-iteration run against a stub `claude` binary emitting a
  ~40KB fake payload — asserts it lands on disk/validates but never reaches stdout. Chosen
  over a live opus smoke-test run because the property under test (does the transport leak
  bytes) is model-independent, and a background agent earlier in this same session had
  already hit the account's usage limit mid-run.
- Plan's Phase 6 (task 009 lazy skill loading) turned out to require zero work: verified
  already fully shipped in `fe7396e` (2026-07-08), three weeks before this plan's Phase 6
  was drafted (`TestContextBudget`'s three gates still pass). Corrected the plan doc
  instead of re-implementing already-shipped work.
- Suite: 593 (was 591 pre-session; +2 from the new smoke test). All local DoD gates green
  except shellcheck (still not installed locally — pre-existing, unrelated to this session).
- Follow-up not done this session: pushing these 6 commits (user-gated, not requested).

## 2026-07-08 — Claude (Fable 5) — E2E validation + gap fixes + eval framework (010)

- Ran the full pipeline headless on a fixture (plan→review→implement→verify): works,
  $1.86 total; refutation/evidence behaviors verifiably fired; verifier numbers matched
  ground truth. Found + fixed: `.claude/**` writes hard-blocked headless (stdout is now the
  explicit delivery contract; recreated ghost script extract-json-from-plan.py);
  implementer stalling on out-of-scope verification (now hands off "verification pending").
- Fixed: PostToolUseFailure hook SyntaxError (logged all failures as "unknown"); verifier
  now diff-scoped by default (--all for repo-wide).
- `/plan` `/review` `/refine` are dual-mechanism: Task tool interactive default, claude -p
  scripted. AppiumLens's 3 command overrides converge (not restored on next update).
- **Task 010 shipped:** `ck eval` + scripts/run-evals.py + evals/ (4 behavioral evals with
  planted-defect refutation test, fabrication tripwire, ground-truth match; per-eval cost
  budgets; offline framework tests in pytest). Suite: 564.

## 2026-07-08 — Claude (Fable 5) — Context budget: lazy skill loading (task 009 core)

- Measured the problem first: 16,120 preloaded skill lines across 18 agents (coordinator
  12 skills / 2,397 lines); registry agentMapping had 30 entries incl. 10 agents with NO
  skill section and 2 commands. Registry drift follow-up from the corpus session: resolved.
- Two-tier skill loading: ≤3 mandatory per agent + on-demand with per-skill triggers;
  AGENT_TEMPLATE protocol updated. Preload now 6,649 lines (−59%); worst agent 559.
- scripts/gen-registry.py regenerates agentMapping from agent files (--check gate, same
  pattern as gen-docs; added to CLAUDE.md commands). agentMapping now 18 honest entries.
- Budget gate tests (TestContextBudget): max-3 mandatory, trigger required per on-demand
  entry, registry --check green. Suite: 552. Plan:
  `.claude/plans/plan-context-budget-lazy-skills.md`.
- Follow-ups CLOSED same day: 8 commands trimmed to 3 mandatory + on-demand trigger;
  usedBy now generated from reverse agentMapping (0 "all" fictions remain, 38 skills
  honestly on-demand-only); SKILL.md splitting measured and skipped (only 3 kit skills
  >300 lines; on-demand loading made size pay-per-use). Fleet re-rolled; output-cap env
  vars (BASH_MAX_OUTPUT_LENGTH, MAX_MCP_OUTPUT_TOKENS) added to 5 projects'
  settings.local.json. AppiumLens MCP server trimming left to owner (filesystem server
  is demonstrably used; no usage evidence for sequential-thinking/greptile).

## 2026-07-08 — Claude (Fable 5) — Agent-registration root cause + fix (spawn contradiction resolved)

- Empirical test settled the Task-tool-vs-`claude -p` question: invalid YAML frontmatter
  (bare `<example>` blocks between fields) had unregistered ALL 28 agents from BOTH
  mechanisms — `claude -p --agent explore` returned "agent not found"; a clean-frontmatter
  probe agent worked (14s). Both prior claims had wrong causality.
- Fixed all 28 agents (examples moved into description block scalars; name/model/color/tools
  preserved), rewrote INVOCATION.md around the two verified mechanisms, corrected stale
  claims in refine.md/gan-build.md, added TestAgentRegistration guard (suite: 549).
- Rolled to all 6 projects via ck update; AppiumLens's 3 Task-tool command overrides restored
  (tracked as locally-modified) pending a cold-boot timing test in ITS MCP-heavy env.

## 2026-07-08 — Claude (Fable 5) — Frontier-behavior corpus upgrade

- Defined a 10-pattern operating spec (what separates frontier-model behavior from
  Opus/Sonnet under the same prompts) and audited the corpus against it with 3 parallel
  agents (shared docs + core agents / commands / skills + registry).
- Applied ~35 surgical edits across `_shared/` (4 docs), 8 agents, 12 commands, 5 skills.
  Fixed 8 contradictions incl. two unexecutable contracts (reviewer --dual self-spawn,
  planner tools vs INVOCATION). Full details: CHANGELOG.md [Unreleased] Changed.
- Model routing: planner→opus, verifier→sonnet (agent frontmatter + command spawn lines +
  .ai/AGENTS.md diagrams).
- 24 anchor tests in tests/test_behavior_spec.py (suite: 547). Plan:
  `.claude/plans/plan-fable-behavior-corpus.md`.
- **Follow-up surfaced, NOT done:** registry `agentMapping`/`usedBy` no longer matches the
  agent .md load lists (implementer 5 vs 15, coordinator 12 vs 16, `usedBy:["all"]` honored
  nowhere) — needs a single source of truth + drift gate; blocks task 009's budget math.

## 2026-07-08 — Claude (Fable 5) — Fleet audit + legacy-install lifecycle

- **Fleet audit:** surveyed all 12 `.claude`-bearing projects in ~/IdeaProjects against the kit
  (4 parallel review agents). Verdicts: the 13 "extra" commands + `i18n-workflow` in
  LeanApis/ai-agent-system are byte-identical round-trips of `templates/commands|skills/`
  (nothing to upstream; per-asset keep/delete calls recorded for task 008); zero graft-worthy
  edits in any project (all version lag); AppiumLens/MobileUIAutomator ran pre-Phase-1 kit
  generations, and the 3 near-current projects were running commands with
  `--dangerously-skip-permissions` (the exact Phase-1 regression) — now fixed by resync.
- **Product change (plan: `.claude/plans/plan-legacy-install-lifecycle.md`):** legacy
  (pre-manifest) installs are now first-class: `ck diff` falls back to kit-source comparison
  (identical/differs/custom/not-installed) and refines manifest diffs into locally-modified /
  kit-updated / both-changed + custom listing; `ck update` works on pre-manifest installs;
  install.sh preserves project-custom agents/commands/skills across reinstalls (old-manifest
  precise mode; asset-dir heuristic for legacy). 7 new behavioral tests (523 total); ruff clean
  across tests/ (was CI-exempt); docs/cli.md + CHANGELOG updated.
- **Fleet resync (via the new `ck update`):** qaforge-ai, LeanApis, ai-agent-system,
  MobileUIAutomator, qa-agents → v2.1.0 manifest-tracked, diff-clean; customs preserved
  (qa-agents' 3 QA agents + 4 commands; MobileUIAutomator's 9 project skills). AppiumLens
  deliberately NOT auto-updated (real customization + open spawn-mechanism question).
- Open decisions surfaced to owner: QA-pack (3 generic QA agents from qa-agents), AppiumLens
  selective sync, Task-tool vs `claude -p` spawn contradiction, `<example>`-in-frontmatter
  YAML validity audit.

## 2026-07-08 — Claude (Fable 5) — /adapt self-adaptation capability

- Added `/adapt` command (`.claude/commands/adapt.md`) and `project-adaptation` skill (`.claude/skills/project-adaptation/SKILL.md`): ClaudeKit now teaches an AI, when the kit is added to **any** project in **any** language, what to change (config.json commands, CLAUDE.md, CONSTITUTION.md, hook profile, .agentignore), how to verify it works (hook block test, four commands, ops round-trip, doctor), and how to keep enhancing the fit (/hookify, /learn, decision recording).
- Registered in skills-registry.json (`usedBy: coordinator, explore`); counts now 40 commands / 74 skills — regenerated via gen-docs; README + docs/ARCHITECTURE + .ai/ counts updated; CHANGELOG `[Unreleased]` Added entry.

## 2026-07-08 — Claude (Fable 5) — AI handover & knowledge-transfer session

- Created the `.ai/` AI operating system: 36 documents covering onboarding, architecture, catalogs (agents/commands/skills/hooks/prompts), knowledge (decisions/knowledge-base/memory/domain/glossary), process guides (development/review/testing/security/performance/debugging/troubleshooting), planning (status/session-state/roadmap/backlog/tech-debt), and meta (playbook/checklists/faq/migration/dependencies/knowledge-graph).
- Created root `CLAUDE.md` (repo previously had none — only user-project templates).
- Sources: full-repository analysis; `review/` audit (2026-07-05); `.claude/plans/phase-1-HANDOFF.md`; git history through `0c9223b`. `.ai/AGENTS.md` (the deep per-agent reference incl. 16 cataloged prompt-layer inconsistencies) was produced by a subagent that read every agent file.
- **No product code, prompts, hooks, or tests modified.** Docs-only session.
- Follow-ups: P1 items in [BACKLOG.md](BACKLOG.md) (WORKFLOW_FILE_TEMPLATES legacy schema fix first); release remains user-gated.

## 2026-07-05/06 — Claude (Opus 4.8, 1M context) — Phase 1 "Fix What's Broken"

- Executed audit tasks 001–006 + 011 in four waves (A–D) on `phase-1-fix-whats-broken`; 14 commits; merged via PR #1.
- Packaging fixed (installable wheel, src-layout, version single-sourcing, bundled assets) · hooks made real (exit 2/stderr/fail-closed, lib.sh, telemetry via stdin JSON) · security layer wired (validator hardening, command-guard, CLI) · skip-permissions eradicated · installer made safe (staging/backup/atomic swap, manifest, settings.json installed) · versions/docs reconciled (renumbering, gen-docs + docs-drift CI, canonical slug) · CI made honest (11 jobs, 2-OS matrix).
- Record: `.claude/plans/phase-1-HANDOFF.md`. Post-merge fix `0c9223b` (py3.12+ setuptools).

## 2026-08-23 — Claude (Opus 5, 1M context) — Phase 2: `ck adapt`

- Finished the verb the previous session's review REJECTED at 65/100. The nine filed
  findings were real; five more were found by adversarially reviewing the fix itself,
  and three of those five were defects this session had just introduced.
- The rejected implementation existed **only inside `ops-ck-adapt.json`'s embedded
  content** — `src/claudekit/adapt.py` was never on disk, so the "1952 baseline / +70
  tests" figures in the handoff were both wrong. Re-measured on a clean clone at
  `14cf45e`: **1983 passed, 1 xfailed**. Final: **2081 passed, 1 xfailed, delta +98**.
- The five filed blockers: an unmatched code fence desynchronised a bare
  `in_fence` toggle so adapt appended a region on every run (1→2→3 measured through
  the CLI); `splitlines()` + `join()` rewrote user bytes outside the region on mixed
  line endings — and **`Path.read_text` was translating `\r\n` before the writer ever
  saw it**, which defeated the splice at the read layer; `ck uninstall` built survivors
  from `modified ∩ exists`, unlinking the receipt over files still on disk;
  `cmd_adapt` never re-stamped the manifest; and `apply_commands` **was never called
  from anywhere** while the report printed "OK — every step either completed".
- The five found by self-review, worth more than the filed five:
  1. Writing `dirty` into the region made the verb self-referentially
     non-idempotent wherever `.claude/` is TRACKED — run 1 dirtied the tree it then
     described. Proof 1's fixture has no `.git`, so it could never see it.
  2. A `run:` string in the TARGET repo reached `hooks/config.json` verbatim
     (`pytest ; touch /tmp/PWNED_BY_ADAPT`), i.e. attacker-controlled shell in a file
     pre-push executes. Detection executing nothing was not enough: the write
     outlives the report.
  3. Blanking an unevidenced command key destroyed user configuration on every run —
     and `project-adaptation` Phase 2 tells the user to set exactly those keys, so the
     verb undid its own documented workflow. `install.sh:495-497` writes them EMPTY,
     which is what proves a non-empty value is the user's.
  4. The two refusal branches omitted every step they never reached, while the fresh
     branch named them. Same overstatement, one branch down.
  5. A test of mine that could not fail: `test_a_stack_profile_value_is_not_filtered`
     used a profile command with no metacharacter, so a mutant that over-applied the
     rule went green. Caught only by mutating.
- **The config silently deleted another session's line.** Its `find` anchors all
  matched exactly once and validation said APPROVED, yet applying it over that
  session's uncommitted `ck eject` removed `"eject": cmd_eject` from the dispatch dict
  — context-carrying edits re-emit old context — breaking 12 of their tests with
  `KeyError: 'eject'`. Closed by stamping a `baseline` (6 files), which now refuses on
  drift instead. Also caught a **stale delivered copy** of the config that validated
  against the drifted tree but was rejected by a pristine `14cf45e` clone.
- Structural: **only 1 of the plan's 21 proofs drove the CLI**, which is exactly how a
  function nothing calls passed three green unit tests. Added a CLI-driven half (real
  `ck init` tree, subprocess, assertions on exit code and printed report) including
  proof 14 (`NEVER_MANAGED` survives), which the plan calls the single
  highest-value test here and which had no test at all. **27 mutants, all bind.**
- Also landed: `ck doctor --strict` exited 1 on every freshly installed tree
  (`templates/skills/i18n-workflow` is copied by the installer but absent from the
  generated registry) — the installer now reconciles it; the task-008 half, so
  `/adapt` and `project-adaptation` delegate the mechanical surface to the verb and
  three adaptation surfaces became two; and the fresh branch now installs FULL mode
  itself and re-checks Rule 0 against the receipt the installer actually produced.
- Net asset delta **0** (29 agents / 42 commands / 76 skills / 22 hooks). Filed rather
  than built: `.claude/plans/plan-adapt-eject-interaction.md` — `ck adapt` on an
  ejected tree refuses with the wrong remedy, and that remedy (`ck init`) points at
  the destructive installer swap decision (A) exists to make unreachable.

## Earlier — v1.0.0 → v2.0.0 (2026-03-16/17)

Original corpus build-out (agents/commands/skills/hooks/templates/modes/MCP/i18n) — see CHANGELOG.md. Delivery-shell defects from this era were the subject of the 2026-07-05 audit (`review/FINAL-REPORT.md`, 49/100).
