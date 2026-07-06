# Task 011 — CI Hardening

## Problem
The CI of a "quality gates" product swallows failures and proves nothing:
- The `cli-tests` job runs `pytest tests/test_cli.py tests/test_security.py || true` — **failures cannot fail the build** (oss-excellence, arch F-23). A `test_security` regression would ship silently.
- Only 5 of 14 test files run in CI at all; `test_i18n`, `test_mcp`, `test_modes`, `test_new_*`, `test_spec_driven`, `test_checkpoint`, `test_security_hooks` never run (testing-review).
- Matrix is Python 3.8/3.10/3.12 on **ubuntu-latest only** — no macOS despite macOS-specific branches (bash 3.2 `${VAR,,}` breakage, BSD `date -r`, `/System` path guards) and no Windows despite advertised support.
- No job builds the pip package (`python -m build` would have caught the P0 backend bug for a year); no job runs install.sh end-to-end + doctor (would have caught the missing settings.json).
- No coverage measurement (the kit demands 80% of users), no lint/mypy on `src/`.
- Structure job asserts stale floors ("≥13 agents, ≥17 commands") that can never catch a 28→14 regression (arch F-14).
- Shellcheck covers `.claude/hooks/` only, not `templates/hooks/` or install.sh-adjacent scripts.
- No check that settings.json hook commands point at files that exist (`ops-enforcement.sh` was untracked in git while settings.json referenced it — arch F-9).

## Root Cause
CI was written to be green, not to be predictive: flaky/failing jobs were suppressed with `|| true` instead of fixed, and expectations were hardcoded as floors instead of derived from the tree.

## Files
- `.github/workflows/ci.yml` (all jobs)
- `.github/workflows/release.yml` (never exercised — verify with task 001's tag)
- `.github/workflows/security.yml`
- New: `.github/workflows/evals.yml` (task 010), docs-drift job (task 006)
- `tests/requirements.txt` (+coverage, ruff, mypy pins)
- `claudekit.manifest.json` (count source — task 005)

## Priority
**P1** (S effort, High impact — oss-excellence rank 3). Do the `|| true` removal on day one of v2.1.

## Estimated Time
2–3 days (plus fixing whatever the newly-honest CI reveals — budget another 1–2 days; the known red test is handled in task 012).

## Risk
Low–Medium. Removing `|| true` will immediately redden CI (the `test_max_deletions_exceeded` failure is known; there may be others in the never-run files). Land task 012's red-test fix in the same PR or sequence it first. macOS runners are slower/costlier — run the full matrix on main + PRs touching shell/py files, path-filtered otherwise.

## Step-by-step Implementation
1. Remove both `|| true` occurrences; merge cli/security tests into the main matrix job; run the **entire `tests/` directory** in one `pytest tests/ -q --timeout=60` invocation.
2. Add `macos-latest` to the matrix (at least one Python version); add a Windows smoke job for the pure-Python surface (`pytest tests/test_validator.py tests/test_security.py` + CLI `--help`) — hooks/installer stay documented as WSL-only for now.
3. New `package-smoke` job: `python -m build && pip install dist/*.whl && claudekit --version && ck --help` in a clean venv (task 001).
4. New `install-integration` job: fixture projects (python + typescript minimum) → `./install.sh <fixture> --full --yes` → assert `.claude/settings.json` exists → `claudekit doctor --strict` (add the flag: warnings ⇒ exit 2, DX review §2) → one ops.json round-trip: `validate → execute --dry-run → execute → rollback`.
5. Coverage: `coverage run -m pytest` + `coverage report --fail-under=60` initially (raise toward the kit's own 70/80 targets as task 012 lands); publish to the README badge. In-process CLI tests (task 012) are what make this meaningful — subprocess-spawned CLI shows 0%.
6. Lint: `ruff check src/ tests/` + `mypy src/` (start permissive, `--ignore-missing-imports`, ratchet later); `bash -n` + shellcheck **recursively** on all `*.sh` (`.claude/hooks/`, `templates/hooks/`, `install.sh`).
7. Replace stale count floors: structure job reads exact expected counts from `claudekit.manifest.json` and fails on drift in either direction.
8. New consistency checks: every hook command referenced in `.claude/settings.json` exists on disk and is executable; every file settings.json references is git-tracked; repo-slug grep (task 006); dangerous-instruction lint (task 010 step 7).
9. Pin all action versions by SHA (executed in task 014; note here for sequencing) and add `dependabot.yml` for actions.
10. Branch protection: make the matrix, package-smoke, and install-integration jobs required.

## Acceptance Criteria
- Introducing a deliberate failure in `test_security.py` fails CI.
- All 14 test files execute in CI logs; total test count in CI ≥ local count (423).
- CI is red if: the wheel doesn't build, install.sh doesn't produce settings.json, doctor --strict warns, an agent is added without manifest/docs regeneration, a settings.json hook path dangles.
- macOS job green (after task 003's bash-3.2/BSD fixes).
- Coverage gate active with a recorded baseline; ruff/mypy/shellcheck jobs green.

## Testing Strategy
CI-about-CI: for each new gate, land a companion "canary" PR (or a scripted `act`/dry-run check) proving it fails on the defect class it guards — e.g., temporarily reintroduce the bad build-backend on a branch and confirm package-smoke reddens. Document each gate's purpose inline in ci.yml comments.

## Rollback Plan
Workflow files are independently revertible. If a new gate flakes (macOS runner variance, API-dependent jobs), demote it to non-required/continue-on-error **with a tracking issue** — never back to `|| true` inside the test command where the suppression is invisible.
