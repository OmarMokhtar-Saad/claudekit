# Plan: planner-token-cap

## Overview

Planner runs burn context on two mechanisms that the prompt only *asks* them not to use:
scratch scripts, and single Bash results of 38–66K chars. Measured: one qa-agents planner run
reached 401K context over 89 turns (20.4M cumulative cache-read tokens), writing `disc.sh`
(20 Write/Edit), `p1a_tests.py` (10), `p1a.py` (9) and slurping results of 58K/57K/42K/41K/38K
chars. Across 40 recent planner runs in 3 repos, planners that *do* carry the "hard ceiling /
compose in memory / no scratchpads" block still end at 120–204K with max single tool result
45–66K chars. Conclusion: the prompt is advisory; there is no mechanical cap.

This plan adds one — a `max_chars` operation in the existing PostToolUse output filter, wired
as a lowest-precedence catch-all capping every Bash stdout at 12,000 chars — and tightens the
planner and reviewer discovery budgets to match it.

## Phase 0: Design Precheck

Ownership: `.claude/hooks/output_filter.py` owns *all* stdout rewriting for Bash PostToolUse
(`tests/test_output_filter.py::test_only_one_hook_rewrites_tool_output` enforces that it is
the sole rewriter), and `.claude/hooks/output-filters.json` is the declarative data it reads.
The value of this change therefore sits in exactly those two files plus their test sibling —
all covered. The prompt half of the value sits in `.claude/agents/planner.md` and
`.claude/agents/reviewer.md`, also covered. No new files are created, so no component count
moves and `scripts/gen-docs.py --check` is unaffected by construction.

Prior-art searches (mandatory): both were run by the invoking session.
`review-record.py rejections search` returned two hits on the keyword "truncate", both in
iron-law flag tables of unrelated briefs — no validated match to this change.
`knowledge-ledger.py search` returned no match. Neither constrains this plan.
Agent memory *does* carry a directly relevant prior: `a-green-check-can-measure-nothing`
(prove a check can fail before trusting it) and `mutation-proof-names-the-wrong-mechanism`
(run every new test file, apply the claimed mutant). Both are honoured by the mutation
controls named per test below.

## Scope

In scope (4 files edited, 0 created, 0 deleted):

- `.claude/hooks/output_filter.py` — new `max_chars` operation.
- `.claude/hooks/output-filters.json` — new `bash-output-cap` base filter (12,000 chars).
- `tests/test_output_filter.py` — `TestMaxChars` regression class + one updated assertion.
- `.claude/agents/planner.md` — per-call output cap, no-scratch-script, no-test-authoring lines.
- `.claude/agents/reviewer.md` — mirrored short discovery budget.
- `CHANGELOG.md` — `[Unreleased]` entry.

Out of scope (named, not done here): fleet sync of the new filter + prompt lines to kitted
projects — including qa-agents, whose `planner.md` predates the ceiling block entirely. That
is a **manual owner step** (`ck fleet update --yes --exclude qa-agents`, then a surgical copy
for qa-agents per `qa-agents-hardened-scripts`), owner-gated, not part of this plan.

## Prerequisites

- `ECC_HOOK_PROFILE=minimal` present in `.claude/settings.local.json` (session start rebuilds it).
- Baseline green: `python3 -m pytest tests/test_output_filter.py -q`.

## Implementation Steps

### Step 1 — `max_chars` bound constant

- **File:** `.claude/hooks/output_filter.py`
- **Action:** edit (op 1, edit 1)
- **Description:** Add `MIN_MAX_CHARS = 200` beside the existing bounds.
- **Details:** A cap below ~200 leaves a head and tail too small to carry context, making the
  filter noise. Bounds live together because "a filter file is data, and unbounded data on a
  hot path is a denial of service".
- **Done when:** the constant exists and is referenced by `compile_filter`.

### Step 2 — parse and validate `max_chars`

- **File:** `.claude/hooks/output_filter.py`
- **Action:** edit (op 1, edits 2–4)
- **Description:** `compile_filter` accepts `{"max_chars": <int>}`, refusing it unless the
  filter declares `"lossy": true` (same rule `tail_lines` already enforces — dropping the
  middle is lossy), unless the value is a non-bool `int >= MIN_MAX_CHARS`. The compiled dict
  gains a `"max_chars"` key; the "no usable op" guard becomes
  `strip is None and tail is None and cap is None`.
- **Details:** Unknown op keys still return `None` (drop the filter) — the existing
  fail-closed-on-nonsense behaviour is preserved.
- **Done when:** a filter with `max_chars` and no `lossy` flag is dropped; with it, compiled.

### Step 3 — apply the cap (head + tail + marker)

- **File:** `.claude/hooks/output_filter.py`
- **Action:** edit (op 1, edits 5–7)
- **Description:** After strip/tail, join the kept lines; if the result exceeds the cap, keep
  `cap // 2` leading chars and `cap - cap // 2` trailing chars around a marker naming the
  omitted byte count and the `CK_RAW_OUTPUT=1` hatch. New `{capped}` placeholder for `summary`.
  `changed` is now `removed or dropped or capped`. The default (no-`summary`) fallback text is
  reworded to "output rewritten: {removed} line(s) removed, {capped} char(s) omitted", so a
  cap-only filter never reports "0 line(s) removed".
- **Details:** Truncation is byte-oriented, not line-oriented, on purpose: the failure mode
  being fixed is *bytes*, and a single 40K-char line (minified JSON, a lockfile) is exactly
  the case a line-based cap would miss. NEVER_FILTER, the `CK_RAW_OUTPUT=1` bypass, the
  non-Bash guard, the fail-soft wrapper and the "no identity rewrite" rule are untouched —
  they sit above `apply_filter` and keep applying.
- **Done when:** a 40,000-char stdout comes back under ~13,000 chars with both ends intact.

### Step 4 — ship the catch-all filter

- **File:** `.claude/hooks/output-filters.json`
- **Action:** edit (op 2)
- **Description:** Append a `bash-output-cap` entry (`"match": "."`, `"lossy": true`,
  `max_chars: 12000`) **after** `pytest-progress`, and document `max_chars` + `{capped}` in
  `_README`. Its `summary` is deliberately SHORT and shares no wording with the inline marker
  (`"[ck output-filter: {id}] stdout capped; see the inline marker for details."`): the message
  is emitted once, not twice, and the summary cannot satisfy the marker assertions in test 3.
- **Details (precedence — checked, not assumed):** `load_filters` preserves base-file order
  (local entries override by `id`, local-only ids append), and `select` returns the **first**
  matching filter. A catch-all placed last therefore never shadows `pytest-progress`: a pytest
  command keeps progress-stripping and is *not* capped. Every other Bash command matches `.`
  and is capped, except NEVER_FILTER commands (generators, `validate-config-json.py`,
  `review-record.py`, `execute-json-ops.py`, `ck doctor`, `shellcheck`, `mypy`, `ruff`), which
  `select` refuses before consulting any filter.
- **Done when:** `[f["id"] for f in doc["filters"]] == ["pytest-progress", "bash-output-cap"]`.

### Step 5 — regression tests

- **File:** `tests/test_output_filter.py`
- **Action:** edit (op 3): update the base-file id assertion, append `class TestMaxChars`.
- **Description:** Seven behavioural tests, each driving the real script as a subprocess with
  a real PostToolUse payload, each naming its RED mutant in its docstring:
  1. `test_a_long_bash_output_is_capped` — RED: delete the `bash-output-cap` entry.
  2. `test_the_head_and_the_tail_both_survive` — RED: replace head+tail with `body[:cap]`.
  3. `test_the_marker_names_the_omitted_byte_count_and_sits_in_the_middle` — **the mandated
     can-it-fail proof**: it asserts the marker appears exactly once, carries the byte count,
     and sits strictly interior (index > 5000 and < len-5000, never on line 1, which is the
     summary). Combined with the short non-overlapping summary, nothing but the inline marker
     can satisfy it. RED: drop the marker (or its byte count) from the truncation branch —
     this test fails while the others still pass.
  4. `test_a_short_output_is_not_rewritten` — RED: cap unconditionally (identity rewrite).
  5. `test_a_never_filter_command_is_not_capped` — RED: delete the `_NEVER` loop from
     `select()` (a behaviour-changing mutant: the command then matches the catch-all).
  6. `test_raw_output_env_prefix_bypasses_the_cap` — RED: remove the `_RAW_MARKER` check.
  7. `test_pytest_keeps_its_own_filter_and_is_not_capped` — the precedence proof; RED: move
     `bash-output-cap` above `pytest-progress` in the base file.
- **Done when:** all seven pass on the clean tree, and controls 3 and 7 have each been shown
  red under their named mutant before any verdict (`mutation-proof-names-the-wrong-mechanism`).

### Step 6 — planner discovery budget

- **File:** `.claude/agents/planner.md`
- **Action:** edit (op 4) — `add_after` the "Bash reads and validates, never authors." bullet.
- **Description:** Two bullets, in the existing block's voice: a per-call output cap (state the
  mechanical 12K cap so the planner expects the marker; `sed -n 'a,bp'` / `grep -n -C3` windows
  ≤80 lines; no full read of a file over ~200 lines; never write or run a script to explore),
  and no test-file authoring.
- **Done when:** the bullets sit inside the Discovery budget list, diff is +7 lines.

### Step 7 — reviewer discovery budget

- **File:** `.claude/agents/reviewer.md`
- **Action:** edit (op 5) — `add_after` "Never re-read a file you already read this run."
- **Description:** One bullet: plan + ops.json once each (explicitly deferring to the file's
  existing "Token-Efficient Ops Review (manifest-first)" rule for any ops.json over ~15 KB), `grep -C`/`sed` windows for touched
  files, restate the ≤20 tool-call ceiling already above it and the 12K stdout cap.
- **Done when:** diff is +5 lines under "Output & Turn Discipline".

### Step 8 — CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** edit (op 6) — `add_after` `## [Unreleased]`.
- **Done when:** entry present under `[Unreleased]`.

## Artifacts touched (for `scripts/check-plan-artifacts.py --check`)

- `.claude/hooks/output_filter.py`
- `.claude/hooks/output-filters.json`
- `tests/test_output_filter.py`
- `.claude/agents/planner.md`
- `.claude/agents/reviewer.md`
- `CHANGELOG.md`

## Testing Strategy

1. `python3 -m pytest tests/test_output_filter.py -q` — all green, including the seven new tests.
2. Mutation controls, hand-applied then reverted: delete the marker text (test 3 red), swap
   the two filter entries' order (test 7 red). Run them; do not trust the docstrings.
3. `python3 -m pytest tests/ -q` — zero failures.
4. `ruff check src/ tests/ scripts/ .claude/operations/scripts/` and `mypy`.
5. `python3 scripts/gen-docs.py --check`, `gen-registry.py --check`,
   `gen-model-policy.py --check`, `check-context-floor.py --check`,
   `check-plan-artifacts.py --check` — all must stay green (no files added/removed, so the
   count gates should be untouched; run them anyway).
6. End-to-end smoke: `sed -n '1,400p' <some large file>` in a normal session and confirm the
   marker appears and names the byte count.

## Rollback Plan

Every operation is an edit to a tracked file; `git checkout -- <path>` per file, or
`git revert` the commit. Fastest partial rollback without touching code: delete the
`bash-output-cap` entry from `.claude/hooks/output-filters.json` — the `max_chars` code then
has no consumer and behaviour returns to today's. Second kill switch already shipped:
`CK_OUTPUT_FILTER=off` in the hook environment disables the script wholesale.

## Risk Assessment

- **HIGH — a capped output silently hides evidence.** Truncation is lossy by definition. Three
  mitigations: the marker names the omitted byte count *and* the `CK_RAW_OUTPUT=1` hatch inside
  the text the model reads; NEVER_FILTER already protects every gate/generator/linter whose
  stdout is read verbatim; and the filter cannot run at all for a failed command — PostToolUse
  does not fire on a non-zero Bash exit, which is already documented as property 1 in
  `output_filter.py`'s module docstring and is restated here, not newly asserted. Even if that
  property were wrong, the loss is bounded: head and tail both survive a cap.
- **MEDIUM — blast radius is every Bash call in every kitted session.** `output_filter.py` is a
  hot-path hook forking an interpreter per Bash call (~363/day here). The new work is a slice
  of an already-materialised string; `TestHotPath::test_the_no_match_path_is_fast` still
  guards the no-match path.
- **MEDIUM — behaviour change for humans.** Long `git diff`/`git log`/`cat` outputs now come
  back truncated. Accepted: that is the point. Reviewers who need the whole diff use
  `CK_RAW_OUTPUT=1`.
- **MEDIUM — precedence.** If the catch-all were ordered before `pytest-progress`, pytest runs
  would lose progress-stripping and gain a cap. Test 7 pins the ordering; the entry is
  appended last.
- **LOW — 12,000 is a judgement, not a measurement.** It is ~3K tokens, roughly 1.5% of a 200K
  window, and above the 4–8K typical useful result. Tunable in one JSON line, per project via
  `output-filters.local.json`.
- **Prior art (searched, not silent):** `review-record.py rejections search` hit two unrelated
  briefs (keyword "truncate" inside iron-law flag tables — neither is an output-filter or
  token-budget rejection); `knowledge-ledger.py search` returned no match. No prior rejection
  governs this change.
- **UNVERIFIED:** `.claude/project-graph.json` hub/impact queries were not run for the same
  reason. `output_filter.py` is plausibly a hub by wiring (settings.json PostToolUse), which is
  why this plan routes to the reviewer.

## Follow-ups (not in this plan)

- Owner-run fleet sync of `output_filter.py`, `output-filters.json`, `planner.md`,
  `reviewer.md` (`--exclude qa-agents`, then a surgical copy for qa-agents).
- Consider a same-shaped cap for the `Read` tool once PostToolUse rewrite support for
  non-Bash tools is verified against the binary (not assumed).
