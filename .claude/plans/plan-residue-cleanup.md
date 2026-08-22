# Implementation Plan: Residue Cleanup (four independent items)

Branch `perf/token-efficiency`, planned at HEAD `64088a5`. Every claim below was
re-measured at that ref before writing; nothing is carried over on trust.

## Overview

Four unrelated leftovers from the secrets-scanner batch: widen the self-scan roots to the
last two committed trees, make a mirror test able to fail on an ADDED clause, record the
recurrence class the batch produced, and give a documented intermittent a capture harness
so its next failure carries its own evidence.

## Scope

- **In scope:** `tests/test_day_one_blockers.py`, three committed review records,
  `.ai/REVIEW_GUIDE.md`, `tests/test_reflection_ledger.py`, `.ai/BACKLOG.md`.
- **Out of scope:** the scanner itself (`.claude/hooks/pre-commit.sh`) is not touched —
  no pattern, clause or exit path changes. No cause is proposed for ITEM 4. No CHANGELOG
  entry: nothing here is user-visible (ITEM 3 is maintainer-facing by the audience rule,
  ITEMS 1/2/4 are tests and review records).

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (CONTRIBUTING.md),
  or Edit/Write is blocked by this repo's own `ops-enforcement`.
- No test fixtures are created by this plan, so the `$TMPDIR` exemption hazard
  (`ops-enforcement.sh:43`) does not arise. Nothing needs `<repo>/.tmp-test-fixtures/`.

---

## ITEM 1 — `review/` and `docs/` join `SCAN_ROOTS`

### Premise, re-verified

`tests/test_day_one_blockers.py:390` currently reads
`SCAN_ROOTS = (".claude", "templates", ".codex", ".agents", "tests", "scripts", "src")`.
I enumerated every git-tracked file under `review/` and `docs/`, applying the hook's own
skip regex and all 13 live patterns (expanded, not source-form). Result — exactly three
matching lines, all under `review/`, all against the `api_key` value-bearing pattern:

| File:line | What it is |
|---|---|
| `review/code-review.md:219` | a P2 finding that quotes an example assignment while explaining the `\x27` bug |
| `review/security-review.md:90` | prose noting the only match in the tree is the intentional bad example in `insecure-defaults/SKILL.md` |
| `review/tasks/003-fix-hook-bugs-and-fail-closed.md:49` | an acceptance-criterion test case (single-quoted form) |

**`docs/` had zero matches before this change and is not edited by this plan.** It joins
`SCAN_ROOTS` for free; no defect there was found or fixed.

### Step 1.1 — Retype the three review lines

- **Files:** `review/code-review.md`, `review/security-review.md`,
  `review/tasks/003-fix-hook-bugs-and-fail-closed.md`
- **Action:** Modify (typography only)
- **Details:** The pattern needs `name`, then `\s*`, then `[:=]`, then a quote. Wrapping
  the name, the separator and the value as three adjacent markdown inline-code spans puts
  a backtick where the regex requires whitespace-or-nothing, so the adjacency is broken
  while the rendered meaning, the finding text and the reading order are identical. No
  verdict, severity, line reference or example VALUE changes — these are review records.

**Anchor safety note (important, and the reason each edit is truncated).** `.claude/plans`
is itself in `SCAN_ROOTS`, and this plan's ops config is committed. A `find` string that
carried the whole offending literal would make the ops config match the live pattern and
block its own commit. Every `find`/`replace` here is therefore cut short of the 8th
non-quote character, so neither the anchor nor its payload can complete the pattern — and
the JSON string terminator (`"`) is itself a quote character, so the concatenation on a
single JSON line cannot complete it either. This document observes the same discipline.

### Step 1.2 — Add the roots

- **File:** `tests/test_day_one_blockers.py`
- **Action:** Modify
- **Details:** Replace the stale comment block (which says `review/` and `docs/` are out of
  scope and names `003-…:49` as the pre-existing blocker) plus the `SCAN_ROOTS` tuple. New
  tuple adds `"review"` and `"docs"`. New comment records why `review` could join, and
  states plainly that `docs` joined with zero findings and zero edits. The
  `.claude/plans` paragraph is preserved verbatim — it is still the live reason.

### Verification

Re-run the enumeration (all 13 expanded patterns × `git ls-files -- review docs`, hook
skip regex applied) and require **zero** matches. Then
`python3 -m pytest tests/test_day_one_blockers.py -q`, whose
`test_no_committed_file_matches_a_live_pattern` is parametrised over the 13 patterns and
now covers both new roots.

### Mutant and flipped cases

- **Mutant:** revert any one of the three retyped lines to its old form.
- **Must flip:** `test_no_committed_file_matches_a_live_pattern[api_key…]` FAILS.
- **Must NOT flip:** the other 12 parametrised cases, and every other test in the file.
- **Would pass against unfixed code:** every test in the module *except* the `api_key`
  parametrisation — including `test_staging_shipped_claude_files_does_not_block`, which
  stages only `.claude/**` and can never see `review/`. Step 1.2 alone (roots without the
  retyping) reds the suite; Step 1.1 alone is a silent no-op. They must land together.

---

## ITEM 2 — `test_skip_mirror_matches_the_hook` must fail on an ADDED clause

### Premise, re-verified

The test asserts two literal tokens appear in `pre-commit.sh`. Changing an existing clause
flips it. **Adding** a third `continue`-guarded clause to `check_secrets` does not: both
tokens are still present, so the mirror `_SKIP_SUFFIX_RE` silently becomes STRICTER than
the control it mirrors, and the damage surfaces as a spurious red in
`test_no_committed_file_matches_a_live_pattern` (a file the hook would now skip is still
scanned here) rather than as a clear failure at the mirror. Measured at `64088a5`:
`check_secrets()` contains exactly **2** `[[ "$file" =~ …` clauses and 2 `continue`s.

### Step 2.1 — Count the clauses

- **File:** `tests/test_day_one_blockers.py`
- **Action:** Modify
- **Details:** Add `_check_secrets_block()`, which extracts the body of `check_secrets()`
  from the hook text with `^check_secrets\(\) \{\n(.*?)\n\}$` (re.S|re.M) and asserts the
  function was found — so a rename of the function fails loudly here instead of returning
  an empty string that trivially counts 0. Then assert
  `len(re.findall(r'\[\[ "\$file" =~', block)) == 2`, with a message naming
  `_SKIP_SUFFIX_RE` as the thing to update. The two existing token assertions stay
  untouched; this is added coverage, not a replacement.

### Mutant and flipped cases

- **Mutant A (the one this step exists for):** add a third clause to `check_secrets`, e.g.
  `if [[ "$file" =~ \.min\.js$ ]]; then continue; fi`.
  **Must flip:** `test_skip_mirror_matches_the_hook` FAILS with "3 skip clauses, mirrors 2".
  **Must NOT flip:** nothing else in the module is required to flip.
  Against the current test this mutant flips *nothing* — that is the gap being closed.
- **Mutant B (regression guard):** change `pdf` to `pdfx` in the hook's first clause.
  **Must flip:** the same test, at the existing token assertion (count stays 2).
- **Mutant C:** rename `check_secrets` to `check_for_secrets`.
  **Must flip:** the same test, at the "not found" assertion.
- **Would pass against unfixed code:** the two token assertions, i.e. the entire current
  body of this test.

---

## ITEM 3 — record the `unreviewed-expansion` recurrence class

### Premise, re-verified

`.ai/REVIEW_GUIDE.md` carries the Class ratchet table (3 entries ⇒ owes a mechanical check
or a written "cannot be mechanised") and the rule **never invent a synonym for a row that
already exists**. I read all 18 existing rows: none covers "the source line is correct and
only the expanded value is wrong". The nearest neighbours are `prose-verified-claim` (a
claim resting on reading prose rather than executing — about the reviewer's method, not
about interpolation) and `validator-executor-divergence` (two components disagreeing).
Neither describes a control whose text is right and whose runtime value is wrong. This is
a new row, not a synonym.

The instance: `.claude/hooks/pre-commit.sh` built patterns as
`"api_key\\s*[:=]\\s*${q}${nq}{8}"`; `lib.sh` defined `ERE_QUOTE_CLASS` /
`ERE_NOT_QUOTE_CLASS` but never exported them and the hook never sourced `lib.sh`, so the
`${:-}` defaults applied — and those defaults were broken, because a `'` inside a
double-quoted `${:-}` default opens a quote context. `nq` expanded to empty, so the
shipped pattern required eight consecutive quote characters and seven value-bearing
patterns could not fire. Three review rounds read the source line and found nothing wrong,
because nothing is wrong with it. Fixed in `8cfdb6e` (verified present in this history:
`fix(security): the secrets scanner's seven value-bearing patterns could not fire`).

### Step 3.1 — Table row

- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Details:** Append one row after the `validator-executor-divergence` row (the table's
  last), in the existing three-column format. "What catches it now" = `nothing yet — 1
  LIVE`, naming the commit and the `bash -x` diagnostic. **1 is the measured count** — one
  instance, this one; the ratchet is not claimed to be at threshold.

### Step 3.2 — Prose entry

- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Details:** Insert a short bolded paragraph in the "What the 2026-08-19/20 batch
  actually proved about this table" run of entries, immediately before the
  "One caveat on everything above:" closer — same voice and shape as the existing
  "Writing a mutant finds defects before the mutant runs." entry. Names the commit, the
  mechanism, why three rounds missed it, and the one-command diagnostic. Maintainer-facing;
  no CHANGELOG entry (`.ai/` is the maintainer half of the audience split).

### Verification

`python3 scripts/check-context-floor.py` — `.ai/REVIEW_GUIDE.md` is not always-on prompt
text, so the floor must be unaffected; run it to confirm rather than assume. Markdown table
renders with the same column count as its neighbours.

### Mutant and flipped cases

None. This is a documentation ratchet with no mechanical check attached — claiming a mutant
for it would be exactly the `vacuous-check` this file already tracks. Stated plainly so the
reviewer does not read the omission as an oversight.

---

## ITEM 4 — capture harness for the documented intermittent

### Premise, re-verified

`.ai/BACKLOG.md:91-103` records `test_receipt_via_json_stdin_clears_the_checkpoint`
(`tests/test_reflection_ledger.py:388`) failing intermittently at `:399` on
`assert ref.pending_checkpoint(SESSION) is None`, with the CLI exiting 0. It states **no
cause is claimed**, records that the ambient-env hypothesis was checked and RULED OUT, and
says "next step is capture, not theory". A third sighting is added by this plan: one
failure in a fresh process at `64088a5`, then two consecutive clean full runs (1,646 passed
each), with output lost to `/dev/null`.

One correction to the entry's wording, worth making while touching it: there is no separate
checkpoint file. `pending_checkpoint()` is a pure reduction over `active_entries()`, which
reads the ledger JSONL at `ledger_path(session_id)`. "The checkpoint file contents" is
therefore captured as *the ledger bytes plus the derived active set plus the returned
checkpoint*, which is strictly more than the entry asked for.

### Step 4.1 — `receipt_diagnostic()` helper

- **File:** `tests/test_reflection_ledger.py`
- **Action:** Modify (insert module-level helper after `fail()`)
- **Details:** Builds and returns a string containing: `ref.ledger_dir()`;
  `ref.ledger_path(SESSION)` and whether it exists; the scoped
  `CLAUDEKIT_REFLECTION_DIR` as the CHILD process received it; `ref.inbox_path(SESSION)`
  and whether it exists; the raw ledger bytes; `ref.active_entries(SESSION)`;
  `ref.pending_checkpoint(SESSION)`; and the CLI's returncode, stdout and stderr.
  Unreadable ledger is reported as `<unreadable: …>` from a narrow `except OSError as exc`
  that puts the exception text INTO the output — not a bare `except`, no `2>/dev/null`, no
  swallowed error, so `python3 scripts/check-silent-failure.py .` stays clean (I walked its
  shell and python rules over this addition; it adds no suppression construct). Stdlib only
  (`json`, `os`, `pathlib` — all already imported).

### Step 4.2 — Attach it to the assertion

- **File:** `tests/test_reflection_ledger.py`
- **Action:** Modify
- **Details:** In `test_receipt_via_json_stdin_clears_the_checkpoint` only, pass
  `receipt_diagnostic(ref, proc, env)` as the message of both assertions at `:398-399`.
  **What is asserted does not change**: same expressions, same operators, same expected
  values. No retry, no `flaky` mark, no reordering, no sleep, no cause implied anywhere in
  the text. The helper is called only when an assertion is about to fail, so the passing
  path costs nothing.

### Step 4.3 — Update the BACKLOG entry

- **File:** `.ai/BACKLOG.md`
- **Action:** Modify
- **Details:** Replace the closing "Next step is capture, not theory…" sentence with: the
  third sighting (date, ref, fresh process, two clean 1,646-pass runs, output lost to
  `/dev/null` — named as the mistake the item exists to prevent); the note that capture is
  now in place and what it dumps; the clarification that the checkpoint is derived from the
  ledger rather than stored in its own file; and an explicit "no cause is claimed, no retry
  was added, the assertion is unchanged — do not close this until a captured failure
  explains it." The item stays OPEN and unlinked to any hypothesis.

### Verification

`python3 -m pytest tests/test_reflection_ledger.py -q` (green — the diagnostic is inert on
the passing path). To prove the harness is not itself vacuous, temporarily invert the
assertion to `is not None` and confirm the failure output contains the ledger path and the
CLI streams; revert immediately.

### Mutant and flipped cases

- **Mutant:** invert the assertion at `:399` to `is not None`.
  **Must flip:** `test_receipt_via_json_stdin_clears_the_checkpoint` FAILS, **and the
  failure text contains `ledger_path:`, `cli stderr:` and the active-entry JSON**. Asserting
  only "it fails" would be a `vacuous-check` — the point is the payload, not the red.
  **Must NOT flip:** every other test in the module, including the sibling
  `test_receipt_via_cli_clears_the_checkpoint` and `test_receipt_via_inbox_…`, which are
  deliberately left alone.
- **Would pass against unfixed code:** the whole module. This item adds no assertion and
  can catch no defect by itself — it is instrumentation, and honest about it.

---

## Testing Strategy

| Item | Command | Expectation |
|---|---|---|
| 1 | `python3 -m pytest tests/test_day_one_blockers.py -q` + the 13-pattern enumeration over `git ls-files -- review docs` | green; enumeration returns zero matches |
| 2 | mutants A/B/C above, applied and reverted one at a time | each reds `test_skip_mirror_matches_the_hook` and nothing else is required to red |
| 3 | `python3 scripts/check-context-floor.py` | unchanged floor |
| 4 | `python3 -m pytest tests/test_reflection_ledger.py -q`, then the inverted-assertion mutant | green; mutant's output carries the evidence |

Full DoD gate — all nine commands from CLAUDE.md must pass before commit:
`pytest tests/ -q` · `ruff check src/ tests/ scripts/` · `mypy` ·
`gen-docs.py --check` · `gen-registry.py --check` · `gen-model-policy.py --check` ·
`check-context-floor.py` · `shellcheck install.sh .claude/hooks/*.sh` ·
`ck doctor --strict`. `ruff` matters here: the new helper and test lines are held to
line-length 100. `shellcheck` and `gen-*` should be no-ops — no shell and no component
counts are touched — and running them is the evidence for that, not the assumption.

Commits (one concern each, conventional):
`test(secrets): let review/ and docs/ into the self-scan roots` ·
`test(secrets): fail the skip mirror when a clause is added` ·
`docs(ai): record the unreviewed-expansion recurrence class` ·
`test(reflection): capture the evidence for an unexplained intermittent`.

## Rollback Plan

Four independent, file-disjoint units except that ITEMS 1 and 2 share
`tests/test_day_one_blockers.py`. Per item: `git checkout -- <files>` for that item, or
revert its commit. ITEM 1's two steps must roll back together (roots without retyping reds
the suite). ITEM 4 is pure instrumentation and can be dropped with no behavioural effect.

## Risk Assessment

- **Low:** ITEM 3 (docs only, no gate consumes that table mechanically). ITEM 4 (no
  assertion changes; helper runs only on the failing path). ITEM 2 (added assertion whose
  expected value, 2, was measured at this ref).
- **Medium:** ITEM 1. Two coupled edits across four files; the roots must not land without
  the retyping. Secondary risk, mitigated by design: the ops config lives under
  `.claude/plans`, which is scanned, so a full-literal anchor would block its own commit —
  every anchor is truncated below the pattern's 8-character threshold for that reason.
- **High:** none.
- **Blast radius:** `tests/test_day_one_blockers.py` is the widest touch — adding roots
  changes the input set of a parametrised test that enumerates the whole index, so an
  unrelated future commit under `review/` or `docs/` can now red this suite. That is the
  intended enforcement, and the hook's own message documents the sanctioned exits (remove
  the value, unstage, or narrow the pattern — never a wholesale file skip).
- **Explicitly not done:** nothing in this plan proposes a cause for ITEM 4, and nothing
  changes `.claude/hooks/pre-commit.sh`. No item was dropped — all four premises held under
  independent measurement at `64088a5`.
