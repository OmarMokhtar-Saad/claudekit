# Plan: close the adversarial review of the capability-tiers change

Slug: `capability-tiers-audit`. Third and final plan of wave-2 Phase 1. Blast radius: **Tier 2** —
7 files, no security/schema surface. Discharges an adversarial `code-reviewer` verdict
(REQUEST CHANGES: 0 critical, 1 high, 4 medium, 4 low) against the two landed plans.

## Problem

The mechanism worked; the **claims about it** outran it. Five distinct honesty gaps:

1. **H1 — the table is authoritative for 29 files and silently non-authoritative elsewhere.**
   `.claude/commands/review.md:89` spawns `--agent reviewer --model opus` unconditionally, while
   `model-policy.json` says `reviewer` → `balanced` → sonnet with opus reachable only via
   `escalate_when`. `--model` beats frontmatter, so the shipped behaviour of `/review` contradicts
   all three new artifacts. An audit found **8** hand-written model literals across 6 files; the
   BACKLOG named 2.
2. **M1 — `model-router` is declared accountable for "naming the capability tier a task earns" and
   names none.** Its output contract is `[HAIKU | SONNET | OPUS]`. `coordinator.md:475` now says
   "never pick a vendor model name by hand … consult model-router when unsure" — routing the
   reader to the one agent guaranteed to hand back a vendor name.
3. **M2 — `INVOCATION.md:33` states an absolute rule that 36+ in-repo files break**, and names a
   gate that reads only `.claude/agents/`. An unenforceable absolute trains readers to treat repo
   rules as advisory.
4. **M3 — the generator silently rewrites every line of a CRLF file.** Neither `open()` passed
   `newline=`, so a reported one-token edit moved 380 bytes. Reproduced.
5. **M4 / L1 / L2 / L3 / L4 — enforcement and tests weaker than advertised**: no named CI step;
   `^model:` searched against the whole file rather than the frontmatter; the "no routing
   regression" test asserted only self-consistency; five of six fail-closed cases snapshotted an
   agent that was never a write candidate; `RESEARCH.md` cited a prose-substring check as proof.

## Approach

Make each claim true, or narrow the claim. Where a contradiction needs a **behaviour** decision,
record it rather than resolve it unilaterally.

**The `callsite_overrides` registry** is the load-bearing idea. Every hand-written `--model`
literal must now either resolve to its own role's tier, or appear in the table with a reason.
`EveryHandWrittenModelNameIsAccountedFor` enforces both arms, and a second test deletes-proofs the
registry (an override whose site no longer exists must be removed, so the registry cannot decay
into a blanket licence).

**`review.md:89` is recorded, not changed.** Repointing `/review` at the balanced tier is a
user-visible behaviour change and needs owner approval (Golden Rule). The entry states plainly
that it is an unresolved contradiction, and `.ai/BACKLOG.md` carries the decision. `santa.md:64,68`
by contrast are a *legitimate* override — the santa-method deliberately pairs two different models
so neither reviewer anchors on the other, and resolving both from one tier would defeat the point.

## Operations (8)

| # | Type | Path | Fixes |
|---|------|------|-------|
| 1 | code_edit | `.claude/model-policy.json` | `callsite_overrides` registry (H1) |
| 2 | code_edit | `scripts/gen-model-policy.py` | frontmatter-anchored regex (L1), `newline=""` (M3), override validation |
| 3 | code_edit | `tests/test_model_policy.py` | pinned shipped models (L2), load-bearing snapshots (L3), CRLF + anchoring + callsite audit |
| 4 | code_edit | `.claude/agents/_shared/INVOCATION.md` | scope the prohibition to what is gated (M2) |
| 5 | code_edit | `.claude/agents/model-router.md` | output contract in tiers (M1) |
| 6 | code_edit | `.ai/RESEARCH.md` | A2 → "Adopted, scoped"; A7 → "prose only, no mechanical check" (L4) |
| 7 | code_edit | `.github/workflows/ci.yml` | named gate step beside `gen-docs` (M4) |
| 8 | code_edit | `tests/test_behavior_spec.py` | re-pin CLAUDE.md's escalation clause (review axis 5) |

## Evidence already gathered (before this plan executes)

Payloads were trialled against a scratch copy of the tree, not reasoned about:

- CRLF, drifted: `crlf 378->378  bytes 13264->13263  delta=-1` — exactly `len("opus")-len("haiku")`,
  every line ending intact. CRLF, in sync: **byte-identical**.
- Callsite audit binds: deleting the `review.md` override fails the test with
  `.claude/commands/review.md:89 spawns --model opus`; restoring it passes.
- Full file: 21 tests pass (up from 15).

## Tests

Four new classes, each proven by mutation rather than by going green:
`LineEndingsSurviveARewrite`, `ModelLineIsReadFromFrontmatterOnly` (including the case that matters
— an agent that LOST its frontmatter line but has one in a fenced body must be *reported*, never
quietly "fixed" by editing prose), `EveryHandWrittenModelNameIsAccountedFor`, and the L2/L3
strengthenings inside the existing classes.

## Risks

- **A registry entry must only exist for a literal that SURVIVES this change.** Review round 1
  rejected this plan for violating exactly that: op 1 registered `model-router.md:103` while op 5,
  in the same plan, rewrote that line into a tier lookup — so the new
  `test_every_recorded_override_still_exists_and_states_a_reason` would have gone red on the first
  CI run, shipping the registry-decay defect the registry exists to prevent. The entry is removed;
  4 overrides remain, one per surviving literal. The mechanism catching its own author on day one
  is the strongest evidence it works.
- **`CALLSITE_RE` under-collects two forms it does not see today.** `--model=opus` (equals form, no
  space) and any invocation split across lines are invisible to it. Neither shape exists in the
  repo (verified by grep), so the audit is complete *now*, but a future contributor using either
  form gets no error. Disclosed rather than discovered later; widening the pattern is cheap when a
  first instance appears.
- **Ops 1–3 are whole-file replacements** whose `find` is the entire current file. If any of the
  three is edited between planning and execution the op **fails closed** — the engine requires an
  exact match, so drift produces a refusal, never a partial or corrupted write. Low risk, stated
  because the shape is unusual.

- **The override registry could become a rubber stamp.** Mitigated by
  `test_every_recorded_override_still_exists_and_states_a_reason`: an entry whose site is gone
  fails, so the registry cannot outlive what it excuses.
- **`review.md` stays contradictory.** Deliberate and disclosed — a silent behaviour change to a
  quality gate is worse than a recorded contradiction. Owner decision, tracked.
- `ci.yml` gains a step: if the gate is red the pipeline stops. That is the intent; the gate passes
  on this tree today.

## Rollback

`git revert` of the commit, or `/rollback` against the engine's backup directory. Ops 1–3 are
whole-file replacements whose `find` is the current file content, so a revert restores exact prior
bytes; ops 4–8 are anchored find/replace pairs. **No agent frontmatter or tier assignment changes**,
so reverting cannot alter which model any agent runs on. Reverting op 7 alone removes the CI step
without affecting the gate's availability locally.
