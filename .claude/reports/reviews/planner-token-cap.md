# Review (round 2) — plan-planner-token-cap

Artifacts: `.claude/plans/plan-planner-token-cap.md`, `.claude/plans/ops-planner-token-cap.json` (6 code_edit ops).
Reviewer has no Bash: nothing below was executed. Round-1 findings re-verified against the current files only.

## Round-1 CRITICAL — RESOLVED

`ops-planner-token-cap.json:48` now ships `bash-output-cap` with
`"summary": "[ck output-filter: {id}] stdout capped; see the inline marker for details."` — it contains
neither `omitted from the middle`, nor `CK_RAW_OUTPUT=1`, nor `{capped}`. The inline marker
(`ops-planner-token-cap.json:26`) is the sole source of all three strings on a capped output.

Test 3 (`ops-planner-token-cap.json:62`) now asserts
`text.count("omitted from the middle") == 1`, `text.count("CK_RAW_OUTPUT=1") == 1`,
`str(len(stdout) - CAP) in text`, `idx > 5000`, `idx < len(text) - 5000`, and
`needle not in text.split("\n", 1)[0]`.

Mutant argument (named mutant: drop the inline marker, or just `str(capped)`, from the truncation branch):

- Drop the whole marker → `body` becomes head+tail only; the prepended summary carries no needle →
  `count(needle) == 1` fails (0). RED.
- Drop only `str(capped)` → with `stdout = "z"*40000`, `capped = 28000`; the body is digit-free and the
  summary is digit-free, so `"28000" in text` fails. RED.
- Positional arithmetic checks out: `head_n = 6000`, summary ≈ 60 chars → `idx ≈ 6060` (> 5000), and
  `len(text) ≈ 12.3K` → `len-5000 ≈ 7.3K` (> idx). The assertions bind with ~1.2K margin; they are not
  vacuous, and they cannot be satisfied by the first line.

The other class members stay green under that mutant (tests 1, 2, 4–7 never reference the marker except
test 7, which asserts its *absence*), so the control is specific. UNVERIFIED by execution: this reasoning
must still be confirmed by actually applying the mutant and running the file before implementation —
`mutation-proof-names-the-wrong-mechanism`.

## Round-1 MINORs

1. Duplicate message per capped output — **resolved** by the disjoint short summary (one emission).
2. Test 5 mutant — **resolved**: now "delete the `_NEVER` loop from `select()`", which makes
   `gen-docs.py --check` match the catch-all and be rewritten, failing `run(data).stdout == ""`. Behaviour-changing.
3. Cap-only fallback summary — **resolved**: `ops-planner-token-cap.json:30` rewords the default to
   `"output rewritten: {removed} line(s) removed, {capped} char(s) omitted."`, and `_README`
   (`:44`) documents `{capped}` and `max_chars`.
4. PostToolUse / non-zero exit premise — **resolved as framing**: `output_filter.py:21-23` already records
   this as measured (`false; exit 3` produced no `[post-tool-use]` entry in hooks.log); the plan now cites
   it as restated, not newly asserted, and bounds the loss if wrong.
5. reviewer.md bullet vs manifest-first — **resolved**: op 5 payload defers explicitly to the
   "Token-Efficient Ops Review (manifest-first)" rule for ops.json over ~15 KB (see new MINOR below).

Prior-art searches are now recorded in the plan (Phase 0 and Risk section): two unrelated "truncate" hits
in iron-law flag tables, knowledge ledger empty. No prior rejection governs this change.

## New finding (introduced by the delta)

- **[MINOR] Over-escaped quotes in the reviewer.md payload.** `ops-planner-token-cap.json:82` contains
  `\\\"Token-Efficient Ops Review (manifest-first)\\\"`, i.e. the inserted markdown will literally read
  `\"Token-Efficient Ops Review (manifest-first)\"` with visible backslashes. Every other payload in this
  ops.json uses plain `\"`. Fix: change `\\\"` → `\"` (or use backticks) in that one payload.

## Score

Plan Quality 93 x 0.40 = 37.2 · Architecture 93 x 0.30 = 27.9 · Security 90 x 0.30 = 27.0 → 92.
Zero open CRITICAL/MAJOR; one cosmetic MINOR in a payload.

=== REVIEW ===
SCORE: 92
DECISION: APPROVED
- [MINOR] .claude/plans/ops-planner-token-cap.json:82 — op 5 payload over-escapes quotes (`\\\"Token-Efficient ... \\\"`), so reviewer.md would gain literal backslashes. Fix: use `\"` like every other payload, or backticks.
- [MINOR] UNVERIFIED (no Bash here): the round-1 CRITICAL is argued resolved by reading, not by execution. Before implementing, apply the test-3 mutant (delete the inline marker; then delete only `str(capped)`) and the test-7 mutant (swap filter order) and show each red, per the plan's own Testing Strategy step 2.
=== END REVIEW ===
