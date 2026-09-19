# Plan: adopt addyosmani/agent-skills CONTRIBUTING governance (C1–C5)

**Master document.** The four executable phases each have their own plan file and ops
config, because `review-record.py resolve` and `check-plan-artifacts.py` both bind
**one plan slug to one ops.json**. A single plan naming four configs cannot be resolved
by either gate — that is the reason for the split, not a stylistic preference.

| Phase | Plan | Ops config | Ops | Item |
|-------|------|-----------|-----|------|
| 1 | [plan-contrib-governance-p1.md](plan-contrib-governance-p1.md) | `ops-contrib-governance-p1.json` | 4 | C1 skill-edit rejection axis |
| 2 | [plan-contrib-governance-p2.md](plan-contrib-governance-p2.md) | `ops-contrib-governance-p2.json` | 10 | C2 routing-separability gate |
| 3 | [plan-contrib-governance-p3.md](plan-contrib-governance-p3.md) | `ops-contrib-governance-p3.json` | 6 | C3 model-name gate |
| 4 | [plan-contrib-governance-p4.md](plan-contrib-governance-p4.md) | `ops-contrib-governance-p4.json` | 5 | C4 + C5 |

Total **25 operations across 4 phases** — well past the ~15-op / 2-phase line, which is
why it ships as four separately-executable configs. Phases are independent: any one can
be executed, reviewed and reverted without the others. Run them in order only because
Phase 3's CLAUDE.md edit names Phase 2's gate.

---

## Overview

Source research: `.claude/reports/research/addyosmani-agent-skills-2026-09-18.md`.
Five governance items from that repo's CONTRIBUTING are adopted here: a rejection
record for skill edits (C1), per-skill routing eval cases with a CI gate (C2), a
"write the procedure, not the workaround" gate (C3), an explicit maintainer rule that
repo-scoped files are not user assets (C4), and a structured skill-gap intake (C5).

## Design precheck — ownership and where the value sits

The data model this change assumes is **one store per axis of history, extended, never
duplicated**. The rejection store (`.claude/knowledge/rejections/INDEX.jsonl` + sibling
briefs, single writer `review-record.py`) already owns "a change that was proposed and
did not survive review". C1's skill edits are the *same fact about a different subject*,
so they become a second `row_type` in that index — not a second ledger (task 008). The
value of C1 sits in `review-record.py` (the writer and the two readers, `search` and
`stats`) and in `.claude/knowledge/rejections/INDEX.jsonl` itself; the prose in the
store README carries the one rule the machinery cannot enforce (commit the row on the
default branch, separately from the rejected change).

C2's value sits in `evals/routing/*.json` (the cases) and `scripts/check-skill-separability.py`
(the ranker) — deliberately **outside** `.claude/`, because they are maintainer CI, not a
shipped asset. C3's value sits in `scripts/check-prompt-model-names.py` plus its
allowlist; the corpus fix-pass it enables is explicitly deferred (below). C4's value is
prose in `.ai/KNOWLEDGE_BASE.md`. C5's value sits in the ledger's `ORIGINS` tuple plus a
template under `.claude/`.

No item's value lands in a file the model does not cover.

## Prior-art check (Phase 0, both stores, run 2026-09-19)

- `review-record.py rejections search "skill edit rejection ledger routing eval gate model name"`
  → exit 0, 13 matches. **None is a validated prior for this work.** The three
  top-scoring rows (`agent-memory-learning`, `iron-law-enforcement-hook`,
  `retro2-backfill`) matched on the generic tokens `ledger`, `gate`, `skill`, `name`;
  their findings are about gen-docs helper classification, ruff/pytest write flags, and
  a stale plan sha — none touches the rejection schema, the eval harness or prompt model
  names. Treated as a miss.
- `knowledge-ledger.py search "<same>"` → exit 0, 2 matches, both `origin: workflow`
  reflection receipts about subprocess env and fixture seeding. Unrelated.
- **Silence is not evidence**: a miss here means unknown, not safe. The specific hazards
  that *are* known priors come from agent memory and are handled explicitly in the Risk
  Assessment below.

## Distribution classification (fleet)

`ck fleet update` only carries assets under `.claude/`.

| Item | Ships to fleet? | Where the contract binds |
|------|-----------------|--------------------------|
| C1 machinery (`review-record.py`) | **yes** (`.claude/operations/scripts/`) | code |
| C1 rule ("row on the default branch, separate commit") | **yes** | prose in `.claude/knowledge/rejections/README.md` |
| C2 cases + ranker + tests | **no** (`evals/`, `scripts/`, `tests/`) | maintainer CI only; the honesty constraint ships as prose in `.claude/skills/eval-harness/SKILL.md` |
| C3 gate + allowlist + tests | **no** (`scripts/`, `tests/`) | contract ships as prose in the CLAUDE.md commands table (this repo) — downstream projects inherit nothing and must not be told they do |
| C4 rule | **no**, by decision (`.ai/`) | it is a rule *about this repo's own files*; shipping it downstream would be the exact category error it forbids |
| C5 template + `ORIGINS` | **yes** (`.claude/`) | template + ledger |

**No fleet sync is performed by this plan.** A final owner-run step is listed in Phase 4
and nothing more; when the owner runs it, it must exclude the `qa-agents` project.

## Testing strategy (all phases)

Behavioural, through subprocess, in temp trees — never structural assertions on function
names. Every new gate ships with a **mutation proof**: a test that injects the exact
defect the gate exists to catch and asserts the gate goes red. A gate without one is
assumed inert (`a-passing-check-can-measure-nothing`).

Full gate after every phase:

```bash
python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
python3 scripts/check-context-floor.py --check
python3 scripts/check-plan-artifacts.py --check
```

If `gen-docs`/`gen-registry` report drift, run the generator — never hand-edit a count.

## Rollback

Each phase is one config. `git revert` of the phase's commit restores the prior tree;
no phase writes outside the repo, none deletes a file (`file_delete` count = 0 across
all four configs), and none has a migration. Phase 1 appends a new `row_type` to an
append-only index — reverting the code leaves those rows in place, where the older
readers ignore them by construction (`_folded_rows` already drops unknown row types only
if told to; see the Phase 1 risk note).

## Risk assessment

- **`_folded_rows` currently lets unknown row types through.** Before Phase 1, any row
  that is not `row_type: "classification"` counts as a brief. If the writer lands before
  the reader edit, `/flow-retro`'s sample-size gate inflates. Mitigation: both live in
  **one** `code_edit` op, so they cannot land apart.
- **Allowlist above an early return exempts every branch below it** (measured hazard,
  memory `allowlist-before-early-return`). Phase 3's gate is ordered scan → collect →
  filter, with no `return` between scan and filter, and a test proves an allowlisted
  file still reds on a *different* phrase.
- **`add_after` is literal concatenation** (memory `ops-add-after-is-literal-concat`).
  Every `add_after` payload in all four configs begins with `\n`. Nothing in the
  pipeline compiles the post-state, so this is checked by reading the payloads, not by
  the validator.
- **Baseline stamping order** (memory `ops-stamp-before-verdict`): stamp the baseline
  *before* recording a review verdict, or the ops.json hash changes and the gate
  deadlocks. These configs ship without a `baseline` block for that reason.
- **One plan slug per config.** Do not merge the four configs; `resolve_ops` tries
  `ops-<slug>.json` and an ambiguous match returns exit 3, which blocks execution.
- **CLAUDE.md is edited in Phase 3 only** (two lines). It is not a protected path for
  `code_edit` (the protected list gates `file_delete`), but `check-context-floor.py`
  weights CLAUDE.md ×4 — run it after Phase 3.
- **UNVERIFIED:** whether the shipped routing cases actually rank their skill in the
  top-5 under the new BM25 ranker over 82 skill descriptions. The ranker cannot be run
  from the planning role. Phase 2 therefore *requires* a tuning step, and states the one
  legal response to a stubborn failure: tune the **case prompt**, never the ranker and
  never a skill description, and if the case still fails, that is a real description
  collision — record it via the C1 axis rather than weakening the gate.
- **UNVERIFIED:** whether any existing test asserts `ORIGINS` has exactly three members
  (Phase 4 adds a fourth). The full suite run in Phase 4's acceptance criteria is the
  check.
- **UNVERIFIED:** whether `gen-registry.py` counts files under `.claude/knowledge/`.
  Phase 4 adds one. Acceptance criteria run the generator's `--check`.

## Deliberately deferred

1. **The C3 fix pass** (converting ~80 genuine model-name occurrences across 21 files to
   tier language). Deferred to its own plan, `plan-prompt-model-name-fixpass`, for a
   mechanical reason: each conversion needs an exact, unique `find` anchor, and 80
   anchors across 21 files is several times the anchor-extraction budget of one planning
   pass — hand-transcribing them is precisely how anchor mismatches get shipped. Phase 3
   makes the debt *explicit and greppable* instead: every un-fixed file enters the
   allowlist with a `PENDING-FIX(plan-prompt-model-name-fixpass)` reason, which the gate
   itself counts and prints on every run.
2. **The 6 skills with no `Use when` in their description** (`context-keeper`,
   `execute-operations-config`, `gan-harness`, `opensource-pipeline`, `search-first`,
   `validate-operations-config`). Decision: the Phase 2 gate **reports** them as a
   non-blocking NOTE with the count, and does **not** fail on them. Reason: a missing
   `Use when` is a *description-quality* defect, while this gate measures *separability*;
   failing one gate on two unrelated defects makes both unfixable in isolation. The NOTE
   is the ratchet — the count is printed on every CI run.
3. **Fleet sync.** Owner-gated, and must exclude `qa-agents`.
