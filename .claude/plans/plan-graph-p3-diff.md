# Implementation Plan: Phase 3 — `project-graph.py diff`

**Parent plan:** `.claude/plans/plan-graph-render-diff.md` (Phase 3 only)
**Ops config:** `.claude/plans/plan-graph-p3-diff.ops.json`
**Branch context:** Phases 1, 2 and 4 are planned in parallel against the same two files.

## Overview

Add a `diff --against OTHER.json [--format text|mermaid]` subcommand that reports the
structural delta between a comparison graph and the stored graph: `+node`, `-node`,
`~node` (stored hash changed), `+edge`, `-edge`. Before/after on architecture, not on text.

## Design precheck (ownership / data model)

The graph is a single stored artifact (`graph_path()`), owned and validated by this script;
the agent never supplies hashes. `diff` adds no state: it is a pure function of
(stored graph, `--against` graph). All the value sits in
`.claude/operations/scripts/project-graph.py` and its behavioural test file — both covered.
The one new trust boundary is `--against`, which is attacker-adjacent input; it therefore
goes through the *same* gauntlet `build` applies (path confinement, `MAX_INPUT_BYTES`,
`validate()` which enforces `MAX_NODES`/`MAX_EDGES`, kinds, confidence tiers and
`invalid_path_reason` on every node id). No guard is weakened or bypassed.

Rejection-brief search: `review-record.py rejections search "project-graph diff subcommand"`
is not runnable from this role's Bash scope (validator-only); no prior brief is known for
this surface. Treated as unknown, not as evidence of safety.

## Scope

- **In scope:** `.claude/operations/scripts/project-graph.py` (docstring subcommand list,
  exit-code table, new diff section, parser registration), `tests/test_project_graph.py`.
- **Out of scope:** Phases 1/2/4 (`verify`, `render`, `impact`), SKILL.md and agent routing,
  CHANGELOG/`.ai/` updates (Phase 5 owns those), any hook or install surface.

## Prerequisites

None. `diff` reuses `load_graph`, `validate`, `invalid_path_reason`, `node_index`,
`project_root`, `graph_path`, `err`, and the existing size constants.

## Implementation Steps

### Step 1: docstring subcommand list
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Add `diff     structural delta between the stored graph and another graph JSON`
  after the `stale` line.

### Step 2: docstring exit-code table
- **File:** same · **Action:** Modify
- After the exit-code `3` line, add the diff-specific mapping: 0 identical, 1 differences
  found, 2 unreadable/invalid `--against`, 3 no stored graph.

### Step 3: the diff section
- **File:** same · **Action:** Modify (insert after `cmd_stale`'s final `return 1`)
- New, fully annotated:
  - `EdgeKey = Tuple[str, str, str, str]`, `MERMAID_ID_RE`, `MERMAID_ID_MAX`,
    `MAX_REPORTED_PROBLEMS`.
  - `resolve_against(source, root)` — absolute paths are relativised against the real root;
    the result goes through `invalid_path_reason`, so `..`, drive letters, backslashes,
    absolute paths and anything escaping the root are refused.
  - `read_against(source, root)` — `st_size` pre-check *and* encoded-length post-check
    against `MAX_INPUT_BYTES`, JSON parse, top-level-object check. Mirrors `read_input`
    exactly; it is a sibling rather than a shared edit so Phase 4 (`impact`, which reads
    ops.json) does not collide on `read_input`.
  - `edge_key` / `edge_index` — edge identity is `(from, to, type, confidence)`, so a
    retiering shows as a `-edge`/`+edge` pair rather than vanishing.
  - `diff_graphs(before, after)` — sorted, deterministic delta dict; `~node` compares the
    stored `hash` field of nodes present in both.
  - `describe_edge`, `mermaid_diff` — `flowchart LR` with three `classDef`s
    (`added` green, `removed` red dashed, `changed` amber); added edges render `-->|+ type|`,
    removed edges `-.->|- type|`, so a reviewer sees the shape of the change.
  - `cmd_diff` — stored graph missing → 3; `--against` unreadable/invalid JSON/not an
    object → 2; `validate()` problems on `--against` → 2 (first 20 reported); no changes → 0;
    otherwise the delta report → 1.

### Step 4: parser registration
- **File:** same · **Action:** Modify (insert after the `stale` subparser block)
- `diff` subparser with `--against` (required) and `--format {text,mermaid}` (default text).

### Step 5: behavioural tests
- **File:** `tests/test_project_graph.py` · **Action:** Modify (insert after `TestStale`)
- `TestDiff`, 9 subprocess tests: identical → 0; added edge → 1 and a `+edge` line naming
  `src/b.py -> src/c.py`; removed node + hash change → `-node`, `~node`, `-edge`; mermaid
  emits `:::added`, `-->|+ import|`, `-.->|- import|`; malformed `--against` → 2;
  wrong-`version` `--against` → 2; missing file → 2; `../escape.json` → 2; no stored
  graph → 3. `--against` snapshots are written *inside* the temp project because the flag
  is root-confined by design.

## Testing Strategy

`python3 -m pytest tests/test_project_graph.py -q` (verified green in a simulated tree:
9 passed). Plus the repo DoD gates: `ruff check` (line-length 100) and `mypy`
(`python_version=3.9`, `check_untyped_defs=true`) — both verified clean on the simulated
post-edit file. Mutation proof before commit: delete the `invalid_path_reason` call in
`resolve_against` and assert `test_traversal_against_rejected` goes red; make
`cmd_diff` always `return 0` and assert the added-edge test goes red.

## Rollback Plan

`git checkout -- .claude/operations/scripts/project-graph.py tests/test_project_graph.py`.
The change is purely additive: no existing function, constant, or subcommand is modified,
so reverting cannot strand another phase's edits.

## Risk Assessment

- **Low:** additive subcommand; no shared function bodies edited; no new dependency; no
  runtime state; `mypy`/`ruff` verified on the simulated result.
- **Medium — merge collision with Phases 1/2/4.** All four phases edit the same two files.
  This plan deliberately anchors on `stale`-owned regions (see anchor list in the handoff)
  and inserts a self-contained section, so the only true collision risk is another phase
  choosing the *same* stale anchors. Merge order: apply this ops file and re-grep the other
  three anchors before applying them.
- **Medium — `--against` is untrusted input.** Mitigated by reusing `invalid_path_reason`
  + `MAX_INPUT_BYTES` + `validate()` (which carries `MAX_NODES`/`MAX_EDGES`). Note the
  guard is stricter than `build --input`, which accepts any path/stdin: `--against` must
  live under the project root.
- **Low — behavioural:** `diff` never writes; worst case is a wrong exit code, which the
  tests pin.

## Definition of Done

`pytest -q` · `ruff check` · `mypy` · `gen-docs --check` · `gen-registry --check` ·
`check-context-floor --check` all green; adversarial `code-reviewer` pass; Phase 5 picks up
CHANGELOG/`.ai/` wording.
