# Implementation Plan: task 008 batch 2 — near-duplicate skill merges

**Status:** SIMULATED — 16 ops configs written, applied end to end in a throwaway
worktree, all gates green, both new gates mutation-proven. **Awaiting owner approval
to execute on the real tree.** Nothing has been applied to `fix/protected-docs-scope`.

## Overview

Task 008 batch 2, as signed off, merges 7 skill names away into 5 survivors:
76 → 69 skills. Every one of the 13 names is PRESENT at `fd9ed2c`.

**Three of the five clusters are correct as written. Two are not, and one hard
constraint the sheet does not mention doubles the deletion count.** All of the
below is measured at `fd9ed2c` on `fix/protected-docs-scope`, working tree clean.

## Final scope after the owner decisions

Five names are removed, not seven: `autonomous-loops`, `verification-loop`,
`dependency-audit`, `session-continuity`, `context-priming`. **76 → 71 skills.**
`token-budget-advisor`, `context-budget`, `token-optimization`, `codebase-mapping`
and `codebase-onboarding` all stay.

Deletions: 5 names × 2 trees (`.claude/skills/` and `.agents/skills/`) = **10
deletions**, so at `MAX_DELETIONS=3` the deletion work alone is 4 configs, and the
survivor grafts, registry rows, aliases and reference updates are separate configs.
Registry rows are never auto-removed on deletion (`gen-registry.py`: "deleting an
asset is owner-gated"), so each removed row is an explicit operation.

---

## The sign-off sheet is wrong in two places — measured, not assumed

Batch 1 established that this sheet can be confidently wrong (it called 24 unique
components a duplicate tree, and called three one-line frontmatter deltas a
three-way merge). This is the third and fourth instance.

### Wrong 1 — the "token/context quintet" is three unrelated concerns, not one cluster

The sheet groups `context-budget` + `token-optimization` as survivors and folds in
`token-budget-advisor`, `context-keeper`, `context-priming`. Measured content:

| Skill | What it actually is | Overlap with the survivors |
| --- | --- | --- |
| `context-budget` (211 L) | corpus token accounting; backs the `/context-budget` command | — survivor |
| `token-optimization` (219 L) | response compression, bounded reads, spilling | — survivor |
| `token-budget-advisor` (140 L) | a user-facing **response-depth menu** (25/50/75/100), token estimation heuristics, shorthand recognition, session depth memory | **none** — no section, table, or rule appears in either survivor |
| `context-keeper` (169 L) | **session save/resume serialization format** | none |
| `context-priming` (155 L) | session-start project-context loading sequence | none |

Folding `token-budget-advisor` into a token-accounting skill is not a merge; it is
either the deletion of a feature or the transplant of an unrelated 140-line
section into a skill whose description does not cover it. Either way it makes the
mis-routing hazard the batch exists to remove *worse*, not better.

**And the sheet has one survivor backwards.** `context-keeper` is the **live**
member of the session-persistence pair:

    .claude/hooks/session-start.sh:133   CONTEXT_FILE=".claude/session-context.md"

`session-context.md` is context-keeper's file, written by `/save-session` and read
by `/resume-session` and by the session-start hook. Its real duplicate is
`session-continuity`, whose `.claude/session-state.json` has **no writer and no
reader anywhere in the repo** — three prose files mention the path and nothing
else:

    $ grep -rln 'session-state\.json' .claude src scripts tests docs .ai | grep -v plans/archive
    .claude/skills/skills-registry.json
    .claude/skills/context-priming/SKILL.md
    .claude/skills/session-continuity/SKILL.md

Deleting `context-keeper` and keeping `session-continuity` would delete the wired
skill and keep the dead one.

`context-priming` is genuinely orphaned — there is no `/prime` command
(`ls .claude/commands/prime.md` → No such file) and no agent references it — but
its subject is session start-up, adjacent to `/load` and `codebase-onboarding`,
not to token accounting.

### Wrong 2 — `codebase-mapping` is machinery, not near-duplicate prose

`codebase-mapping` is the authoring contract for `project-graph.py`: Step 7 emits
the `.claude/project-graph.json` sidecar, with the confidence tiers
(`extracted`/`inferred`/`ambiguous`), the `build --check` / `build --force` /
`hubs` invocation sequence, the `stale` refresh protocol and its exit-code
contract, and the hub/god-node table. Two test files assert it by name:

    tests/test_project_graph.py:436   assert [p.name for p in self._copies("codebase-mapping")] == ["SKILL.md"]
    tests/test_new_skills.py:20       "codebase-mapping",

`codebase-onboarding` produces two human artifacts — a 2-minute onboarding guide
and a starter `CLAUDE.md` — and contains no graph machinery at all. Zero heading
overlap beyond `## Purpose`. These are complementary; the pair is not a duplicate.

---

## The constraint the sheet does not mention: there is a second skills tree

`.agents/skills/` is a tracked, full-size skills corpus — 76 directories against
`.claude/skills/`'s 76 plus the registry — and it is **not** a clean mirror:

    $ diff -rq .agents/skills .claude/skills | grep -c '^Files'
    42
    Only in .agents/skills: source-command-review
    Only in .claude/skills: verification-gap-lens

So 42 of 76 files diverge, the mirror carries a skill name the canonical tree does
not, and it is missing one the canonical tree has. It is owner-known debt
(`.ai/DECISIONS.md` decision 22 leaves `.agents/` untouched; `.ai/BACKLOG.md:254`
files the drift) and `tests/test_knowledge_ledger.py:282` asserts mirror content
for one skill, so it is load-bearing for the suite.

**For batch 2 specifically, `.claude/` is the content source and the mirror holds
nothing unique.** Proven for all 13 batch-2 files: every mirror-only line is a
`.Codex/`→`.claude/` path substitution, a "Codex"→"Claude Code" product
substitution, an `AGENTS.md`→`CLAUDE.md` substitution, or a
`disable-model-invocation: true` frontmatter line. No operative rule exists only
in the mirror.

But it changes the arithmetic: mirroring the deletions is 7 names × 2 trees = **14
deletions**, which at `MAX_DELETIONS=3` is 5 configs of deletions alone, before
survivor edits, registry aliases, and reference updates. `.agents/` is **not**
shipped (`grep -n '\.agents' install.sh MANIFEST.in pyproject.toml` → 0 hits), so
this is in-repo hygiene, not consumer exposure.

---

## What batch 2 actually buys — stated honestly

Three of the five merges are real unions of complementary material, so the
survivors **grow**:

| Cluster | Survivor now | Merge-away | Survivor after union |
| --- | --- | --- | --- |
| loop pair | `autonomous-loop` 200 L (6-phase Ralph pipeline) | `autonomous-loops` 251 L (convergence criteria, 3 loop patterns, 4 safety guards with code, state tracking, anti-patterns) | ~400 L |
| verification pair | `verification-before-completion` 190 L (the discipline: never claim without running) | `verification-loop` 272 L (the runbook: 6 phases with per-ecosystem commands, continuous mode, PostToolUse wiring) | ~430 L |
| dependency pair | `supply-chain-audit` 179 L (threat detection: typosquat, abandoned, lockfile integrity, permission scope) | `dependency-audit` 154 L (upgrade lifecycle: semver risk matrix, safe incremental upgrade process, changelog checklist, when to replace, anti-patterns) | ~300 L |

The corpus loses 7 skill **names** and roughly **zero** corpus tokens. The payoff
is the stated one — removing the mis-routing hazard of two adjacent descriptions —
not size. Description budget does improve: 7719/9000 chars now, ~700 freed.

---

## Scope — as proposed, pending the decisions below

Clusters A–C proceed as signed off. D and E are held for the owner.

### A. loop pair — `autonomous-loops` → `autonomous-loop`
Graft, in order, after the existing `## Integration`: Core Concept's use/do-not-use
bounds, Convergence Criteria (hard/soft/budget), the three Loop Design Patterns,
the four Safety Guards **with their code blocks**, Loop State Tracking JSON, the
Report format, and the Anti-Patterns table. Reconcile the two iteration budgets
explicitly (survivor says max 5; merge-away's quality loop says 10) rather than
letting one silently win.

### B. verification pair — `verification-loop` → `verification-before-completion`
The survivor keeps the Iron Law and the 6-step gate; the merge-away contributes
the executable runbook. Both must survive: the discipline without the commands is
unactionable, the commands without the discipline are skippable. Also update the 5 live
consumers: `.claude/agents/coordinator.md`, `.claude/commands/loop-start.md`,
`prp-implement.md`, `gan-build.md`, `.claude/skills/gan-harness/SKILL.md`.

`.claude/plans/plan-skill-loading-contract.md` also names `verification-loop` and is
**deliberately not touched**: it is a spent plan (its ops are already in
`plans/archive/plan-skill-loading-contract.ops.json`), and its table at line 29 is a
measurement of the corpus as it stood, not an instruction to load anything. Editing a
dated record falsifies it. An earlier draft of this plan listed it as a consumer to
update; review caught that, and the scope-out is stated here rather than left implicit.

### C. dependency pair — `dependency-audit` → `supply-chain-audit`
Graft the manifest/lock inventory table, the 4-step CVE assessment process (the
survivor has commands but no reachability/exploitability triage step), the semver
range and upgrade-risk matrices, the changelog checklist, the safe incremental
upgrade process, dependency health signals, when-to-replace, and anti-patterns.
Update consumers: `.claude/agents/security-scanner.md`, `.claude/agents/devops.md`,
`README.md:254`, `docs/SKILLS.md:98`, `docs/ARCHITECTURE.md:516`. **Measured, because
an earlier draft of this sentence was vague enough to look like a hard-rule-8
violation:** `gen-docs.py` owns *counts* in those files and the one `<!-- BEGIN
GENERATED:inventory -->` block, which is `README.md:315-322`. The three rows edited
here are at 254, 98 and 516 — all outside any generated block; `grep -n 'BEGIN
GENERATED' docs/SKILLS.md docs/ARCHITECTURE.md` returns nothing. The skill tables are
hand-maintained, so editing them by anchor is correct and hard rule 8 is untouched.

### D. session lifecycle — `session-continuity` + `context-priming` → `context-keeper`
Owner decision 1: re-scoped. `token-budget-advisor` **stays** as its own skill;
`context-budget` and `token-optimization` are **not** merged. Instead the cluster
becomes the session-lifecycle pair with the survivor reversed — `context-keeper`
survives because `session-start.sh:133` reads its file, and `session-continuity`
merges away because `.claude/session-state.json` has no reader or writer.

Grafted from `session-continuity`: the structured decision record (rationale +
`alternatives_rejected`), pending tasks with `priority`/`blocked_by`, the
`gotchas`/`conventions` context fields, the history array with its 10-entry cap,
the Save Rules and Load Rules lists, external-modification conflict detection
("verify file state, flag conflicts"), and the session summary display format.
Grafted from `context-priming`: the 5-step priming sequence, the key-config table,
the tech-stack profile, the conventions-extraction list, the priming template,
selective priming by task type and by scope, refresh triggers, and the performance
rules. `usedBy: ["coordinator"]` transfers from `session-continuity` to
`context-keeper`, and `coordinator.md` is updated.

### E. onboarding pair — DROPPED from batch 2
Owner decision 2. `codebase-mapping` and `codebase-onboarding` both stay. Their two
descriptions are rewritten so they no longer compete for routing — mapping declares
itself the machine-readable graph/index producer, onboarding the human guide and
starter `CLAUDE.md` producer. No deletion, no test changes, no alias.

Plus, for every removed name: one `renamed` alias entry in the registry (skills-only
map, which already exists, is validated by `gen-registry.py`, and is read by
`ck doctor`), and the mirrored deletion in `.agents/skills/` per decision 3.

---

## Owner decisions — ANSWERED 2026-08-24

1. **Token/context cluster.** → **(b)+(c)**: keep `token-budget-advisor`, reverse
   the session pair. Recorded in cluster D above.
2. **Onboarding pair.** → **drop from batch 2, fix descriptions only.** Cluster E.
3. **`.agents/` mirror.** → **mirror the deletions only**; no survivor grafts into
   the mirror. The widened content divergence stays carried debt.

Original wording of the questions, kept for the record:

1. **Token/context cluster.** Options: (a) merge only `token-optimization` ↔
   `context-budget` boundaries and drop the other three from batch 2; (b) keep
   `token-budget-advisor` as its own skill and re-target `context-keeper` /
   `context-priming` to the session-lifecycle cluster; (c) re-scope the pair to
   `session-continuity` → `context-keeper` (survivor reversed, dead file retired);
   (d) proceed exactly as the sheet says. I recommend (b)+(c): it removes three
   duplicate *names* — `session-continuity`, `context-priming` — without deleting
   a live hook contract or a user-facing feature.
2. **Onboarding pair.** Recommend dropping it from batch 2: not a duplicate, and
   `codebase-mapping` is a script contract with test coverage. Alternative: keep
   both, and fix only the two descriptions so they no longer compete.
3. **`.agents/` mirror.** Mirror the batch-2 deletions (14 deletions, ~5 extra
   configs), or leave the mirror alone and record the divergence as carried debt?

---

## The batch must be simulated before it runs

Validation is not the gate; applying is. `validate-config-json.py` proves an
anchor is present and unique, not that the produced text is whole — in batch 1
every config returned `-> APPROVED` while the applied result left 110 tests red.

    git worktree add --detach <tmp> HEAD
    # copy untracked files in by hand — `git diff | git apply` does not carry them
    # apply every config in INDEX order, then:
    python3 -c 'import ast,pathlib;[ast.parse(p.read_text()) for p in pathlib.Path("tests").glob("*.py")]'
    python3 scripts/gen-docs.py && python3 scripts/gen-registry.py
    python3 -m pytest tests/ -q

Compare against that worktree's own baseline (~17 pre-existing failures in
`test_ops_enforcement_scope`, `test_pipeline_e2e`, `test_profiles`,
`test_hooks_behavioral`, `test_dispatch_payload`), never against zero.

`add_before` does not append a newline — it abutted its anchor three times in one
batch-1 session. Every graft is checked for MD022 and for a blank line at the seam.

---

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost in any merge | **token diff**: every backtick span, dotted identifier, **bold span and ALL-CAPS imperative bullet** in the deleted file present in the survivor; each remaining absence justified individually. Headings-only acceptance is what lost three sections in batch 1. `tests/test_i18n.py::test_the_i18n_workflow_fold_survives` is the shape to copy. |
| 1b | The proof itself has no blind spot | Review found one: the first derivation was backtick spans and dotted identifiers only, so an operative rule carrying neither — `NEVER save secrets, credentials, or API keys in the state file`, `One dependency at a time. One version bump at a time. Tests after every change.` — was invisible to it, and a regression dropping one would have passed every assertion. Bold spans and imperative bullets were added for exactly that class: 127 → 163 asserted fragments. |
| 2 | Each acceptance test actually binds | mutate the shipped survivor — delete one grafted section — and read the failure. A test that cannot be made to fail is decoration. |
| 3 | Every removed name still resolves | `ck doctor` on a tree using the old name reports the rename and the downstream files |
| 4 | No consumer left pointing at a deleted skill | `tests/test_008_batch2_merges.py::TestNoConsumerPointsAtADeletedSkill` over `.claude/agents|commands|skills|hooks|operations`, `docs/`, `src/claudekit/`, `scripts/`, `README.md`. Records are excluded **on a stated principle** — a dated record is falsified by being edited — and the scope claim is itself asserted by `test_the_promised_scope_is_actually_the_scope`, because the first version of that class checked three directories while this row promised eight. Review found the gap. |
| 5 | Counts are generator-derived | `gen-docs.py --check` and `gen-registry.py --check` after regeneration; never hand-edited (hard rule 8) |
| 6 | Mirror parity, if decision 3 says mirror | `diff -rq .agents/skills .claude/skills` shows no batch-2 name on either side |

## Risk

Medium, and it is content risk, not mechanical risk. Three of the merges are real
unions of complementary prose; a headings-only or spot-check acceptance would lose
material, which is exactly how batch 1 lost the per-language i18n formatting APIs.
The prose corpus is the product's moat.

## Rollback

`git revert` of one commit, or `restore-backup.py` per shard. No consumer sees a
removed name: every deletion enters the registry `renamed` alias map for one
release.

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

Plus one adversarial diff review by a fresh `code-reviewer` prompted to REFUTE,
ceiling 3 rounds. Verifier does not auto-run — ask.


---

## Simulation results — measured, not asserted

Throwaway detached worktree at `fd9ed2c`, untracked config files copied in by hand
(`git diff | git apply` does not carry them).

    baseline (worktree, before the batch):  17 failed, 2203 passed, 1 skipped, 1 xfailed
    after all 16 configs applied:           17 failed, 2366 passed, 1 skipped, 1 xfailed

Same 17 failures, name for name — the documented worktree baseline in
`test_ops_enforcement_scope`, `test_pipeline_e2e`, `test_profiles`,
`test_hooks_behavioral` and `test_dispatch_payload`. **Zero new failures**, 163 new
tests passing.

    ast.parse OK (tests/, src/, scripts/)
    Counts: agents=29 commands=55 skills=71 hooks=26   OK: docs counts are current.
    OK: registry matches the filesystem (18 mapped agents, 11 without skills, 71 skills)
    Model policy in sync: 29 agent roles.
    skill descriptions   7475   9000   OK      (was 7475 after / 7719 before)
    TOTAL               92735  99000   OK: context floor within budget
    ruff: All checks passed!   mypy: no issues in 28 source files   shellcheck: clean
    check-protected-differential: OK: no undisclosed path lost protection
    ck doctor --strict: exit 0, zero warnings

### The simulation caught two things validation could not

**1. `ck doctor --strict` went red on the merges being documented.** All 16 configs
validated `-> APPROVED`, and the applied result still failed the doctor gate: batch 1's
alias scan warns which files still name a removed skill, `--strict` fails on any
warning, and every batch-2 survivor names the skill it absorbed in its own seam. Five
warnings, gate red. Fixed in `008-b2-16` by exempting exactly one file — the alias
target's own `SKILL.md` — with `tests/test_doctor_alias_scope.py` proving the exemption
does not widen.

**2. A consumer that names no skill.** `tests/test_new_skills.py::test_total_skill_count`
asserted `>= 76`. No grep for any removed name would have found it — the same class of
miss as batch 1's seven test files reaching the deleted tree through a `TEMPLATE_DIR`
constant.

### Both new gates are mutation-proven

Deleting one grafted section from the shipped survivor:

    MUTANT: deleted the Safe Incremental Upgrade Process section (942 chars)
    FAILED test_supply_chain_audit_kept_the_union[Safe Incremental Upgrade Process]
    FAILED test_supply_chain_audit_kept_the_union[Rollback Strategy]
    2 failed, 165 passed

Widening the doctor exemption from the target's own file to every file — the mutant a
lazy fix would have shipped:

    MUTANT: exemption widened from the target's own file to every file
    FAILED test_any_other_file_naming_the_old_id_still_warns
    1 failed, 1 passed        (restored: 2 passed)

### Union proof, by token diff

Every backtick span and dotted identifier in each deleted file is present in its
survivor. Derived, not spot-checked:

    autonomous-loop                   200 ->  452 lines | union tokens missing: NONE
    context-keeper                    169 ->  489 lines | union tokens missing: NONE
    supply-chain-audit                179 ->  334 lines | union tokens missing: NONE
    verification-before-completion    190 ->  459 lines | union tokens missing: NONE

The 127 fragments asserted by `tests/test_008_batch2_merges.py` were derived from those
token sets (tokens in the deleted file, absent from the survivor before the merge) plus
the prose headings that carry no token — headings **as well as**, never instead of,
which is the hole batch 1 shipped through.

## What the 16 configs do

| # | Config | Effect |
| --- | --- | --- |
| 01-04 | `*-union` | the four union grafts, plus the frontmatter each one needed (`allowed-tools: Read, Bash, Grep, Glob` on the verification survivor — the grafted runbook has to be able to run) |
| 05 | `onboarding-descriptions` | owner decision 2: no merge, descriptions rewritten so the pair stops competing |
| 06-08 | `consumers-*` | 13 reference updates across 3 agents, 3 commands, 3 skills, `README.md`, `docs/SKILLS.md`, `docs/ARCHITECTURE.md` |
| 09-12 | `delete-*` | 10 deletions, 5 names × 2 trees, three per config under `MAX_DELETIONS=3` |
| 13 | `registry` | 5 rows dropped, 5 `renamed` aliases added |
| 14 | `tests` | the acceptance suite, plus the two existing tests that had to move |
| 15 | `docs` | CHANGELOG `[Unreleased]` + 5 maintainer docs |
| 16 | `doctor-alias-scope` | the gate the simulation caught, and its mutation guard |

## Still owner-gated before execution

- **Approval to execute** (Golden Rule, per plan).
- **A real review record.** Batch 2 is Tier 3, so `--no-approval` does not apply:
  reviewer >= 90/100 on this plan + its ops, then a fresh adversarial `code-reviewer`
  on the diff. Both need the Agent tool. `--no-approval` was used **only** inside the
  throwaway worktree, for simulation, and is disclosed here for that reason.


---

## Review round 1 — REVISE, 84/100, and what changed

A fresh `reviewer` scored 84 (Plan Quality 78, Architecture 86, Security 90) with one
CRITICAL and two MAJOR. It verified the re-scope evidence independently — the
`session-start.sh:133` reader, the two tests naming `codebase-mapping`, the mirror's
10 target files, the `main.py` anchor, and three union tokens carried into the graft —
and then found three things I had wrong. All five findings are addressed:

**[CRITICAL] A dangling reference shipped.** My own cluster-B text listed six
consumers of `verification-loop` and the configs updated five;
`.claude/plans/plan-skill-loading-contract.md` was named and never touched. Verified:
it still contains the string, at lines 29 and 80. **Resolution:** it is a *spent* plan
— its ops are in `plans/archive/` — and its table is a dated measurement, not a load
instruction, so editing it would falsify a record. Scoped out explicitly with that
reason in cluster C, and the plan text that wrongly promised the edit is corrected.
The finding was right that the gap was undisclosed; the fix is disclosure, not an edit.

**[MAJOR] The acceptance test was narrower than the claim it existed to prove.**
`ROOTS` was three directories while proof row 4 promised six roots plus `README.md`.
That is the batch-1 failure mode exactly — a test asserting a property it does not
exercise — and it meant the CRITICAL above would have passed CI silently.
**Resolution:** `LIVE_ROOTS` is now `.claude/agents|commands|skills|hooks|operations`,
`docs/`, `src/claudekit/`, `scripts/` plus `README.md`; records are excluded on a
stated principle rather than by convenience; and `test_the_promised_scope_is_actually
_the_scope` asserts the scope itself, so a future narrowing goes red.

**[MAJOR] The union proof had a blind spot.** Backtick spans and dotted identifiers
cannot see an emphasised rule or an ALL-CAPS imperative bullet. Measured: 8 imperative
bullets and 31 bold spans across the five deleted files were invisible, including
`NEVER save secrets, credentials, or API keys in the state file` and `One dependency at
a time. One version bump at a time. Tests after every change.` **Resolution:** both
classes added to the derivation, 127 → 163 asserted fragments. Widening it also
surfaced five bold labels I had *paraphrased* in seam text rather than carried — `Use
when:`, `Do NOT use when:`, `Run this skill:`, and the dependency core principle — now
carried verbatim. Two absences remain and are justified individually, the way the i18n
fold's three were: the bold Integration bullets that pointed **at** a skill this batch
deletes. A bullet telling the reader to load a deleted skill is the one thing a union
must not preserve.

**[MINOR] Intra-operation edit coupling.** In `008-b2-01` the graft anchor depended on
an earlier edit in the same operation having already run. True, and an untested
assumption to lean on. **Resolution:** the two edits are reordered so neither depends
on the other — graft first against the file as it is on disk, then rename.

**[MINOR] `docs/` hand-edits vs hard rule 8.** Not a defect, but my wording invited the
doubt. Measured and recorded in cluster C: the only generated block in those three
files is `README.md:315-322`; the edited rows are at 254, 98 and 516, and
`grep -n 'BEGIN GENERATED' docs/SKILLS.md docs/ARCHITECTURE.md` returns nothing.

Round 2 reads only the diff since this verdict.
