# Implementation Plan: Graph Phase 2 — `render`

**Parent plan:** `.claude/plans/plan-graph-render-diff.md` (Phase 2 only)
**Ops config:** `.claude/plans/plan-graph-p2-render.ops.json`
**Branch:** `feat/graph-render-diff`

## Phase 0 — design precheck

The change assumes the existing ownership model unchanged: the LLM owns *claims*
(nodes/edges), the script owns *facts* (hashes, LOC) and *judgment* (validation,
queries). `render` adds no new authority — it is a pure function `validated IR ->
text`. All of its value sits in one file, `.claude/operations/scripts/project-graph.py`,
plus its behavioural twin `tests/test_project_graph.py`; both are covered by the ops.
There is no data model to migrate, no persisted artifact (`--out` writes a
caller-named file, never `.claude/project-graph.json`), and no new trust boundary:
the rendered HTML is inert, offline, and derived only from data the graph already
contains.

**Rejection-brief search:** `review-record.py rejections search "graph render mermaid
html subcommand"` -> exit 3, no match. Silence is not evidence; treated as unknown.

**Project graph:** `.claude/project-graph.json` does not exist in this repo, so no
hub/blast-radius query was possible (`load_graph` returns None). Blast radius assessed
by hand: the script is invoked by `.claude/hooks/session-start.sh` (`stale` only) and
by the `codebase-mapping` skill; neither path is touched.

---

## Overview

Add a `render` subcommand to `project-graph.py` that emits either a Mermaid
`flowchart LR` or a single self-contained HTML page from the stored graph, bounded by
`--focus`/`--depth`/`--kind`/`--min-confidence`, and refusing to draw a graph that
would fail Phase 1's `verify` unless `--allow-unverified` is passed.

## Scope

- **In scope:** `.claude/operations/scripts/project-graph.py` (docstring, imports, two
  helper extractions, the render section, the subparser); `tests/test_project_graph.py`
  (one new `TestRender` class + docstring contract line).
- **Out of scope:** Phase 1 (`verify`), Phase 3 (`diff`), Phase 4 (`impact`), Phase 5
  (skill/agent wiring, CHANGELOG, `.ai/`). No hook, no `settings.json`, no installer,
  no component counts, no security surface, no new dependency.

## Prerequisites — the Phase 1 coupling (READ THIS FIRST)

`cmd_render` calls **`collect_violations(graph, root, strict=False) -> List[str]`**.
**Phase 1 owns that definition; this plan deliberately does NOT define it.** Applying
these ops alone leaves the module with an undefined name:

```
F821 Undefined name `collect_violations`  project-graph.py:744  (verified with ruff)
```

That is the *only* defect introduced by ordering; with a stub in place the module is
ruff-clean, mypy-clean, and the full test file passes (43 passed, verified in a
simulation copy). **Phase 1's ops must be applied before Phase 2's**, or the two must
land in the same commit.

Contract Phase 2 relies on (assumptions, each stated again in the handoff report):

| # | Assumption about Phase 1's helper | Consequence if wrong |
|---|---|---|
| A1 | Named exactly `collect_violations`, module-level, in this same file | `NameError`/F821 |
| A2 | Signature `(graph: dict, root: Path, strict: bool = False) -> List[str]` — `strict` defaulted, so Phase 2 may omit it | TypeError at call time |
| A3 | Returns `[]` for a clean graph; a non-empty list means "do not render" | Refuses valid graphs, or renders invalid ones |
| A4 | Each string is a one-line, human-readable violation naming the offending node id | `test_refuses_unverified_graph_unless_overridden` asserts `"src/d.py" in stderr` |
| A5 | It is a **pure query** — reads the graph and the filesystem, prints nothing, never exits | Render output would be polluted / process killed |
| A6 | A file-backed node whose path no longer exists is a violation in non-strict mode | The refusal test cannot construct a failing graph |
| A7 | The graph built from `sample_input()` (a.py textually imports b and c) is clean in non-strict mode | `test_clean_graph_renders_without_the_override` fails |

## Implementation Steps

### Step 1 — module docstring (op 1)
- **File:** `.claude/operations/scripts/project-graph.py` · **Modify**
- Add `render` to the subcommand list; extend the exit-code table so `1` covers
  "render over a graph that fails verify without `--allow-unverified`".

### Step 2 — imports and one constant (op 2)
- `import math` (ring layout), `from html import escape` (SVG text/attribute escaping),
  `typing.Set`, and `DEFAULT_RENDER_DEPTH = 2`.

### Step 3 — extract the two traversal/counting helpers (op 3)
- `cmd_path`'s inline adjacency build -> `adjacency_map(graph, undirected=False)`.
- `cmd_hubs`'s inline fan tally -> `fan_counts(graph)`.
- **Why:** the spec forbids a second BFS. `path` walks *edge trails* ("how does A reach
  B"); render needs a *ball of radius N* ("what sits near X") — different outputs, but
  they now share one adjacency builder, and `god_nodes()` shares `hubs`' exact flag
  rule so the diagram can never disagree with the ranking.

### Step 4 — the render section (op 4, inserted above `build_parser`)
- `god_nodes(graph, threshold=DEFAULT_THRESHOLD) -> Set[str]` — same rule as `hubs`.
- `nodes_within(graph, start, depth) -> Set[str]` — the single ball-BFS, undirected.
- `select_subgraph(graph, focus, depth, kind, min_confidence)` — focus ball, then kind
  filter (the focus node always survives its own diagram), then the confidence floor;
  edges are kept only when both endpoints survive, so no dangling edge is ever drawn.
- `render_mermaid` — `flowchart LR`; node shape by kind (`MERMAID_SHAPE`); arrow by
  confidence (`-->` / `-.->` / `-.->|?|`); god-nodes get `classDef god` + a `class` line.
  Node ids are aliased to `n0…nN`, so arbitrary path characters can never break syntax.
- `circular_layout` / `render_html` — deterministic ring layout computed in Python, SVG
  emitted server-side; `HTML_TEMPLATE` is 67 lines (budget ~120). One page: inline SVG,
  a `<script type="application/json">` island, click-to-highlight-neighbours, a text
  filter, `prefers-color-scheme` theming. No CDN, no framework, no URL of any kind —
  the SVG is inline HTML5 so it needs no `xmlns`. `</` inside the island is escaped.
- `cmd_render` — no graph -> 3; verify gate -> 1; ambiguous `--focus` -> 0 with
  candidates, unknown -> 3; `--out` write failure -> 2; otherwise stdout.

### Step 5 — subparser (op 5)
`render [--format mermaid|html] [--focus NODE] [--depth N] [--kind K]
[--min-confidence TIER] [--out PATH] [--allow-unverified]`.

### Step 6 — behavioural tests (op 6)
New `TestRender` class in `tests/test_project_graph.py`, all via subprocess against the
real script, plus one contract line in the module docstring.

## Testing Strategy

Fixture: 4 file nodes with one edge per confidence tier and a genuine 2-hop node
(`a -extracted-> b -ambiguous-> d`, `a -inferred-> c`).

1. mermaid emits exactly one line per edge, one `-->`, one `-.->`, one `-.->|?|`.
2. `--focus src/a.py --depth 1` includes `b`, excludes the 2-hop `d`.
3. `--depth 2` includes `d` (proves 2 is a bound, not a filter bug).
4. `--min-confidence extracted` leaves exactly the one extracted arrow.
5. A 30-leaf star emits `classDef god` and a `class … god;` line.
6. `--format html --out` writes a file with no `http://`, no `https://`, an inline
   `<svg`, the JSON island, `prefers-color-scheme`, and exactly two `<script` tags.
7. The island round-trips through `json.loads` with all 3 edges.
8. A clean graph renders with exit 0 and no override (A7).
9. Deleting a file-backed node's file makes `render` exit 1 naming it; `--allow-unverified`
   then exits 0 and still draws it.
10. No graph -> 3; unknown `--focus` -> 3.

Tests that are about *rendering* pass `--allow-unverified` so they stay independent of
Phase 1's violation wording; only tests 8 and 9 exercise the gate.

**Mutation proof (all four verified RED in a simulation copy):** collapse
`MERMAID_ARROW` to one arrow · replace the `dist >= depth` bound with `>= 99` ·
short-circuit the verify gate to `if False:` · lift the confidence floor to `99`.

**Simulation evidence (scratch copy, ops applied mechanically):** every `find` matched
exactly once · `py_compile` OK · `ruff check --line-length 100 --target-version py39`
clean (with the Phase 1 stub) · `mypy --python-version 3.9` clean · `pytest -k Render`
11 passed · whole file 43 passed.

## Rollback Plan

Single-commit revert. Ops 1, 2, 4, 5 and both test edits are pure additions — deleting
the added blocks restores the prior file byte-for-byte. Op 3 is the only in-place
change; to undo it, inline `adjacency_map(graph)` back into `cmd_path` and
`fan_counts(graph)` back into `cmd_hubs` (both bodies are quoted verbatim in the ops
`find` fields).

## Risk Assessment

- **High:** ordering against Phase 1. Landing Phase 2 alone breaks `ruff`/`mypy` on
  `collect_violations` (F821, verified). Mitigation: sequence Phase 1 first, or squash.
- **Medium:** docstring anchor collision — Phase 1 will almost certainly edit the same
  subcommand list and exit-code lines. If Phase 1 lands first, both `find` strings in
  op 1 must be re-anchored before applying (`validate-config-json.py` catches this: it
  checks find patterns against the current file).
- **Medium:** op 3 refactors two *covered* code paths (`hubs`, `path`). Behaviour is
  identical and the existing `TestHubs`/`TestPath` tests are the proof; they passed
  unchanged in simulation.
- **Low:** HTML self-containment regressing later — asserted by test 6, not by eye.
- **Low:** context floor / gen-docs — no component counts, no skill prose touched.

## Definition of Done

`pytest -q` · `ruff check` · `mypy` · `gen-docs --check` · `gen-registry --check` ·
`gen-model-policy --check` · `check-context-floor --check` · `shellcheck` all green
(after Phase 1 lands) · adversarial `code-reviewer` pass on the diff.
