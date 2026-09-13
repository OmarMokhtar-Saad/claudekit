# Implementation Plan: `action-first` behavioral mode

Tier 2 (multi-file; no security/schema/architecture surface). Branch `feat/action-first-mode`.
Ops config: `.claude/plans/ops-action-first-mode.json` (5 ops, 1 phase). User-approved.

## Overview

Add an eighth behavioral mode, `action-first`, that puts the answer or next action on the
first line, keeps steps and lists short, and never trims safety output. Concept inspired by
the MIT-licensed skill ayghri/i-have-adhd; all wording is original, credited in one line.

## Phase 0: Design precheck

Modes are standalone prompt files in `.claude/modes/`, selected by `/mode`
(`.claude/commands/mode.md`). No generator counts modes; they are guarded by name in
`tests/test_modes.py` and `tests/test_structure.py`. The value lives entirely in the new
mode file plus those two name lists and the command table -- all covered by this plan.
Rejection-brief search: not run (planner Bash scoped); no known prior rejection for modes.

## Scope

- **In scope:** new mode file, `/mode` table + example, test name lists and a behavioral
  rule-presence test, CHANGELOG entry.
- **Out of scope:** installer changes (install.sh copies `.claude/modes/` wholesale),
  docs counts (modes are not generator-counted), fleet sync.

## Implementation Steps

### Step 1: Create the mode file
- **File:** `.claude/modes/action-first.md` -- Create
- Frontmatter `name: action-first`, `description:`; sections Purpose, Rules (10), Do this /
  Not this, Response Patterns (Question, Task done, Blocked, Multi-step instructions),
  Session Behavior. One-line credit to ayghri/i-have-adhd (MIT).

### Step 2: Register in the /mode command
- **File:** `.claude/commands/mode.md` -- Modify
- Add table row after `token-efficient`; add `/mode action-first` example line.

### Step 3: Test name list + behavioral rule test
- **File:** `tests/test_modes.py` -- Modify
- Add `"action-first"` to `EXPECTED_MODES`; docstring "7" -> "8"; count floor 7 -> 8.
- New `TestActionFirstRules` class: parametrized over key phrases for each rule (answer
  first, one action per step, no tangents, Done/Now/Next, time estimates, wins, cap of 5 /
  `N more`, no preamble/recap/closers, bold one thing, never drop error output / security
  warnings / destructive-action confirmations), plus the four Response Patterns and the
  Do this / Not this example. Deleting any rule fails a test.

### Step 4: Structure test name set
- **File:** `tests/test_structure.py` -- Modify; add `"action-first"` to `EXPECTED_MODES`.

### Step 5: CHANGELOG
- **File:** `CHANGELOG.md` -- Modify; bullet at top of `## [Unreleased]`.

## Testing Strategy

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-action-first-mode.json
python3 scripts/check-plan-artifacts.py --check
python3 -m pytest tests/test_modes.py tests/test_structure.py -q
python3 -m pytest tests/ -q
ruff check tests/
python3 scripts/gen-docs.py --check
```
Mutation proof: delete the "Lists capped at 5" rule line locally -> `TestActionFirstRules` fails.

## Rollback Plan

`git checkout -- .claude/commands/mode.md tests/test_modes.py tests/test_structure.py CHANGELOG.md`
and `rm .claude/modes/action-first.md`; or the executor's backup restore.

## Risk Assessment

- **Low:** additive prompt file and test additions; no hub files beyond tests.
- **Medium:** `add_after` is literal concatenation -- payloads carry their own leading newline.
- **High:** none.
