# Plan: close the open issues carried out of wave-2 phases 1 and 2

Slug: `open-issues`. Blast radius: **Tier 2** — four files, no security or schema surface. Clears
the decisions parked in `.ai/BACKLOG.md` now that the owner has said to fix them.

## Problems

1. **`/review` contradicted the model policy.** `.claude/commands/review.md:89` spawned
   `--agent reviewer --model opus` unconditionally, while `reviewer` earns the `balanced` tier with
   most-capable reachable only via `escalate_when`. `--model` beats frontmatter, so the shipped
   behaviour of `/review` disagreed with all three artifacts phase 1 added. Recorded as an override
   at the time because repointing a quality gate is user-visible; now authorised.
2. **`CLAUDE.md` had 8 chars of headroom** against the context floor — any addition would fail the
   gate.
3. **`CLAUDE.md` carried stale hand-written component counts** — "75 skills · 19 hooks" against a
   real 76 and 21. Hard rule 8 says never hand-edit counts; this line was hand-edited *and* wrong.
4. **The context-floor gate was undocumented.** `scripts/check-context-floor.py` was not in
   `CLAUDE.md`'s Commands block, so the Definition of Done said "all six commands" while eight
   gates existed.
5. **`--list` ambiguity** in the eval harness (residual note from the phase-2.1 review).

## Approach

**1 — repoint `/review`.** `--model sonnet`, matching the reviewer's tier, and the prose says so
plus names the escalation path. The `callsite_overrides` entry is **deleted**, which is the load-
bearing part: `EveryHandWrittenModelNameIsAccountedFor` then requires the literal to resolve from
the table, so the two cannot silently diverge again. Note the command's own `model:` frontmatter
(line 3) is untouched — that is `/review`'s model, a different axis from the agent it spawns.

**2–4 — reclaim headroom by deleting a drift surface, not by raising the budget.** Removing the
counts fixes issue 3 and buys space for issue 2 at once. Three duplicative passages are compressed
(orientation prose, a quality-gates line that restates what reviewer.md/verifier.md enforce, a DoD
sentence that said "six commands"). The floor gate is **added** to the Commands block, so the file
gains a documented gate while getting smaller: **7,748 → 7,627 chars**, and headroom **8 → 492**
budget units.

**The budget itself is deliberately NOT raised.** `check-context-floor.py` offers that escape with
owner sign-off, and it would have been the easy fix. Raising a ceiling because the file is near it
is how a gate stops meaning anything; the file was carrying content it should not have.

## Operations (4)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `CLAUDE.md` | drop stale counts, document the floor gate, reclaim headroom |
| 2 | code_edit | `.claude/model-policy.json` | delete the now-unneeded `review.md` override |
| 3 | code_edit | `.claude/commands/review.md` | spawn the reviewer on its own tier |
| 4 | code_edit | `evals/cassettes/README.md` | state that `--list` makes no pass/fail claim |

## Tests

No new tests: every change is already covered by gates that will now bind differently.

- Ops 2+3 are checked by `test_model_policy.py::EveryHandWrittenModelNameIsAccountedFor` — with the
  override gone, `review.md`'s literal must equal the reviewer tier's model or the suite fails.
  **This is the test that makes op 3 safe**, and it is why the override deletion is not optional.
- Op 1 is checked by `check-context-floor.py` and by
  `test_model_policy.py::PolicyProseNamesTiersNotVendors`.
- Verification: revert op 3's literal to `opus` while keeping op 2, and the audit must fail naming
  `review.md`. Run and pasted before this is considered done.

## Risks

- **`/review` now runs on a smaller model by default.** That is the point — the policy says
  `balanced` — but it is a real behaviour change to a quality gate, and reviews of multi-phase,
  architecture, or security plans should escalate per `escalate_when`. The command names that path;
  it does not automate the judgement, and cannot.
- **Headroom is improved, not solved.** 492 budget units is ~123 chars of CLAUDE.md text. The
  structural fix is moving content into the agents that consume it, which the floor script's own
  comment names as the real win. Recorded in `.ai/BACKLOG.md` rather than attempted here.
- Removing counts from `CLAUDE.md` means a reader must run `gen-docs.py --check` to learn them.
  That is the intent of hard rule 8.

## Rollback

`git revert`, or `/rollback` against the engine backup. Ops 1–2 are whole-file replacements that
fail closed on drift; ops 3–4 are anchored find/replace pairs. Reverting op 3 without op 2 puts the
corpus in a state the audit test **rejects**, which is correct: the override and the literal must
move together, and the suite says so rather than letting them drift.
