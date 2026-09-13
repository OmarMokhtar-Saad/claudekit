# Implementation Plan: Action-First Rollout

## Overview
Apply the style in `.claude/modes/action-first.md` (commit 5896e9f) to four surfaces:
agent reports, session handoff templates, plan templates, and `ck doctor` output. Additive
only: no machine-parsed block is removed, renamed or reordered.

## Phase 0: Design Precheck
Ownership model: each surface's text lives in exactly one source file. `.agents/skills/` is
a membership-only mirror (`scripts/gen-agents-mirror.py` checks directory names, not
content), so no mirror edit is needed. `scripts/gen-registry.py` reads only agent `## Skill
Loading` sections, which this plan does not touch. Parsers checked by grep across
`scripts/`, `.claude/operations/scripts/`, `src/`, `tests/`, `.claude/hooks/`: `=== REVIEW ===`
(review-record.py uses the LAST block, anywhere in the text), `RESULT-JSON` (executor
stdout), `Readiness:` (tests match `startswith`/regex), `Saved:` (resume-session greps
`head -5`). No parser reads `PLANNER COMPLETE`, `VERIFICATION REPORT`, `CODE REVIEW
REPORT`, `BUG DIAGNOSIS REPORT`, or the session-context section headings.

Rejection-brief search (`action-first doctor template agent report`): 2 matches
(agent-memory-learning, e2e-lane-a), both matched only on the word "agent". Neither
concerns report templates or doctor output. Validated as non-matching; what this plan does
differently from their defects: every budget number below was measured on a simulated
post-state, not asserted.

## Scope
- **In Scope:** the four agents named by the owner, context-keeper, save-session,
  resume-session, writing-plans, planner plan template, `ck doctor`, docs/cli.md, CHANGELOG.
- **Out of Scope:** hook messages (blocking-hook stderr contract); `.claude/commands/code-review.md`
  (its own inline report template; not one of the named agents); `.claude/agents/_shared/OUTPUT_TEMPLATE.md`;
  `.claude/commands/checkpoint.md` (git checkpoints, not a handoff); `.claude/agents/HANDOFF_PROTOCOL.md`
  (agent-to-agent, parsed decision taxonomy). No session HANDOFF template ships in `templates/`.

## Budgets (measured on a scratch copy with all four configs applied)
| Gate | Before | After | Limit |
|---|---|---|---|
| pipeline agent bodies (planner+reviewer+implementer chars) | 42983 | 42948 | 43000 |
| save-session.md lines (command-budget ratchet) | 108 | 108 | 108 |
| resume-session.md lines | 108 | 108 | 108 |
| `ck lint .` | clean | clean | - |

planner.md is the tight one (17 chars headroom). Each config touching it is net-negative on
its own, so execution order between ops-af-agents and ops-af-plans does not matter.

## Implementation Phases

### Phase A: Agent reports (~10 min) — `.claude/plans/ops-af-agents.json`, 4 ops
- `.claude/agents/planner.md`: `Next action:` line before `PLANNER COMPLETE`; two checklist
  lines merged into one (budget offset). No findings list exists, so no cap.
- `.claude/agents/verifier.md`: `Next action:` + `Top findings: <at most 5>; "N more" below`
  before `VERIFICATION REPORT`. Full ISSUES list, scores and HANDOFF blocks unchanged.
- `.claude/agents/code-reviewer.md`: same two lines before `CODE REVIEW REPORT`; the silent-failure
  "Highest-Risk Files" list capped at 5. `VERDICT:` line, `=== REVIEW ===` block and its
  `- [CRITICAL]` lines unchanged and uncapped (the rejection store reads them).
- `.claude/agents/debugger.md`: `Next action:` before `BUG DIAGNOSIS REPORT`. No findings summary, so no cap.
- **Done when:** `ck lint .` clean and `check-context-floor.py --check` OK.

### Phase B: Handoff / session state (~5 min) — `.claude/plans/ops-af-handoff.json`, 3 ops
- `.claude/skills/context-keeper/SKILL.md`: `Done: / Now: / Next:` lines after `**Task:**` in the
  Required Fields template; state line before `CONTEXT RESUMED` in the resume summary.
- `.claude/commands/save-session.md`: template becomes Saved / Project + Status / Task / Done / Now /
  Next, before history. `## Current Status` folds into the Project line: same 5-line span,
  so the 108-line ratchet holds. `**Saved:**` stays on line 2 (resume greps `head -5`).
- `.claude/commands/resume-session.md`: state line replaces the `===` underline under `CONTEXT RESUMED`.
- **Done when:** both commands still measure 108 lines; `tests/test_008_batch2_merges.py` green.

### Phase C: Plans (~5 min) — `.claude/plans/ops-af-plans.json`, 2 ops
- `.claude/skills/writing-plans/SKILL.md`: Task List item names phases with `(~N min)` and `Done when:`;
  a Done-When criterion row; the good example uses `Done when:`; each of the three
  templates ends with a `Done when:` line with an estimate; checklist item added.
- `.claude/agents/planner.md`: step template gains `- **Done when:** <observable check> (~<N> min)`;
  removes one filler sentence and merges two revision-feedback steps (budget offset).
- **Done when:** pipeline agent bodies <= 43000.

### Phase D: `ck doctor` verdict (~20 min) — `.claude/plans/ops-af-doctor.json`, 4 ops (revision 2)
Revised after reviewer REJECTED revision 1 (83/100). Revision 1 buffered output and scraped
backticks out of hint prose. Revision 2 does neither. Phases A-C are already applied; finds
are re-anchored against the current `main.py` (all 11 unique).
- `src/claudekit/cli/main.py`:
  - `cmd_doctor(args) -> int` is a 3-line wrapper. The old body is renamed
    `_doctor_checks(args, tally)`, logic unchanged, and it still streams live.
  - The wrapper then prints one verdict line as the LAST stdout line.
  - No buffering. Existing lines, streams and exit codes are unchanged.
- `check()` gains an optional `fix_cmd=None`. It records the first failure's and the first
  warning's `fix_cmd` (`None` when that check declared none).
- Explicit `fix_cmd` sites, each for one unconditional command only:
  - `.claude/ directory exists` -> `ck init`
  - hook not executable -> `chmod +x {hook_path}`
  - wired hooks missing -> `ck update`
  - hook helpers missing -> `ck update`
  - shellcheck warning -> `_SHELLCHECK_INSTALL.get(sys.platform)`: `brew install shellcheck`
    on darwin, `apt-get install shellcheck` on linux, none elsewhere
- Deliberately NO `fix_cmd`:
  - version drift: conditional (older project vs stale package)
  - agent memory: backticks there are `memory: project`, not a command
  - Python/Bash/Git absent, count mismatches, invalid JSON: no single command
- Verdict forms:
  - `FAIL N/M failed — next: run `<cmd>`` (the first failing check's fix_cmd), else
    `... next: fix the first [✗] line above`
  - `FAIL score S/100 below --min-score F — next: ...`
  - `WARN N/M warned — next: ...`, printed as `FAIL` when `--strict` exits 1
  - `PASS N/M passed — next: nothing`
- `tests/test_doctor_verdict.py` (new):
  - Behavioral: `ck doctor` in an empty `tmp_path` exits 1, the header is still the first
    non-blank line, and the last line is `FAIL ... next: run `ck init``.
  - Behavioral: `--min-score 101` in `tmp_path` ends with FAIL, and the error text is on
    stderr only.
  - Regression: parses `main.py` with `ast`. Every `fix_cmd=` literal (or f-string head)
    starts with a known runnable (`ck `, `bash `, `brew `, `apt-get `, `python3 `, `pip `,
    `chmod `, `git `). Any other expression form fails, except `_SHELLCHECK_INSTALL.get`,
    whose values are checked the same way. The drift and agent-memory calls must carry no
    `fix_cmd`.
  - Unit tests for the verdict function.
- `docs/cli.md`: documents the closing verdict line. `CHANGELOG.md`: one `[Unreleased]` bullet covering all four phases.
- **Done when:** full suite, ruff, mypy pass.

## Testing Strategy
Run the CLAUDE.md DoD command block.
- A-C (simulated before execution): lint, context-floor and registry OK; 290 + related tests passed.
- D revision 2, on a scratch copy of the current tree with `ops-af-doctor.json` applied:
  - ruff: clean. mypy: `Success`, no notes.
  - 128 passed: `tests/test_doctor_verdict.py`, `test_doctor_score.py`, `test_cli.py`,
    `test_doctor_gate.py`, `test_eject.py`, `test_doctor_alias_scope.py`,
    `test_hook_delivery.py`, `test_gate_scope.py`.
  - Real run ends with `PASS 27/27 passed — next: nothing`.

## Rollback Plan
Each config is on its own concern. Use the executor backups, or `git checkout -- <paths>` for
the paths listed above, and `rm tests/test_doctor_verdict.py`.

## Risk Assessment
- **Low:** prompt-template additions (A-C). No parser reads the touched headers.
- **Medium:** planner.md sits 52 chars under the pipeline budget after this change, so any
  later planner edit must trim. The approval gate keys on the ops filename slug first
  (`af-agents` etc.), then `plan` = `action-first-rollout`. Record the review verdict under the slug the executor resolves.
- **High (route to reviewer):** Phase D changes PUBLIC CLI output. The new LAST stdout
  line breaks any script that reads the final line expecting the old closing text. The
  old closing messages (`All checks passed!` etc.) stay the last line of the report
  itself. Only `readiness(...)`/`startswith` consumers exist in tests; CI and install.sh
  only run doctor. Fleet consumers are unknown. A new check that forgets `fix_cmd` just
  degrades to the "line above" pointer. A prose `fix_cmd` fails the ast test.
