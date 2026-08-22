# Plan — Close the review-loop gaps that cost rounds and tokens

**Tier:** 2 (multi-file; prompts + policy + one new read-only script; no security/schema surface)
**Slug:** `review-loop`
**Ops config:** `.claude/plans/ops-review-loop.json`

## The diagnosis, corrected against the source

Five causes were proposed for the repeated review rounds. Reading the files changes two of them:

`CLAUDE.md:72` **already says** "Stop at the first round with zero blocking findings; ceiling 3
rounds; rounds 2+ read only the diff since the last verdict." The policy is not missing. It lives
only in the orchestrator's context and **never reaches the reviewing agent's own prompt** —
`code-reviewer.md` carries no exit rule and no delta contract, so a fresh instance re-reviews the
whole artifact and returns a sub-90 number with zero blockers, which reads as a rejection.

Likewise `reviewer.md:265-270` already routes execution-dependent reviews to `code-reviewer`;
what is missing is the same line in `CLAUDE.md`, where routing decisions are actually made.

So the work is **propagating policy into the prompts that execute it**, plus one mechanical check
and one design gate. It is not new policy.

## The design model (stated before any config is authored)

- **Ownership is unchanged.** Plan review (`reviewer` + `review-record.py`, ≥90/100) gates
  execution and is not touched — `APPROVAL_THRESHOLD` keeps its meaning. Code review is a
  separate prose flow with no record; its gate becomes **blocking-finding count**, never a score.
- **The ledger is the prior round's report**, saved by the orchestrator under
  `.claude/reports/reviews/` (already gitignored, runtime state — never cited as source).
  No new machinery: `code-reviewer` is read-only and cannot write a ledger, so the contract is an
  output section it must fill, not a file it must maintain.
- **Files that carry the value:** `.claude/agents/code-reviewer.md` (exit rule, delta contract,
  inherited findings), `CLAUDE.md` (design precheck + reviewer routing),
  `scripts/check-plan-artifacts.py` (new), `.ai/REVIEW_GUIDE.md`, `CHANGELOG.md`.

## Changes

1. **`code-reviewer.md` — Phase 0b, round scope.** Round ≥2 reads the prior report, reviews only
   `git diff <last-verdict-sha>`, and inherits prior findings rather than re-deriving them.
2. **`code-reviewer.md` — the exit rule.** VERDICT is a function of Critical+High:
   zero blockers ⇒ APPROVE / APPROVE WITH SUGGESTIONS, and Medium/Low findings become
   follow-ups, never grounds for another round. A numeric score is not the code-review gate.
3. **`code-reviewer.md` — INHERITED FINDINGS section** in the report: every prior finding gets
   `discharged | open | superseded` with the evidence that discharged it.
4. **`code-reviewer.md` — anti-patterns:** never re-report an inherited finding without a status;
   never request another round with zero blockers.
5. **`CLAUDE.md` — pre-ops design precheck** for Tier 2/3: one paragraph naming the ownership /
   data model and the files carrying the change's value, before authoring ops.json. Phase 1a's
   sidecar and Phase 2's ownership model both died on questions answerable here.
6. **`CLAUDE.md` — reviewer routing:** `reviewer` = plans, no Bash; `code-reviewer` = code, has
   Bash, the only one that can run a mutation proof.
7. **`scripts/check-plan-artifacts.py`** — every path an ops config writes must be named in its
   plan.md. This is the mechanical form of a finding raised in three consecutive rounds; per the
   recurrence ratchet a class at three entries earns a check.
8. **`.ai/REVIEW_GUIDE.md`** — document the exit rule, the ledger, and a tools row in the
   two-systems table.
9. **`CHANGELOG.md`** — `[Unreleased]` entry.

## Proofs

1. `python3 scripts/check-plan-artifacts.py .claude/plans/ops-review-loop.json` passes for this
   plan, and fails when a target path is removed from plan.md — proven by mutating the shipped
   artifact, not by reading it.
2. `python3 -m pytest tests/test_check_plan_artifacts.py -q` green (behavioral: builds a plan +
   ops pair in tmp, asserts exit 0, then drops a path and asserts exit 1 naming it).
3. Full DoD gate: pytest, ruff, mypy, gen-docs --check, gen-registry --check,
   gen-model-policy --check, check-context-floor, shellcheck.

## Not in scope (stated, not silently dropped)

- **CI wiring for check-plan-artifacts.py.** Existing plans predate the rule; wiring it into the
  DoD gate now would redden the suite for unrelated history. The script ships and is run per-plan;
  making it CI-blocking is a separate owner decision after a backfill pass.
- Changing `APPROVAL_THRESHOLD` or anything in the plan-review execution gate.
