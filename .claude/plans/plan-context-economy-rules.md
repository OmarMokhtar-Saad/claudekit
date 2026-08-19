# Implementation Plan: Context Economy Rules (I6, Workstream 4)

## Overview

Fold read-bounding, output-spill, and script-first rules (adapted from
`chaos-engine/references/context-economy.md` and `script-first.md`, MIT,
ShaftHQ/SHAFT_ENGINE) into the two existing token skills. No new skill is created —
the always-on routing surface is already a tracked cost (BACKLOG P2 / task 009).

## Gap Confirmation (verified by reading both skills)

- `.claude/skills/token-optimization/SKILL.md` covers compression levels 1-3,
  abbreviated output, activation, and exceptions. It says nothing about how much you
  **read**, nothing about spilling oversized tool results, nothing about script-first.
- `.claude/skills/context-budget/SKILL.md` covers static component accounting (agents,
  skills, MCP schemas) and an audit report format. It accounts only for the *floor*
  (loaded components), never the *variable* in-session cost of reads and pasted output.

Confirmed gap: neither skill addresses read-bounding or output spill.

## Context Floor Headroom (measured before planning)

`python3 scripts/check-context-floor.py --json` → `"ok": true`

| Bucket | Current | Budget | Headroom |
|---|---|---|---|
| skill descriptions | 9892 | 14000 | **4108** |
| agent descriptions | 7566 | 10000 | 2434 |
| command descriptions | 3861 | 6000 | 2139 |
| CLAUDE.md | 29264 | 31000 | 1736 |
| pipeline agent bodies | 39144 | 43000 | 3856 |

This plan **reduces** the skill-descriptions bucket by 10 chars (9892 → 9882): the
`token-optimization` frontmatter description goes from 178 to 168 chars. The
`context-budget` description is untouched. All other additions are SKILL.md **bodies**,
which are loaded on demand and cost zero always-on budget.

## Scope

- **In Scope:** `.claude/skills/token-optimization/SKILL.md` (bounded reads, spill,
  script-first, guard clause, attribution, shortened description) and
  `.claude/skills/context-budget/SKILL.md` (one accounting strategy for read/output waste).
- **Out of Scope:** any other skill, any agent, any hook, `.claude/settings.json`,
  `CLAUDE.md`, `CHANGELOG.md`, `docs/`, `skills-registry.json`, component counts.

## Split Rationale

| Concern | Owner | Why |
|---|---|---|
| Bounded reads, narrow-once, no-reread, excerpt-over-dump | token-optimization | behavioral |
| Spill (head/tail + path + one fact), distillate, failure-loop | token-optimization | behavioral |
| Script-first probes | token-optimization | behavioral |
| Guard clause (safety/negation/attribution) | token-optimization | guards the behaviors |
| Measuring read/output waste in an audit | context-budget | accounting |

## Prerequisites

None. Both files exist; all `find` anchors verified unique with `grep -cF` = 1.

## Implementation Steps

### Step 1: Shorten the token-optimization description
- **File:** `.claude/skills/token-optimization/SKILL.md`
- **Action:** Modify (frontmatter)
- **Details:** Replace `code-only responses, and efficient formatting techniques` with
  `bounded reads, and spilling large tool results`. 178 → 168 chars; the routing signal
  now names the new behaviors while shrinking always-on cost.

### Step 2: Add bounded-reads, spill, and script-first sections
- **File:** `.claude/skills/token-optimization/SKILL.md`
- **Action:** Modify (body, inserted before `## Measurement`)
- **Details:** Three new sections. Spill cross-references
  `.claude/agents/_shared/INVOCATION.md` ("paths, never payloads") as authoritative for
  agent handoffs rather than restating it, and cites the measured 80.3M-token burn in
  `.claude/plans/plan-token-waste-workflow-fixes.md` as evidence.

### Step 3: Add the guard clause and attribution
- **File:** `.claude/skills/token-optimization/SKILL.md`
- **Action:** Modify (body, appended after the final Exceptions bullet)
- **Details:** Guard clause verbatim in spirit — **token savings never drop negation,
  safety, or required attribution** — plus the MIT attribution to ShaftHQ/SHAFT_ENGINE.

### Step 4: Add read/output waste accounting
- **File:** `.claude/skills/context-budget/SKILL.md`
- **Action:** Modify (body, inserted before `## Budget Report Format`)
- **Details:** New "Strategy 5: Account for Read and Output Waste" distinguishing the
  static floor from variable in-session cost, and delegating the behavioral fixes to
  `token-optimization` (audit here, change behavior there). Description unchanged.

## Testing Strategy

1. `python3 scripts/check-context-floor.py --json` → `ok: true`, skill descriptions 9882.
2. `python3 -m pytest tests/ -q` → zero failures (frontmatter/skill-shape tests).
3. `python3 scripts/gen-docs.py --check` → no drift (no components added or removed).
4. `ck doctor --strict` → clean.
5. Manual: both SKILL.md files still parse as valid YAML frontmatter + markdown; no
   duplicated INVOCATION.md contract text (`grep -c "paths, never payloads"` stays 1
   per file at most, as a reference not a restatement).

## Rollback Plan

`git checkout -- .claude/skills/token-optimization/SKILL.md .claude/skills/context-budget/SKILL.md`.
Edits are additive body text plus one frontmatter line; no file is created or deleted.

## Risk Assessment

- **Low Risk:** all four edits are text-only, in files owned exclusively by this
  workstream; the context-floor bucket net-decreases; no counts are hand-edited.
- **Medium Risk:** none material. Section ordering in token-optimization shifts
  (`## Measurement` moves later) — anchor-based edits are unaffected, but a parallel
  workstream editing the same file would conflict; per decomposition, none may.
- **High Risk:** none.

## Dependencies / Cross-Workstream Needs

- CHANGELOG `[Unreleased]` entry for these skill changes must be added by whichever
  workstream owns `CHANGELOG.md` — not this one.
- If another workstream adds or lengthens skill descriptions, the shared 14000-char
  budget is the coupling point; this plan releases 10 chars into it.
- If a workstream edits `.claude/agents/_shared/INVOCATION.md` section titles, the
  cross-reference in Step 2 should be re-checked (reference is by file path, so it
  degrades gracefully).
