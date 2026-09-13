# Implementation Plan: Skill Slim Wave 1 (progressive disclosure)

## Overview
`ck skill audit --json` flags 22 kit skills over the body budget (300 lines / 2000 tokens),
55,706 body tokens. This wave slims the six largest. Each SKILL.md keeps its rules, hard
gates and decision tables. Templates, runbook commands, long checklists and background move
**verbatim** into `.claude/skills/<name>/references/*.md`, and SKILL.md says when to read
each one. The frontmatter (including descriptions) stays the same, so the always-on context
floor does not change. `install.sh` did not ship `references/` before, so this plan also
changes it to copy that directory.

Owner approval: token slimming of oversized skills (given to the invoking session).
Tier: **3** (32 ops across 8 configs, >15 ops; touches `install.sh`, which is part of
delivery). The reviewer is required.

## Phase 0: Design precheck
Ownership model: a skill is its **directory**. SKILL.md is the entry point, and
`references/*.md` holds on-demand text that SKILL.md links with a relative markdown link.
These files carry what the skill is worth in practice:
- `install.sh` line 234 (`cp "$skill_dir"*.md`) copies only the top level, so it **dropped
  `references/`**. That was a real design defect, and ops-0 fixes it. No kit skill had a
  subdirectory before this wave, so nothing had noticed.
- The install manifest (`os.walk`), `preserve_assets.py`, `fleet-sync.py`/`fleet-enhance.py`
  and the MANIFEST.in `recursive-include .claude *` all walk recursively, so they already
  cover `references/`.
- `skill_fit.missing_references` resolves relative links from SKILL.md and reports
  `missing referenced file` problems. That makes every pointer a checked link.
- `gen-registry.py`, `gen-docs.py`, `check-context-floor.py` and `gen-agents-mirror.py`
  look only at `SKILL.md` and frontmatter. They are unaffected (all ran green on the
  scratch tree).
- Tests that pin skill content: `tests/test_008_batch2_merges.py` (union fragments for 4
  skills, plus the bare-old-name gate), `tests/test_008_b3c7_harness_fold.py` (the
  context-budget union), `tests/test_behavior_spec.py` (`REFUTE` stays in SKILL.md),
  `tests/test_project_graph.py` (one SKILL.md copy of context-keeper),
  `tests/test_new_skills.py`, `tests/test_skill_fit.py` (corpus has zero broken skills).

Rejection-brief search (`rejections search "skill slim references token"`): 8 matches,
all retro2-* briefs about a stale heldout MANIFEST sha and a duplicated SESSION_ID_SHAPE
literal. No validated match. This plan touches neither.

Project graph: not consulted. The change is to prompt text, install.sh and tests, not
Python imports.

## Scope
- **In scope:** the six SKILL.md files; 20 new reference files; the `install.sh` copy loop;
  the widened content-pin helpers in two tests; the `ck doctor` alias-scan exemption in `src/claudekit/cli/main.py`; a new behavioral test file; a CHANGELOG entry.
- **Out of scope:** the other 16 over-budget skills (later waves); the `.agents/skills/` Codex
  mirror (its gate checks membership only, and its content already differs for 40 files);
  frontmatter/description changes; fixing inconsistencies that already exist in the moved
  text (listed under Risks); SESSION_STATE/CHANGELOG_AI updates (done at the end of the
  work period, not in ops).

## Method (how the content was produced)
All SKILL.md and reference text was **generated from original line ranges** by a builder
script, not retyped. A part is either a verbatim original line range or a short new
connective/summary text. Proofs, run on a scratch copy of this worktree:
1. **Coverage diff:** every non-blank line of each original SKILL.md appears verbatim in
   the new SKILL.md or one of its references. Result: 490/440/452/412/461/336 original
   lines, **0 not covered** for all six.
2. **Replay:** the 8 configs below were run in order through the real
   `validate-config-json.py` and `execute-json-ops.py` on a fresh copy. Result: all
   validated (only the benign "parent directory doesn't exist" warning, since the executor
   creates it) and all executed. The 32 target files are **byte-identical** to the built
   tree.
3. The gates were run on the built tree (see Testing Strategy).

## Implementation Steps

Each config is one step. Apply them in this order. The test-harness changes go first, so
the suite stays green after every config. The budget test goes last, because it needs all
six skills slimmed.

### Step 0: Ship references/ and widen the content pins
Config: `.claude/plans/ops-skill-slim-wave1-0-harness.json` (4 ops)
- **File:** `src/claudekit/cli/main.py`. **Action:** Modify. `_stale_alias_references` (the
  `ck doctor` renamed-asset scan) exempted exactly one file: the replacement's SKILL.md.
  Moving the "merged from X" seam prose into references/ made `ck doctor --strict` WARN
  six times on this repo, and 3 tests in `tests/test_doctor_gate.py` went red (found by
  diffing full-suite failure sets). The exemption now also covers files directly in the
  replacement's own `references/`, and nothing wider. The new test proves that a
  different skill's references/ still warns.
- **File:** `install.sh`. **Action:** Modify. After the `cp "$skill_dir"*.md` line, add a
  bash-3.2-safe block: `if [[ -d "${skill_dir}references" ]]` then `mkdir -p` and
  `cp "${skill_dir}references/"*.md` into `$DEST/skills/$skill_name/references/`.
  Top-level copy semantics are unchanged.
- **File:** `tests/test_008_batch2_merges.py`. **Action:** Modify.
  - Add `_skill_text(skill)`, which returns SKILL.md plus its sorted `references/*.md`.
  - Point the four union tests at `_skill_text`.
  - `_body` stays SKILL.md-only for the tests that need a rule in the always-loaded body:
    allowed-tools, "The cap that", `session-context.md`.
  - `test_no_bare_reference_in_a_live_document` now also allows the survivor's own
    `references/` files. The "Merged from `<old>`" seam prose moved there with its section.
- **File:** `tests/test_008_b3c7_harness_fold.py`. **Action:** Modify. Add `REFERENCES`.
  The union test reads SKILL.md plus the references.

### Step 1: verification-before-completion (PROTECTED)
Config: `.claude/plans/ops-skill-slim-wave1-1-verification.json` (3 ops)
- **Create** `.claude/skills/verification-before-completion/references/gate-and-traps.md`,
  holding the gate diagram, the four rationalization traps and the single-claim report
  template.
- **Create** `.claude/skills/verification-before-completion/references/runbook.md`, holding
  the whole "The Runbook (merged from `verification-loop`)" half: six phases with commands,
  the Verification Loop Report, Continuous Mode, and the PostToolUse hook.
- **Modify** `.claude/skills/verification-before-completion/SKILL.md`.
  - Kept verbatim: the Iron Law, Steps 1-6 including REFUTE and CLAIM, Common Failures,
    Red Flags, and When Verification Is Not Possible.
  - New text: a one-line gate order; a 4-line trap summary that keeps the "run at minimum
    the targeted tests and note the subset" rule; a runbook intro and a phase/pass-criteria
    table; two read-when pointers.
  - Every rule survives in meaning in the body. Only illustrations, templates and
    commands moved.

### Step 2: context-keeper
Config: `.claude/plans/ops-skill-slim-wave1-2-context-keeper.json` (4 ops)
- **Create** `references/save-resume.md` (original lines 11-170),
  `references/structured-state.md` (173-336) and `references/priming.md` (339-490), all
  under `.claude/skills/context-keeper/`.
- **Modify** `.claude/skills/context-keeper/SKILL.md`.
  - New text: a situation table (which half you need, and that no `/prime` command exists).
  - Kept verbatim: the freshness gate; File Location, including that the hook reads
    `session-context.md` when it is under 48h old; the command table; anti-patterns; all
    save and load rules; refresh triggers; performance rules.

### Step 3: incident-response
Config: `.claude/plans/ops-skill-slim-wave1-3-incident-response.json` (7 ops)
- **Create** these files under `.claude/skills/incident-response/references/`:
  `phases.md`, `severity.md`, `communication.md` (comms templates, the provenance comment,
  roles, war room), `rollback.md`, `postmortem.md` (rules and template), `runbooks.md`.
- **Modify** `.claude/skills/incident-response/SKILL.md`.
  - New text: a phase goal/output table and a severity-at-a-glance table.
  - Kept verbatim: mitigation options and rules, postmortem timeline, database rollback
    rules, post-mortem rules, war-room rules of engagement, escalation triggers, integration.

### Step 4: autonomous-loop
Config: `.claude/plans/ops-skill-slim-wave1-4-autonomous-loop.json` (4 ops)
- **Create** these files under `.claude/skills/autonomous-loop/references/`:
  `pipeline-phases.md` (phase detail, diagram, iteration/completion reports),
  `loop-design.md` (architecture, convergence, three patterns) and `safety-guards.md`
  (guard code, state tracking, report, anti-patterns).
- **Modify** `.claude/skills/autonomous-loop/SKILL.md`.
  - Kept verbatim: exit conditions, all safety controls (limits, rate limiting, circuit
    breaker, rollback), integration, use/do-not-use, and the reconciled iteration budget
    ("The cap that binds ... unless the invoker raises it").
  - New text: a mandatory convergence and guards paragraph.

### Step 5: context-budget
Config: `.claude/plans/ops-skill-slim-wave1-5-context-budget.json` (4 ops)
- **Create** `.claude/skills/context-budget/references/audit.md`,
  `.claude/skills/context-budget/references/budget-report.md` and
  `.claude/skills/context-budget/references/harness-optimization.md`.
- **Modify** `.claude/skills/context-budget/SKILL.md`.
  - Kept verbatim: token rules of thumb, when-to-run, the harness constraint sentence, the
    apply-changes rules with the backup command, and Constraints.
  - New text: a 5-step audit summary and a harness workflow summary.

### Step 6: supply-chain-audit
Config: `.claude/plans/ops-skill-slim-wave1-6-supply-chain-audit.json` (4 ops)
- **Create** `.claude/skills/supply-chain-audit/references/tree-and-typosquatting.md`,
  `.claude/skills/supply-chain-audit/references/cve-and-lockfile.md` and
  `.claude/skills/supply-chain-audit/references/upgrade-lifecycle.md`.
- **Modify** `.claude/skills/supply-chain-audit/SKILL.md`.
  - Kept verbatim: both core principles, the severity action matrix, the recommended
    actions summary, the golden rule, and anti-patterns.
  - New text: a 6-step audit summary and a CVE-reachability/semver paragraph.

### Step 7: Behavioral test and CHANGELOG
Config: `.claude/plans/ops-skill-slim-wave1-7-test-changelog.json` (2 ops)
- **Create** `tests/test_skill_references.py`. It checks that:
  - every `references/*.md` is linked from its SKILL.md;
  - the real `ck skill audit --json` reports no problems for skills with references and no
    over-budget wave-1 skill;
  - a real `install.sh --full` copies every reference byte-identical and records it in
    `.claudekit-manifest.json`.
  It forces `ECC_HOOK_PROFILE=minimal`.
- **Modify** `CHANGELOG.md`: add an `[Unreleased]` entry (user-visible: token savings and
  the installer fix).

## Measured before/after (`ck skill audit --json`, scratch copy)

| Skill | Lines before | Tokens before | Lines after | Tokens after | Refs |
|---|---|---|---|---|---|
| context-keeper | 485 | 3918 | 90 | 983 | 3 |
| incident-response | 435 | 3194 | 105 | 1225 | 6 |
| autonomous-loop | 448 | 3016 | 113 | 1125 | 3 |
| context-budget | 407 | 2994 | 77 | 851 | 3 |
| verification-before-completion | 456 | 2966 | 146 | 1347 | 2 |
| supply-chain-audit | 330 | 2845 | 75 | 957 | 3 |
| **Six skills** | **2561** | **18933** | **606** | **6488** | **20** |

Delta: -12,445 SKILL.md body tokens (-65.7%). Kit-wide over-budget: 22 skills / 55,706
tokens -> 16 skills / 36,773 tokens. `verification-before-completion` is 47 tokens over the
1,300 target, but well inside the 2,000 budget. This is deliberate: every discipline rule
of the protected skill stays in the body.

## Testing Strategy
Run on the scratch tree (built tree == replayed tree):
- `ruff check` on the three touched test files: pass.
- `gen-docs.py --check`, `gen-registry.py --check`, `gen-model-policy.py --check`,
  `check-context-floor.py --check`, `gen-agents-mirror.py --check`, `shellcheck install.sh`:
  all OK.
- Targeted pytest (merges, b3c7, behavior_spec, new_skills, project_graph, skill_fit,
  install, and the new file): 502 passed. That run exposed 5 failures in
  `test_no_bare_reference_in_a_live_document`, which Step 0's seam allowance fixes.
- Full `pytest tests/`: a pristine unmodified copy and the slimmed copy were run side by
  side in the same scratch location. The failures present in both come from the
  environment: the copy has no `.git`, and a `/private/tmp` path breaks the hook-scope,
  git-baseline and plan-index tests. The gate is **no failure unique to the slimmed
  tree**. The first comparison found 3 unique failures (doctor strict), and the
  `main.py` change fixes them. The final comparison is reported in the handoff.
- Mutation proofs:
  - The new test file fails 4/4 on the pristine tree.
  - The install test fails with "install dropped skills/autonomous-loop/references/..."
    when the slimmed skills are paired with the old `install.sh`.
- `ruff` and `mypy` on `src/claudekit/cli/main.py`: clean.

After execution, the implementer runs the same commands in the worktree, plus
`python3 scripts/check-plan-artifacts.py --check` and `mypy` (no Python in `src/` changes).

## Rollback Plan
- Every change is in git-tracked files or new files. `git checkout -- <paths>` restores the
  modified files (install.sh, CHANGELOG.md, two tests, six SKILL.md). Delete the new
  `references/` directories and `tests/test_skill_references.py`.
- The executor backs up each config's `code_edit` targets under its backup dir, so a
  per-config restore is possible.
- Partial application: configs 1-6 are independent of each other. Step 0 is safe on its
  own. Step 7's budget test fails until 1-6 are all applied, so roll back 7 first.

## Risk Assessment
- **Low:** content loss. The coverage diff and byte-identical replay rule it out
  mechanically. Frontmatter is the same, so there is no context-floor, registry or routing
  change.
- **Medium: summary text is new prose.**
  - The new connective tables and paragraphs (phase tables, severity-at-a-glance, audit
    summaries, the runbook pass-criteria table) paraphrase the moved originals.
  - The reviewer should check each against the verbatim original in its reference.
  - The rules themselves were copied verbatim, not paraphrased.
- **Medium: test semantics widened.**
  - The union pins now accept a fragment in `references/`, where before only SKILL.md
    counted.
  - `_body` (SKILL.md-only) still guards the rules that must stay always-loaded.
  - The new test adds a link/orphan check and an install check.
- **Medium: moved text keeps now-stale position words.**
  - For example: "the Quality-Improve pattern below" (autonomous-loop SKILL.md), "See
    Postmortem Template below" (incident references/phases.md), and "Use the `### Status
    Update` template above" (references/communication.md).
  - They were kept verbatim because the coverage proof and the union pins require it.
    They are harmless but imprecise.
- **Medium: installed projects get `references/` only on reinstall/`ck update`** with the
  fixed install.sh. A project that syncs only SKILL.md would point at missing files.
  `fleet-sync.py` walks recursively, so fleet syncs carry them.
- **Low: the `.agents/skills/` Codex mirror** still holds the full pre-slim SKILL.md. Its
  gate checks membership only, so it stays green but diverges in content.
- **Existing inconsistencies preserved, not fixed:**
  - supply-chain-audit: High CVE is "48 hours" in the CVSS matrix but "Within 1 week" in
    triage.
  - context-budget: lines x 15 vs lines x 1.3 token estimates.
  - verification runbook: `[ -f ".eslintrc*" ]` never globs.
- **Hub/boundary:** `install.sh` is part of delivery. The edit adds a guarded copy and
  changes nothing else (shellcheck clean).
