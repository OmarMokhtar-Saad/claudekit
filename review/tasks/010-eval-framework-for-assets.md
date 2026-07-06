# Task 010 — Eval Framework: Golden & Regression Tests for Prompt Assets

## Problem
The product is 30 agents / 73 skills / 39 commands of prompts executed by an LLM with shell access — and it has **0% behavioral coverage**. `tests/` asserts file existence and keyword presence (a skill rewritten to instruct auto-approval of `rm -rf` passes green — testing-review §missing-1); the `/eval` command + `eval-harness` skill define a YAML eval format but there is **no runner, no golden transcripts, no CI job** (missing-features #3). The kit that enforces "80% coverage" and a "90/100 review gate" on user code cannot prove its own planner emits a valid ops.json. The README's "85% token reduction" claim is unbenchmarked. The review gate itself is uncalibrated LLM self-report: no scoring anchors, no output validation (malformed `SCORE:` silently breaks `/refine`), and a Goodhart loop where `/refine` iterates until ≥90 (ai §4.1).

## Root Cause
Prompt assets were treated as documentation (structure-testable) rather than as the executable product (behavior-testable). Eval infrastructure requires API spend and headless-run plumbing that was never prioritized; the score gates were designed as rituals without a measurement plan.

## Files
- New: `evals/` — `evals/suites/<agent>/*.yaml` (the eval-harness skill's format), `evals/fixtures/` (reuse `examples/python-fastapi` as the fixture repo), `evals/golden/` (snapshot ops.json outputs), `evals/results/` (trend JSON)
- New: `src/claudekit/evals/runner.py` + CLI `ck eval` (shells to `claude -p --output-format json`; assertions in stdlib Python)
- New: `schemas/review-schema.json`, `schemas/verify-schema.json` (structured verdicts — missing-features #8)
- New: `scripts/check-review-block.py` (regex + arithmetic validation of reviewer output; sub-scores must produce SCORE)
- `.claude/agents/reviewer.md` (calibration anchors + machine-parseable Output Contract — ai Offender #5), `verifier.md` (split mechanical/judgment or upgrade model — ai §4.2)
- `.claude/commands/refine.md` (parse via the checker; fresh-reviewer-per-iteration made explicit)
- New: `_shared/EXAMPLE_PIPELINE.md` (one worked end-to-end few-shot: real plan → valid ops.json → review block → execution log — ai §4.4, improvement #15)
- `.github/workflows/evals.yml` (nightly; API key secret; skipped on forks)

## Priority
**P0–P1** (missing-features gap #3; prerequisite safety net for tasks 008/009's content surgery).

## Estimated Time
1.5–2 weeks for runner + 5 core-agent suites + CI; anchors/contract are 1–2 days within that.

## Risk
Medium. LLM nondeterminism makes evals flaky — assert on *structural/machine-checkable* properties (ops.json validates, decision enum present, forbidden strings absent), not exact text; allow N-of-M pass thresholds. API cost — nightly not per-PR, small fixture tasks, Haiku where the assertion allows. Golden snapshots will churn on model updates — snapshot the *validated structure*, not raw text.

## Step-by-step Implementation
1. **Structured verdicts first:** define `review-schema.json` (score int, decision enum, critical_count, warning_count, issues[] with severity/location/fix) and require reviewer to emit `reviewer.json` beside `reviewer.md`; same for verifier. Add the ai Offender #5 Output Contract + calibration anchors (95/90/80/65 exemplars) to reviewer.md; delete progress bars.
2. `scripts/check-review-block.py`: validates presence, integer score, decision-consistency (APPROVED ⇒ score ≥90 AND critical_count == 0), and sub-score arithmetic. `/refine` and the implement-gating hook call it before trusting any verdict.
3. **Gating hook:** PreToolUse/command-level check that `/implement` proceeds only when a schema-valid `reviewer.json` exists with `score >= threshold` (threshold read from CONSTITUTION frontmatter, not hardcoded) — the 90/100 gate becomes mechanical (missing-features #8).
4. **Runner:** `ck eval [suite]` — for each case: prepare fixture tmpdir → invoke `claude -p --agent <name> --output-format json` (scoped tools, never skip-permissions — task 004) → run assertions → write results JSON. Stdlib + the YAML format already specified in the eval-harness skill.
5. **Five core suites:**
   - *planner:* output contains an ops.json that **passes `validate-config-json.py`** (would have caught the schema-split bug, ai §3.1); plan file created in `.claude/plans/`.
   - *reviewer:* rejects a fixture plan with a hardcoded secret / missing rollback (mandatory-rejection rules); emits schema-valid reviewer.json; approves a known-good plan.
   - *implementer:* executes via script only (assert no Edit/Write tool calls in the transcript); backup manifest created; rollback restores.
   - *verifier:* correct pass/fail on fixture repos with passing/failing tests.
   - *coordinator:* routes 6 canned requests to the expected first-hop agent.
6. **Golden tests:** snapshot the validated ops.json structure for 3 fixed tasks; fail on structural drift.
7. **Asset content lint** (deterministic, runs per-PR, no API): dangerous-instruction grep across all shipped markdown (`rm -rf`, `--dangerously`, "auto-approve", "skip review") with an allowlist for defensive contexts (testing-review missing test 8); frontmatter schema validation.
8. **Benchmark the claims:** measure token usage of the file-based-handoff pipeline vs a naive shared-context run on a fixture task; publish methodology + numbers (README "85%" claim, oss-excellence #12).
9. CI: `evals.yml` nightly + on-demand label; trend JSON committed; regression alert when a suite's pass rate drops.

## Acceptance Criteria
- `ck eval planner` runs green locally with an API key; deliberately corrupting planner.md's schema section turns it red.
- Nightly workflow exists, runs the 5 suites, commits trend data.
- `/implement` is mechanically blocked without a valid `reviewer.json` ≥ threshold (demonstrated in fixture).
- A malformed reviewer response (missing SCORE) is caught by the checker and retried, not silently accepted by `/refine`.
- Dangerous-instruction lint green on the current tree and red on a seeded violation.
- Published benchmark section replaces the unbacked "85%" claim.

## Testing Strategy
This task *is* the testing strategy for the prompt layer. Meta-testing: unit tests for the runner's assertion engine and the review-block checker (pure Python, no API); a mocked-transport mode (`--replay` from recorded transcripts) so the runner's logic is testable in plain CI.

## Rollback Plan
All additive (new dirs, new CI job, new schemas). The implement-gating hook is the only behavior change — it honors `ECC_HOOK_PROFILE=minimal` for instant disable. Prompt edits to reviewer.md (anchors/contract) are revertible commits; keep the old output format accepted by the checker for one release (dual-parse) to avoid breaking in-flight workflows.
