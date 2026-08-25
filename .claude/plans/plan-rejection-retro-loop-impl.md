# Implementation Plan — Rejection Retro Loop (execution plan for the approved design)

**Slug:** `rejection-retro-loop-impl` · **Tier:** 3 · **Design contract:**
[`plan-rejection-retro-loop.md`](plan-rejection-retro-loop.md) (owner-approved)
**Evidence:** `.claude/reports/research/self-learning-agent-loops.md`

This document does not re-decide anything. It sequences the approved design into five
independently executable, independently reviewable ops configs.

## Design precheck (ownership / data model)

The value of this change lives in exactly three carriers: (1) **the review record store**
`.claude/reports/reviews/<ops-slug>.json`, whose `rounds[]` is the only durable trace of a
verdict — and which today only ever sees the round that passed; (2) **the brief store**
`.claude/knowledge/rejections/<ops-slug>.md` + `INDEX.jsonl`, tracked files that carry the
rejection signal across sessions; (3) **the prompt corpus** (`reviewer.md`,
`code-reviewer.md`, `planner.md`), which is both the producer of the signal and the thing
the loop eventually edits. Ownership is single-writer throughout: `review-record.py
cmd_write` is the only writer of records and briefs; `flow-analyst` **proposes** and never
writes to any of the three. The one place the model does not cover is pre-Phase-0 history —
it exists only inside session transcripts, which is precisely why `transcript-miner.py` is
in scope and why the analyst is built after capture has run, not before.

## Scope

- **In scope:** Phase 0 prompt/pipeline change; brief emission in `cmd_write`; the brief
  store; `transcript-miner.py`; `flow-analyst` + `/flow-retro`; `rejections search` and the
  `planner.md` Phase 0 call; behavioural tests.
- **Out of scope:** any cron/automatic cadence; the analyst self-applying edits; a frozen
  held-out plan set (the guardrail is *stated* in the analyst prompt, building the set is a
  follow-up); backfilling briefs from the 166 existing transcripts (the miner makes it
  possible; running it is an owner-gated operation, not an op in these configs).

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (CONTRIBUTING.md),
  or Edit/Write is blocked by this repo's own enforcement hooks.
- Each config is executed through the operations engine with its own review record; the
  approval gate resolves the slug from the config filename (`_approval_slugs`), which is
  why each file is named `ops-retro-<phase>.json`.

## Phase order (load-bearing)

Phase 0 is a hard prerequisite. The live corpus is **80 records / 80 APPROVED / 79-of-80
single-round**, so the brief trigger (2 non-approving rounds on one slug) can never fire
today — not because review always passes, but because rejecting rounds are never written.
Every later phase is inert until Phase 0 ships.

```
phase0  ──▶  capture  ──▶  miner  ──▶  analyst  ──▶  closure
(record      (brief +      (transcript  (flow-analyst  (rejections search
 rejections)  INDEX)        slicer)      + /flow-retro)  + planner Phase 0)
```

`miner` and `analyst` both depend only on `capture`; they are ordered miner-then-analyst so
the analyst prompt can reference a script that already exists.

---

## Phase 0 — record the rejections (`ops-retro-phase0.json`, 8 ops)

### Step 0.1 — `.claude/agents/reviewer.md`
**Action:** Modify. The Output Format section already says the block is mandatory; it does
not say *on a rejection*. Add the explicit every-round rule with the measured corpus number
as its justification, so a future editor cannot read the rule as "when approving".

### Step 0.2 — `.claude/agents/code-reviewer.md`
**Action:** Modify. This agent emits **no** `=== REVIEW ===` block at all, and deliberately
emits no numeric score ("a number invites another round"). Its rejections are therefore
100% unrecorded. Add a *Machine-Readable Verdict Block* section with a fixed
VERDICT→DECISION/SCORE mapping table, framed explicitly as a gate token rather than a
quality rubric, and restating that the Exit Rule — not the number — decides rounds.
`CANNOT REVIEW` emits no block (nothing was reviewed). See "Judgement calls" below.

### Step 0.2a — `.claude/operations/scripts/review-record.py`
**Action:** Modify (5 edits). Add `--only-non-approving`: the write refuses when the *parsed*
decision is `APPROVED`, exits **5**, and records nothing. Keyed on the decision word rather
than the score because `cmd_check` authorises on `decision == "APPROVED"` plus a threshold —
refusing every APPROVED regardless of score is strictly the conservative side of that gate.
Exit 5 is documented in the module docstring. Nothing about the default path changes: without
the flag, `write` behaves exactly as before.

**`CONDITIONAL` is deliberately NOT refused.** `cmd_check:395` requires the literal
`"APPROVED"`, so a recorded CONDITIONAL can never authorise execution — refusing it would
protect nothing and would drop a genuinely non-approving round out of the rejection corpus this
feature exists to build. CONDITIONAL rounds are real signal about where review friction sits.
The predicate therefore means exactly one thing — *could this verdict authorise execution?* —
the same discipline that removed the shell's duplicate parser: one definition, one scope. A
test asserts a recorded CONDITIONAL still fails `check` with exit 4.

### Step 0.2b — `.claude/commands/code-review.md` (Steps 5b + 5c, in one edit)
**Action:** Modify. Step 0.2 alone is **inert**: `/code-review` referenced `review-record.py`
nowhere, and `/review` never spawns `code-reviewer`, so the new block would be emitted into a
channel with no consumer. Add a Step 3b that binds the verdict to the ops.json behind the
implementation — **recording only `BLOCK` and `REQUEST CHANGES`.**

That restriction is a safety property, not a preference. `review-record.py` writes
score/decision at the TOP level, which is exactly what `/implement`'s gate reads; recording an
APPROVE from a *diff* review would let a review that never scored the plan authorise execution
of its ops.json. A non-approving verdict cannot — `check` still exits 4. The rejection corpus
wants only the rejections anyway, so nothing is lost.

**Document order is the contract: producer 5b, then recorder 5c.** The recorder was
originally Step 3b, anchored before Step 4, while its producer was Step 5b — shipped order
`3b, 4, 5, 5b`. An agent reads this command top to bottom, so the recorder ran **before**
anything wrote the report, found nothing, and skipped. The suite passed because the harness
ran producer-then-recorder, an order the document did not have: the same end-to-end gap as
rounds 3–5, expressed as ordering. Both sections are now emitted by **one** `add_after` edit
(two anchors could not express this — the recorder's anchor would have to be text the producer
had not inserted yet at validation time), and the harness **discovers** its execution order by
regex over the shipped headings rather than hardcoding it, so it cannot express an order the
document does not have.

**Step 5b produces the file Step 5c reads.** The recording step's `REVIEW_OUT` default
pointed at `.claude/reports/last-code-review.txt`, which **nothing in the repo wrote** — Step 5
is a display-only template. `[ -s "$REVIEW_OUT" ]` was therefore false forever and the step
skipped in silence, the third variant of one bug: *the recording path was never exercised
end-to-end under production conditions, and each round's test manufactured the precondition
production lacked* (round 3: the parse; round 4: `env` injection; round 5: the test wrote the
report file itself). The same op now adds **Step 5b**, a bash fence that `mkdir -p`s and writes
the report verbatim via heredoc at the point the report is produced.

**Every skip is announced.** Missing report, no plan found, no ops.json resolved — each prints
one line to stderr. Silent skipping is *how* all three variants survived review.

**The bind is observable.** The resolved plan and ops basenames are echoed before the write, so
a mis-bind from the `ls -t` default (kept — it matches `review.md:26`) is visible rather than
silent.

**The step binds its own inputs.** `$PLAN_FILE` and the review text are bound nowhere else in
`code-review.md`, and an unbound `PLAN_FILE` makes `resolve` fail, `OPS_FILE` empty, and the
whole body skip — **silently**. The fence therefore binds both itself, the way Step 1 builds
`TARGET`/`PR_NUM` from `$ARGUMENTS`: `REVIEW_OUT` defaults to
`.claude/reports/last-code-review.txt` (the report saved verbatim from Step 5) and `PLAN_FILE`
to the newest `.claude/plans/plan-*.md`, the same default `/review` uses. Both are explained in
prose immediately above the fence, and a test asserts every variable the fence reads is
assigned in it.

**A `CANNOT REVIEW` round skips this step entirely.** It emits no block by design, so
`parse_verdict` fails and the write exits 1 — the `*)` arm would otherwise print a recording
warning for a round that correctly recorded nothing. The fix is prose, not a wider `case`:
swallowing exit 1 would mask real errors.

**The shell does no verdict parsing at all — `--only-non-approving` does it.** An earlier
revision filtered the review text in shell before deciding whether to write. That is a second
parser, and two parsers read different things: `_BLOCK_RE` matches `===\tREVIEW\t===` (it uses
`\s*`) while no shell glob does, so on a two-block review with mismatched anchor whitespace the
filter took `REJECTED` from block 1 while `parse_verdict` wrote `APPROVED` from block 2 — the
escalation reopened through a tab. **Measured, not argued:** the old filter records `APPROVED`
on that input; the shipped path records nothing. Patching the shell pattern only moves the
mismatch to the next character class, so the decision moved inside the one real parser:
`write --only-non-approving` refuses `APPROVED`/`CONDITIONAL` with **exit 5** and writes
nothing. The command pipes the review straight through and treats exit 5 as the normal, quiet
outcome of a passing review. Step 0.2a adds the flag in the same phase, so Phase 0 is still
executable on its own.

### Step 0.3 — `.claude/commands/review.md`
**Action:** Modify. The scripted path already records unconditionally; the Task-tool path
(step 2) is prose that a model reads as "record the approval". Make it say: record the
verdict on **every** round, rejections included.

### Step 0.4 — `.claude/commands/refine.md`
**Action:** Modify. Same: expand the one-line comment above the `write --from-review -`
call so the `|| true` is not read as "this only matters when approving".

### Step 0.5 — `tests/test_rejection_briefs.py`
**Action:** Create. Phase-0 half only: eight tests that execute or assert on the **shipped**
Step 3b snippet (extracted from the command file, run under `bash`) — prose-REJECTED + APPROVED
block records nothing; a REVISE block records; two blocks with the approving one last records
nothing; **two blocks whose anchors differ in whitespace records nothing** (the round-4
regression); an approving verdict is refused *quietly*, with no WARNING; **every variable the
fence reads is assigned in it** (the round-5 inert-in-production regression); the prose names
both inputs; a `CANNOT REVIEW` round is told to skip.

**Nothing is injected into the snippet's environment.** The earlier helper exported
`PLAN_FILE` and `review_output` before running the fence, which kept the suite green while the
shipped path was inert — the test supplied what the command lacked and then proved the command
worked. Plus five tests of the `--only-non-approving` gate itself, a token-level guard that
fails if `sed`/`grep`/`awk`/`cut`/`DECISION`/`SCORE`/`APPROVED` reappears anywhere in the
fence (a four-literal blacklist missed `grep -q DECISION`), and spec test **#9** (a REVISE round produces a record
with `decision: REVISE`), plus corpus assertions that both reviewer prompts carry the
every-round rule and that every DECISION spelling in the code-reviewer mapping table is one
of `review-record.py`'s `VALID_DECISIONS`. `ECC_HOOK_PROFILE` forced explicitly at module
level. Later phases extend this same file.

### Step 0.6 — `.claude/knowledge/rejections/README.md`
**Action:** Create. The store's contract, written before anything writes to it: what is in a
brief, what is *never* in one (absolute transcript path, SessionStart reflection token), and
why a raw session UUID is present on purpose.

**Validation:** `python3 -m pytest tests/test_rejection_briefs.py -q` ·
`python3 scripts/check-context-floor.py --check`
**Rollback:** `git checkout -- .claude/agents/reviewer.md .claude/agents/code-reviewer.md
.claude/commands/review.md .claude/commands/refine.md` ·
`rm tests/test_rejection_briefs.py .claude/knowledge/rejections/README.md`

---

## Phase capture — brief emission (`ops-retro-capture.json`, 4 ops)

### Step C.1 — `.claude/operations/scripts/review-record.py`
**Action:** Modify (one `code_edit` op, 5 edits).

1. **Imports** — add `importlib.util` and `subprocess`.
2. **Docstring/Usage** — document the new `--session-id` flag and the brief side effect.
3. **`_records_dir` → `_project_root`** — extract the ancestor walk so the brief store and
   the record store resolve the repo root through one function instead of two copies.
4. **New `rejections` section** (inserted before `cmd_resolve`): `REJECTIONS_DIR`,
   `BRIEF_TRIGGER = 2`, `is_rejecting()`, `_rejections_dir()`, `_sanitizers()`,
   `_digest()`, `_session_id()`, `_prompt_version()`, `_index_rows()`, `_append_brief()`,
   `emit_brief()`.
5. **`cmd_write` call site + `--session-id` argument.**

**Fail-soft, by construction — not bolted on.** `cmd_write` is the write half of the
execution-approval gate. Three independent properties make brief emission unable to
withhold an approval:
- **Ordering:** `emit_brief` is called *after* both `_safe_write` calls have already put
  the record and the snapshot on disk. There is no path where the brief is attempted
  before the verdict is durable.
- **Containment:** the call is wrapped in a bare `try/except Exception` that warns to
  stderr and falls through; nothing inside it can alter `cmd_write`'s return value.
- **Interrupts still work:** the guard is `BaseException` (so a `SystemExit` raised by
  `reflection.py`'s module-level code cannot fail a write that already succeeded), but a
  `KeyboardInterrupt` is warned about and then **re-raised** — silently eating Ctrl-C on the
  approval path would be its own defect.
- **Degradation:** every sub-failure has a defined non-fatal outcome — sanitizers
  unimportable ⇒ brief skipped with a note (never written unsanitised); corrupt INDEX line
  ⇒ that line skipped with a note; unresolvable session id ⇒ `"unknown"`; git absent ⇒
  `prompt_version: "unknown"`; symlink on the store path ⇒ refuse and note.

**Safety of tracked content.** Findings go through `reflection.py`: `_safe_text` first
(which *rejects*), falling back to `bounded_token` (which *digests*). So a finding carrying
an absolute path or a credential-shaped token lands as a digest rather than either leaking
or silently dropping the signal. The SessionStart reflection token is never read here. The
session UUID is recorded raw and deliberately — it is a local transcript filename, and a
hash makes root-cause analysis impossible — but only if it matches `^[0-9a-fA-F-]{8,64}$`.

**Verdict provenance.** `verdict_origin` (`rubric` | `gate-token`, new `--verdict-origin`
flag, default `rubric`) is written to the record, folded through `ROUND_KEYS` into `rounds[]`,
and copied to the index row. Without it a reviewer-judged 60 and code-reviewer's
table-derived 60 are the same integer in the corpus, and any score trend the analyst reads is
an artefact of which agent happened to review. `flow-analyst` is told to exclude `gate-token`
rows from every trend claim (they still count for defect type and trigger).

**Idempotency.** Key = `slug` + `round`. `INDEX.jsonl` is appended only when no existing
row carries that pair; the markdown brief is appended only when its `<!-- round: N -->`
marker is absent. Re-running `write` for the same round is a no-op on both files.

**Trigger.** Count non-approving rounds across `rounds[] + the current verdict`; emit when
that count reaches `BRIEF_TRIGGER` (2) **and** the current round is itself non-approving.
`is_rejecting()` is the exact complement of `cmd_check`'s gate, so "rejection" has one
meaning in the file.

### Step C.1b — `.claude/commands/code-review.md`
**Action:** Modify. Add `--verdict-origin gate-token` to the call wired in Step 0.2b. It is
deliberately split across phases: the flag does not exist until Step C.1 adds it, and each
phase must be executable on its own.

### Step C.2 — `tests/test_rejection_briefs.py`
**Action:** Modify. Add spec tests **#1** (two REVISE rounds ⇒ brief + exactly one INDEX
line per round), **#2** (REVISE then APPROVED ⇒ no brief), **#3** (path/credential-shaped
finding ⇒ refused or digested), **#4** (no raw reflection token anywhere; session UUID
present and equal to what was passed), **#5** (re-run ⇒ no duplicate INDEX line), **#8**
(corrupt INDEX line ⇒ skipped with a note, exit still 0 and the verdict still recorded).

### Step C.3 — `.claude/knowledge/rejections/.gitignore`
**Action:** Create. **Documentation, not a mechanism** — stated as such in the file. No
ancestor rule ignores `.claude/knowledge/` today, and if one ever did, git cannot re-include
a path underneath an excluded *directory* from a nested `.gitignore` anyway; the fix would
have to un-ignore the directory in the repo-root file. The negations are kept only to record
the intent where someone will look for it.

**Validation:** `python3 -m pytest tests/test_rejection_briefs.py tests/test_review_record.py -q`
(the existing review-record suite is the regression proof that the approval path is
unchanged) · `ruff check` · `mypy`
**Rollback:** `git checkout -- .claude/operations/scripts/review-record.py tests/test_rejection_briefs.py`

---

## Phase miner — transcript slicer (`ops-retro-miner.json`, 3 ops)

### Step M.1 — `.claude/operations/scripts/transcript-miner.py`
**Action:** Create. `transcript-miner.py <session-uuid> --around <ops-slug>`. Globs
`~/.claude*/projects/*/<uuid>.jsonl` (the root wildcard covers every account directory),
streams line by line, and emits the reviewer verdict block, the run-up to it, and the tool
failures in that window. Exit 3 when no transcript matches — a pruned or version-moved
transcript is normal, never an error. Output capped by `--max-lines` (default 400) and per
line, so a tens-of-MB file can never enter a context window whole.

**Written against the real corpus, not a guess.** Surveyed 2002 live transcripts and one
647-entry file: `message.content` is **always a list of typed blocks** (`text`, `thinking`,
`tool_use`, `tool_result`) and ~36% of entries are `attachment`/`system` records with no
message at all. The first draft assumed `content` could be a bare string — a shape with **zero
occurrences** in real data — and fell through to `json.dumps(entry)` for anything else. Run
against a real transcript it emitted whole hook payloads: terminal escape sequences, hook
stdout, and **absolute transcript paths**, into output whose entire purpose is to stay small
and quotable and which gets pasted into committed reports. The synthetic fixture never caught
it because it was shaped to the code rather than to reality. Now: only `user`/`assistant`
entries are read, blocks are handled by type (`thinking` dropped — largest and least
reviewable; `tool_use` reduced to its name, since `input` holds paths and command lines),
there is **no raw-JSON fallthrough**, and every emitted line passes a host-path redactor.
`--list` no longer requires `--around` and prints filenames rather than absolute paths.

### Step M.1b — `.claude/hooks/reflection.py`
**Action:** Modify (additive only). Add `redact_secrets()` plus its vendor-marker patterns
beside `looks_like_credential` and `_SECRET`.

**Why here and not in the miner.** `tool_result` blocks are the channel that actually carries
`.env` reads, `env` dumps, `settings.local.json`, and git remotes with tokens — and this output
is quotable into `.claude/reports/retro/<date>.md`, which is **tracked**. The briefs get
credential treatment; this strictly higher-risk raw channel was getting less. A second
credential pattern inside `transcript-miner.py` would be two definitions of "what a secret
looks like" that must stay in sync — the same one-definition-two-scopes failure that produced
the round-3 bug. So the knowledge stays in one file and gains a **third disposition**:
`_safe_text` rejects, `bounded_token` digests, `redact_secrets` **redacts in place** so the
evidence stays readable. Every existing name is untouched; the function is new.

Covers `sk-`/`sk-ant-`, `ghp_`/`gho_`/`github_pat_`, `AKIA`, `xox*`, `Bearer <tok>`,
`-----BEGIN * PRIVATE KEY-----`, and `"…(token|secret|key|password)…": "…"`, then an entropy
pass that reuses `looks_like_credential` unchanged, piece by piece, so prose survives.
Labelled in its own docstring as a shape heuristic, not proof (hard rule 6).

### Step M.2 — `src/claudekit/cli/main.py`
**Action:** Modify. Add `transcript-miner.py` to `ck doctor`'s required-scripts list, so a
half-installed tree is reported rather than discovered by the analyst at run time.

### Step M.3 — `tests/test_rejection_briefs.py`
**Action:** Modify. Spec test **#7** plus the shape regressions: the fixture is rebuilt in
the **shapes the real corpus uses** (list blocks, a `thinking` block, a `tool_use` with a path
in its input, an `attachment` record carrying an absolute path, an errored `tool_result`), and
asserts the verdict window is returned, no harness entry is dumped as raw JSON, no host path
survives to stdout, `thinking` text is not emitted, `tool_use` is reduced to its name, `--list`
works without `--around`, and an unknown UUID exits 3 naming degradation rather than failure.

**Miner wiring:** `transcript-miner.py` imports `redact_secrets` by path and **fails closed**
— no scrubber, no output (exit 1), never a silent downgrade to raw tool text. Also documented:
`FAILURE_MARKERS` is a substring grep, not a verdict reader, so `REJECTED` matches any line
containing the word; the analyst reads hits as failure *signals*, never as verdicts.

**Validation:** `python3 -m pytest tests/test_rejection_briefs.py -q` · `ck doctor --strict`
**in this repo**; see Post-execution for installed trees.
**Rollback:** `rm .claude/operations/scripts/transcript-miner.py` ·
`git checkout -- src/claudekit/cli/main.py tests/test_rejection_briefs.py`

---

## Phase analyst — `/flow-retro` + `flow-analyst` (`ops-retro-analyst.json`, 3 ops)

### Step A.1 — `.claude/agents/flow-analyst.md`
**Action:** Create. The **only** new agent. ExpeL-shaped: pool briefs, extract insights,
and emit explicit **ADD / EDIT / UPVOTE / DOWNVOTE** operations over a maintained insight
list — the operation set is what stops the checklist growing monotonically. Phases inside
the one agent: (0) sample-size gate, (1) ODC classification, (2) root cause across the
three causes that need opposite fixes (weak plan / miscalibrated rubric / underspecified
task), (3) best practice read FIRST from `.claude/reports/research/` — the grant lists no MCP tools, so an unanswerable context7 question is recorded as a stated gap rather than guessed at (Judgement call 8), (4) proposal.
Guardrails from §6 are written into the prompt as refusals, not advice: external anchor
metric mandatory (ops executed / tests passed / human accepted — the reviewer score is not
an oracle), never tune planner and reviewer in the same cycle, bounded edit budget, no
monotonic growth, and the sample-size gate (≥5 briefs across ≥3 sessions) labelled in the
prompt as engineering judgement rather than a cited result. Output:
`.claude/reports/retro/<date>.md` + a paired ops.json. **Proposes only; never applies.**
`model: opus` (matches the `most-capable` row added in Step A.3).

### Step A.2 — `.claude/commands/flow-retro.md`
**Action:** Create. On demand only — no cadence, no cron. Gathers the INDEX, applies the
sample-size gate before spawning anything, dispatches `flow-analyst`, and hands the owner a
proposal. Degrades to brief-only when the miner exits 3.

### Step A.3 — `.claude/model-policy.json`
**Action:** Modify. One `roles` row for `flow-analyst`, `tier: "most-capable"`, inserted in
alphabetical position after `explore`. Tier name only, never a vendor model name.
Without this row `gen-model-policy.py --check` fails.

**Validation:** `python3 scripts/gen-model-policy.py --check` ·
`python3 scripts/check-context-floor.py --check` · then **regenerate, then verify** for the
two generator-owned artifacts — `python3 scripts/gen-registry.py && python3
scripts/gen-registry.py --check`, `python3 scripts/gen-docs.py && python3 scripts/gen-docs.py
--check`. A hand-added agent file is *designed* to fail `gen-registry.py --check`
(`scripts/gen-registry.py:212-216`), so listing `--check` alone as this phase's gate was a
gate that could not pass. `flow-analyst.md` uses the canonical `## Skill Loading` heading with
bold skill names, so the generator derives its mapping rather than routing it to
`agentsWithoutSkills`.
**Rollback:** `rm .claude/agents/flow-analyst.md .claude/commands/flow-retro.md` ·
`git checkout -- .claude/model-policy.json`

---

## Phase closure — the feedback loop (`ops-retro-closure.json`, 4 ops)

### Step L.1 — `.claude/operations/scripts/review-record.py`
**Action:** Modify (one op, 2 edits): `cmd_rejections_search()` + the `rejections search`
subparser. Mirrors `knowledge-ledger search` exactly — same exit contract (0 = hit, 3 = no
match), same "this is a prior, not a proof" closing line, same "silence is not evidence"
note — so `planner.md` Phase 0 reads identically for both stores.

### Step L.2 — `.claude/agents/planner.md`
**Action:** Modify. Phase 0 gains a mandatory `rejections search` call, copying the shape of
`debugger.md:215`: build the query, search, exit 3 ⇒ continue, exit 0 ⇒ validate the prior
against the current tree before trusting it, silence is not evidence. **Without this step
the briefs are an archive, not a loop.**

### Step L.3 — `tests/test_rejection_briefs.py`
**Action:** Modify. Spec test **#6**: `rejections search` exits 3 with no match and 0 on a
hit; plus a corpus assertion that `planner.md` Phase 0 actually contains the call.

### Step L.4 — `CHANGELOG.md`
**Action:** Modify. One `[Unreleased] / ### Added` entry covering the whole feature. Single
entry in the final phase rather than five competing edits to the same anchor.

**Validation:** full DoD (below)
**Rollback:** `git checkout -- .claude/operations/scripts/review-record.py
.claude/agents/planner.md tests/test_rejection_briefs.py CHANGELOG.md`

---

## Post-execution (manual, NOT operations)

`gen-docs.py` is **not** on the `run_command` allowlist (`shared.py:ALLOWED_RUN_COMMANDS` —
formatters and lockfile generators only), and hard rule 8 forbids hand-editing counts. So
after the analyst phase executes, run by hand:

```bash
python3 scripts/gen-docs.py            # regenerate agent/command counts
python3 scripts/gen-model-policy.py    # sync flow-analyst frontmatter to its tier row
python3 scripts/gen-registry.py        # register flow-analyst's skill mapping
python3 scripts/gen-registry.py --check   # then verify
python3 scripts/gen-docs.py --check
```

**Re-sync installed trees.** The miner phase adds `transcript-miner.py` to `ck doctor`'s
required-script list, so `ck doctor --strict` reports it Missing against any tree installed
before this change until the kit is re-installed/synced there. That is the gate working, not
a defect — but it must not be discovered by a user.

## Testing strategy

One behavioural file, `tests/test_rejection_briefs.py`, built up phase by phase and holding
all 9 spec cases. Every test drives the real script through `subprocess` in a temp tree —
no imports of private helpers, no structural assertions about function names. Case **#9** is
the Phase-0 regression and must fail if either reviewer prompt loses the every-round rule.
`ECC_HOOK_PROFILE` is forced explicitly at module level, per CLAUDE.md.

## Rollback plan

Each phase is a self-contained `git checkout --` / `rm` (listed per phase above). Reverse
order: closure → analyst → miner → capture → phase0. Nothing here migrates data or changes
an existing on-disk schema: `rounds[]`, `score`, `decision` and `ops_sha256` are written
exactly as before, so a rollback of any phase leaves existing records readable by the
unpatched script, and the brief store is purely additive (delete the directory).

## Risk assessment

- **High — `cmd_write` sits on the execution-approval path.** A crash here does not
  degrade the retro feature, it withholds an approval. Mitigated by ordering + containment
  + per-failure degradation (Phase capture), and proven by re-running the *existing*
  `tests/test_review_record.py` unchanged.
- **High — `review-record.py` is a hub.** It is called by `/review`, `/refine`,
  `/implement`'s STEP 0 gate, and `execute-json-ops.py`'s approval gate. Two phases edit it;
  neither touches `cmd_check`, `cmd_diff`, or any field those readers consume.
- **Medium — code-reviewer's verdict vocabulary changes shape.** It gains a derived number
  in a machine block. If a model starts *citing* that number, the "count, not score" exit
  rule erodes. Mitigated by explicit prompt framing; flagged below as a judgement call.
- **Medium — tracked briefs redden the secret self-scan once committed.** Known trap: re-run
  the gates AFTER committing, not before.
- **Low — transcript layout is Claude Code's, not ours.** Pruned or moved transcripts are
  exit 3 by design.
- **Low — context floor.** One agent + one command; descriptions kept short and gated by
  `check-context-floor.py --check` in the analyst phase.

## Fixture audit (round-6, whole plan)

Every place a test supplies something production must produce, re-checked with that lens:

| Phase | Fixture | Verdict |
|---|---|---|
| phase 0 | step **order** | **WAS the defect (round 6).** The harness ran 5b→5c while the document said 3b→…→5b. It now derives the order by regex from the shipped headings and asserts it, and a static test pins `index(5b) < index(5c)`. |
| phase 0 | report file at `REVIEW_OUT` | **WAS the defect.** Now produced by executing Step 5b's own fence; only the report *payload* is substituted, because supplying the report is the reviewer's job. |
| capture | brief store, `INDEX.jsonl` | Clean — both are created by `emit_brief` itself; tests only read what the shipped code wrote. |
| capture | `.claude/reports/reviews/`, plan + ops files | Clean — `cmd_write` mkdirs the records dir, and plans/ops are genuine user inputs. |
| miner | session transcript | **WAS a defect of the same class**, in shape rather than existence: Claude Code produces transcripts (this kit cannot), but the fixture used a shape the real corpus never emits, hiding a raw-JSON dump and a host-path leak. Fixture rebuilt from a survey of 2002 real transcripts; the fixed miner re-verified against a real one. |
| analyst | `.claude/reports/retro/` | Clean — written by `flow-analyst`'s `Write`, which creates parents. Nothing asserts on it. |
| closure | `INDEX.jsonl` for `rejections search` | Clean — produced by real `write` calls in the test body. |

## Follow-ups (accepted, not done here)

**Every budget this change touches now sits at or near 100%. The next one-line addition to
any of them re-breaks a gate that is currently green.** Recorded so the next person meets it
as a known constraint rather than a surprise CI failure:

| Gate | After this change | Limit | Headroom |
|---|---|---|---|
| `command-budget` `code-review.md` | 140 | 140 | **0 lines** |
| `command-budget` `refine.md` | 466 | 466 | **0 lines** |
| `command-budget` `review.md` | 125 | 125 | **0 lines** |
| `command-budget` `flow-retro.md` | 38 | 40 | 2 lines |
| `check-context-floor` pipeline agent bodies | 42816 | 43000 | **184 chars (99.6%)** |

Adding to any of the three zero-headroom commands means trimming the same file first, or an
owner-gated baseline change — `ck lint --update-baseline` is not a unilateral call. The floor
is the tighter one in practice: `planner.md` and `reviewer.md` are loaded into **every**
pipeline spawn, so a sentence there costs more than a sentence anywhere else.

Three MINORs from the round-8 review, deliberately deferred:

1. **`code-reviewer.md` grew ~42 lines and was not trimmed.** It is not in `PIPELINE_AGENTS`
   (`context_floor.py:48` counts only `planner`, `reviewer`, `implementer`) and agents have no
   line ratchet, so nothing gates it today. Worth trimming when that file is next opened.
2. **`cmd_record_code_review` hand-builds an `argparse.Namespace`** to call `cmd_write`.
   Correct as shipped — every attribute `cmd_write` reads is present and its `getattr`
   defaults cover the rest — but a shared options dataclass would make that safe by
   construction instead of by inspection.
3. **`tests/test_rejection_briefs.py` asserts the command's prose names its inputs**, which is
   redundant with the four tests that execute the shipped fence. Harmless, and it fails loudly
   if the prose and the fence drift apart, so it stays until it costs something.

## DoD

pytest · ruff · mypy · gen-docs --check · gen-registry --check · gen-model-policy --check ·
check-context-floor --check · shellcheck · `ck doctor --strict` · CHANGELOG · conventional
commit.

## Judgement calls (flagged, not silently resolved)

1. **code-reviewer's score.** The spec says code-reviewer must emit the anchored block on
   every round; the agent's own Exit Rule says "do not emit a numeric score", and
   `review-record.py` refuses to parse a block without `SCORE:`. Resolved by a fixed
   VERDICT→SCORE mapping table (95/92/75/60) framed as a gate token. The alternative —
   teaching `review-record.py` to accept a score-less block — changes the parser on the
   approval path and was rejected as higher risk. **Owner may prefer the alternative.**
2. **`CANNOT REVIEW` emits no block.** Nothing was reviewed, so there is no verdict to
   record; the caller sees NO RECORD and fails closed. Not stated in the spec. Step 3b's prose
   tells such a round to skip the step, so its unparseable-verdict exit 1 never reaches the
   warning arm — the `case` is NOT widened to swallow exit 1, which would mask real errors.
3. **Session id source.** The spec assumes a session id reaches `cmd_write`; no env
   contract is documented for it. Resolved as `--session-id` flag → `CLAUDE_SESSION_ID` →
   `CLAUDEKIT_SESSION_ID` → `"unknown"` (matching `dispatch.sh:185`/`lib.sh:168`). The
   commands are **not** edited to pass `--session-id`; the env var already covers the live
   path. **Flagged:** if the owner wants it explicit, that is a further `review.md`/
   `refine.md` edit.
4. **`prompt_version`.** The spec requires it but does not define it. Resolved as short git
   HEAD of the repo holding the prompts, `"unknown"` when git is unavailable.
5. **ODC `defect_type` / `trigger` are recorded EMPTY, and nothing can yet fill them.**
   `cmd_write` cannot classify a defect and a guessed label is worse than an absent one, but
   that leaves two fields with no writer at all. **Stated follow-up (not in these configs):**
   a `review-record.py rejections classify <slug> <round> --type T --trigger X` subcommand
   that appends a corrected INDEX row (append-only, same as every other write here), so the
   analyst or a human can close the loop. Until it exists, the distribution-shift analytic in
   §5 of the spec runs on hand-annotated data or not at all — the analyst says so in its
   report.
6. **Backfill is not an operation.** The spec calls the miner the sole source for
   pre-Phase-0 data but does not order a backfill run; running it over 166 transcripts is
   owner-gated and left out of these configs.
7. **CHANGELOG is edited once, in the closure phase**, not per phase — five edits to the
   same anchor would make the phases non-independently-executable.
8. **`flow-analyst` cannot call context7, and the prompt says so plainly.** The grant lists
   no MCP tools, so "record the gap" is the NORMAL path rather than a fallback: it names the
   unanswered question and the owner decides whether to run context7 or widen the grant. The
   spec's "call context7 yourself" assumes an MCP grant this agent does not have; granting
   MCP tools to a new agent is an owner decision, not a planner's.
9. **`flow-analyst`'s tool grant is the enforcement.** It holds `Read/Grep/Glob/Write` and
   **no `Bash` and no `Edit`** — so it cannot modify a prompt in place, and `/flow-retro`
   runs `transcript-miner.py` on its behalf. `Write` is required (its outputs are files) and
   is scoped to `.claude/reports/retro/` **by instruction, not by a guard**; the prompt says
   exactly that rather than asserting an enforcement the grant does not provide (hard rule 6).
10. **The frozen held-out plan set** (§6 held-out validation) is *stated* in the analyst
   prompt as a precondition for shipping a prompt edit, but no set is constructed here.
   That is a follow-up, and the analyst is told to refuse a ship recommendation without it.
