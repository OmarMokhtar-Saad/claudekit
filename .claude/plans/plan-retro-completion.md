# Implementation Plan — Retro Loop Completion (six owner-approved follow-ups)

**Slug:** `retro-completion` · **Tier:** 3 · **Predecessor:**
[`plan-rejection-retro-loop-impl.md`](plan-rejection-retro-loop-impl.md) (shipped: 74e5fed,
b355a4f). This plan does not re-decide that design. It closes the six gaps its Follow-ups
and Judgement-calls sections recorded, as six independently executable ops configs.

| Phase | Config | Ops | Item |
|---|---|---|---|
| trim | `ops-retro2-trim.json` | 2 | **E** — trim `code-reviewer.md` |
| session | `ops-retro2-session.json` | 8 | **A** — close the `session_id` gap |
| classify | `ops-retro2-classify.json` | 5 | **B** — `rejections classify` + `stats --by-type` |
| heldout | `ops-retro2-heldout.json` | 5 | **C** — frozen held-out plan set |
| backfill | `ops-retro2-backfill.json` | 5 | **D** — `rejections backfill` |
| nits | `ops-retro2-nits.json` | 2 | **F** — two recorded test-quality nits |

**Order is load-bearing: trim → session → classify → heldout → backfill → nits.**
`nits` moves `cmd_write`'s body, so it must run last.

**Verified by execution, against a baseline.** All six configs were applied in order to a
full copy of the working tree (six `rc=0`), and the whole suite was run on that tree **and
on an unmodified copy of the same tree**:

| | baseline | after all six |
|---|---|---|
| `pytest tests/ -q` | 42 failed, **4293** passed | 42 failed, **4329** passed |

The two failure sets are **byte-identical** (`comm` over the sorted `FAILED` lines: zero
new, zero fixed) — all 42 are pre-existing and environmental, the git-dependent suites
failing because the copy carries no `.git`. Net effect: **+36 passing tests, no regression.**
Also: `ruff check src/ tests/ scripts/` clean; `mypy` **3 errors, all pre-existing in
`fleet-sync.py`** (H1 kept it from becoming 4); `check-context-floor.py --check` OK.

Two defects were found by this execution and fixed before shipping: a held-out fixture pair
that had drifted while the plan was being written, and a non-imputation assertion written
against a corpus that structurally could not contain an unclassified row.

**Validation state, measured just now** — `validate-config-json.py` passes on five of six
configs against the tree as it stands today. `ops-retro2-nits.json` reports two anchors not
found, and that is correct rather than a defect: both are lines `session` rewrites
(`emit_brief(...)`'s call and `record-code-review`'s `session_id=`), so it validates only
after `session` executes. The anchors of `classify` and `backfill` were deliberately
reworked to avoid the same coupling — `classify` wraps `cmd_rejections_stats` instead of
editing the body `session` touches — so those two validate today. **Re-run the validator
immediately before executing each phase**, which is the correct habit regardless.

---

## Design precheck (ownership / data model)

The value of these six items lives in four carriers. (1) **`INDEX.jsonl`** — after this
plan it holds three row kinds, not one: live brief rows, **classification** rows (item B),
and **backfilled** rows (item D). Single-writer is preserved: `review-record.py` is still
the only writer, and every kind is *appended*, never rewritten, so a correction never
destroys what it corrects. (2) **The session-pointer file** in reflection.py's external
ledger root — new, and deliberately outside the repository, because it holds a raw session
id and a pid list; nothing in it can ever be committed. (3) **`.claude/knowledge/heldout/`**
— the frozen fixture manifest, which pins existing committed artifacts by sha256 rather
than copying them. (4) **The prompt corpus** — `code-reviewer.md`, `flow-analyst.md`,
`flow-retro.md`, and three commands, which are edited only in line-neutral ways because
every command budget they sit in is at zero headroom.

The one place the model does **not** cover, stated plainly: a rejection recorded by a
session whose id cannot be proven is permanently unattributable. Item A makes that visible
and refuses to guess; it does not make it recoverable. Historical rejections that predate
Phase 0 are reachable only through item D, and only as *reconstructions*.

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` (CONTRIBUTING.md).
- Each config is executed with its own review record; the approval gate resolves the slug
  from the filename, which is why each is `ops-retro2-<phase>.json`.

## Rejection-brief search (mandatory Phase 0)

```
$ python3 .claude/operations/scripts/review-record.py rejections search \
      "session id brief index classify backfill"
REJECTIONS: 1 match(es)
  slug: fleet-skill-phaseA (round 2, REVISE 82)
```
**Validated against the tree, not trusted.** The hit is real and its two findings are:
(a) a test asserting registry rows that no operation in the config produced, and (b) a
byte-shrink claim assessed structurally rather than executed. Both are *fixture-audit*
defects — a test proving something the shipped config did not do. That is the same class
this plan is most exposed to, so it is answered directly in the Testing strategy below
("what a weaker version would not catch", per test) and in the two places it bites hardest:
item E's size claim is **measured**, not asserted, and item A's tests execute the shipped
hook rather than hand-writing the pointer file it produces. A single brief is a prior, not
a proof, and the store contains exactly one — silence about the other five items is
**unknown**, not evidence of safety.

---

## Phase trim — item E (`ops-retro2-trim.json`, 2 ops)

### Step E.1 — `.claude/agents/code-reviewer.md` (one op, 5 edits)

Cut rationale, keep every rule:

1. The Silent-Failure preamble's `/audit`-routing paragraph collapses to two lines. The
   phrase `not covered by the eval suite` is **kept verbatim** — `tests/test_008_b3c2`
   asserts it, and dropping it would trade one honest statement for a green diff.
2. `## Reporting Format` (the merged agent's per-finding schema) is replaced by a pointer
   to the canonical Output Format. This is the removal of a **conflicting duplicate**, not
   of a rule: two per-finding schemas shipped side by side and only the canonical one
   carries the mandatory `Class:` field, so the deleted one was actively wrong.
3. The merged section's second `## Severity Classification` table (the top-level
   **Severity Definitions** already governs) becomes a three-line calibration note. The
   four severity words it contained survive elsewhere in the file, which is checked.
4. + 5. The Machine-Readable Verdict Block's corpus-history paragraph and its gate-token
   paragraph are compressed to their rules; the rationale moves to Step E.2.

**What is NOT trimmed, and why.** `tests/test_008_b3c2_silent_failure_merge.py`'s `UNION`
list pins ~25 fragments of the merged section — including `Silent Failure Audit Summary`,
`Highest-Risk Files`, `Investigation Workflow` and the code-example tokens (`db.execute`,
`asyncio.gather`, `logger.debug`, …). Those are where the remaining bulk is. Cutting them
means editing that test's `UNION`, i.e. weakening a merge-completeness guarantee, which is
an owner call and not a planner's. It is left as a **named option**, not taken.

### Step E.2 — `.claude/knowledge/rejections/README.md`
**Action:** Modify. Append the rationale removed in E.1 (why the block is mandatory on
every round; why the number is a gate token) so nothing is lost, in the file that is read
on demand rather than loaded into every spawn.

### Measured size (`wc -c`, not asserted)

| File | Before | After | Δ |
|---|---|---|---|
| `.claude/agents/code-reviewer.md` | **22 305 bytes / 624 lines** | **21 422 bytes / 600 lines** | **-883 bytes, -24 lines** |

Measured by replaying the config's edits in memory against the file on disk, not estimated.

**This buys no gate margin, and the brief's premise that it would is wrong — flagged, not
silently resolved.** `code-reviewer.md` is not in `PIPELINE_AGENTS`
(`src/claudekit/context_floor.py:48` counts `planner.md`, `reviewer.md`, `implementer.md`
only), agents have no line ratchet in `ck lint`, and the floor's "agent descriptions"
category counts frontmatter descriptions, which this does not touch. Trimming it is worth
doing on its own merits — it is loaded into every `/code-review` and `/audit` spawn — but
the zero-headroom budgets are `code-review.md` 140/140, `refine.md` 466/466,
`review.md` 125/125 and the 43 000-char pipeline floor, and **none of them are affected**.
Every command edit in the phases below is therefore **line-neutral by construction**
(flags appended to lines that already exist), which is verified by a test, not by counting
in review.

**Validation:** `python3 -m pytest tests/test_008_b3c2_silent_failure_merge.py -q` ·
`python3 scripts/check-context-floor.py --check` · `python3 -c "import os;
print(os.path.getsize('.claude/agents/code-reviewer.md'))"` before/after.
**Rollback:** `git checkout -- .claude/agents/code-reviewer.md
.claude/knowledge/rejections/README.md`

---

## Phase session — item A (`ops-retro2-session.json`, 8 ops)

**The measured problem.** The one live brief records `session: unknown`. Measured in this
environment: `CLAUDE_SESSION_ID` and `CLAUDEKIT_SESSION_ID` are both **unset**; 21
transcripts were modified in the last two hours; the newest of them is
`agent-acc59c4dcc01e05a5.jsonl` — a **subagent** transcript — and the next three belong to
**concurrent sessions**, one of which is actively working in this repo.

**Therefore "most recently modified transcript" is not implemented.** It resolves, on this
host, to a subagent's file, and even filtered it cannot separate concurrent sessions. A
wrong id is strictly worse than `unknown`: `transcript-miner.py` would slice an unrelated
session and `flow-analyst` would attribute someone else's work as the cause of this
rejection, with nothing downstream able to detect it. `unknown` is honest and recoverable.

### Step A.1 — `.claude/hooks/reflection.py`
**Action:** Modify (additive). Add `record_session_pointer()`, `session_pointers()`,
`_pointer_path()`, `_ancestor_pids()` and `SESSION_POINTERS` / `POINTER_TTL_SECONDS`.

The pointer records `(session_id, this process's ancestor pids, transcript basename,
epoch)` into `ensure_ledger_dir()/session-pointers.jsonl` — the external ledger root,
which is **outside the repository by construction**, 0700, symlink-audited, and therefore
cannot be committed (satisfies "no session token in any tracked file"). Rows are keyed by
session id (rewrite-on-repeat), capped at 64, and expire after 24h. `int(datetime.now(
timezone.utc).timestamp())` rather than `time.time()` so no import is added.

### Step A.2 — `.claude/hooks/reflection-gate.py`
**Action:** Modify. `handle_session_start` calls `record_session_pointer(session_id,
field(event, "transcript_path", "transcriptPath"))` inside a bare `try/except` — a
SessionStart hook may never fail because a retro feature could not write a pointer.
This is the only place in the repo that holds an authoritative session id: it arrives in
the hook payload, and nothing else sees it.

### Step A.3 — `.claude/operations/scripts/review-record.py`
**Action:** Modify (9 edits).

1. `_session_from_pointers()` — intersects **this** process's ancestor chain with the
   recorded ones and returns a session id only when the match is **unique at the nearest
   depth**. Nesting resolves correctly (an inner `claude -p` shares the outer session's
   ancestors, so the *nearest* match wins); two genuinely concurrent sessions match at the
   same depth and the answer is `unknown`. `_ancestor_pids` is **imported from
   reflection.py**, not reimplemented — one definition of "who is my process tree", the
   same discipline that put `redact_secrets` in one file.
2. `agent-*` ids are excluded explicitly. `_SESSION_ID_RE` already rejects them (`g`, `n`,
   `t` are not hex), so the check is redundant **on purpose**: if that regex ever widens,
   the exclusion must not widen with it.
3. `_session_id()` — flag → env → **proof** → `"unknown"`. A non-empty value that is not
   transcript-filename-shaped is announced and dropped rather than recorded.
4. Resolution moves **inside** `emit_brief`, after the trigger check (every APPROVED write
   reaches that function too, and spawning `ps` to decide nothing is pure cost on the
   approval path). `emit_brief`'s fourth parameter becomes the *explicit* id.
5. **`unknown` is announced at write time**: one `WARNING` naming the slug and the
   consequence ("`transcript-miner.py` cannot resolve it; `/flow-retro` degrades to
   brief-only for this round"). It is emitted from inside the existing fail-soft
   `try/except BaseException`, so it cannot alter `cmd_write`'s return value.
6. `rejections stats` gains `unresolved_sessions=N` plus a `NOTE` when non-zero;
   `rejections search` reports how many of its hits are brief-only.
7. `record-code-review` gains `--session-id`, plumbed through to the write.

### Step A.4-A.6 — `/review`, `/refine`, `/code-review`
**Action:** Modify, **line-neutral** (the flag is appended to a line that already exists).
Each passes `--session-id "${CLAUDE_SESSION_ID:-}"`; an empty value is treated as absent.

**Say plainly what this does and does not do.** A slash command's bash fence has no
channel to the session id either — there is no env var, and the payload only reaches
hooks. So passing it through is *not* the fix: it makes the dependency visible at the call
site and it works the moment a wrapper or a future Claude Code release exports the
variable. **The fix is A.1 + A.2**, and everything else is best-effort-or-unknown.

### Step A.7 — `tests/test_rejection_briefs.py`
**Action:** Modify. Six tests; each is stated below with what a weaker version misses.

### Step A.8 — `.claude/knowledge/rejections/README.md`
**Action:** Modify. Document the resolution order, why recency is refused, and that
`session: unknown` means brief-only rather than "no transcript existed".

**Validation:** `python3 -m pytest tests/test_rejection_briefs.py tests/test_review_record.py
tests/test_reflection*.py -q` · `ruff check` · `mypy` · `shellcheck` (no shell changed).
**Rollback:** `git checkout -- .claude/hooks/reflection.py .claude/hooks/reflection-gate.py
.claude/operations/scripts/review-record.py .claude/commands/review.md
.claude/commands/refine.md .claude/commands/code-review.md tests/test_rejection_briefs.py
.claude/knowledge/rejections/README.md`

---

## Phase classify — item B (`ops-retro2-classify.json`, 5 ops)

### Step B.1 — `.claude/operations/scripts/review-record.py`
**Action:** Modify (6 edits). `rejections classify <slug> <round> --type T --trigger X
[--by NAME]`:

- **Append-only.** A classification is a new `{"row_type": "classification", …}` line in
  `INDEX.jsonl`. History is never rewritten; re-classifying appends again and readers take
  the last. A correction that destroys what it corrects is not a corpus.
- **Never guessed.** The subcommand refuses unless the `(slug, round)` brief row exists
  (exit 3) and unless `--type` is in the closed vocabulary (**exit 2** — argparse's
  `choices` rejects the value before the body runs; the body's own check exits 1 for a
  caller that bypasses argparse). Nothing infers a type from findings text: "a guessed classification is worse than an absent one" is preserved
  by having only an explicit human/analyst call able to write one.
- **The vocabulary is `flow-analyst.md`'s, not IBM's.** `missing-ops-json`,
  `file-ownership`, `security-surface`, `scope-overflow`, `drifted-anchor`,
  `missing-rollback`, `untested-behaviour`, `other` — the seven the analyst prompt already
  names, plus an escape hatch. One definition, two consumers; B.4 rewrites the prompt's
  prose list into exactly these tokens so they cannot drift.
- `_folded_rows()` applies the latest classification to each brief row; `search` and
  `stats` read folded rows, so a classification row never counts as a brief.
- The markdown brief gains a `<!-- classification: round N -->` section, so the
  "(unclassified — assigned by /flow-retro or a human)" line in the brief cannot go stale.
- `rejections stats --by-type` prints the `defect_type` and `trigger` distributions over
  **classified rows only**, with `unclassified=N` shown beside them and a line stating that
  unclassified rows are **not imputed**. A distribution that silently treats absent as
  "other" is the failure this whole field exists to avoid.

### Step B.2 — `tests/test_rejection_briefs.py` · Step B.3 — README ·
### Step B.4 — `.claude/agents/flow-analyst.md` (vocabulary + "call `classify`") ·
### Step B.5 — `.claude/commands/flow-retro.md` (line-neutral: `stats --by-type`)

**Judgement call (flagged):** `--trigger` is **not** a closed set. `flow-analyst.md`
defines trigger as "which reviewer rubric line caught it", and the rubric's lines are not a
stable enumeration; a closed list would go stale silently. It is validated by *shape*
(`[a-z0-9-]{3,40}`) only. If the owner wants it closed, the rubric line ids are the set to
close it on.

**Validation:** `pytest tests/test_rejection_briefs.py -q` · `ruff` · `mypy` ·
`python3 scripts/check-context-floor.py --check`
**Rollback:** `git checkout -- .claude/operations/scripts/review-record.py
tests/test_rejection_briefs.py .claude/knowledge/rejections/README.md
.claude/agents/flow-analyst.md .claude/commands/flow-retro.md`

---

## Phase heldout — item C (`ops-retro2-heldout.json`, 5 ops)

### What the corpus actually supports (measured, before designing anything)

88 verdict records in `.claude/reports/reviews/`. **All 88 are APPROVED**; scores span
90–96; 52 have a `plan` field pointing at a plan file that still exists; every record has
its `.ops.json` snapshot on disk.

**Therefore the held-out set can only detect one direction of regression, and the protocol
says so in its own README.** It answers "does an edited prompt still approve what it
approved?" — it catches a prompt edit that makes the reviewer *harsher*. It cannot catch
one that makes it *laxer*, because there is not a single recorded rejection to hold out.
The rejection corpus that would close that gap is exactly what the retro loop is now
accumulating (and what item D may reconstruct); until then this is half a harness and is
labelled as half a harness.

### Step C.1 — `.claude/knowledge/heldout/MANIFEST.json`
**Action:** Create. 14 fixtures, selected **deterministically**: for each distinct score
(90, 91, 92, 93, 94, 95, 96) the smallest and largest config by operation count, among
records whose plan file still exists, ties broken by slug. That spans 1–18 ops, 0–25 edits,
and includes the only multi-round record in the usable set (`fleet-skill-phaseA`). Each
entry pins `record`, `plan`, `snapshot`, the recorded `score`/`decision`, and the **sha256
of the plan and of the ops snapshot**.

Freezing is by hash, not by copy: the artifacts are already committed, and transcribing
fourteen plan documents into an ops config would be both enormous and a second copy that
drifts. The cost is that editing one of those plan files invalidates its fixture — which is
the *intended* behaviour of a frozen set, and `heldout-check.py` reports it as
`DRIFTED` (a fixture to re-freeze deliberately), never as a silent pass.

### Step C.2 — `.claude/knowledge/heldout/README.md`
**Action:** Create. The protocol, stated so a future edit knows exactly how it is scored:

1. Record the baseline: every fixture's recorded decision (all `APPROVED`, ≥90).
2. Apply the proposed prompt edit on a branch.
3. Re-review each of the 14 fixtures with `/review` (or `claude -p --agent reviewer`),
   saving each verdict into a results JSON.
4. `python3 scripts/heldout-check.py --results <file>` compares and **fails on any
   fixture that flips APPROVED → non-APPROVED**, and reports mean score delta.
5. A proposal ships only on a clean run, and the run is attached to the proposal.

**Step 3 is manual and is not automated — stated rather than implied.** Automating it
means a script that spawns `claude -p` fourteen times: it costs real tokens, it is
non-deterministic (the same plan can score 92 or 94 across runs), and it must never sit in
CI. So `heldout-check.py` automates the two *deterministic* halves — fixture integrity and
the comparison — and the replay is an owner-invoked step. The decision flip is the gate;
the score delta is reported but **not** gated, because a ±2 wobble between runs is noise
and gating on noise would make the harness a coin toss.

### Step C.3 — `scripts/heldout-check.py`
**Action:** Create. `--verify` (default): re-hash every fixture, print `OK` / `DRIFTED` /
`MISSING`, exit 0/4. `--results <json>`: verify first, then fold in replay verdicts, print a
per-fixture table, exit 5 on any decision regression or missing verdict. `--freeze`:
re-record the hashes, naming every artifact that moved. Stdlib only, py3.9, no
`datetime.UTC`, no PEP-604.

**`--freeze` exists because the set went stale while it was being written.** Two pinned
plans (`plan-dispatcher-payload.md`, `plan-fleet-skill-enhancement.md`) moved between
hashing and execution, and `--verify` caught both — the mechanism working, but a hash typed
into a plan is not re-typable by hand. If `--verify` reports `DRIFTED` immediately after
this phase executes, run `--freeze` and state in the commit why each artifact moved.

### Step C.4 — `tests/test_heldout_set.py`
**Action:** Create. Behavioural: run the shipped script.
### Step C.5 — `.claude/agents/flow-analyst.md`
**Action:** Modify. The "if no frozen set exists yet, say so" clause now names the real
path and the real command, and keeps the refusal for the direction the set cannot test.

**Validation:** `pytest tests/test_heldout_set.py -q` · `python3 scripts/heldout-check.py
--verify` (expect `OK` ×14 immediately after execution) · `ruff` · `mypy`
**Rollback:** `rm -r .claude/knowledge/heldout scripts/heldout-check.py
tests/test_heldout_set.py` · `git checkout -- .claude/agents/flow-analyst.md`

---

## Phase backfill — item D (`ops-retro2-backfill.json`, 5 ops)

### Step D.1 — `.claude/operations/scripts/transcript-miner.py`
**Action:** Modify. Add `project_dir_name()`, `transcript_roots(project_root)` and
`iter_project_transcripts(project_root)` — every `*.jsonl` for **one project**, excluding
`agent-*.jsonl` (subagent transcripts are not sessions) — plus `CLAUDEKIT_TRANSCRIPT_ROOT`
as an explicit override.

**Scoping is the whole control, and it was measured.** The home-wide glob reaches **83
project roots and 2021 transcripts, only 174 of them this repository's**, and every project
in the fleet is kitted — so an `ops-<slug>.json` mention filter scopes *nothing*, matching
other repositories' configs exactly as well as ours. An unscoped `--write` would have
appended another repository's finding text and raw session UUIDs into this repo's TRACKED
brief store. Scoped, the same dry run reads 174 transcripts and proposes 5 rows, all of
them this project's.

**`reflection.py`'s `_project_key()` cannot be reused for this, contrary to the obvious
guess.** It is a sha256 **digest** of the root by design ("the path itself records no host
path") — measured here as `a1dfac50d1af2c56`, which names no directory Claude Code ever
created. Claude Code names each project directory after the absolute path with every
character outside `[A-Za-z0-9-]` replaced by `-`
(`/Users/…/claudekit` → `-Users-…-claudekit`, and a `/.worktrees/` segment → `--worktrees-`,
both verified against the live layout). `project_dir_name()` implements exactly that and
**fails closed**: an unresolvable project directory yields *no* roots, never the home-wide
glob, because a silent widening back to 83 projects is the failure being removed.

The override exists for two reasons and only those: an operator whose layout differs, and
tests that must not scan the developer's real home directory. It relocates *where* the
scan looks; it does not manufacture any of the data the scan reads — the test's transcript
is written in the shapes the real corpus uses (list blocks, `tool_result`, `attachment`
records), which is exactly the fixture defect the miner phase already paid for once.

### Step D.2 — `.claude/operations/scripts/review-record.py`
**Action:** Modify. `rejections backfill [--limit N] [--since DATE] [--write]`:

- **`--dry-run` is the default and is not a flag.** Writing requires `--write`. The dry run
  prints transcripts scanned, verdict blocks found, how many were attributable, how many
  would be written, the reasons for every skip, and up to three sample rows — then states
  that nothing was written.
- **Reconstructed, and marked as such.** Rows carry `"source": "backfill"`,
  `"verdict_origin": "reconstructed"`, and a **negative** `round`. A transcript-derived
  verdict is not a recorded one: the round number is not in the transcript, so a negative
  ordinal (`-1`, `-2`, … oldest first per slug) both preserves the `(slug, round)`
  idempotency key and can never collide with a live positive round. *(Judgement call: the
  alternative was a separate `backfill_round` field, which would have meant teaching every
  reader a second key. Flagged.)*
- **Slugs are normalised through `ops_slug()` / `plan_slug()`** — the same functions the
  live records use. Capturing the stem directly yielded `contract-layer-c-pin.ops` for
  `ops-contract-layer-c-pin.ops.json`, keying a backfilled row under a slug that can never
  join its own live history, so the trend folding it exists for would silently never
  happen.
- **Attribution refuses rather than guesses**, exactly like item A: the slug comes from
  `ops-<slug>.json` / `plan-<slug>.md` mentions in the verdict entry and its run-up; **zero
  or more than one distinct candidate ⇒ skipped and counted**, never assigned to the
  likeliest.
- **Only non-approving verdicts** are backfilled — `is_rejecting()`, the same predicate as
  everywhere else — so backfill cannot introduce a row that looks like an approval.
- **It never touches `.claude/reports/reviews/`.** It writes the brief store only. A
  reconstructed verdict must not be able to become an execution authorisation, and the only
  way to guarantee that is to keep it out of the file `cmd_check` reads.
- **Credentials are scrubbed first, fail-closed.** `redact_secrets` is imported from
  `reflection.py` by path; if it is unavailable the subcommand **exits 1 and emits
  nothing**, before any transcript text reaches stdout or a tracked file. Findings then go
  through `_digest` as every brief finding does.
- `parse_verdict` is the only verdict reader. Backfill never re-derives a decision.

### Step D.3 — `tests/test_rejection_briefs.py` · Step D.4 — README ·
### Step D.5 — `.claude/agents/flow-analyst.md` (exclude `reconstructed` from trends, and
say how many rows were excluded — the same rule `gate-token` already has).

**Validation:** `pytest tests/test_rejection_briefs.py -q` · a **dry run against the real
corpus** (`rejections backfill` with no flags) whose report is pasted into the execution
evidence · `ruff` · `mypy`
**Rollback:** `git checkout -- .claude/operations/scripts/transcript-miner.py
.claude/operations/scripts/review-record.py tests/test_rejection_briefs.py
.claude/knowledge/rejections/README.md .claude/agents/flow-analyst.md`. Rows already
written by `--write` are removed by deleting the `"source": "backfill"` lines — they are
identifiable precisely because they are marked.

---

## Phase nits — item F (`ops-retro2-nits.json`, 2 ops)

### Step F.1 — `.claude/operations/scripts/review-record.py`
**Action:** Modify (7 edits). `cmd_write`'s body becomes
`write_verdict(plan, ops, *, from_review=None, score=None, decision=None,
session_id=None, verdict_origin="rubric", only_non_approving=False)`; `cmd_write(args)`
becomes a three-line argparse adapter; `cmd_record_code_review` calls `write_verdict(...)`
with keywords and the hand-built `argparse.Namespace` disappears. The five `args.*` reads
inside the body (`args.ops`, `args.from_review` ×3, `args.score`/`args.decision`,
`args.plan`) become parameters, and the two `getattr(args, …, default)` calls become
ordinary defaults — which is the actual point: today's correctness rests on inspecting
that every attribute happens to be present.

### Step F.2 — `tests/test_rejection_briefs.py`
**Action:** Modify. `test_the_prose_names_the_inputs_the_fence_needs` asserted that the
*prose* mentions `REVIEW_OUT` and `PLAN_FILE` — it passes on a fence that documents two
inputs and then passes neither. Replaced by
`test_the_fence_passes_the_inputs_it_documents`, which parses the **invocation** and
asserts `--report "$REVIEW_OUT"` and `--plan "$PLAN_FILE"` are actually passed to
`record-code-review`, plus a keyword-API test that `write_verdict` is callable with
keywords and that no `argparse.Namespace` is constructed anywhere in the module.

**Validation:** `pytest tests/test_rejection_briefs.py tests/test_review_record.py -q` ·
`ruff` · `mypy`
**Rollback:** `git checkout -- .claude/operations/scripts/review-record.py
tests/test_rejection_briefs.py`

---

## Testing strategy — what each new test catches that a weaker one would not

**No test may supply what production lacks.** That mistake cost four of the seven rounds
the predecessor plan paid for, so every case below names the weaker version it replaces.

| Test | A weaker version would pass when… |
|---|---|
| A1 `no env var ⇒ unknown AND a warning` | …the id were silently `unknown`. Asserting only the *value* passes on a silent degrade, which is the exact defect: the live brief already says `unknown` and nobody knew. The env vars are **stripped**, reproducing the shipped condition rather than the developer's. |
| A2 `the pointer written by the REAL hook resolves` | …the resolver only understood a hand-written pointer file. The test executes `reflection-gate.py` with a SessionStart payload and asserts the id the **hook** recorded is the id the **brief** carries — so a hook that never writes one, or a format drift between writer and reader, fails. |
| A3 `two concurrent sessions ⇒ unknown` | …the resolver took `matches[0]`. This is the measured environment (21 transcripts, concurrent sessions), and it is the only test that distinguishes "proof" from "first plausible answer". |
| A4 `a pointer with foreign pids is never used` | …the resolver fell back to recency. It asserts no *wrong* id, which is the property that matters; a test asserting "some id" would accept the fabrication. |
| A5 `stats reports unresolved_sessions` | …unknown briefs were counted as ordinary ones. Visibility is the deliverable, not the resolution. |
| A6 `all three call sites pass --session-id, line-neutrally` | …the flag were added and the file grew past its zero-headroom budget. Asserts both the flag **and** the line count. |
| B1 `classify refuses an unknown (slug, round)` | …it appended a row for a brief that does not exist, i.e. invented a classification. |
| B2 `classify refuses a type outside the vocabulary` | …free text entered the distribution and made it unqueryable again. |
| B3 `re-classifying appends and the reader takes the last` | …the writer rewrote history. Asserts the *first* row is still on disk. |
| B4 `stats --by-type never imputes` | …unclassified rows were folded into `other`, producing a confident distribution over data that does not exist. |
| B5 `the prompt's vocabulary equals the script's` | …the two drifted; a corpus assertion over `flow-analyst.md` and `DEFECT_TYPES`. |
| C1 `heldout-check --verify reports DRIFTED on a mutated fixture` | …verification passed on any tree, i.e. froze nothing. Mutates a real fixture in a temp copy. |
| C2 `--results fails on APPROVED → REVISE` | …the harness reported a regression and exited 0. The exit code **is** the gate. |
| C3 `manifest fixtures all exist and hash true today` | …the manifest were transcribed with a stale hash — the round-8 "assessed structurally, not executed" defect, in a new place. |
| D1 `default run writes nothing` | …the default were `--write`. Asserts `INDEX.jsonl` is **absent** after a default run. |
| D2 `--write marks rows as reconstructed and is idempotent` | …backfilled rows were indistinguishable from live ones, or a re-run doubled the corpus. |
| D3 `two candidate slugs ⇒ skipped, counted, never assigned` | …attribution guessed, which is item A's failure mode in a second place. |
| D4 `a credential in a transcript never reaches stdout or the brief` | …scrubbing were applied after emission, or only to the brief. Feeds a `sk-ant-`-shaped token through a real transcript-shaped fixture. |
| D5 `agent-*.jsonl is never scanned` | …subagent transcripts were mined as sessions. |
| F1 `write_verdict is callable with keywords; no Namespace is built` | …the refactor left the Namespace in place behind a new name. |
| F2 `the fence passes the inputs it documents` | …the prose named two inputs the invocation never passed — which is precisely today's test. |

`ECC_HOOK_PROFILE` is forced at module level in every file, per CLAUDE.md.

## Rollback plan

Six self-contained `git checkout --` / `rm` sets, listed per phase, applied in reverse
order (nits → backfill → heldout → classify → session → trim). No phase migrates data or
changes an on-disk schema that an unpatched reader consumes: `INDEX.jsonl` gains new row
kinds, and every reader of the old shape ignores rows it does not recognise because
classification and backfill rows are additive lines. `.claude/reports/reviews/` is not
touched by any phase.

## Risk assessment

- **High — `review-record.py` remains the write half of the execution-approval gate**, and
  four of six phases edit it. Nothing added runs before the record is durable; every
  addition is inside the existing fail-soft envelope or in a subcommand that `cmd_check`
  never reaches. Item F moves the body of the very function that gate calls: the proof is
  `tests/test_review_record.py` **unchanged** — if it still passes, the gate is unchanged.
- **High — item A adds `ps` subprocess calls near the approval path.** Mitigated by
  resolving *after* the brief trigger (so approving writes never pay), by a 12-hop bound
  and a 5s timeout, and by the enclosing `except BaseException`.
- **Medium — item D reads other sessions' transcripts.** Fail-closed scrubbing, dry-run by
  default, no writes outside the brief store, `agent-*` excluded.
- **Medium — PID reuse could, in principle, make a stale pointer match.** Bounded by the
  24h TTL and the uniqueness requirement; a collision yields `unknown` far more often than
  a wrong id, because two matches at one depth is the refusing case. Flagged, not
  eliminated.
- **Medium — the held-out set is one-directional** (no recorded rejections exist to hold
  out). Stated in its own README rather than implied away.
- **Low — context floor.** No line is added to any zero-headroom command; item E reduces
  an ungated file. `check-context-floor.py --check` runs in every phase's validation.
- **Low — tracked briefs and fixtures redden the secret self-scan once committed.** Known
  trap: re-run the gates **after** committing.

## Post-execution (manual, NOT operations)

```bash
python3 scripts/gen-docs.py && python3 scripts/gen-docs.py --check     # scripts/ gained a file
python3 scripts/gen-registry.py && python3 scripts/gen-registry.py --check
python3 scripts/gen-model-policy.py --check
python3 .claude/operations/scripts/review-record.py rejections backfill  # dry run, evidence
```
CHANGELOG `[Unreleased]` gets **one** entry covering all six items, added in the same
manual pass — six edits to one anchor would make the phases non-independently-executable,
the same reasoning the predecessor plan used.

## Judgement calls (flagged, not silently resolved)

1. **Item E buys no gate margin.** The brief's sequencing premise ("E is what buys margin
   back") does not hold: `code-reviewer.md` is gated by nothing. Every later item is made
   to fit by line-neutral edits instead. E is still done first and still worth doing.
2. **The deep trim of `code-reviewer.md` is not taken.** ~25 fragments of the merged
   silent-failure section are pinned by `tests/test_008_b3c2`'s `UNION`; cutting them means
   weakening a merge-completeness test. Owner call.
3. **Commands cannot know the session id.** Passing `--session-id` is honest plumbing, not
   a fix; the fix is the hook pointer. If the owner would rather not touch
   `reflection-gate.py`, the alternative is to accept permanent `unknown` and keep only the
   warning — which is a legitimate, smaller change.
4. **Process-tree proof over content proof.** The alternative — scanning recent transcripts
   for the ops slug being recorded — is stronger evidence but reads other sessions' files
   on the approval path and fails whenever the verdict text never reaches the session
   transcript (the `claude -p` path). Ancestry is cheap, local, and refuses cleanly.
5. **Negative round numbers mark backfilled rows.** Preserves one idempotency key at the
   cost of an odd-looking integer. The alternative field was rejected as a second key.
6. **`--trigger` is shape-validated, not a closed set** (see phase classify).
7. **The held-out set tests one direction only**, because 88 of 88 records are APPROVED.
8. **The held-out set freezes by hash, not by copy.** Editing a pinned plan invalidates its
   fixture on purpose; re-freezing is an explicit owner action.
9. **Held-out replay is not automated.** Fourteen `claude -p` spawns, non-deterministic and
   token-costly; only integrity and comparison are automated, and the README says so.
10. **Backfill is run by the owner, not by an operation.** The configs add the subcommand;
    no `run_command` executes it. The dry run belongs in the execution evidence.

## DoD

pytest · ruff · mypy · gen-docs --check · gen-registry --check · gen-model-policy --check ·
check-context-floor --check · shellcheck · `ck doctor --strict` · CHANGELOG · conventional
commit.
