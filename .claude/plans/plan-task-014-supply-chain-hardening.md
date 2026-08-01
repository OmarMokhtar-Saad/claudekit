# Implementation Plan: Task 014 — Supply Chain Hardening (executable slice)

**Goal:** close the four supply-chain holes that can be closed today — mutable action refs,
floating `npx @latest` MCP servers, unpinned test deps, and no CI guard against regressing any
of them — without touching anything that needs a live release or a GitHub account action.

**Approach:** declarative pins everywhere (SHA for actions, `@x.y.z` for npm, `--hash` for pip),
each pin backed by a mechanical guard (a CI job + three new tests) so the hardening cannot rot
back to `@latest` silently, plus honest risk disclosure in the MCP template docs.

**Riskiest step:** replacing `tests/requirements.txt` with a hash-pinned lock — a wrong or
incomplete hash set breaks the *entire* CI matrix (2 OSes x 4 Pythons) at the install step,
before a single test runs. Mitigation: the lock was resolved on the oldest supported
interpreter (3.9), every pinned package was verified to publish wheels for cp39–cp314 on Linux
and macOS/arm64, and the exact file was installed successfully with `--require-hashes` in a
clean venv before this plan was written (evidence in "Verification Evidence" below).

---

## Overview

Task 014 (`review/tasks/014-supply-chain-hardening.md`) covers eight steps. Five of them are
actionable in the current repo state; three are blocked on a live release or on the repo owner's
GitHub account. This plan implements the five and records the three as excluded, with reasons.

## Scope

**In scope**

1. SHA-pin every `uses:` ref across the three workflows, with a precise `# vN.x.y` comment.
2. Least-privilege `permissions:` blocks on every workflow.
3. Dependabot coverage for the hash-pinned test lock (`/tests` pip directory).
4. Exact version pins for all five MCP servers; filesystem server read-only by default.
5. Risk disclosure ("what this grants") in `templates/mcp/README.md`.
6. Hash-pinned `tests/requirements.txt` + `--require-hashes` installs in CI and release.
7. A CI guard job that fails on any unpinned `uses:` ref or any `@latest` under `templates/mcp/`.
8. Three new `tests/test_mcp.py` assertions enforcing the MCP pins mechanically.

**Out of scope** (see "Open Decisions / Excluded")

- Release signing, `SHA256SUMS`, Sigstore, SLSA provenance, PyPI attestations.
- Claiming/redirecting the alternate GitHub repo slug.
- Installer-verification docs in the top-level `README.md` (depend on a signed tag existing).

## Prerequisites

- None. All version resolution was done during planning; no network access is required at
  execution time.
- The gitignored `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` must be present,
  per `CLAUDE.md` "Session setup gotcha", or the ops engine's writes will be blocked.

---

## Context Summary (what discovery found)

Several of the task's step-1/step-2 items were **already done** in a prior session, which
shrinks this plan considerably:

| Task 014 item | Actual current state | Work needed |
|---|---|---|
| SHA-pin `ci.yml` | Already SHA-pinned, comments say `# v4` / `# v5` | Upgrade comments to `# v4.3.1` / `# v5.6.0` |
| SHA-pin `release.yml` | Already SHA-pinned, coarse comments | Upgrade comments |
| SHA-pin `security.yml` | **Not pinned** — `@v4`, `@v5`, `@v4` | Pin all three refs |
| `dependabot.yml` | **Exists** (github-actions + pip at `/`) | Add `/tests` pip directory |
| `permissions:` in `ci.yml` | Already `contents: read` | None |
| `permissions:` in `release.yml` | Already top-level read + per-job write/id-token | None |
| `permissions:` in `security.yml` | **Missing** | Add `contents: read` |
| MCP pins | 2 of 5 on `@latest`, 3 unversioned, filesystem `--allow-write .` | Pin all 5, drop `--allow-write` |
| `templates/mcp/README.md` | **Exists**, no risk disclosure, documents `@latest` | Add disclosure, fix docs |
| `tests/requirements.txt` | 3 loose ranges, no hashes | Replace with hash-pinned lock |
| CI pin guard | Absent | New `supply-chain-pins` job |

Other discovery findings that shaped the design:

- **The ops engine fails on ambiguous anchors.** `execute_code_edit` (execute-json-ops.py:522)
  aborts the whole operation when a `find` string matches more than once. `ci.yml` contains 11
  identical `checkout` lines and 8 identical `setup-python` lines, so every comment upgrade is
  anchored from its unique job key (`  coverage:`, `  lint:`, …) rather than the bare `uses:`
  line.
- **`file_create` refuses to overwrite** (validate-config-json.py GUARD 18), so every existing
  file is modified via `code_edit`; only `tests/requirements.in` is a genuine create.
- **`requirements.txt` is in `PROTECTED_PATTERNS`** (shared.py:18) — that guard blocks *deletion*
  only, not edits, so rewriting it via `code_edit` is permitted. No `file_delete` ops exist in
  this plan at all (0 of the MAX_DELETIONS=3 budget used).
- **`tests/test_ops_configs.py::test_queued_ops_configs_validate_against_head`** re-validates
  every non-archived `.claude/plans/*.json` on each test run, so this ops config must keep
  matching HEAD until it is executed and archived.
- `templates/mcp/mcp-settings.json` has exactly one copy in the repo (no duplicate under
  `.claude/` or `src/`), so a single edit is sufficient.
- `templates/commands/mcp.md` documents the same package specs including two `@latest`, so it
  must be updated in lockstep or the docs contradict the config.

### Resolved versions (measured during planning, 2026-08-01)

`npm view <pkg> version`:

| Server | Package | Pinned version |
|---|---|---|
| context7 | `@upstash/context7-mcp` | `3.2.5` |
| sequential-thinking | `@modelcontextprotocol/server-sequential-thinking` | `2026.7.4` |
| playwright | `@playwright/mcp` | `0.0.78` |
| memory | `@modelcontextprotocol/server-memory` | `2026.7.4` |
| filesystem | `@modelcontextprotocol/server-filesystem` | `2026.7.10` |

GitHub tags for the existing/new action SHAs (`api.github.com/repos/<repo>/tags`):

| SHA | Tag |
|---|---|
| `34e114876b0b11c390a56381ad16ebd13914f8d5` | `actions/checkout` **v4.3.1** |
| `a26af69be951a213d495a4c3e4e4022e16d87065` | `actions/setup-python` **v5.6.0** |
| `ea165f8d65b6e75b540449e92b4886f43607fa02` | `actions/upload-artifact` **v4.6.2** (new pin) |
| `cef221092ed1bacb1cc03d23a2d87d1d172e277b` | `pypa/gh-action-pypi-publish` **v1.14.0** |
| `3bb12739c298aeb8a4eeaf626c5b8d85266b0e65` | `softprops/action-gh-release` **v2.6.2** |

Existing SHAs are kept as-is (this is a pinning task, not an upgrade task); Dependabot will now
propose the major bumps (`checkout` v7, `setup-python` v7, `gh-release` v3) as reviewable PRs.

---

## Implementation Steps

### Step 1: Pin and constrain `security.yml`

- **File:** `.github/workflows/security.yml`
- **Action:** Modify
- **Description:** The only workflow still on mutable tags, and the only one with no
  `permissions:` block — so it currently runs with the repository default token scope.
- **Details:**
  - Add a top-level `permissions: contents: read` before `jobs:`.
  - `actions/checkout@v4` → `@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1`
  - `actions/setup-python@v5` → `@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0`
  - `actions/upload-artifact@v4` → `@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2`
  - `contents: read` is sufficient: `upload-artifact` v4 uses the runtime artifact service, not
    the `GITHUB_TOKEN` contents scope.

### Step 2: Precise version comments in `ci.yml`

- **File:** `.github/workflows/ci.yml`
- **Action:** Modify
- **Description:** Upgrade all 19 `# v4` / `# v5` comments to `# v4.3.1` / `# v5.6.0` so a human
  reading the file knows which release the SHA corresponds to.
- **Details:** 11 edits, one per job (`test`, `coverage`, `lint`, `docs-drift`,
  `dangling-hooks`, `shellcheck`, `permission-gate`, `structure`, `validate-registry`,
  `package-smoke`, `install-integration`), each anchored on the job key line because the `uses:`
  lines are byte-identical across jobs.

### Step 3: `--require-hashes` installs in `ci.yml`

- **File:** `.github/workflows/ci.yml`
- **Action:** Modify
- **Details:**
  - `test` job: `pip install -r tests/requirements.txt` →
    `pip install --require-hashes -r tests/requirements.txt`
  - `coverage` job: `pip install -r tests/requirements.txt pytest-cov` →
    `pip install --require-hashes -r tests/requirements.txt`. The trailing `pytest-cov` must go:
    hash-checking mode rejects any unhashed requirement on the same command line. `pytest-cov` is
    now part of the lock instead.
  - `pip install -e .` is a separate invocation and is unaffected (the project has zero runtime
    dependencies).

### Step 4: Add the `supply-chain-pins` CI guard job

- **File:** `.github/workflows/ci.yml`
- **Action:** Modify (append a job)
- **Description:** The mechanical guard that keeps steps 1–5 from rotting.
- **Details:** New job with two `run:` steps, bash-3.2-safe (POSIX `grep -E`, no `grep -P`, no
  bashisms beyond `$( )`):
  - **Every workflow action is SHA-pinned:** greps all `uses:` lines in `.github/workflows/`,
    allows local `uses: ./…` composite refs, and fails on any line lacking a 40-hex commit SHA.
    Verified today against the pre-change tree: it reports exactly the three `security.yml` lines
    and nothing else.
  - **MCP template carries no floating versions:** fails on any `@latest` under `templates/mcp/`.
  - Both steps print the offending lines before `exit 1` (fail loud, fail specific).

### Step 5: Extend Dependabot to the test lock

- **File:** `.github/dependabot.yml`
- **Action:** Modify
- **Details:** The existing `pip` entry watches `/` (i.e. `pyproject.toml`). Add a second `pip`
  entry for `/tests` so the hash-pinned lock is also tracked, with a comment noting that the lock
  carries `--hash` lines and may need manual regeneration if a Dependabot PR drops them.

### Step 6: Create `tests/requirements.in`

- **File:** `tests/requirements.in`
- **Action:** Create
- **Description:** The human-edited source of truth; `requirements.txt` becomes generated output.
- **Details:** `pytest>=7.0`, `jsonschema>=4.0`, `setuptools>=64` (existing, with its existing
  explanatory comment preserved) plus `pytest-cov>=4.0` (moved in from the CI command line).

### Step 7: Replace `tests/requirements.txt` with a hash-pinned lock

- **File:** `tests/requirements.txt`
- **Action:** Modify (full-content replacement via `code_edit`)
- **Description:** 16 packages (4 direct + 12 transitive), every one pinned `==` with the full
  set of sha256 digests for every distribution file on PyPI, so the same file verifies on Linux
  and macOS across Python 3.9–3.13.
- **Details:**
  - Pins: `pytest==8.4.2`, `jsonschema==4.25.1`, `setuptools==82.0.1`, `pytest-cov==7.1.0`,
    `pluggy==1.6.0`, `attrs==26.1.0`, `coverage==7.10.7`, `iniconfig==2.1.0`,
    `jsonschema-specifications==2025.9.1`, `packaging==26.2`, `pygments==2.20.0`,
    `referencing==0.36.2`, `rpds-py==0.27.1`, `typing-extensions==4.16.0`, and
    `exceptiongroup==1.3.1` / `tomli==2.4.1` behind `python_full_version < "3.11"` markers.
  - The header documents the regeneration procedure both ways (`pip-compile --generate-hashes`,
    and the pip `--report` + PyPI-JSON fallback used here because `pip-compile`/`uv` are not
    installed in this environment).
  - `CONTRIBUTING.md`'s plain `pip install -r tests/requirements.txt` keeps working: pip enters
    hash-checking mode automatically once any requirement carries a hash.

### Step 8: `--require-hashes` in `release.yml` + precise comments

- **File:** `.github/workflows/release.yml`
- **Action:** Modify
- **Details:** Same install change as CI (the release gate runs the same suite), and comment
  upgrades to `# v4.3.1`, `# v5.6.0`, `# v1.14.0`, `# v2.6.2`. No `permissions:` change — the
  file is already least-privilege (top-level `contents: read`; `contents: write` + `id-token:
  write` scoped to the single publish job).

### Step 9: Pin the MCP servers and drop default write access

- **File:** `templates/mcp/mcp-settings.json`
- **Action:** Modify
- **Details:** All five `args` arrays get exact `@x.y.z` specs; `filesystem` loses
  `--allow-write` and keeps `.` as its scoped path. `-y` is deliberately **kept** — `npx` without
  it prompts interactively, which would hang MCP server startup; the auto-confirm is not the
  security control here, the version pin is.
- **Design note:** JSON admits no comments, and this file is parsed by `json.load` in
  `tests/test_mcp.py` and copied verbatim by users, so the "commented opt-in" for write access
  lives in `README.md` as a clearly-labelled alternative `args` line rather than as an
  unparseable inline comment.

### Step 10: Risk disclosure + docs in `templates/mcp/README.md`

- **File:** `templates/mcp/README.md`
- **Action:** Modify
- **Details:**
  - New "What this grants (read before enabling)" section immediately after the intro: a
    per-server capability/blast-radius table, the mitigations actually applied, and the explicit
    statement that a version pin fixes *which* remote code runs, not *that* remote code runs.
  - Playwright heading: drop `@latest` from the package name.
  - Filesystem section rewritten around the read-only default, with the write opt-in shown as a
    separate labelled snippet and a warning that MCP filesystem writes bypass this kit's hooks.
  - "Filesystem server path" customization section rewritten for the new default.
  - New "Updating the pinned versions" section (bump procedure; never restore `@latest`).
  - Troubleshooting row updated for the read-only default.
- **Wording constraint:** the disclosure prose deliberately says "a floating `latest` tag"
  rather than the literal token, because the step-4 guard greps the whole of
  `templates/mcp/` and would otherwise fail on its own documentation. Verified by
  simulating the edits: the resulting README contains no occurrence of the literal token.

### Step 11: Sync `templates/commands/mcp.md`

- **File:** `templates/commands/mcp.md`
- **Action:** Modify
- **Details:** The package table lists the same specs (two of them `@latest`). Replace all five
  rows with the pinned specs and describe filesystem as read-only by default.

### Step 12: Extend `tests/test_mcp.py`

- **File:** `tests/test_mcp.py`
- **Action:** Modify
- **Details:** Add `import re` and a module-level
  `PINNED_SPEC = re.compile(r"^(@[^@/]+/)?[^@]+@\d+\.\d+\.\d+$")`, then three tests in the
  existing `TestMCPSettings` class, matching its fixture/parametrize conventions:
  - `test_package_spec_pinned_to_exact_version` (parametrized over `EXPECTED_SERVERS`) — every
    non-flag, non-path arg must match `PINNED_SPEC`.
  - `test_no_floating_version_specs` — no arg ends with `@latest`.
  - `test_filesystem_is_read_only_by_default` — `--allow-write` absent from filesystem args.

### Step 13: CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Details:** One `### Added` bullet under `[Unreleased]` covering the pins, the guard job, and
  the MCP risk disclosure (DoD requires a CHANGELOG entry for user-visible changes; the MCP
  template and test-dep install are both user-visible).

---

## Testing Strategy

**Before execution**

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-task-014-supply-chain-hardening.json
python3 .claude/operations/scripts/execute-json-ops.py .claude/plans/ops-task-014-supply-chain-hardening.json --dry-run
```

**After execution — full DoD gate**

```bash
python3 -m pytest tests/ -q                 # 516 existing + 7 new mcp assertions
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
shellcheck install.sh .claude/hooks/*.sh
```

**Targeted verification**

```bash
# Acceptance criteria from the task file
grep -rn "uses:.*@v[0-9]" .github/workflows/          # expect: no matches
grep -rn "@latest" templates/mcp/                      # expect: no matches
python3 -m pytest tests/test_mcp.py -v                 # expect: all pass, incl. 3 new

# The new CI guard, run locally exactly as CI runs it
grep -rnE '^[[:space:]]*(- )?uses:' .github/workflows/ \
  | grep -vE 'uses:[[:space:]]*\./' \
  | grep -vE 'uses:[[:space:]]*[^[:space:]]+@[0-9a-f]{40}([[:space:]]|$)'   # expect: empty

# The lock actually installs under hash checking
python3 -m venv /tmp/ck-lock && /tmp/ck-lock/bin/pip install --require-hashes -r tests/requirements.txt
```

**Canary checks (prove the guards actually fail)**

- Temporarily set one `uses:` back to `@v4` → the `supply-chain-pins` job must fail.
- Temporarily set one MCP spec back to `@latest` → both the guard job and
  `test_no_floating_version_specs` must fail.
- Temporarily re-add `--allow-write` → `test_filesystem_is_read_only_by_default` must fail.

## Verification Evidence (collected during planning, not asserted)

- `npm view` returned the five versions in the table above (executed 2026-08-01).
- GitHub tags API mapped every SHA to an exact release tag (table above).
- Dependency resolution ran on Python 3.9 (`pip install --dry-run --report`), the oldest CI
  interpreter, so no pin can be newer than 3.9 support allows.
- PyPI JSON was queried for every pinned version: `coverage 7.10.7` and `rpds-py 0.27.1` (the
  only packages with compiled wheels) publish `cp39`–`cp314` wheels including macOS arm64;
  `tomli` ships binary wheels for cp311+ plus a pure wheel, and is marker-gated to <3.11 anyway.
  Everything else is pure-Python (`py3-none-any` + sdist).
- The exact lock file content in this ops config was installed into a clean venv with
  `pip install --require-hashes` and succeeded: 16 packages, no hash mismatches.

## Rollback Plan

Every change is declarative and additive; there is no data migration and no state.

- **Whole plan:** `python3 .claude/operations/scripts/restore-backup.py <backup-dir>` (the engine
  backs up each touched file before its first edit), or `git checkout -- <path>`.
- **A pinned action SHA breaks CI:** update the SHA — the same one-line change as a tag bump.
  Do not revert to a tag ref.
- **A pinned MCP version breaks a user:** bump the pin in `mcp-settings.json` and
  `templates/commands/mcp.md`. Never restore `@latest` (CI would fail anyway).
- **The lock fails to install on some matrix cell:** revert `tests/requirements.txt` and the two
  `--require-hashes` flags (3 hunks); `tests/requirements.in` can stay harmlessly.
- **The guard job is too strict:** it is a standalone job — deleting it removes the gate without
  touching any other job.

## Risk Assessment

**Low**

- SHA pins + version comments (cosmetic to behavior; SHAs already in use in ci/release).
- `permissions: contents: read` on `security.yml` (the job only reads the checkout and uploads
  artifacts; no token writes anywhere in it).
- Dependabot `/tests` entry (opens PRs; cannot break a build on its own).
- MCP version pins (template only; not consumed by the test suite beyond shape assertions).
- New tests + CHANGELOG.

**Medium**

- **Filesystem server default change** — a user who relied on `--allow-write` in the template
  gets a read-only server after copying the new config. Mitigated by an explicit opt-in snippet
  in the README and a CHANGELOG entry; this is the intended, disclosed behavior change.
- **CI guard false positives** — a future legitimate `uses:` form (e.g. a local composite action
  or a Docker `uses: docker://`) could trip the grep. The `./` case is already allowlisted;
  `docker://` would need one more allowlist line if ever adopted.
- **`pytest-cov` moving into the lock** — the `coverage` job's install line changes shape. If the
  edit lands but the lock edit does not, that job fails fast and loudly (never silently skips the
  coverage gate).

**High**

- **The hash-pinned lock is the one change that can red the entire matrix.** Hash-checking mode
  is all-or-nothing: one missing digest for one platform wheel breaks install on that cell before
  any test executes. This is mitigated as described in Verification Evidence (3.9-based
  resolution, cp39–cp314 wheel coverage confirmed per package, real `--require-hashes` install
  performed), but it remains the step to watch on the first CI run after execution. If it fails,
  the failure is unambiguous (pip prints the offending package) and the rollback is 3 hunks.

## Open Decisions / Excluded

These task-014 items are deliberately **not** in this plan or its ops config:

1. **Release integrity — `SHA256SUMS`, Sigstore/GPG signing, SLSA provenance, PyPI attestations
   (task 014 step 5).** Blocked: `CLAUDE.md` states the release tag + PyPI publish are
   user-gated, and the release pipeline has never run (zero tags). Signing steps that have never
   executed are speculative code in a workflow nobody can test; they should land in the same
   change that performs the first real release (task 001), where each step's output can be
   verified against a real artifact. Note that `release.yml` already uses Trusted Publishing via
   OIDC with `id-token: write` scoped to the publish job — the OIDC half of this item is done;
   what remains is `--attestations`, `SHA256SUMS`, and signature upload.
2. **Installer-verification docs in the top-level `README.md` (task 014 step 6).** Depends on (1):
   documenting `git verify-tag` and a `SHA256SUMS` check before either exists would ship
   instructions that fail for the reader. Deferred to the release change.
3. **Repo-slug claim/redirect (task 014 step 7).** Requires the repo owner to register or
   redirect a GitHub account/repository — a manual account action no agent can perform. Owner
   decision, tracked in task 006 (canonicalization) alongside this.
4. **Upgrading action majors (checkout v7, setup-python v7, gh-release v3).** Intentionally not
   bundled: this plan pins, it does not upgrade. Dependabot will now raise those as separate,
   reviewable PRs — which is the point of adding it.
5. **`@latest` in files outside `templates/mcp/`.** The new CI guard is scoped to
   `templates/mcp/` as specified. `templates/commands/mcp.md` is fixed by this plan anyway, so
   `grep -rn "@latest" templates/` also comes back clean; widening the guard to all of
   `templates/` is left as a follow-up decision (it could false-positive on future prose).

## Traceability: plan step → operations

| Step | Ops index | File |
|---|---|---|
| 1 | 1 | `.github/workflows/security.yml` |
| 2, 3, 4 | 2 | `.github/workflows/ci.yml` (one `code_edit`, 14 edits) |
| 5 | 3 | `.github/dependabot.yml` |
| 6 | 4 | `tests/requirements.in` (`file_create`) |
| 7 | 5 | `tests/requirements.txt` |
| 8 | 6 | `.github/workflows/release.yml` |
| 9 | 7 | `templates/mcp/mcp-settings.json` |
| 10 | 8 | `templates/mcp/README.md` |
| 11 | 9 | `templates/commands/mcp.md` |
| 12 | 10 | `tests/test_mcp.py` |
| 13 | 11 | `CHANGELOG.md` |

### How this ops config was produced

Every `find` anchor was extracted from, or checked against, the real file on disk, then all
11 operations were replayed in order against an in-memory copy of the tree to prove each
anchor matches exactly once (the engine aborts on 0 or >1 matches). The simulated outputs
were then re-verified: the workflows parse as YAML and expose 12 jobs including
`supply-chain-pins`; the MCP config parses as JSON and satisfies all three new test
assertions; the guard grep returns empty against the post-change workflows; and
`grep -rn "uses:.*@v[0-9]"` / `grep -rn "@latest" templates/mcp/` both come back clean.
Finally `execute-json-ops.py --dry-run` reported success for all 11 operations
(1 `file_create`, 10 `code_edit`, 0 `file_delete`).

Operations config: `.claude/plans/ops-task-014-supply-chain-hardening.json`
(11 operations, 0 deletions of the MAX_DELETIONS=3 budget).
