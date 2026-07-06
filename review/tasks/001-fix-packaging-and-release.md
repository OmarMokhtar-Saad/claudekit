# Task 001 — Fix Packaging & Release Pipeline

## Problem
The pip distribution channel has never worked. `pyproject.toml:3` declares `build-backend = "setuptools.backends._legacy:_Backend"`, a module that does not exist in any setuptools release (verified: `import setuptools.backends` → `ModuleNotFoundError`). Every `pip install .`, `pip install -e .`, and `python -m build` fails at backend import, so the `claudekit`/`ck` console scripts are unreachable and `docs/cli.md`'s documented install path is fiction. Even once fixed, the config installs a top-level package literally named `src` (`include = ["src*"]`, entry point `src.cli.main:main` — pyproject.toml:29-31, 39-40), colliding with the most common scratch package name in the Python ecosystem. The wheel would also contain no product: no `MANIFEST.in`/package-data, so `.claude/`, `templates/`, and `install.sh` are absent and `claudekit init` only works parasitically on a separate git clone. There are zero git tags, `release.yml` has never run, and the project is not on PyPI.

## Root Cause
Packaging was written once, never exercised: no CI job builds the wheel or runs `pip install .`. A hallucinated/typo'd backend string survived because nothing could fail on it. The `src`-layout convention was misunderstood (`src` treated as the package instead of the container). `setuptools-scm>=8` is required in build deps (pyproject.toml:2) with no `[tool.setuptools_scm]` config and a static `version` — contradictory leftovers.

## Files
- `pyproject.toml:3` (backend), `:7` (version), `:2` (setuptools-scm), `:13` (email), `:29-31, 39-41` (scripts/packages), `:34` (Homepage slug)
- `src/cli/main.py:13` (`__version__ = "1.1.0"`), `src/__init__.py`, `src/cli/__init__.py`, `src/security/__init__.py`
- `tests/test_cli.py:31` (asserts literal `"1.1.0"` — codifies the drift)
- `.github/workflows/release.yml`, `.github/workflows/ci.yml`
- `install.sh:7` (VERSION=2.0.0)

## Priority
**P0** — blocks PyPI, the CLI, task 005 (`ck update`), and task 007 (plugin work benefits from a working package).

## Estimated Time
1–2 days (backend fix is minutes; the rename and CI smoke are the bulk).

## Risk
Low–Medium. The rename `src.*` → `claudekit.*` touches every import in `src/` and `tests/`, but grep confirms nothing external imports `src.security` (architecture-review F-7). PyPI naming: `claudekit` is a well-known **npm** package in the same niche (carlrannaberg/claudekit) — check PyPI availability and decide on disambiguation before first publish.

## Step-by-step Implementation
1. `pyproject.toml`: set `build-backend = "setuptools.build_meta"`, `requires = ["setuptools>=64"]`; drop `setuptools-scm`.
2. Restructure to true src-layout: `git mv src/cli src/claudekit/cli`, `git mv src/security src/claudekit/security`; add `src/claudekit/__init__.py` with `__version__ = importlib.metadata.version("claudekit")` (guarded fallback for repo-run).
3. Update `[tool.setuptools.packages.find] where = ["src"]`; entry points `claudekit = "claudekit.cli.main:main"`, `ck = "claudekit.cli.main:main"`.
4. Delete `__version__ = "1.1.0"` from `main.py`; read from package metadata. Update `tests/test_cli.py:31` to assert against `importlib.metadata.version`, not a literal.
5. Fix all intra-repo imports (`from src.security…` → `from claudekit.security…`) in tests and any scripts.
6. Declare `[project.optional-dependencies] validation = ["jsonschema>=4"]`, `dev = ["pytest", "pytest-timeout", "coverage"]`; modernize `license = "MIT"` (PEP 639); add 3.13 classifier; bump `requires-python` to `>=3.9` (3.8 EOL'd 2024-10).
7. Package assets for the wheel (coordinate with task 005/007): either `MANIFEST.in` + `[tool.setuptools.package-data]` shipping `.claude/` as `claudekit/assets/`, or defer to the v3.0 asset move — at minimum document that v2.1 pip still requires a checkout, and make `find_claudekit_root()` honor `CLAUDEKIT_HOME` (see task 005).
8. Fix `Homepage` slug to the canonical repo (coordinate with task 006).
9. CI: add a `package-smoke` job — `python -m build && pip install dist/*.whl && claudekit --version && ck --help` in a clean venv.
10. Align `install.sh:7` VERSION with pyproject at release time (CI templating or a release checklist step); tag `v2.1.0` and verify `release.yml` end-to-end; publish to PyPI via Trusted Publishing.

## Acceptance Criteria
- `pip install .` succeeds on Python 3.9–3.13; `claudekit --version` and `ck --version` print the pyproject version.
- `pip show -f claudekit` lists no top-level `src` package.
- CI fails if the wheel can't build or the console script can't run.
- One git tag exists; `release.yml` produced a GitHub Release with sdist+wheel; PyPI page live (or a documented decision on the name).
- Exactly one version string in the repo (pyproject); `grep -rn "1\.1\.0\|3\.1\.0" src/ install.sh` returns nothing version-related.

## Testing Strategy
- New `tests/test_packaging.py`: build wheel in tmpdir, inspect namelist for `claudekit/` and absence of `src/`.
- CI package-smoke job (step 9) on the full Python matrix.
- Existing `test_cli.py` re-run against the installed entry point, not just `python3 src/cli/main.py`.

## Rollback Plan
The change is contained to packaging metadata + a directory rename. Revert the commit(s); no user-facing installs depend on pip yet (it never worked), so rollback risk to users is nil. If a bad wheel reaches PyPI, `pip yank` the release and publish a post-fix.
