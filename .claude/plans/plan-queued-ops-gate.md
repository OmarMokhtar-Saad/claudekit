# Implementation Plan: the queued-ops staleness gate scans nothing

**Status:** EXECUTED 2026-08-24. Tier 2 (one test module + a bulk archive move). **3 ops
configs** — config 03 switched the new test onto pytest's `tmp_path`, which is what every
other temporary tree in that module already uses; the first draft reached for
`tempfile.TemporaryDirectory` and a function-local import.

**The widened gate caught this plan's own configs, twice** — first `02`, then `03`, each
spent the moment it executed and each reddening the suite until archived. That is the gate
working on its first run, and it is why the archive step is now part of the loop rather
than an afterthought.

## The defect

`tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head`
is decoration. It enumerates `.claude/plans/` with `os.listdir` and keeps only entries
where `os.path.isfile(...)` and the name ends in `.json` — that is, **top-level files
only**. Every ops config in this repo lives in an `ops-<slug>/` subdirectory.

Measured on `main` at `cfc8a09`:

- **0** top-level `.json` configs in `.claude/plans/` — so the gate's input set is empty
  and it has been passing vacuously;
- **50** configs in 16 `ops-*/` subdirectories;
- **35 of those 50 already fail `validate-config-json.py`**, i.e. the exact condition the
  gate exists to report.

**Probed, not reasoned about** (the repo's own lesson, three times over this month):
an invalid config written to `.claude/plans/ops-PROBE/probe.json` leaves the test GREEN;
the byte-identical file at `.claude/plans/probe.json` turns it RED. That is the whole bug
in one experiment.

## Why the backlog exists at all

The gate is also the mechanism that would have reminded anyone to archive. Because it
never fired, 16 spent config directories accumulated in the live tree, every one of them
already executed:

| Directory(ies) | Configs | Executed in |
| --- | --- | --- |
| `ops-008-b3c1` … `ops-008-b3c7` | 41 | the seven batch-3 cluster commits, `775abd4`..`15075ac` |
| `ops-b3c2-disclosure`, `ops-b3c2-scan` | 2 | `15075ac` |
| `ops-b3c7-newline` | 1 | `cc7fb35` |
| `ops-findings-lane-a`, `ops-findings-lane-b` | 2 | `24144f0` |
| `ops-findings-lane-a-r2`, `ops-findings-lane-a-r2-tests`, `ops-findings-lane-b-docs`, `ops-findings-changelog` | 4 | `9c85238` |

Every one has a `backups/` directory from its own execution and landed in the commit that
did the work, so "spent" is established by evidence rather than by inference from the 35
validation failures. The 15 that still validate are spent too — a config whose anchors
happen to survive its own edit is not a queued config.

## Order matters

Widening the gate first turns the suite red on 35 pre-existing failures, which is how a
gate gets reverted instead of fixed. So: **archive first, widen second, in one commit.**

| # | Step | How |
| --- | --- | --- |
| A | Move the 16 spent directories to `.claude/plans/archive/` | `git mv` — see "Outside the engine" |
| B | One archive README row per group | ops config `01-archive-rows` |
| C | Widen the scan and prove the widening binds | ops config `02-widen-gate` |
| D | Match the module's `tmp_path` idiom | ops config `03-tmp-path-idiom` |

## Outside the engine, disclosed

Step A is 16 directory renames, not content edits. The operations engine has no move
operation, and expressing a move as delete+create would need 50 deletions against a
`MAX_DELETIONS=3` limit that exists precisely to stop bulk deletion — so `git mv` is the
right tool and the constraint is not being routed around. **No file content changes in
step A**, which `git show --stat` on the commit will confirm (pure renames).

## What step C actually changes

`_queued_ops_configs(plans_dir)` walks the tree, prunes `archive/` **by name** (spent
configs belong there — that is the point), and returns every `*.json` beneath. The
repo-wide assertion then runs over that set.

The widening is proven by a **second test that does not touch the repo**:
`test_the_queued_ops_scan_reaches_subdirectories` builds a throwaway plans tree holding
`ops-x/bad.json` and `archive/ops-y/bad.json`, and asserts the helper returns the first
and not the second. Without the walk, that test is red. A gate whose own coverage depends
on the repo happening to contain a violation is the failure mode this plan is fixing, so
the proof is constructed rather than borrowed.

## Not in scope

- The 3 `drifted` plans and the `not_started` plans `gen-plan-index.py` reports. Different
  gate, different evidence, and none of them is this defect.
- Any judgement about whether the 35 stale configs' *content* was correct. They executed;
  their plans and archive rows own that story.

## Mutation proofs, run against the shipped file

| Mutant | Result |
| --- | --- |
| `_queued_ops_configs` reverted to the top-level-only `os.listdir` scan | `test_the_queued_ops_scan_reaches_subdirectories` RED |
| the `archive/` prune removed from the walk | same test RED |
| shipped version | 6 passed, 1 skipped |

Both halves of the contract bind. Under mutant 1 the repo-wide gate stays GREEN, which is
the original defect reproduced on demand: **the constructed test is the only thing that can
see it.**

## Adversarial review — NOT performed

`CLAUDE.md`'s review floor asks for a fresh `code-reviewer` on every diff before merge.
This session was instructed not to spawn agents, so that round did not happen and this
change carries **no independent verdict**. Recorded here rather than left implicit; a
reviewer should read `tests/test_delivery_contract_smoke.py` and the rename set.

## Definition of Done

The full `CLAUDE.md` gate list, re-run after committing. Plus: `git show --stat` shows
step A as renames only, and the new subdirectory test is red against the old helper.
