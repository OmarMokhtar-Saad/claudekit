# Implementation Plan: agent-token-caps

## Overview
Subagent cost is `turns x context`. Measured on 2026-09-16 transcripts, one planner burned
6.0M cache-read tokens over 87 turns while consuming only ~102 KB of tool results, and every
subagent starts at ~21-23k tokens before doing any work. This plan attacks both multipliers in
prompt-space only: a hard turn ceiling plus a one-Write output discipline for `planner.md` and
`reviewer.md`, and a move of reference-grade prose out of those two always-injected files into
on-demand `_shared/*-reference.md` companions.

## Phase 0: Design Precheck

**Ownership model.** The fixed cost of a subagent run is exactly: CLAUDE.md (7.8 KB) + the
agent file + the host-controlled skill/MCP listings. `.claude/agents/_shared/INVOCATION.md`
(15.6 KB) is **referenced, not injected**: `grep -n INVOCATION .claude/agents/planner.md`
returns two prose mentions (lines 207, 211) that name a path for on-demand reading; nothing
concatenates it into the subagent system prompt. **Therefore INVOCATION.md is left alone** —
splitting it would cut nothing. The value of this change sits in exactly two files,
`.claude/agents/planner.md` (13,644 B) and `.claude/agents/reviewer.md` (17,910 B), plus the
per-turn multiplier, which lives in the instruction text of those same two files. The model and
the value-carrying files coincide; no design defect.

**Prior searches.** `review-record.py rejections search` and `knowledge-ledger.py search` were
NOT run for this plan (caller capped discovery at 20 batched calls and supplied the measured
findings directly). Treated as `UNVERIFIED:` in Risk Assessment — silence is not evidence.

**Gate survey (what pins these files).**
- `scripts/gen-model-policy.py --check` — gates **frontmatter only** (role/tier). No frontmatter
  line is touched by this plan.
- `scripts/check-context-floor.py` — measures frontmatter *descriptions*, skill/command
  descriptions and CLAUDE.md, not agent bodies. Unaffected (and only improves).
- `.claude/lint-baseline.json` — `command_lines` only; it ratchets `.claude/commands/*.md`.
  Agent files are **not** in the baseline. Unaffected.
- `tests/test_agent_doc_ops_examples.py` — `MIN_EXAMPLES[".claude/agents/planner.md"] = 1`:
  planner.md must keep at least one valid ops.json fence. The Phase 3 fence is **kept**; only
  the prose bullets under it move.
- `tests/test_behavior_spec.py` — asserts `"Headless fallback" in planner.md`; planner
  frontmatter `tools` contains `Write` and not `Agent`; reviewer.md contains `"Refute"` and
  `"CRITICAL"`, contains `"orchestrated by the command layer"`, and does NOT contain
  `"Spawn two independent sub-reviewers"`.
- `tests/test_single_source_contracts.py` — reviewer.md must contain `"HANDOFF_PROTOCOL.md"`
  and must NOT contain `"REVISE = score < 70"` / `"CONDITIONAL = score 70-89 OR"` or any
  score-band restatement.
- `tests/test_rejection_briefs.py` — planner.md Phase 0 branches on `rejections search` exit
  codes; that Phase 0 text is **not** moved.
- `tests/test_cli*.py`, `test_adapt.py`, `test_doctor_gate.py`, `test_ops_enforcement_scope.py`
  use planner.md/reviewer.md only as arbitrary manifest paths — content-agnostic.

Every one of those pinned phrases stays in the agent file it is asserted against; the new test
(Step 6) re-pins them mechanically so a future move cannot quietly break them.

## Scope
- **In Scope:** `.claude/agents/planner.md`, `.claude/agents/reviewer.md`, two new
  `.claude/agents/_shared/*-reference.md` files, one new behavioral test, CHANGELOG.
- **Out of Scope:** `INVOCATION.md` (not injected — see Phase 0), the host-controlled skill
  listing and MCP schemas, CLAUDE.md (owned by a concurrent planner), `.claude/settings.json`,
  `.claude/hooks/*`, `.claude/commands/implement.md`, `.ai/REVIEW_GUIDE.md`, any other agent.
- **Out of Scope:** `docs/`. `grep -n "planner\|reviewer" docs/*.md` finds only inventory rows
  (file name, colour, tools) in `docs/AGENTS.md` and `docs/ARCHITECTURE.md`, plus a
  `docs/CUSTOMIZATION.md` line pointing at reviewer.md's scoring formula. The `## Scoring
  Formula` heading and the weight line stay in reviewer.md, so that pointer stays true. No
  docs edit is required; generated counts do not change (no asset added to a counted class —
  `_shared/` files are not agents).

## Prerequisites
- None. All targets exist; no dependency, schema or security surface is touched.

## Implementation Steps

### Step 1: Create the planner reference companion
- **File:** `.claude/agents/_shared/planner-reference.md`
- **Action:** Create
- **Description:** Holds, verbatim, the reference-grade prose moved out of planner.md: the
  plan.md document skeleton, the ops.json hard-rules bullets, the three tiered briefing
  templates, the reviewer handoff block, the Operations Config Rules list, the revision
  protocol, the self-review checklist and the coordinator output block.
- **Details:** Move, not rewrite — every rule is preserved byte-for-byte.
- **Done when:** the file exists and `grep -c "GUARD 26"` returns 1. (~2 min)

### Step 2: Create the reviewer reference companion
- **File:** `.claude/agents/_shared/reviewer-reference.md`
- **Action:** Create
- **Description:** Holds the three scoring criteria tables, the four validation-step
  checklists, the human-facing REVIEW REPORT template + progress-bar spec, the three handoff
  templates, the Review Principles and the Anti-Patterns list.
- **Details:** The machine-readable `=== REVIEW ===` verdict block **stays in reviewer.md** —
  it is the parser contract for `review-record.py --from-review` and must never require a
  second Read to emit.
- **Done when:** the file exists and contains `NEVER approve a plan without ops.json`. (~2 min)

### Step 3: planner.md — turn ceiling and output discipline
- **File:** `.claude/agents/planner.md`
- **Action:** Modify
- **Description:** Extend (do **not** duplicate) yesterday's Discovery budget block. Adds a
  hard ceiling of 30 tool calls for the whole run, a no-re-read rule, and an emission rule:
  compose in memory, emit plan.md and ops.json in at most two Write calls, never draft via
  Bash heredocs or scratchpad files.
- **Details:** anchored on the existing `- Cap: ~25 tool calls ...` bullet, which is kept and
  followed by the new bullets.
- **Done when:** `grep -c "no Bash heredoc drafts" planner.md` returns 1. (~3 min)

### Step 4: planner.md — move reference prose out
- **File:** `.claude/agents/planner.md`
- **Action:** Modify
- **Description:** Four replacements swap moved blocks for one-line pointers:
  (a) plan.md skeleton, (b) ops.json hard-rules bullets, (c) `## Tiered Briefing Format`
  through the end of `## Operations Config Rules`, (d) `## Handling Revision Feedback`
  through end of file.
- **Details:** Each pointer names `.claude/agents/_shared/planner-reference.md` and says when
  to Read it (once, before writing the artifacts). The Phase 3 ops.json JSON fence and the
  Phase 4 `Headless fallback` paragraph are untouched.
- **Done when:** `wc -c planner.md` < 10000 (simulated post-state: 9779, from 13644, -28.3%). (~6 min)

### Step 5: reviewer.md — discipline + move reference prose out
- **File:** `.claude/agents/reviewer.md`
- **Action:** Modify
- **Description:** Inserts an `## Output & Turn Discipline` section (ceiling ~20 tool calls,
  one Write for the report, no re-reads, no scratchpads) before `## Refute Before You Score`,
  then four replacements move: the scoring criteria tables + Validation Steps, the human
  REVIEW REPORT template + Progress Bars, and Handoff Formats + Review Principles +
  Anti-Patterns.
- **Details:** `## Scoring Formula` heading, the weight line, `## Decision Logic` with its
  `HANDOFF_PROTOCOL.md` pointer, the `=== REVIEW ===` block and its parser rules all stay.
- **Done when:** `wc -c reviewer.md` < 12400 (simulated post-state: 12135, from 17910, -32.2%)
  and `grep -c "=== REVIEW ===" reviewer.md` >= 1. (~8 min)

### Step 6: Behavioral ratchet test
- **File:** `tests/test_agent_prompt_size.py`
- **Action:** Create
- **Description:** Pins (1) byte ceilings for planner.md and reviewer.md, (2) existence and
  non-triviality of both reference files, (3) that each agent file names its companion, and
  (4) that every moved rule still exists *somewhere* (agent file or its companion) and every
  gate-pinned phrase still exists in the agent file itself.
- **Details:** The ceilings sit ~400 B above the expected post-state, so re-adding a moved
  block fails the test — that is the positive control. Docstring records how to prove it.
- **Done when:** `python3 -m pytest tests/test_agent_prompt_size.py -q` passes. (~5 min)

### Step 7: CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Description:** One `[Unreleased]` bullet describing the caps and the split.
- **Done when:** the bullet is the first entry under `## [Unreleased]`. (~1 min)

## Testing Strategy
- New `tests/test_agent_prompt_size.py` (Step 6) — the behavioral ratchet.
- Regression sweep, all must stay green:
  `python3 -m pytest tests/test_behavior_spec.py tests/test_single_source_contracts.py
  tests/test_agent_doc_ops_examples.py tests/test_rejection_briefs.py tests/test_context_floor.py -q`
  then the full `python3 -m pytest tests/ -q`.
- Gates: `python3 scripts/gen-model-policy.py --check`, `python3 scripts/check-context-floor.py
  --check`, `python3 scripts/gen-docs.py --check`, `python3 scripts/check-plan-artifacts.py
  --check`, `ruff check`.
- Positive control for the ratchet: append 1 KB of filler to planner.md and confirm
  `test_agent_prompt_size.py` FAILS before trusting the green run. A ceiling that cannot fail
  measures nothing.
- Prompt-behaviour control (manual, cheap): run one Tier-2 plan through the slimmed planner
  and confirm the brief still contains the tier template and the `HANDOFF TO: reviewer` block
  — i.e. the pointer is actually followed.

## Rollback Plan
- `git checkout -- .claude/agents/planner.md .claude/agents/reviewer.md CHANGELOG.md`
- `rm .claude/agents/_shared/planner-reference.md .claude/agents/_shared/reviewer-reference.md
  tests/test_agent_prompt_size.py`
- No generated artifact, manifest hash or install-time state depends on the new files; the
  fleet manifest is regenerated on release, not here.

## Risk Assessment
- **Low Risk:** CHANGELOG entry; the new test; the reference file creations (additive).
- **Low Risk:** context-floor / model-policy / lint-baseline gates — none of them measures an
  agent body (verified above), so this plan cannot move their numbers.
- **Medium Risk:** *Pointer compliance.* Moved rules only bind if the agent actually Reads the
  companion. Mitigation: every pointer is imperative ("Read ... once, before you write"), and
  the companion is a single Read (~5-6 KB) replacing 5-8 KB of always-paid prompt — net win
  even when it is always read. If a downstream review finds the reviewer skipping its
  companion, the cheap fix is to pull the Anti-Patterns list back inline.
- **Medium Risk:** *Anchor fidelity.* Four of the edits use multi-KB `find` strings copied from
  `sed -n` output. A transcription error fails loudly at execution (the engine cannot find the
  anchor) — it cannot half-apply.
- **Medium Risk:** *Concurrent planners.* Two other planners own `.claude/settings.json`,
  `.claude/hooks/*`, `CLAUDE.md`, `.claude/commands/implement.md`, `.ai/REVIEW_GUIDE.md`. This
  ops.json touches none of them; the only shared file is `CHANGELOG.md`, where an `add_after`
  on `## [Unreleased]` is order-tolerant but will conflict if another plan anchors on the same
  literal line in the same execution window. Execute CHANGELOG-touching plans serially.
- **High Risk:** none. No code, no security surface, no schema, no deletion op.
- `UNVERIFIED:` the two mandatory prior searches (rejections / knowledge-ledger) were not run
  under the caller's discovery cap. A prior rejection about slimming agent prompts, if one
  exists, is unexamined.
- **Measured (not estimated):** every edit was applied in a simulation before this plan was
  handed off. planner.md 13,644 -> 9,779 B (**-28.3%**); reviewer.md 17,910 -> 12,135 B
  (**-32.2%**). Each `find` string is unique (`count == 1`) and the real validator reports
  `All find patterns exist in files`. planner.md misses the >=30% target by 1.7 points because
  the new turn-ceiling and output-discipline text is added to the same file; the gross prose
  moved out of planner.md is 5,398 B (39.6% of the original). Raising the target would require
  moving Phase 0/Phase 1 discipline text, which is exactly the instruction this plan exists to
  strengthen. Ceilings are set ~250 B above the measured post-state.
