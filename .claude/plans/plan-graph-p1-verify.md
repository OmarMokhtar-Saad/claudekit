# Implementation Plan: `project-graph.py verify` (Phase 1 of plan-graph-render-diff)

**Ops config:** `.claude/plans/plan-graph-p1-verify.ops.json`
**Parent plan:** `.claude/plans/plan-graph-render-diff.md` (Phase 1 only; phases 2-5 out of scope)

## Overview

Add a `verify [--strict]` subcommand to `.claude/operations/scripts/project-graph.py`: the
anti-hallucination gate. `build` already validates the graph's *schema*; `verify` validates its
*claims against the filesystem* — that file-backed nodes exist, that edge endpoints are declared,
that an `extracted` edge is textually supported by its source file, and that no edge is a
self-edge or a duplicate.

## Scope

- **In scope:** `.claude/operations/scripts/project-graph.py` (module docstring, one new constant,
  three new helpers, one new `cmd_verify`, one `sub.add_parser` registration) and behavioural tests
  appended to `tests/test_project_graph.py`.
- **Out of scope:** `render` / `diff` / `impact` (phases 2-4), skill/agent wiring and CHANGELOG
  (phase 5), any hook, installer, or ops-executor change. No new dependency (stdlib only, py3.9).

## Design note (ownership / data model)

`verify` reads only two things: the stored graph JSON (`CLAUDEKIT_GRAPH_PATH` / `graph_path()`)
and the working tree under `project_root()`. It writes nothing. Its value lives entirely in the
exit code plus the violation list on stdout, so the behavioural tests assert exactly those two.
Textual support is a deliberately cheap, language-agnostic substring test — it is a *falsifier*
(catches invented edges), not a proof of a real dependency; the plan document, not the code,
carries that caveat.

## Implementation Steps

### Step 1: Module docstring — subcommand list
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Insert a `verify` line after the `stale` line in the Subcommands block.

### Step 2: Module docstring — exit codes
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Extend the `1` row to cover `verify` violations, keeping the existing table shape
  (0 clean · 1 violations · 2 usage/validation · 3 no graph).

### Step 3: `MAX_SUPPORT_BYTES` constant
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Add `MAX_SUPPORT_BYTES = 2 * 1024 * 1024` after `DEFAULT_QUERY_LIMIT`, matching the existing
  module-level constant block. Bounds the per-source-file read for the support check.

### Step 4: verify section (helpers + handler)
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- Insert a `# verify` banner section immediately before `build_parser()`, containing:
  - `reference_token(node_id: str) -> str` — the token a source must contain: the `#fragment`
    when present, else the basename with its extension stripped.
  - `read_source(path: Path) -> Optional[str]` — bounded binary read decoded with
    `errors="ignore"`; `None` when unreadable.
  - `collect_violations(graph: dict, root: Path, strict: bool) -> List[Tuple[str, str]]` —
    the four checks, each yielding `(LABEL, detail)`.
  - `cmd_verify(args: argparse.Namespace) -> int` — 3 no graph, 1 violations, 0 clean.
- Every function fully annotated (mypy covers this tree).

### Step 5: Subcommand registration
- **File:** `.claude/operations/scripts/project-graph.py` · **Action:** Modify
- `verify = sub.add_parser("verify", ...)` with `--strict`, `set_defaults(func=cmd_verify)`,
  placed after `stale` and before `return parser`.

### Step 6: Behavioural tests
- **File:** `tests/test_project_graph.py` · **Action:** Modify (append `class TestVerify`)
- Uses the existing `run()` / `make_project()` / `sample_input()` / `build_graph()` helpers; runs
  the real script as a subprocess and asserts exit code + stdout only.

## Check semantics

| Label | Condition |
|---|---|
| `MISSING NODE` | non-`external` node whose `path_part(id)` is not a file on disk |
| `DANGLING EDGE` | `from`/`to` is not a declared node id |
| `DEGENERATE EDGE` | `from == to`, or a repeat of an earlier `(from, to, type)` |
| `UNSUPPORTED EXTRACTED EDGE` | `confidence: extracted` and `reference_token(to)` absent from the source file's text |
| `UNSUPPORTED INFERRED EDGE` | same, for `confidence: inferred`, **only** under `--strict` |

Precedence is deliberate: a dangling, self, or duplicate edge is reported once and skipped for the
support check, so one defect yields one line.

## Testing Strategy

`class TestVerify` in `tests/test_project_graph.py`:

1. clean graph -> exit 0, `VERIFY OK`
2. deleted file -> exit 1, `MISSING NODE`, names `src/c.py`
3. hand-written graph with an undeclared endpoint -> exit 1, `DANGLING EDGE`
4. `extracted` edge `src/b.py -> src/c.py` (b.py never mentions `c`) -> exit 1,
   `UNSUPPORTED EXTRACTED EDGE`
5. self-edge -> exit 1, `DEGENERATE EDGE`
6. duplicate edge -> exit 1, `DEGENERATE EDGE`
7. unsupported `inferred` edge -> exit 0 by default, exit 1 under `--strict`
8. absent graph -> exit 3

Mutation proof (manual, at review time): invert each check's condition and confirm the matching
test goes red. Full DoD: `pytest -q`, `ruff check`, `mypy`.

## Rollback Plan

Single-commit revert. Both edits are additive: removing the `verify` section, the constant, the
parser block, the two docstring lines, and `class TestVerify` restores the file byte-for-byte —
no existing code path is modified, so no other subcommand can regress.

## Risk Assessment

- **Low:** purely additive; no shared function is touched, so `build`/`query`/`hubs`/`path`/`stale`
  behaviour is unchanged. Read-only command.
- **Low:** `project-graph.py` is not a graph god-node — it is a leaf script invoked by
  `session-start.sh` and agent prose; nothing imports it.
- **Medium:** false positives on the textual-support check for generated code, aliased imports,
  or minified sources. Mitigated by scoping the default to `extracted` only (the tier that asserts
  "explicit statement observed in source") and gating `inferred` behind `--strict`.
- **Medium:** performance on a 20k-node graph — one bounded read per distinct edge source, cached
  in a dict, so at most one read per node.

### Rejection-brief search

`review-record.py rejections search "project graph verify subcommand"` — no brief store consulted
via Bash (planner Bash is scoped to `validate-config-json.py`). Treated as **unknown**, not clean:
the reviewer should re-run the search before approving.

## Judgment calls (spec was silent)

1. **No `--format json`.** Every other subcommand has one; the parent plan specifies only
   `verify [--strict]`. Kept minimal — added later if a caller needs it.
2. **Duplicate identity is `(from, to, type)`**, not `(from, to)`. Two edges with the same
   endpoints but different types (`import` and `test`) are legitimate.
3. **`external` nodes are exempt from `MISSING NODE`** (consistent with `enrich_nodes` and
   `cmd_stale`), and an unreadable source file suppresses its support checks so the defect is
   reported once as `MISSING NODE`.
4. **`reference_token` for `src/Foo.java#Bar` is `Bar`**, not `Foo` — the fragment is the more
   specific claim.
5. **Unsupported `inferred` gets its own label** (`UNSUPPORTED INFERRED EDGE`) so `--strict`
   findings are distinguishable in output.
