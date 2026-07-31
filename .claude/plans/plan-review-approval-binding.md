# Plan: Bind Review Verdicts to the Artifact (Reviewer-First)

**Status:** REVISION 3 — after review #1 (68 REVISE) and review #2 (72 CONDITIONAL, 5
CRITICAL/MAJOR); awaiting re-review
**Ops config:** `.claude/plans/ops-review-approval-binding.json`
(9 operations · 11 `code_edit` edit anchors · 2 `file_create` — validated, dry-run clean, and
the new script rehearsed with 17/17 tests passing, §8)
**Date:** 2026-07-31
**Owner approval required:** yes (changes `/review`, `/implement`, `/refine`, and the reviewer agent)

---

## 1. Problem

The quality gate is not bound to anything. `/review` prints a verdict to stdout
(`review.md:70`) and nothing is persisted; `/implement` STEP 0 asserts *"An approved plan
exists (review score >= 90)"* as prose the agent attests to itself. Grepping the commands,
the agent specs and every ops script for `hash|checksum|fingerprint|sha` returns nothing.

So an ops.json can be edited freely between approval and execution, and the pipeline cannot
tell. **This is not hypothetical — it happened in the session that produced this plan:**

- Review #6 scored `ops-hardening-implementer-contract.json` **97/100 APPROVED at 72 edits**.
- Four "cheap MINOR fixes" were then applied, reaching **74 edits**, and `/implement` ran on
  that. Every pre-flight check passed, because the validator proves the file is *valid* and
  the dry-run proves it is *applicable* — neither knows which version was approved.
- One of those post-approval edits (resetting `_result_emitted` in `finally`) **reintroduced
  the double-emission bug review #3 had already caught.** It was stopped only because a test
  written earlier in the same session happened to fail. Nothing in the pipeline flagged it.

## 2. Why the fix goes in the reviewer, not the implementer

The obvious fix — make `/implement` refuse on a hash mismatch — is actively harmful on its
own. Re-approval currently means a **full** review, and full reviews are the dominant cost in
this pipeline. Measured across the seven reviewer invocations of the previous session:

| Round | 1 | 2 | 3 | 4 | 5 (killed) | 5 retry | 6 | **Total** |
|---|---|---|---|---|---|---|---|---|
| Tokens | 108k | 106k | 112k | 119k | 110k | 121k | 124k | **~800k** |

Each round re-read the same ~93 KB of plan + ops.json and re-verified the same ~70 anchors,
because a handful of edits had changed. A drift gate layered on top of that makes every
one-line post-approval fix cost ~120k tokens — a gate that expensive gets bypassed, which
returns us to exactly the failure it was meant to prevent.

**So cheap re-approval must exist before mandatory re-approval is safe.** Reviewer first.

## 3. Design

### Op 1 — `.claude/operations/scripts/review-record.py` (new, stdlib-only)

Review #1 (68 REVISE) found 3 CRITICAL / 5 MAJOR in the first design; review #2 (72
CONDITIONAL) then found the fix for finding **(a)** was itself wrong, plus 4 more MAJOR. Both
rounds are folded in here, each pinned by a test:

- **(a) ops.json resolution** — round 1 guessed a single filename form and failed for this
  very plan; round 2's fix tried three *slug*-based forms but never the form `/plan` and
  `/refine` actually emit (`${PLAN_FILE%.md}.ops.json` — the **un-stripped** stem, e.g.
  `plan-<ts>.ops.json`), which would have bricked the mainline pipeline while claiming to
  secure it. `resolve` now tries `{stem}.ops.json` first, then three slug-based fallbacks, and
  reports `AMBIGUOUS` (not a silent pick) if more than one candidate exists.
- **(b) `check` deleting the ≥90 gate** — fixed: refuses (exit 4) a matching-hash record whose
  decision isn't APPROVED or whose score is below 90.
- **(c) template-echo parsing** — fixed: parsing moved into the script behind strict anchored
  regex, validated range/enum, last-block-wins.
- **(d, round 2) delta soundness** — no ceiling on delta size, prior score anchoring the
  reviewer, no persisted prior findings — all fixed (below).
- **(e, round 2) CHANGELOG duplicate heading, no rollback section, cwd/symlink edge cases,
  `ck doctor` blind spot, off-by-one in the changed-line counter, main.py anchor drift** — all
  fixed below and enumerated in the risk table.

| Subcommand | Purpose | Exit codes |
|---|---|---|
| `resolve <plan>` | Find the plan's ops.json — tries the un-stripped stem form first (what `/plan`/`/refine` produce), then 3 slug fallbacks; reports ambiguity | 0 · **3** unresolvable/ambiguous |
| `write <plan> <ops> --from-review -` | Parse the verdict, record `sha256` + score + decision + findings, snapshot the config | 0 / 1 |
| `check <plan> <ops>` | Prove the file matches an **APPROVED, ≥90** record | **0** ok · **2** DRIFT · **3** no/unreadable record · **4** not approved |
| `diff <plan> <ops>` | Normalized diff *approved → current* + prior findings (prior score withheld); demands a full review past a size ceiling | 0 · **3** no record |

Records live in `.claude/reports/reviews/<slug>.json` (resolved relative to the nearest
ancestor containing `.claude/`, not raw cwd — round 2 finding) with the snapshot alongside as
`<slug>.ops.json`.

**Diff normalization (found by measuring, not by reasoning).** A raw line diff of JSON is
worthless the moment indentation, key order, or ascii-escaping shifts: measured on the real
60 KB artifact, a formatting-only change produced a diff **larger than the file itself**, which
would make delta review cost *more* than a full review and silently defeat the whole mechanism.
`diff` canonicalizes both sides (`indent=2, ensure_ascii=False, sort_keys=True`) before
comparing; hashing still uses raw bytes, so any change blocks. **Size ceiling (round 2 MAJOR):**
past `max(40 lines, 25% of the approved file)` changed, `diff` prints `FULL REVIEW REQUIRED`
instead of a delta — the floor exists because a pure ratio would force full review on exactly
the small post-approval fixes this mechanism is meant to make cheap, which a test now pins on a
4-edit fixture. **Anchoring (round 2 MAJOR):** the delta block surfaces prior findings but
deliberately withholds the prior score, so the reviewer re-judges instead of reaffirming.

### Ops 2–3 — the reviewer side (the load-bearing half)

- **`review.md`** calls `review-record.py resolve` instead of constructing a path. If a prior
  record's hash no longer matches, it injects the `DELTA REVIEW MODE` block (diff + prior
  findings, no prior score) unless the diff tool demanded a full review. The raw reviewer
  output is piped straight into `review-record.py write --from-review -`. It also has an
  explicit numbered step for the Task-tool (interactive default) path, where the bash block
  never runs: save the subagent's output and record it manually, "a review whose verdict was
  never recorded is not an approval." This is still prose enforcement for that one path — see
  the risk table; it fails closed (unrecorded → `/implement` exit 3), not silently.
- **`reviewer.md`** gains a `Delta Review Mode` section (verify changed anchors against the
  filesystem, check whether the delta reopens a listed prior finding, never assume small means
  safe) and a note that a caller-specified output format (the `=== REVIEW ===` block) overrides
  the agent's own default REVIEW REPORT template — round 1 found the two formats contradicted
  each other, which meant the parser could receive nothing parseable.

### Op 4 — the implementer side (cheap, now that re-approval is cheap)

`implement.md` STEP 0 item 1 keeps the "review score >= 90" language and adds the mechanical
gate as **two separate Bash calls** (`resolve` then `check` with the printed path) — round 2
found the implementer's tool grant is a literal prefix match on
`python3 .claude/operations/scripts/*` (`INVOCATION.md:75`), which an `OPS=$(python3 ...)`
shell assignment does not satisfy. All five exit codes get explicit handling; exit 1 is a STOP,
never read as approval.

### Op 5 — `refine.md`

Round 1's edit here was doubly wrong: it claimed `/review` gets called from inside `/refine`'s
loop (it doesn't — `/refine` builds its own `REVIEWER_MSG` per cycle and only writes plan.md +
ops.json once, at Step 3, after convergence), and it landed the edit inside a printed
user-facing banner. Fixed: the edit is now a truthful Notes-section bullet — there is nothing
on disk for `review-record.py` to bind to during iterations 1..N; once Step 3 writes both
files, `resolve`/`write` run once against the *final* iteration's verdict, same as a one-shot
`/review`. Automatic delta review *across* refine iterations is explicitly named as a real,
unclaimed follow-up (it would need an ops.json persisted per iteration, which `/refine` does
not do today).

### Ops 6–9 — gitignore, tests, doctor, CHANGELOG

- **`.gitignore`** excludes `.claude/reports/reviews/`.
- **`tests/test_review_record.py`**, 17 behavioral tests: `resolve` against the actual
  `/plan`/`/refine` naming form plus 3 slug fallbacks, ambiguous-candidate detection, and the
  unresolvable case; post-approval drift → 2; a matching hash with a REVISE/sub-90 verdict
  refused → 4; template-echo does not parse; last-block-wins; delta stays under 20% of a
  200-edit fixture; a reformat + key-reorder + ascii-escaping change together still read as "no
  changes" (round 2 found the first version's key-reorder test round-tripped to the original
  order and exercised nothing); a 4-edit small-plan addition still gets delta review, not a
  forced full review (pins the size-ceiling floor); a sweeping rewrite trips `FULL REVIEW
  REQUIRED`; prior findings shown, prior score withheld.
- **`src/claudekit/cli/main.py`** adds `review-record.py` to `ck doctor`'s required-script
  list, anchored on the actual multi-line `for script in [...]:` layout (round 2 found the
  original anchor didn't match that layout).
- **CHANGELOG.md** — inside the existing `### Added` block under `[Unreleased]`, not a
  duplicate heading.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Parsing the verdict is brittle | Strict anchored regex inside the script, last-block-wins, range/enum validated before write; 3 tests pin this |
| Delta mode could let a reviewer under-scrutinize | Changed anchors still verified against the filesystem; prior findings shown, prior score withheld; size ceiling forces full review past 25%/40-line churn |
| ops.json naming form guessed wrong | `resolve` now tries the exact form `/plan`/`/refine` emit first, then 3 fallbacks; ambiguity is reported, never silently resolved |
| Records could drift from plans (renames) | Slug derives from the plan filename; a rename yields `NO RECORD` (exit 3), blocking rather than silently passing |
| Interactive (Task-tool) reviews skip recording | Explicit manual-record step in `review.md`; genuinely still prose for that one path, but skipping it fails closed at `/implement` (exit 3) rather than silently approving |
| Symlink at the record/snapshot path, or at the reviews directory itself | `_safe_write` refuses when either the leaf or its parent is a symlink |
| `check` invoked from a subdirectory | Records resolve from the nearest ancestor containing `.claude/`, not raw cwd |
| Unreadable/corrupt record | Reported as exit 3 (no usable record), not exit 2 (drift) — the two failure modes read differently to a user |
| `ck doctor` blind to a missing script | Added to the required-script list, anchor matches the real file |
| Adds friction to a legitimate quick fix | That is the point; delta mode plus the size floor keep the friction proportionate |

Security: no new dependencies, no network. Writes are confined to `.claude/reports/reviews/`
and refuse to follow a symlink at either the leaf or the directory. The gate is strictly
additive — it can only refuse execution, never approve it; every `check` failure mode (1/2/3/4)
defaults to blocking.

## 5. Out of scope

- Signing/authenticating records (a local actor can delete one; this defends against drift and
  mistakes, not a hostile operator — same honest framing as "denylist speed bump, not a
  sandbox").
- Recording plan.md's hash as well as ops.json's. The ops.json is what executes; plan drift is
  a documentation problem, not an execution one.
- Wiring the check into a hook rather than the command prompt (task 010 territory).
- Automatic delta review across `/refine` iterations (§3 Op 5) — would need ops.json persisted
  per iteration, which the loop does not do today.
- Pruning old records — grows unboundedly locally; harmless since it's gitignored.

## 6. Rollback

The engine's own auto-backup covers execution failure. To undo a **completed** run:

```bash
git checkout -- .claude/commands/review.md .claude/commands/implement.md \
  .claude/commands/refine.md .claude/agents/reviewer.md \
  CHANGELOG.md .gitignore src/claudekit/cli/main.py
rm -f .claude/operations/scripts/review-record.py tests/test_review_record.py
rm -rf .claude/reports/reviews/    # only if created by a rehearsal, not real approvals
```

Or `restore-backup.py <backup-name>` / `/rollback latest` against the batch backup the
executor creates automatically.

## 7. Validation commands

```bash
python3 -m pytest tests/test_review_record.py -q     # 17 new tests
python3 -m pytest tests/ -q                          # expect 608 passing (591 measured + 17)
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
```

## 8. Evidence (measured)

- Validator on this ops.json: **APPROVED**, exit 0.
- Dry-run: exit 0, **9/9 operations, 11/11 edit anchors bound, 0 failures**.
- New script rehearsed from the `file_create` payload: `py_compile` OK, **17/17 tests pass**,
  `ruff` clean on both the script and the test file.
- Baseline suite measured directly before writing this evidence: **591 passed** (not the 599
  the prior revision projected without re-measuring).
- Every finding from both review rounds re-verified against the fixed script, not assumed:
  ```
  resolve on the ACTUAL /plan naming form (plan-<ts>.ops.json, un-stripped) -> exit 0
    (this exact form was BROKEN in revision 2 — the CRITICAL that motivated round 2)
  resolve plan-demo.md with 2 candidate ops.json files -> AMBIGUOUS, exit 3

  check (REVISE 68, bytes unchanged)   -> exit 4  (was exit 0 in revision 1)
  check (APPROVED 97, bytes unchanged) -> exit 0
  ```
- Delta-normalization: **707 B vs 69,378 B (99% smaller)** on the real
  `ops-hardening-implementer-contract.json`, with a deliberate reformat AND a real edit present.

## 9. Sequencing note

The working tree holds the same **12 uncommitted files** from the ops-hardening change plus the
new plan files (verified via `git status` just now — round 2 correctly caught the previous
revision's stale claim here, though its own claim that the tree was already committed was also
wrong; both were checked directly this time). This plan should not be executed on top of that
work — commit or stash it first, so the two changes have independent rollback points.
