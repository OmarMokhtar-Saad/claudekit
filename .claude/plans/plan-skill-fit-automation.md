# Implementation Plan: Skill-Fit Automation

## Overview
The owner approved automating the skill-fit loop (PR #42) so nobody runs it by hand. This
plan adds one non-blocking, rate-limited Stop hook that refreshes `ck skill audit --save`
and `ck skill card --publish`. It also adds a `ck doctor` line that is information only, and
documents how to schedule a weekly fleet refresh without shipping a scheduler.

**Tier 2.** Multi-file. The only security surface is a new hook. It is advisory, can never
exit 2, and adds no public API or schema. Reviewer is optional under the tier table. It is
recommended because the change touches the hook registry and the profile-guard declaration.

## Phase 0: Design precheck
Ownership model: the project owns `.claude/reports/skills/` (the audit report and the new
rate-limit stamp, which are local state). The user owns the card registry
(`~/.claudekit/registry/cards/`, or `$CLAUDEKIT_REGISTRY`). The kit owns the hook, its
settings.json wiring, its dispatch-registry row, and its profile declaration. These files
carry that model: `.claude/hooks/skill-fit-refresh.sh`, `.claude/settings.json`,
`.claude/hooks/dispatch-registry.json`, `src/claudekit/profiles.py` (GUARDED_HOOKS) and
`.claude/profiles/minimal/profile.json`. Downstream, `install.sh` already ignores
`.claude/reports/`. This repo does not, so `.gitignore` gains `.claude/reports/skills/`.
`.claude/state/` was rejected for the stamp because install.sh does not ignore it downstream.

Rejection-brief search (`rejections search "hook background skill session"`, exit 0) found
14 matches. Two apply:
- **agent-memory-learning**: the hook count drifted through gen-docs helper classification.
  This plan's hook is a standalone `.sh` that no other hook sources. The measured count goes
  from 27 to 28 after `gen-docs.py`.
- **fleet-skill-phaseA**: a test asserted registry rows that no op produced. Here every
  asserted artifact is produced at test time by executing the hook in tmp_path. No test
  asserts a generated file that an op does not write.

## Approach chosen (and rejected alternatives)
- **Stop hook, not SessionEnd.** Every existing background hook (cost-tracker,
  desktop-notify, format-typecheck) is on Stop, and `dispatch-registry.json` has no SessionEnd
  event. Adding a new event would widen the registry/test surface for no gain. Stop fires per
  turn, so the hook limits itself to one run per 24h.
- **A new hook, not a fold-in to cost-tracker.sh.** Folding in would avoid a hook-count
  change, but cost-tracker is deliberately profile-independent (`test_profiles.py`). The
  owner asked for profile gating, and a guard there would be an undeclared guard. So this is
  a separate, declared, guarded hook.
- **Profile gating: off under `minimal`, on under `standard` and `strict`.** `minimal` is the
  maintainer posture (this repo's own settings.local.json). Publishing cards automatically
  from the kit repo is unwanted. The guard is written in the one form `profiles._scan_shell`
  recognises: `[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0`.
- **Doctor uses `info()`, not `check(..., "warn")`.** `check("warn")` increments
  `checks_warned`, and that makes `doctor --strict` return 1. `info()` is the same route
  the patch-level version note takes, so it touches neither the score nor `--strict`.

## Scope
- **In scope:** the hook, its wiring/registry/profile declaration, the doctor info line, the
  repo .gitignore, behavioural tests, docs (HOOKS.md, cli.md, README reachable count),
  CHANGELOG, and regenerating the counts.
- **Out of scope:** creating any cloud or cron routine (documentation only), changing
  `install.sh`, fleet sync to downstream repos, and a `SessionEnd` event.

## Prerequisites
- Branch from `origin/main` (c040ab5, which contains PR #42).
- Maintainer `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal`.

## Implementation Steps

### Step 1: Create the hook
- **File:** `.claude/hooks/skill-fit-refresh.sh` (Create, mode 0755)
- **Details:** bash 3.2-safe, and every path exits 0 with nothing printed.
  - Profile guard first. Opt-out `CLAUDEKIT_SKILL_REFRESH=0`. Stands down when
    `$CK_ROOT/.claude/skills` is absent.
  - Rate limit uses `find "$STAMP" -mmin -$INTERVAL_MIN` (portable BSD/GNU) against
    `$CK_ROOT/.claude/reports/skills/refresh.stamp`. The stamp is touched BEFORE running, so a
    concurrent Stop stands down.
  - CLI resolution: first the importable `claudekit.cli.main` (`python3 -m`), then `ck` on
    PATH. If neither exists, it logs WARN and exits.
  - Each step runs `(cd $CK_ROOT && exec ...)` in the background with a sleep/kill watchdog
    (macOS has no `timeout`). Default 60s, `CLAUDEKIT_SKILL_REFRESH_TIMEOUT`. `wait` goes to
    `2>/dev/null` so bash's "Terminated" job notice never reaches stderr (measured: without
    it the silent-output test fails).
  - Logs `[skill-fit-refresh] [INFO|WARN]` lines to `$SCRIPT_DIR/hooks.log`.

### Step 2: Wire it in `.claude/settings.json`
- **Action:** Modify. Append a Stop entry after format-typecheck, backgrounded with `&`
  exactly like its siblings.

### Step 3: Dispatch registry row
- **File:** `.claude/hooks/dispatch-registry.json`. Add an `advisory` Stop row. Required by
  `test_registry_covers_every_settings_registration`.

### Step 4: Declare the guard
- **File:** `src/claudekit/profiles.py`. Add `"skill-fit-refresh": "skill-fit-refresh.sh"`
  to GUARDED_HOOKS, and drop the stale word "eleven" (the table already held 12).

### Step 5: minimal profile declares it off
- **File:** `.claude/profiles/minimal/profile.json`. Add `"skill-fit-refresh": "off"`.
  standard and strict inherit `on` from `base_layer()`. python extends standard.

### Step 6: Doctor info line
- **File:** `src/claudekit/cli/main.py`, after the Skill visibility block.
- **Details:** runs only when `.claude/` exists and `skill_fit.registry_dir().is_dir()`.
  Calls `skill_fit.match(Path("."))`. `SkillFitError`, `OSError` and `ValueError` stay
  silent. When N > 0 it prints
  `info("N skill suggestion(s) from other projects — run `ck skill match`")`.

### Step 7: Ignore local state in this repo
- **File:** `.gitignore`. Add `.claude/reports/skills/`. The anchor is the
  settings.local.json block. That anchor is chosen on purpose: the `skills-applied.json`
  line from c838ac4 is not on origin/main.

### Step 8: Behavioural tests
- **File:** `tests/test_skill_fit_refresh.py` (Create). 10 tests. Each copies the hook into
  a tmp project, runs it from a foreign cwd with forced `ECC_HOOK_PROFILE`, and sets HOME and
  CLAUDEKIT_REGISTRY inside tmp_path.
  - standard and strict: the audit and the card are written, stdout and stderr are empty,
    and an INFO line is logged.
  - minimal and the opt-out: nothing is written.
  - Rate limit: the second run stands down, and a stamp aged 25h runs again.
  - A failing step (no manifest, so card exits 1) is logged as WARN, with exit 0 and silence.
  - A hung fake CLI is killed by a 1s timeout, finishes in under 30s, and logs "timed out".
  - A project without skills does nothing.
  - Doctor: with a registry card, the info line appears and the `--strict` exit code and the
    summary lines are identical to the run without a registry. With no registry, nothing is
    printed.

### Step 9: Docs
- `docs/HOOKS.md`: catalog row, and the reachable count goes from 24 to 25 (hand-maintained
  prose, not a gen-docs field: 28 shipped minus 3 unwired).
- `README.md`: the same reachable count, from 24 to 25.
- `docs/cli.md`: a "Keeping it fresh without running it by hand" subsection covering the
  hook's knobs, the doctor line, and a weekly fleet-refresh loop with a crontab/launchd example.
  It states that ClaudeKit creates no scheduler.

### Step 10: CHANGELOG
- `CHANGELOG.md` `[Unreleased]` entry.

### Step 11 (post-ops, main agent, NOT in ops.json): regenerate counts
`python3` is not in the run_command allowlist, so this step cannot be an op. After
execution, run `python3 scripts/gen-docs.py`. It rewrites 27 to 28 in README.md (2 sites),
AGENTS.md, docs/HOOKS.md, and the README inventory block. Never hand-edit these.

## Testing Strategy
Run from the repo root after execution and Step 11:
```bash
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
python3 scripts/check-context-floor.py --check
python3 scripts/check-plan-artifacts.py --check
shellcheck install.sh .claude/hooks/*.sh
ck doctor --strict
```
**Scratch verification already done** (the full worktree copied to the session scratchpad
and the ops applied with `--no-approval` in that copy; round 1 had 11 ops, this revision
has 12):
- All ops applied, 0 errors.
- `test_skill_fit_refresh.py`: 10 passed.
- `gen-docs --check` OK after regeneration, gen-registry OK, context floor OK, ruff clean,
  mypy clean, shellcheck clean on the new hook.
- Mutation proofs:
  - Removing the minimal guard fails `test_minimal_profile_does_nothing` and the 3
    profile-declaration tests.
  - Disabling the doctor print fails
    `test_doctor_reports_suggestions_as_info_without_touching_strict`.
- 15 `test_ops_enforcement_scope.py` failures plus 1 `test_profiles.py` ops-enforcement
  test showed up only in the scratch copy. They are caused by the scratchpad path matching
  ops-enforcement's OS-scratchpad exemption, not by this change. Re-check them in the real
  tree.

## Rollback Plan
The executor backup directory restores every edited file. Delete
`.claude/hooks/skill-fit-refresh.sh` and `tests/test_skill_fit_refresh.py`, then re-run
`python3 scripts/gen-docs.py`. Per project, `CLAUDEKIT_SKILL_REFRESH=0` disables the hook
without a code change. Delete `.claude/reports/skills/refresh.stamp` to force a run.

## Risk Assessment
- **Low:** the doctor line uses info-only routing and is proven not to change `--strict`.
  The docs and CHANGELOG changes are also low risk.
- **Medium:**
  - The new hook is on every Stop in every standard/strict project. It is bounded by the
    rate limit (one `find` per turn when inside the interval), backgrounded by settings.json,
    and always exits 0.
  - `settings.json` and `dispatch-registry.json` both sit on the hook boundary. The registry
    coverage test binds them.
- **Medium (product/privacy):** under standard/strict, `card --publish` now runs without a
  person asking. Cards are sanitized metadata. They go to a user-level directory on the same
  machine and never leave it, and secret-shaped descriptions are withheld by
  `_card_refusal`. Still, this changes when the publish happens. The owner approved
  automation, and the opt-out is documented.
- **Medium (fleet):** downstream repos get the hook only on update/fleet sync. A downstream
  `settings.json` that is merged rather than replaced may not gain the Stop entry. Check
  during fleet sync.
- **Unverified:** whether `ck` resolution picks the right interpreter when a pipx `ck` and a
  different `python3` coexist. The hook prefers the `python3` that can import claudekit.
