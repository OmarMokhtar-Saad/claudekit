# Plan: contrib-governance P2 — routing cases and the separability gate (C2)

Phase 2 of [plan-contrib-governance.md](plan-contrib-governance.md). Ops config:
`.claude/plans/ops-contrib-governance-p2.json` (10 operations, 0 deletions).

## Problem

The existing harness (`evals/definitions/*.json`, `scripts/run-evals.py`, `ck eval`,
`tests/test_evals.py`) holds four **agent-behaviour** evals that cost API money, so no
gate can run them per-commit. Nothing checks the skill corpus itself: 82 skill
descriptions compete for the same requests and nothing notices when two of them collide.
Separately, `.claude/skills/eval-harness/SKILL.md` documents a `.claude/evals/` layout
that does not exist on disk — a doc defect, not a directory to create.

## What this gate measures — and what it must never claim

The ranker is a deterministic BM25 scorer over the `name` + `description` frontmatter of
every `.claude/skills/*/SKILL.md`. **It is not Claude Code's router.** It measures
**description separability**: whether the words a user would plausibly type reach the
owning skill's description more strongly than any other skill's. A failure is a real
defect (two descriptions competing for one request); a pass is *not* evidence that the
live router picks the same skill. That sentence appears in the script docstring, the
cases' `note` field, `evals/routing/README.md`, the skill prose and the test docstrings —
and a test asserts the phrase "routing accuracy" appears nowhere in the layer. This is
hard rule 6's honesty discipline applied to a gate.

## Scope

In: an offline, zero-API routing-case layer for **five** skills, a stdlib ranker, a
pytest gate with a mutation proof, and the eval-harness doc fix. Out: cases for the other
77 skills; any change to `run-evals.py`, the API-costing definitions, or `ck eval`.

## Tasks

### T1 — the case layer

- **Files:** `evals/routing/README.md`, `evals/routing/using-superpowers.json`,
  `evals/routing/clarify.json`, `evals/routing/writing-plans.json`,
  `evals/routing/systematic-debugging.json`,
  `evals/routing/verification-before-completion.json`
- **Action:** `file_create` ×6
- **Details:** each case carries `skill` (must equal the file stem), `note` (the honesty
  sentence), `top_k`, ≥3 `positive` prompts, ≥2 `negative` prompts each naming the
  `owner` skill that should win, and one `expectation` sentence describing the
  behavioural claim.
- **Done when:** the six files exist and `python3 -m json.tool` parses each.

### T2 — the ranker and gate

- **File:** `scripts/check-skill-separability.py` (new)
- **Action:** `file_create`
- **Details:** stdlib only (`json`, `math`, `re`, `collections`, `pathlib`). `--check`,
  `--skills-dir`, `--cases-dir`, `-v`. Exit 0 = every case separates, 1 = a collision, a
  malformed case, or a case naming a skill that does not exist. `--skills-dir` /
  `--cases-dir` exist so the tests can point the real gate at a fixture corpus — a gate
  that can only run against the live tree cannot be proven able to fail.
- **Rules enforced:** the case's skill and every negative's `owner` must exist; the file
  stem must equal `skill`; each positive must rank the case skill within `top_k`; each
  negative must rank its named `owner` **first** and must **not** rank the case skill
  first. A zero score is not a rank — an empty result fails a positive and fails a
  negative's owner claim, rather than passing vacuously.
- **Reported, never failed on:** skills whose description has no `Use when`. Six exist
  today (`context-keeper`, `execute-operations-config`, `gan-harness`,
  `opensource-pipeline`, `search-first`, `validate-operations-config`). That is a
  description-quality defect, not a separability one; failing one gate on two unrelated
  defects makes both unfixable in isolation. The printed count is the ratchet.
- **Done when:** `python3 scripts/check-skill-separability.py --check` exits 0.

### T3 — tests, including the collision mutation proof

- **File:** `tests/test_skill_separability.py` (new)
- **Action:** `file_create`
- **Details:** a three-skill fixture corpus in `tmp_path` plus the real repo run. The
  mutation proof rewrites one fixture skill's description into a copy of the owner's and
  asserts the gate goes **red** and names the colliding skill. Also covers: a case naming
  a missing skill; a negative that ranks the case skill first; missing `Use when`
  reported without failing; and the honesty ratchet (no file in the layer contains
  "routing accuracy").
- **Done when:** `python3 -m pytest tests/test_skill_separability.py -q` passes, and
  `test_a_colliding_description_reds_the_gate` fails if the collision check is removed.

### T4 — fix the eval-harness doc defect and document the new layer

- **File:** `.claude/skills/eval-harness/SKILL.md`
- **Action:** `code_edit`, 2 edits
- **Details:** (1) state plainly that this repo's harness is at the repository root, name
  the real paths, and mark the generic `.claude/evals/...` sketch below it as an
  illustration for a user project rather than a description of this repo; (2) add the
  offline routing-separability layer with the honesty constraint. This is the one piece
  of C2 that ships to the fleet — the contract travels as prose because the CI half does
  not live under `.claude/`.
- **Done when:** the skill no longer asserts `.claude/evals/` is where this repo's evals
  live, and names `evals/routing/` plus the separability caveat.

### T5 — CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** `code_edit` (`add_after` `## [Unreleased]`, leading newline in payload)

## Files touched

- `evals/routing/README.md`
- `evals/routing/using-superpowers.json`
- `evals/routing/clarify.json`
- `evals/routing/writing-plans.json`
- `evals/routing/systematic-debugging.json`
- `evals/routing/verification-before-completion.json`
- `scripts/check-skill-separability.py`
- `tests/test_skill_separability.py`
- `.claude/skills/eval-harness/SKILL.md`
- `CHANGELOG.md`

## Mandatory tuning step (this phase is not done when the ops execute)

The five shipped cases were written against the real descriptions but **were never
run** — the planning role cannot execute the ranker. After execution:

1. Run `python3 scripts/check-skill-separability.py --check -v`.
2. For every failure, tune the **case prompt**. Never tune the ranker to make a case
   pass, and never edit a skill description to make a case pass — both convert a
   measurement into a mirror.
3. If a case still fails with a prompt a real user would plausibly type, that is a **real
   description collision**. Do not weaken the gate: record it with
   `review-record.py rejections skill-edit` (Phase 1) or
   `knowledge-ledger.py open --origin workflow`, and either fix the description as its
   own change or drop that one prompt with the finding referenced in the commit body.

## Acceptance criteria

1. `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-contrib-governance-p2.json` → PASS.
2. `python3 scripts/check-skill-separability.py --check` → exit 0, and prints the
   `Use when` NOTE with a count of 6.
3. `python3 -m pytest tests/ -q` → zero failures.
4. Proven able to fail: `python3 -m pytest tests/test_skill_separability.py -q -k collision`
   is red when the collision check is commented out. Record the observation in the commit
   body.
5. `ruff check scripts/ tests/` and `mypy` clean.
6. `python3 scripts/gen-docs.py --check` and `python3 scripts/gen-registry.py --check`
   clean (nothing here adds a component; if either reports drift, run the generator —
   never hand-edit a count).
7. `grep -ri "routing accuracy" evals/routing scripts/check-skill-separability.py` finds
   nothing.

## Rollback

`git revert` the phase commit. Nothing outside `evals/routing/`, `scripts/`, `tests/` and
two documentation files changes; no state is written at runtime.
