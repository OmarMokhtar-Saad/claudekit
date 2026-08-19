# Implementation Plan: Independent Review Floor (G6) + Iron-Law Scope Memo (G1)

## Overview
Two deliverables in one workstream. **Part A** adds a per-PR independent adversarial
diff-review floor to `CLAUDE.md`'s blast-radius tiering, sized to fit the measured
context-floor headroom. **Part B** records the `.claude/**` Iron-Law exemption
asymmetry as an OPEN decision in `.ai/DECISIONS.md` — no code change, owner-gated.

## Scope
- **In Scope:** `CLAUDE.md` (one added bullet), `.ai/DECISIONS.md` (one added entry).
- **Out of Scope:** any hook (`ops-enforcement.sh`), `.claude/settings*.json`, agents,
  skills, commands, `CHANGELOG.md`, `docs/`, and the PRODUCT templates
  (`.claude/local/CLAUDE.template.md`, `templates/*/CLAUDE.md`). No component counts
  are touched (hard rule 8). Part B is deliberately NOT implemented as code.

## Prerequisites
- None. Both edits are additive text; no build, no dependency, no migration.

## Evidence (verified by reading the files in this checkout)

**G6 — no independent review floor on implementation:**
- `CLAUDE.md:66` — Tier 1 ends at "create minimal ops.json -> validate -> execute ->
  compile-verify. SKIP planner/reviewer."
- `CLAUDE.md:67` — Tier 2 is "planner + ops.json; reviewer ONLY if architecture is
  touched".
- `CLAUDE.md:69` — "the verifier agent NEVER auto-runs after implementation."
- Net: a Tier 1 or Tier 2 change can reach a PR with zero independent read of the
  resulting diff. `reviewer` reviews PLANS (a pre-image), not the produced diff;
  `code-reviewer` reviews diffs but is never required by the ladder.

**G1 — Iron Law does not cover this repo's own product:**
- `.claude/hooks/ops-enforcement.sh:47` —
  `case "$ABS_TARGET" in "$ABS_ROOT/.claude/"*) exit 0 ;; esac` exempts everything
  under this project's `.claude/`.
- `.claude/hooks/ops-enforcement.sh:50` —
  `echo "$ABS_TARGET" | grep -qE '\.(md|txt|rst|adoc)$' && exit 0` exempts every
  markdown/text file anywhere in the project.
- `.claude/hooks/ops-enforcement.sh:13` —
  `[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0` short-circuits the whole
  hook; `CLAUDE.md:11` ("Session setup gotcha") instructs maintainers to keep
  `ECC_HOOK_PROFILE=minimal` in `.claude/settings.local.json`, and that file is present
  in this checkout.
- This repo's deliverable IS the prompt corpus (agents + commands + skills, all `.md`
  under `.claude/`). So the Iron Law effectively covers `src/claudekit/**` and exempts
  the primary product: prompt edits land as direct Edits with no ops.json, no review
  record, no backup, no rollback — and with `minimal` set, no enforcement at all.
  Decision-log entry #17 shows the escape hatch was a deliberate ergonomics choice;
  the *scope* question it created was never recorded.

## THE BINDING CONSTRAINT — measured context floor

`scripts/check-context-floor.py:45` sets `CLAUDE_MD_MULTIPLIER = 4` and `:72`
multiplies CLAUDE.md's raw char count by it (main context + 3 pipeline subagent
injections), so one CLAUDE.md char costs ~4x a char in a single agent body.

Measured with `python3 scripts/check-context-floor.py --json`:

| Metric | Before | After (predicted) | Budget |
|---|---|---|---|
| CLAUDE.md raw chars | 7,316 | 7,617 | 7,750 |
| CLAUDE.md delivery-weighted | **29,264** | **30,468** | 31,000 |
| Weighted headroom | 1,736 | **532** | — |
| Total floor | 89,727 | 90,931 | — |
| `ok` | true | true (predicted) | — |

The added bullet is exactly **301 raw chars = 1,204 weighted**, which fits the 1,736
weighted headroom with 532 to spare. The budget is NOT raised (raising it needs owner
sign-off and defeats the gate). Detail that did not fit was compressed, not relocated;
no agent body is touched by this workstream.

## Implementation Steps

### Step 1: Add the per-PR independent review floor to CLAUDE.md
- **File:** `CLAUDE.md`
- **Action:** Modify (insert one bullet immediately after the Tier 3 line, `:68`)
- **Description:** Add a tier-independent review floor to the "Blast-radius tiering"
  block, placed after Tier 3 so it visibly applies to all three tiers rather than
  reading as a Tier-3 clause.
- **Details:** The inserted line reads:

  `  - **Review floor (all tiers)**: every PR gets >=1 adversarial diff review before it merges — fresh `code-reviewer` instance, never the author, prompted to REFUTE not approve. Stop at the first round with zero blocking findings; ceiling 3 rounds; rounds 2+ read only the diff since the last verdict.`

- **Design rationale (why this exact shape):**
  - **Per-PR, not per-step.** The source floor (chaos-engine SKILL.md iron law 6, MIT)
    asks for both; only the per-PR clause is enforceable, because a pull request can be
    counted and a step cannot. Adopting only the countable clause is the honest subset.
  - **Does not contradict the token/model policy.** Tier 1 keeps SKIP planner/reviewer
    and Tier 2 keeps its conditional plan review; the floor adds exactly one
    diff-scoped `code-reviewer` pass per PR (haiku/sonnet-class, diff-sized context),
    not a reinstated full pipeline per change. N Tier-1 changes batched into one PR
    cost one review, so the cost is bounded by PR count, not change count.
  - **Separate instance, never the author, prompted to REFUTE.** Required by the source
    design: a self-review inherits the author's context and anchoring, which is exactly
    the failure the floor exists to catch. "Refute" framing is stated because an
    approve-framed reviewer converges on approval.
  - **Zero-yield stop + 3-round ceiling.** The source measured blocking-finding yield of
    14, 5, 0, 0 across rounds on one PR; stopping at the first zero saved ~2 hours with
    identical content. Our `/refine` and `/santa` have score thresholds but no
    zero-yield stop and no ceiling — this states the stopping rule at the policy layer
    where all tiers see it. Re-reading only the diff since the last verdict keeps
    rounds 2+ cheap and prevents full-branch re-anchoring.

### Step 2: Record the Iron-Law scope asymmetry as an OPEN decision
- **File:** `.ai/DECISIONS.md`
- **Action:** Modify (insert one table row immediately before the `| 20 |` row, `:7`)
- **Description:** Append decision entry **21** at the top of the table, per the file's
  own instruction "Add new entries at the top", using the existing
  `| # | Decision | Context | Alternatives rejected | Consequence |` row format.
- **Details:** The entry is recorded as **OPEN — awaiting owner sign-off**, not as
  decided, per CLAUDE.md "surface open decisions instead of deciding them" and the
  file's own standing process ("Product/surface changes → owner decides"). It carries
  the file:line evidence, two steelmanned options, second-order cost of each, the
  do-nothing outcome, and a recommendation.
- **The two options, steelmanned (summarised in the entry, expanded here):**
  - **Option A — repo-local override: treat `.claude/**` as source in THIS repo only.**
    Strongest case: the Iron Law's whole justification (validated, backed-up,
    rollback-capable, auditable change — decision-log #8) applies *most* to the prompt
    corpus, because prompts are this product's only deliverable and prompt drift is the
    named risk in decision-log #1. It also restores dogfood signal: we would be the
    first users of our own primary gate, which is the only way its ergonomics get
    honestly tested. Second-order cost: every prompt tweak becomes a plan + ops.json +
    execute cycle, which is a real velocity tax on the highest-churn files in the repo,
    and it collides head-on with `ECC_HOOK_PROFILE=minimal` (#17) — the override is
    inert unless maintainers also stop running `minimal`, which is the actual behaviour
    change and the expensive half.
  - **Option B — leave the exemption, accept no dogfooding, document it.** Strongest
    case: the exemption is correct for the 99% case (user projects, where `.md` is
    genuinely not source), and #17 exists precisely because kit developers were blocked
    by the kit's own enforcement. Prompt edits are already covered by git, CI drift
    gates (gen-docs, gen-registry) and review — the Iron Law's benefits are partly
    redundant here. Second-order cost: we ship a gate we do not ourselves run, so its
    failure modes surface in user projects rather than ours, and the "Iron Law" framing
    in CLAUDE.md and README is broader than what is enforced — a honesty-of-claims
    problem, which this repo's own value ordering ranks above token economy and
    convenience.
  - **A third option worth naming (not recommended as primary): narrow the `.md`
    exemption at `:50` so it does not swallow `.claude/agents|commands|skills/**`,
    while leaving `:13` alone.** Cheaper than A, but still inert under `minimal`.
- **What breaks if we do nothing:** nothing breaks mechanically — this is a slow leak,
  not a fault. The concrete costs: (1) no rollback path for a bad prompt edit beyond
  git; (2) no review record for changes to the product itself; (3) zero dogfood signal
  on our primary gate, so ergonomics regressions in the ops engine are found by users;
  (4) a claims-honesty gap between the stated Iron Law and its actual coverage.
- **Recommendation carried in the entry:** Option A scoped narrowly — a repo-local
  source-scope override plus a decision on whether maintainers stop defaulting to
  `minimal` — but recorded as OPEN, because the velocity cost lands entirely on the
  owner and is not ours to spend.

## Testing Strategy
- `python3 scripts/check-context-floor.py --json` → `ok: true`, CLAUDE.md weighted
  = 30,468 (assert < 31,000). This is the load-bearing check for Step 1.
- `python3 scripts/gen-docs.py --check` → pass (no component counts changed, so this
  must be unaffected; a failure means the edit accidentally touched a count).
- `python3 scripts/gen-registry.py --check` → pass (no agent files touched).
- `python3 -m pytest tests/ -q` → zero failures (regression safety net; neither file is
  under test, so any failure is unrelated and must be triaged, not absorbed).
- Manual read of the diff: exactly two inserted lines, no reflow of neighbours, the
  `.ai/DECISIONS.md` row renders as a valid table row with 5 cells.
- No new test is added: both changes are policy/record text with no executable
  behaviour. The mechanical property that *can* regress (context floor) is already
  covered by an existing gate.

## Rollback Plan
- Both operations are single-line insertions. Revert with
  `git checkout -- CLAUDE.md .ai/DECISIONS.md`, or delete the two inserted lines.
- The ops engine's own backup of each edited file provides a second path.
- No state, schema, generated artifact, or downstream consumer depends on either line,
  so rollback is complete and side-effect free.

## Risk Assessment
- **HIGH / OWNER-GATED — `CLAUDE.md` is user-visible.** CLAUDE.md's own "How to work"
  requires owner sign-off for anything user-visible. Step 1 changes the stated working
  policy for every contributor and every pipeline run in this repo. **This plan must
  not be executed until the owner signs off on the review-floor bullet.**
- **Medium — policy/practice divergence.** The floor is prompt-enforced only; nothing
  mechanically counts reviews per PR. If no one honours it, we add a claim we do not
  meet — the exact failure mode Part B complains about. Mitigation: task 010 (eval
  framework) is the right place to make it mechanical; do not overstate it in `docs/`
  until then (CLAUDE.md "Quality gates" already sets that rule).
- **Medium — context-floor proximity.** After this edit CLAUDE.md sits at 30,468 of
  31,000 weighted, leaving only 532 weighted (133 raw) chars. The next CLAUDE.md
  addition will almost certainly need to relocate content into a consuming agent.
  Flag for the coordinator: **other workstreams must not also add to CLAUDE.md
  without re-measuring**, or the last one to land breaks the gate.
- **Medium — the floor is inert for this repo's dominant workflow (reviewer finding).**
  A per-PR floor only fires at a PR boundary, and recent history on
  `perf/token-efficiency` is direct commits (`cbfdcec`, `f783c6e`, `942c86b`,
  `1d62740`, `80e31e9`) with no PR at all. So for most maintainer work today the floor
  changes nothing. This is stated here rather than in the Overview deliberately: the
  honest claim is "closes the gap for PR-based work", not "closes G6". Making it bite
  on direct-commit work would need either a PR-only policy or a per-commit trigger —
  both are behaviour changes beyond this workstream.
- **Owner call, recorded not acted on — fleet-sync marker.** The insertion lands inside
  the `<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v1 START -->` / `END` block (`CLAUDE.md:61`
  and `:72`), which is fleet-synced idempotently to 16 kitted downstream projects with
  "skip if marker present" semantics. Nothing will clobber this edit, but those 16
  copies will silently never receive the review floor unless the marker is bumped to
  v2 — and bumping it changes sync semantics for all 16. That is an owner decision,
  not this workstream's; recorded here only.
- **Low — `.ai/DECISIONS.md`** is maintainer-facing, additive, and explicitly marked
  OPEN; it commits us to nothing.
- **Low — no counts, no hooks, no product templates touched**, so hard rules 4 and 8
  are untouched by construction.

## Dependencies / cross-workstream needs
- **Conflict risk on CLAUDE.md:** this workstream owns the file exclusively. Any other
  workstream that needs a CLAUDE.md line must route it here; two independent
  insertions will both pass validation locally and jointly blow the 524-char headroom.
- **Not ours, but implied:** if the owner later chooses Option A in Part B, the change
  lands in `.claude/hooks/ops-enforcement.sh` and/or `.claude/settings.local.json` —
  both explicitly outside this workstream. No edit to either is planned here.
- **`code-reviewer` agent body:** the floor references it but does not modify it. If a
  parallel workstream edits `code-reviewer.md`, it should keep the REFUTE framing and
  the zero-yield stop consistent with the CLAUDE.md wording landed here.
- **CHANGELOG:** the review floor is user-visible and normally warrants an
  `[Unreleased]` entry, but `CHANGELOG.md` is explicitly not this workstream's file.
  Flag to the coordinator to assign that line elsewhere after sign-off.
