# Implementation Plan: Phase 4 — `project-graph.py impact`

**Parent plan:** `.claude/plans/plan-graph-render-diff.md` (Phase 4 only)
**Ops config:** `.claude/plans/plan-graph-p4-impact.ops.json`
**Branch context:** phases 1-3 are planned in parallel against the same file.

## Overview

Add an `impact --ops PLAN.ops.json` subcommand to
`.claude/operations/scripts/project-graph.py`. It maps every `path` in an ops.json to a
graph node and reports fan-in, fan-out, god-node flag and whether the touched set spans
more than one top-level package. Exit 1 means "architecture touched — route to
`reviewer`", replacing the judgment call in CLAUDE.md's Tier-2 rule with a computed answer.

## Ownership / data model (Phase 0)

The value of this change lives in exactly two files: the script (the decision function) and
its behavioural test module. The graph itself (`.claude/project-graph.json`) is generated
runtime state, deliberately not committed — `impact` therefore has to behave sanely when the
graph is absent (exit 3) or incomplete (UNKNOWN, see below). No hook, installer, schema or
security surface is touched. Rejection-brief search:
`review-record.py rejections search "project-graph impact ops blast radius"` — no store of
briefs applies to a new subcommand on this script; treated as unknown, not as clearance.

## Scope

- **In scope:** `.claude/operations/scripts/project-graph.py` (new subcommand + two small
  shared helpers), new `tests/test_project_graph_impact.py`.
- **Out of scope:** phases 1, 2, 3 and 5 of the parent plan (`verify`, `render`, `diff`,
  agent/SKILL wiring, CHANGELOG). No new dependency; stdlib only, py3.9, fully annotated.

## Parallel-edit safety

Every edit is anchored to a **distinct, stable region**, chosen so phases 1-3 (which add
their own subcommands) do not collide:

| # | Anchor (verbatim, `grep -cF` == 1) | Mode |
|---|---|---|
| 1 | `  stale    re-hash file-backed nodes; report what changed since mapping` | `add_after` (docstring subcommand list) |
| 2 | `  3  no graph file, or query/path found no match -> caller falls back to grep` | `add_after` (exit-code table) |
| 3 | `        god = total >= args.threshold or (fan_in[node_id] >= GOD_FAN_IN and loc >= GOD_LOC)` | `replace` (single line inside `cmd_hubs`) |
| 4 | `    print("Re-map the listed files and run: project-graph.py build --merge --input -")\n    return 1` | `add_after` (end of `cmd_stale`) |
| 5 | the three-line `stale = sub.add_parser(...)` block in `build_parser` | `add_after` |

No edit touches the `typing` import line, `build_parser`'s `return parser`, or any region a
sibling phase would naturally own. Anchor 3 is the *only* touch inside an existing function
and is a one-line substitution.

## UNKNOWN-path policy (explicit)

A path present in the ops.json but absent from the graph is **not** evidence of low impact —
it means the graph does not know the file (never mapped, newly created, or stale). Silence is
not evidence. Handling:

1. The row is printed with `UNKNOWN` and dashes for fan-in/fan-out/loc (never zeros — zeros
   would read as "leaf").
2. In JSON output it appears under `"unknown"` and its metric fields are `null`.
3. Any UNKNOWN path forces **exit 1** (escalate), listed in the verdict reason.

`file_create` operations therefore always escalate. That is the correct default: a new file
is by definition unmapped and its coupling is unknown until someone looks. If this proves
noisy in practice, the fix is to re-map before planning (`build --merge`), not to soften the
gate.

## Implementation Steps

### Step 1: docstring subcommand list
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Add `  impact   blast radius of a plan's ops.json; exit 1 = route to reviewer`.

### Step 2: exit-code table
- Add a line documenting `impact`'s exit-1 semantics (hub, cross-package, or UNKNOWN path)
  and exit 2 (unreadable ops.json) / 3 (no stored graph).

### Step 3: shared god-node predicate
- Replace the inline `god = ...` expression in `cmd_hubs` with `is_god_node(...)`. The
  thresholds (`GOD_FAN_IN`, `GOD_LOC`, `--threshold`) stay in one place; `impact` calls the
  same function, so the two commands can never disagree.

### Step 4: the `impact` implementation
Inserted after `cmd_stale`:
- `is_god_node(fan_in, fan_out, loc, threshold=DEFAULT_THRESHOLD) -> bool`
- `fan_counts(graph) -> Tuple[Dict[str, int], Dict[str, int]]`
- `top_package(rel) -> str` — first path segment
- `read_ops(source, root) -> Tuple[Optional[dict], Optional[str]]` — **same guards as
  `build`**: reject anything resolving outside the project root, refuse files over
  `MAX_INPUT_BYTES` (stat *and* decoded length, matching `read_input`'s two-stage check),
  and turn JSON/OS errors into a message the caller turns into exit 2.
- `ops_paths(data) -> Tuple[List[str], Optional[str]]` — ordered, de-duplicated `path`
  values; operations without a `path` (`run_command`) are skipped; malformed entries error.
- `cmd_impact(args) -> int` — each collected path is additionally run through the existing
  `invalid_path_reason` (the same traversal check `build` applies to node ids) before it is
  used; then node lookup, metrics, verdict.

### Step 5: parser wiring
- `impact` subparser: `--ops` (required), `--threshold` (default `DEFAULT_THRESHOLD`),
  `--format text|json`.

### Step 6: behavioural tests
- **File:** `tests/test_project_graph_impact.py` (new — a separate module so parallel phases
  extending `tests/test_project_graph.py` cannot conflict).

## Testing Strategy

All via `subprocess` against the real script, with `CLAUDEKIT_PROJECT_ROOT` /
`CLAUDEKIT_GRAPH_PATH` pointed at a temp project (the existing module's pattern):

1. ops.json touching a god-node → exit 1, `GOD-NODE` in output.
2. ops.json touching one leaf file in one package → exit 0.
3. ops.json naming a path absent from the graph → exit 1, `UNKNOWN` in output, and the
   metrics are dashes, not zeros.
4. Malformed JSON → exit 2; missing file → exit 2; `../` traversal → exit 2.
5. No stored graph → exit 3.
6. Two top-level packages, both leaves → exit 1 (cross-boundary).
7. `--format json` emits `escalate`, `unknown`, `god_nodes`.
8. Mutation proof (manual, recorded in review): flip `escalate` to `False` and assert 1, 3
   and 6 go red.

Gates: `python3 -m pytest tests/test_project_graph_impact.py -q`, `ruff check
.claude/operations/scripts/project-graph.py tests/`, `mypy`.

## Rollback Plan

Revert the commit, or: delete `tests/test_project_graph_impact.py`, delete the `impact`
block after `cmd_stale`, the `impact` subparser block, the two docstring lines, and restore
the inline `god = total >= args.threshold or (...)` expression in `cmd_hubs`.

## Risk Assessment

- **Low:** docstring lines; new test module; new subcommand (purely additive, no existing
  exit code changes).
- **Medium:** the `cmd_hubs` one-line substitution — it is the only shared-behaviour edit;
  `tests/test_project_graph.py::TestHubs` covers it and must stay green. Also medium: merge
  conflict with parallel phases 1-3 in `build_parser` / after `cmd_stale`; anchors are
  distinct but the regions are adjacent, so land phases in order and re-validate.
- **High:** none. `project-graph.py` is not a GOD-NODE consumer of other modules and nothing
  imports it (standalone script invoked by subprocess).
