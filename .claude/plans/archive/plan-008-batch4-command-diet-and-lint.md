# Implementation Plan: task 008 batch 4 — corpus lint + single-source contracts

**Status:** SIMULATED, awaiting execution. 5 ops configs in `.claude/plans/ops-008-batch4/`.

## Overview

Batch 4 as signed off was "command diet + lint rules". Measured, the diet is not a
tidy-up and the lint rules are not additions to an existing gate — **`ck lint` does not
exist.** What follows is scoped to what measurement supports.

## The sign-off sheet is wrong here too — measured, not assumed

This is the fifth instance across this task; batch 1 found two, batch 2 found two.

**The ≤40-line command budget is unreachable.** Measured 2026-08-24 across all 55
commands:

    min 47   median 129   mean 133   max 466   total 7338 lines
      <= 40 lines:  0/55 (0%)        <=100 lines: 12/55 (21%)
      <= 60 lines:  1/55 (1%)        <=150 lines: 45/55 (81%)
      <= 80 lines:  7/55 (12%)       <=200 lines: 50/55 (90%)
    excess over a 40-line budget: 5138 lines across 55 files
    largest: refine 466 · ship 228 · gan-build 227 · opensource 222 · loop-start 220

The spec's "reduce commands to ≤40 lines" is therefore a rewrite of 70% of the command
prose, not a lint rule. **Owner decision: ≤40 binds new commands, with a no-growth
ratchet on existing ones.** A gate the corpus cannot satisfy is a gate someone turns
off — and this repo has already shipped three gates that passed against a mutant, which
is the same failure in the other direction.

**`ck lint` does not exist.** `grep -n 'add_parser' src/claudekit/cli/main.py` lists 19
subcommands and lint is not among them. The handoff's "lint rules feeding `ck lint`"
assumed a host that has to be built, so this batch ships the subcommand, the module,
and the three rules.

**One of the three rules flags nothing today. The other two do — and the first draft
of this plan got that wrong.**

`duplicate-triggers` is genuinely clean: zero exact duplicate "use when" clauses, and
zero skill pairs above 0.25 Jaccard on description keywords — batch 2 merged five names
away precisely to reach that state. It is a regression guard, indistinguishable from a
rule that does not run, which is why it is mutation-proven.

`skill-agent-costume` is **not** clean, and this plan claimed it was. Review found the
error and it was a live false negative, not a wording slip: `allowed-tools` appears in
two YAML forms in this corpus, the rule read only the same-line one, and **two skills
declare it as a block list containing `Agent`** —
`.claude/skills/gan-harness/SKILL.md:8` and
`.claude/skills/opensource-pipeline/SKILL.md:8`. So the rule skipped the exact grant it
exists to catch, and `test_the_shipped_corpus_is_clean` would have passed over two real
violations. **That is the third gate in this repo to pass against a mutant, and this one
was mine, in the batch whose stated purpose is preventing it.**

Both forms are parsed now. The two real violations are **waived by name, with a reason
each**, in `.claude/lint-baseline.json`: both are genuine orchestration prose
(`gan-harness` runs Generator → fresh Evaluator → Adjudicator; `opensource-pipeline`
spawns Sanitizer → Forker → Packager), converting an orchestration skill into an agent
is agent-corpus work belonging with batch 3, and a rule that failed the DoD on day one
would be turned off. Same ratchet shape as the command budget: record what exists, block
what is new. Waived **by name, never by pattern** — a glob would silently cover the next
skill someone adds. Filed in `.ai/BACKLOG.md`.

## The contradictions, which are the real find

The handoff described "10 files define their own reviewer taxonomy" and "two
disagreeing coordinator routing tables" as duplication. Both are worse: the duplicates
have **drifted into contradiction**, so the corpus states two different answers.

**Reviewer taxonomy.** `.claude/commands/review.md:88` says `REVISE = score < 70`.
`.claude/agents/reviewer.md:346` says score < 70 is `REJECTED`. `REJECTED` appears in no
formula in `review.md` at all. And `reviewer.md` declares four decisions in its anchored
block (`:253`) but only three in its summary template (`:297`) and three score bands
(`:329`, `:336`, `:346`) — leaving `REVISE`, which
`.claude/operations/scripts/review-record.py:42` accepts, with **no band at all**.

This is not theoretical. **Batch 2's own round-1 verdict came back `REVISE` at 84**,
which both files' tables would have called `CONDITIONAL`. The verdict that actually
gated that batch matched neither definition in the corpus.

The canonical taxonomy resolves it by making **findings gate before score** — an open
CRITICAL or MAJOR is `REVISE` at any score, so a high score cannot approve past a
blocker. That is the behaviour that already happened; this writes it down.

**Coordinator routing.** The two tables disagree on five of eight intents:

| Intent | `agents/coordinator.md` | `commands/coordinator.md` |
| --- | --- | --- |
| feature | Planner → Reviewer → Implementer → Verifier → GitOps | refine → implementer → verifier |
| bug | Debugger → Planner → Reviewer → Implementer → Verifier → GitOps | debugger → refine → implementer |
| refactor | Planner → Reviewer → Implementer → Verifier → GitOps | refine → implementer → verifier |
| docs | DocUpdater | documenter |
| review | *(absent)* | verifier, optional reviewer |

The tiebreaker is in the command file's own prose (`:112`): "`/refine` replaces the
manual planner → reviewer → planner cycle." So `refine` **is** the pair, and the agent
table was spelling out a sequence the corpus had already composed. The agent file keeps
the one table; the command file references it and retains the two conventions it was
the **only** source of — the refine equivalence, and the create/update docs split that
`HANDOFF_PROTOCOL.md` has carried as two pipelines all along while the table offered one
destination.

## Scope — 5 configs

| # | Config | Effect |
| --- | --- | --- |
| 01 | `ck-lint` | `src/claudekit/lint.py` (3 rules), the subparser, dispatch entry, `tests/test_lint.py` |
| 02 | `lint-baseline` | `.claude/lint-baseline.json` — the ratchet's starting point, 55 commands |
| 03 | `reviewer-taxonomy` | canonical definition in `HANDOFF_PROTOCOL.md`; the contradicting formulas in `reviewer.md`, `review.md`, `refine.md` replaced by references |
| 04 | `coordinator-routing` | one table in `agents/coordinator.md`, corrected; `commands/coordinator.md` references it |
| 05 | `tests-and-changelog` | `tests/test_single_source_contracts.py` + CHANGELOG |

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | Each lint rule actually binds | Mutation, per rule: an over-budget new command, a command grown past the ratchet, a skill granted `Agent`, two skills with overlapping descriptions. `tests/test_lint.py` asserts the finding AND the clean case for each. |
| 2 | The ratchet holds oversized commands rather than failing on them | A 466-line command with a recorded baseline produces zero findings; the same file plus one line produces exactly one. |
| 3 | A corrupt baseline fails closed | If an unreadable baseline read as empty, every command would look new and a 466-line file would "pass" a 40-line budget. `RuntimeError`, asserted. |
| 4 | The frontmatter parser cannot be evaded | A 400-word description does not push `allowed-tools` out of view — the block is read to its closing fence, not to a line cap. |
| 5 | The taxonomy matches what gates execution | The prose's four spellings are asserted equal to `review-record.py`'s `VALID_DECISIONS` tuple. Prose that drifts from the parser cannot gate anything. |
| 6 | The contradictions are gone, not moved | `REVISE = score < 70` and `CONDITIONAL = score 70-89 OR` asserted absent from all three files. |
| 7 | Deduplication lost nothing | The two conventions that lived only in the deleted routing table are asserted present in the file that replaced it. This is the batch-1 mistake the assertion exists to prevent. |
| 8 | The dedup stays done | Both single-source tests assert the *absence* of a second copy, because the corpus regrew duplicates between the 008 spec and batch 1. |

## Risk

Low-to-medium. `ck lint` is new surface, so nothing can regress by its absence, and it
is not wired into CI by this batch — that is a separate, owner-gated decision. The
taxonomy and routing edits are prose, and the risk there is losing a convention that
lived only in a deleted copy, which proof 7 covers.

## Rollback

`git revert` of one commit, or `restore-backup.py` per shard. `ck lint` is additive;
deleting `.claude/lint-baseline.json` makes the budget rule report every command as new,
which is loud rather than silent.

## Definition of Done

    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/
    mypy
    python3 scripts/gen-docs.py --check
    python3 scripts/gen-registry.py --check
    python3 scripts/gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    shellcheck install.sh .claude/hooks/*.sh
    python3 scripts/check-protected-differential.py --baseline main --require-baseline
    ck lint          # the new gate, against this repo's own corpus

Plus one adversarial diff review by a fresh `code-reviewer` prompted to REFUTE.
