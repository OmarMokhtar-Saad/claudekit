# Implementation Plan: Rename the PyPI distribution to `claudekit-agents`

## Overview

The PyPI distribution name changes from `claude-kit` to **`claudekit-agents`** (owner-decided,
2026-09-07). PyPI refused `claude-kit` as confusable with an existing unrelated project named
`claudekit` — PyPI ignores separators when testing names for similarity, so `claude-kit` collapses
onto `claudekit`. That refusal has blocked every release this project has ever attempted; nothing
has ever been published, so `pip install claude-kit` was never a working command and there are no
downstream users to migrate. The plan also bumps the version to **3.2.1** (v3.2.0 is already tagged
and released, and a built wheel embeds its distribution name, so the rename cannot ship under that
tag) and adds a CHANGELOG entry.

## What does NOT change (state this everywhere, it is the whole point)

- The **import package** stays `claudekit` (`src/claudekit/`, `import claudekit`).
- The **console scripts** stay `claudekit` and `ck`.
- The **GitHub repository** stays `OmarMokhtar-Saad/claudekit`.
- Only the **distribution** (the argument to `pip install`, the `[project] name`, the
  `importlib.metadata` key, the wheel/sdist filename stem) moves.

## Design precheck: the coupling that makes this not a find-and-replace

`src/claudekit/_version.py` declares `DIST_NAME = "claude-kit"` and uses it **twice, with two
different meanings**:

1. as the argument to `importlib.metadata.version()` (the *installed distribution* key), and
2. as the value it compares against the `[project] name` it reads out of the neighbouring
   `pyproject.toml` to decide whether the tree above `src/claudekit/` is a **genuine source
   checkout** (`source_version()`, the expensive half of the guard).

`src/claudekit/cli/main.py:45` repeats the literal a **third** time, inside the branch taken when
`claudekit._version` cannot be imported at all — so that site structurally cannot derive the value
and must be pinned by a test instead.

If `pyproject.toml`'s `name`, `DIST_NAME`, and the `metadata.version()` argument do not move
**together**, `_project_field(text, "name") != DIST_NAME` becomes true in this very repo: a source
checkout stops recognising itself, `source_version()` returns `None`, and the CLI silently falls
back to stale installed metadata while `install.sh` keeps stamping the source version into every
manifest — the exact defect that took seven review rounds and merged as PR #37 (`ck doctor` calling
a freshly installed project DRIFTED). This plan moves all three in one config and adds a test class
that fails if any one of them moves alone.

## Scope

- **In scope:** the three coupled functional sites; every other functional use of the distribution
  name; user-facing install/error text; maintainer docs that state current truth; the release
  workflow's trusted-publisher instructions; the version bump; a CHANGELOG `## [3.2.1]` entry; test
  updates plus the new coupling test; a DECISIONS row recording the rename.
- **Out of scope:** renaming the import package, the console scripts, or the repo; tagging or
  publishing (owner-gated); folding the existing `## [Unreleased]` CHANGELOG entries under
  `[3.2.1]` (see Unsettled); any `run_command` — no generated artifact changes, so nothing needs
  regenerating.

## Files deliberately left as historical record (renaming these would falsify them)

| Path | Why untouched |
|---|---|
| `CHANGELOG.md` lines 98, 2384 (entries for 3.2.0 and older) | Published history: those releases *did* describe `claude-kit`. Only a NEW `[3.2.1]` section is added. |
| `.claude/plans/archive/**`, `.claude/plans/plan-version-source-precedence.md`, `plan-omniroute-adoption.md`, `plan-memory-store.md`, `phase-1-*.md`, `plan-day-one-blockers.md` | Executed/archived plans are records of what was true when written. |
| `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`, `.ai/BACKLOG.md` | Dated session and backlog entries; rewriting them fabricates a past. |
| `review/**` (`oss-excellence.md`, `documentation-review.md`, `roadmap.md`, `tasks/001-*.md`) | The 2026-07 audit that *caused* the naming question. Its wording is evidence. |
| `.ai/DECISIONS.md` row **#20** (“Publish under PyPI name `claude-kit`”) | A decision record. It is **superseded by a new row #24**, not edited — an ADR log that rewrites old rows stops being an audit trail. |
| `.agents/**` and `.claude/skills/**` mentioning unrelated `pip install <package>` | Not about this distribution. |

## Implementation Steps

Each step is one `code_edit` operation; all 46 `find` anchors were verified to occur **exactly
once** in their target file with `str.count` (not `grep -c`, which counts lines).

### Functional (the coupled three, first)
1. **`pyproject.toml`** — `[project] name` → `claudekit-agents`; `version` → `3.2.1`. Only this file
   carries the semver literal: `tests/test_packaging.py::test_single_version_source_of_truth`
   forbids one in the shipped package, and PR #36 made `__init__.py` and `cli/main.py` derive.
2. **`src/claudekit/_version.py`** — `DIST_NAME` → `claudekit-agents`, with the two-meanings-plus-a-
   third-site coupling written into the comment above it; docstring mentions at the module head and
   in `source_version()` updated (the generic ones reworded to “ClaudeKit”, which cannot go stale).
3. **`src/claudekit/cli/main.py`** — the `metadata.version("…")` fallback literal, with a comment
   saying it must equal `DIST_NAME` and cannot import it (that branch means the import failed) and
   naming the test that pins it; the user-visible
   `pip install 'claudekit-agents[validation]'` hint and its docstring; one stale comment.

### Tests
4. **`tests/test_version_precedence.py`** — stop hardcoding the name: load `_version.py` **by file
   path** (`importlib.util.spec_from_file_location`, never `import claudekit`, which on this machine
   resolves through an editable install pointing at a *different* checkout) and derive `DIST_NAME`;
   every synthetic tree and the subprocess metadata lookup now use it. Adds
   `TestTheDistributionNameIsOneString`.
5. **`tests/test_hooks_behavioral.py`** — one docstring naming the package.

### Other functional / user-visible text
6. **`src/claudekit/memory.py`** — docstring naming the package hooks must work without.
7. **`.claude/hooks/command-guard.sh`** — the header rationale plus the two rc-127 messages a user
   actually reads (`hlog` line and the `printf` to stderr).
8. **`README.md`** — the install line; its trailing comment explained the old name choice and is now
   wrong, so it is replaced rather than patched.
9. **`CHANGELOG.md`** — new `## [3.2.1] — 2026-09-07` section inserted immediately above `[3.2.0]`.
10. **`docs/HOOKS.md`** — the profile table's permissive-path sentence.
11. **`CLAUDE.md`** and 12. **`AGENTS.md`** — the identity sentence. No component count is touched,
    so `gen-docs.py --check` and `check-context-floor.py --check` are unaffected.
13. **`setup.py`** — the module docstring's `pip install` example.
14. **`.github/workflows/release.yml`** — the one-time-setup comment now says the project **does not
    exist on PyPI yet** and the publisher must be registered as a **pending publisher under account
    settings** (`Your account → Publishing`), not on a project page; plus the `dist/` filename
    comment (`claudekit_agents-<version>`). No workflow step globs the old stem — `ci.yml:246` and
    `release.yml:69` use `dist/*`.

### Maintainer docs (current truth, not history)
15. `.ai/CONTEXT.md` · 16. `.ai/FAQ.md` (the whole Q&A is rewritten — the old answer's *reason* is
now wrong, so substituting the string would leave a false explanation) · 17. `.ai/MIGRATION_GUIDE.md`
(2 install lines) · 18. `.ai/SYSTEM_OVERVIEW.md` (install line + key-numbers line; counts untouched)
· 19. `.ai/DEPENDENCIES.md` (extras install + external-services line) · 20. `.ai/MEMORY.md` ·
21. `.ai/PLAYBOOK.md` (post-publish check) · 22. `.ai/TROUBLESHOOTING.md` · 23.
`.ai/AI_PROJECT_HANDOVER.md` (also records that the publisher is still unregistered) ·
24. `.ai/DECISIONS.md` (new row **#24**, superseding #20's name and not its principle).

## Every path the ops config writes

`pyproject.toml` · `src/claudekit/_version.py` · `src/claudekit/cli/main.py` ·
`tests/test_version_precedence.py` · `tests/test_hooks_behavioral.py` · `src/claudekit/memory.py` ·
`.claude/hooks/command-guard.sh` · `README.md` · `CHANGELOG.md` · `docs/HOOKS.md` · `CLAUDE.md` ·
`AGENTS.md` · `setup.py` · `.github/workflows/release.yml` · `.ai/CONTEXT.md` · `.ai/FAQ.md` ·
`.ai/MIGRATION_GUIDE.md` · `.ai/SYSTEM_OVERVIEW.md` · `.ai/DEPENDENCIES.md` · `.ai/MEMORY.md` ·
`.ai/PLAYBOOK.md` · `.ai/TROUBLESHOOTING.md` · `.ai/AI_PROJECT_HANDOVER.md` · `.ai/DECISIONS.md`

24 operations, 46 edits, zero file creates, zero deletes, zero `run_command`.

## Testing Strategy — one mutation proof per behaviour

Run only the touched test files:

```bash
python3 -m pytest tests/test_version_precedence.py tests/test_packaging.py -q
python3 -m pytest tests/test_hooks_behavioral.py -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
shellcheck install.sh .claude/hooks/*.sh
python3 scripts/gen-docs.py --check && python3 scripts/check-context-floor.py --check
python3 scripts/check-plan-artifacts.py --check
```

| Behaviour | Test | Mutation that reds it |
|---|---|---|
| The three sites name ONE distribution | `TestTheDistributionNameIsOneString::test_pyproject_version_module_and_cli_name_one_distribution` | Change the name in **any one** of `pyproject.toml` `[project] name`, `_version.DIST_NAME`, or `cli/main.py`'s `metadata.version("…")` literal → the equality assert fails. Verified against a simulated post-state: mutating pyproject alone yields `claude-kit != claudekit-agents`. |
| The name is the one PyPI accepted | `…::test_the_distribution_name_is_the_one_pypi_accepted` | Rename all three *consistently* (which the first test cannot see) → `DIST_NAME == "claudekit-agents"` fails, so a future rename must be a deliberate act that edits a test. |
| A source checkout still reports its tree | existing `test_a_source_checkout_reports_the_source_version` | Revert the precedence, or leave `DIST_NAME` behind while pyproject moves → the synthetic tree stops matching and metadata wins. |
| The name guard still rejects a foreign tree | existing `test_an_unrelated_neighbouring_pyproject_is_not_a_kit_source` | Drop the `name` check → reports `6.6.6`. |
| No semver literal re-enters the package | existing `test_no_hand_bumped_version_literal_remains` + `test_single_version_source_of_truth` | Add `"3.2.1"` to `__init__.py` or `cli/main.py` → fails. |
| Installer and CLI agree at the bumped version | existing `test_the_installer_and_the_cli_cannot_disagree` | Bump pyproject without moving the name coherently → manifest/CLI disagree, "Install version drift". |

Pre-verified before handoff (simulated post-state in a scratch copy, tree untouched):
all 46 anchors unique; `py_compile` passes on all 5 edited Python files; `bash -n` passes on
`command-guard.sh`; the new test's assertions pass and its mutant fails; no new line exceeds
100 chars.

## Rollback

- Nothing is created or deleted; every operation is a reversible in-place edit, and the ops engine
  takes a backup before writing — `python3 .claude/operations/scripts/restore-backup.py` restores
  the pre-execution state.
- Ungated fallback: the branch is `chore/pypi-rename`, so `git checkout -- .` (pre-commit) or
  `git revert` (post-commit) returns the tree to `origin/main` behaviour exactly.
- Partial-failure shape: the engine is atomic per config, so a failed run leaves no half-applied
  rename. If one is somehow observed, the tell is `python3 -c "import claudekit; print(claudekit.__version__)"`
  from the checkout printing installed metadata instead of `3.2.1` — the coupling defect. Restore the
  backup rather than hand-patching one of the three sites.
- Nothing is published, so there is no PyPI action to undo. A wrong name is only recoverable
  *before* an upload; after one, the name is permanently occupied.

## Risk Assessment

- **Low:** the 15 documentation-only edits; the version bump (pyproject is the single source and two
  tests already pin it); `CHANGELOG.md`/`README.md`/`CLAUDE.md`/`AGENTS.md` are delete-protected, and
  every operation here is an edit, so no protected-file guard is engaged.
- **Medium — the three-way coupling.** Mitigated by moving all three in one config and by the new
  test. Residual: `cli/main.py`'s literal cannot be derived (its branch exists precisely because
  `_version` is unimportable), so it is pinned only by a source-text regex; if that fallback were
  ever restructured the regex could silently match nothing — hence the explicit
  `assert literals` guard in the test.
- **Medium — the release workflow is still unexercised.** The publisher for `claudekit-agents` does
  not exist on PyPI; the workflow comment now says so, but nothing mechanically verifies it. The
  first tag push remains the test.
- **Prior rejection brief consulted:** `.claude/knowledge/rejections/fleet-a2b-d1-d3.md` (packaging
  metadata, REVISE 75) — its defect class is *claims about the built artifact that were never
  verified by building*. This plan differs in that it makes no claim about sdist/wheel contents;
  it changes only the name stem, and no CI step or test globs the old stem (`dist/*` in
  `ci.yml:246` and `release.yml:69`). No brief matches the rename itself; absence of a brief is not
  evidence of safety.
- **No blast-radius escalation:** no `.claude/project-graph.json` in this worktree, so hub analysis
  is unavailable; the widest-fanout file touched is `cli/main.py`, edited only in comments and one
  string literal.

## Unsettled (owner call, deliberately not decided here)

1. **The `## [Unreleased]` CHANGELOG block.** It holds post-3.2.0 entries (the ops parse gate work)
   that *will* ship inside 3.2.1. This plan inserts `[3.2.1]` below them and leaves them alone
   rather than relabelling nine paragraphs of someone else's release notes. Folding them in is a
   one-line heading move if the owner wants it.
2. **`.ai/SYSTEM_OVERVIEW.md` and `.ai/MEMORY.md` still say “version 2.1.0”** — pre-existing drift,
   out of scope here, worth a separate sweep.
