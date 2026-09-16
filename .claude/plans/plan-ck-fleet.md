# Implementation Plan: `ck fleet` — one permitted command for fleet sync

## Overview
Add a `ck fleet <list|diff|update|verify>` subcommand so syncing ClaudeKit into every
kitted project under a root is one permitted command instead of a hand-written script per
change. New code lives in `src/claudekit/cli/fleet.py` and reuses `cli/main.py`'s manifest
internals (`_load_manifest`, `_classify_manifest`, `_managed_files`, `_sha256`,
`find_claudekit_root`, `cmd_update`) by calling them directly — never by shelling out to `ck`.

## Design Precheck (ownership / data model)
The kit's ownership model is already the manifest: `.claude/.claudekit-manifest.json` maps
each managed path to its install-time sha256. That receipt is what distinguishes "untouched
downstream" (current hash == manifest hash) from "locally modified" (current != manifest),
and the kit source tree supplies the third hash ("what it should be now"). Every value this
feature needs lives in those three hashes, so `fleet` adds **no new state file**: it is a
loop over projects plus a presentation layer on top of the existing three-hash comparison.
Repo discovery is by presence of the manifest under `<child>/.claude/`, never a hardcoded
list (a list is a silent-omission machine). No security, schema, or protected-file surface
is touched.

## Scope
- **In Scope:** `src/claudekit/cli/fleet.py`, a thin wrapper + parser + dispatch entry in
  `src/claudekit/cli/main.py`, `tests/test_cli_fleet.py`, `docs/cli.md`, CHANGELOG.
- **Out of Scope:** any git commit/push/branch behaviour (owner's step — the command only
  *prints* the suggested `git -C <repo> add -A .claude .agents .gitignore` line); recursive
  discovery below the immediate children of `--root`; changes to `install.sh`, the manifest
  schema, or `cmd_update`'s own semantics.

## Prerequisites
- None. Python 3.9, stdlib only, zero runtime deps. `.claude/settings.local.json` with
  `ECC_HOOK_PROFILE=minimal` must be present for Edit/Write to be permitted (CONTRIBUTING).

## Implementation Steps

### Step 1: New module `src/claudekit/cli/fleet.py`
- **File:** `src/claudekit/cli/fleet.py`
- **Action:** Create
- **Description:** Discovery + the four verbs.
- **Details:**
  - `discover(root, include, exclude, source)` — immediate children of `--root` only; keep a
    child iff `<child>/.claude/.claudekit-manifest.json` is a file; skip the source repo, any
    path containing `.bak-`, and any git worktree whose `gitdir:` pointer resolves inside the
    source repo; `--include`/`--exclude` are `fnmatch` globs on the directory name.
  - `_branch(repo)` — reads `.git/HEAD` (directory or `gitdir:` file form). No subprocess.
  - `_fleet_list` — one row per repo: name, branch, manifest version/mode, source hash
    prefix, dirty (modified+missing) count.
  - `_fleet_diff` — per repo the `cmd_diff` three-way classification
    (`locally modified` / `kit-updated` / `both changed` / `missing` / `custom`) reduced to
    counts plus the explicit list of locally-modified paths.
  - `_fleet_update` — snapshots every managed file's hash, calls
    `main.cmd_update(Namespace(target=repo, yes=True))` (which backs up and preserves exactly
    as today), re-snapshots, and prints `written / preserved / skipped` per repo. `--dry-run`
    is a real plan: it reports which files *would* be overwritten and which custom files would
    be preserved, without calling `cmd_update`. Non-dry, non-`--yes` runs list the repos and
    ask once for confirmation. Returns 1 if any repo's update returned non-zero.
  - `_fleet_verify` — for every manifest-owned path: missing => drift; current == manifest
    hash but != kit source hash => drift (stale, untouched); current != manifest hash =>
    locally modified, allowed and counted. Paths with no kit counterpart are skipped.
    Returns 1 on any drift.
  - `cmd_fleet(args)` dispatches on `args.action`.

### Step 2: Wire the command into the CLI
- **File:** `src/claudekit/cli/main.py`
- **Action:** Modify
- **Details:** (a) a thin `cmd_fleet(args)` wrapper above `cmd_eval` that imports
  `claudekit.cli.fleet` lazily (keeps import cost off every other verb and avoids a cycle);
  (b) a `fleet` subparser inserted before the `# eval` parser with
  `action`, `--root`, `--include`, `--exclude`, `--yes`, `--dry-run`; (c) `"fleet": cmd_fleet`
  in the `commands` dispatch dict.

### Step 3: Tests
- **File:** `tests/test_cli_fleet.py`
- **Action:** Create
- **Details:** Follows `tests/test_cli.py`: `sys.path`-inserted import of the module, a fake
  kit source under `tmp_path` exported via `CLAUDEKIT_HOME`, fake installs built from that
  source. Cases: discovery skips non-kitted dirs / `.bak-` dirs / the source repo; include and
  exclude globs; `list` prints each repo; `verify` returns 0 when the fleet matches source;
  **`verify` returns 1 when drift is planted** (file content stale, manifest hash updated to
  match it, so it is untouched-but-outdated); `verify` tolerates a locally-modified file;
  `update --dry-run` never calls `cmd_update` and writes nothing.

### Step 4: Docs + CHANGELOG
- **Files:** `docs/cli.md` (new `### claudekit fleet ...` section after `update`),
  `CHANGELOG.md` (`[Unreleased]` bullet).
- **Details:** `docs/` component counts are generator-owned, but `gen-docs.py` counts
  agents/commands/skills assets — a CLI subcommand changes none of them, so no count is
  hand-edited and **no `run_command` op is needed** (and `python3` is not on the executor's
  run_command allowlist anyway). `python3 scripts/gen-docs.py --check` is run as a validation
  step instead.

## Testing Strategy
- `python3 -m pytest tests/test_cli_fleet.py tests/test_cli.py -q` then the full suite.
- Negative control: the drift test must fail before the drift is planted — confirm by
  running the clean-fleet case and the drift case and seeing 0 then 1.
- `ruff check src/ tests/`, `mypy`, `python3 scripts/gen-docs.py --check`,
  `python3 scripts/gen-registry.py --check`, `ck doctor --strict`.
- Manual smoke: `ck fleet list --root ~/IdeaProjects` and `ck fleet update --dry-run`.

## Rollback Plan
- Delete `src/claudekit/cli/fleet.py` and `tests/test_cli_fleet.py`; revert the three edits in
  `main.py`, the `docs/cli.md` section and the CHANGELOG bullet. No data migration, no state
  file, so rollback is a pure `git checkout`.

## Risk Assessment
- **Low:** docs/CHANGELOG text; `list`/`diff`/`verify` are read-only.
- **Medium:** `fleet update` multiplies `cmd_update`'s blast radius across every discovered
  repo. Mitigations: discovery is manifest-gated, `--dry-run` is a real plan, non-`--yes`
  runs confirm once with the repo list printed, each repo keeps `cmd_update`'s own backup,
  and no git mutation is ever performed.
- **Medium:** `main.py` is a hub file; the edits are additive (one wrapper, one parser, one
  dict entry) and do not alter any existing verb.
- **UNVERIFIED:** `.claude/project-graph.json` hub query not run (graph not consulted in this
  worktree); `main.py` is treated as a hub by inspection (2874 lines, 20 dispatch entries).
- **UNVERIFIED:** rejection-brief search not run — Bash access is scoped to the ops validator
  in this spawn, so a miss here is unknown, not evidence of absence.
