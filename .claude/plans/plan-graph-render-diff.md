# Implementation Plan: Graph render / diff / impact — the Archify ideas, minus what we already built

**Branch:** `feat/graph-render-diff` · **Ops configs:** this parent is documentation-only; the
executable units are `plan-graph-p1-verify.ops.json`, `plan-graph-p2-render.ops.json`,
`plan-graph-p3-diff.ops.json`, `plan-graph-p4-impact.ops.json`, applied in that order.
**Source:** owner request "do them all" against the five Archify-inspired ideas.

## Overview

Archify's contribution is *not* the diagram — it is `agent emits JSON IR -> deterministic
validator gates it -> renderer is a pure function of the validated IR`. ClaudeKit already
owns two of those three stages: `.claude/operations/scripts/project-graph.py` (573 lines,
covered by `tests/test_project_graph.py`) validates agent-supplied nodes/edges, computes
hashes/LOC itself, and answers `query` / `hubs` / `path` / `stale`. The **renderer stage
does not exist**, and neither does before/after.

So idea 1 (graph IR) and most of idea 2 (validator) are shipped. This plan builds only the
gap: render, diff, impact, and a stricter `verify`.

## Scope

- **In scope:** `.claude/operations/scripts/project-graph.py` (four new subcommands),
  `tests/test_project_graph.py`, `.claude/skills/codebase-mapping/SKILL.md`,
  `.claude/agents/{explore,planner,refactor-cleaner}.md` (routing lines), `CHANGELOG.md`,
  `.ai/CHANGELOG_AI.md`, `.ai/SESSION_STATE.md`.
- **Out of scope:** any hook, `.claude/settings.json`, `install.sh`, the ops executor,
  component counts, security surface. No new runtime dependency (hard rule 8). No Node.
- **Not built, deliberately:** a committed `.claude/project-graph.json` gated in CI —
  CLAUDE.md classifies generated indexes and runtime state as *not source artifacts*
  ("re-derive, don't cite"). Freshness stays on-demand via `stale`/`verify`, not a CI diff.

---

## Phase 1 — `verify`: the validator decides the diagram is true

New subcommand `project-graph.py verify [--strict]`.

| Check | Failure |
|---|---|
| every file-backed node id resolves to an existing path | `MISSING NODE` |
| every edge endpoint is a declared node | `DANGLING EDGE` |
| every `extracted` edge's source file contains a textual reference to the target stem | `UNSUPPORTED EXTRACTED EDGE` |
| self-edges, duplicate edges | `DEGENERATE EDGE` |

Exit 0 clean · 1 violations found · 3 no graph. `--strict` promotes `inferred` edges with no
textual support to violations too. This is the anti-hallucination gate: an LLM can assert an
edge, but an unsupported `extracted` claim is now mechanically rejected.

## Phase 2 — `render`: pure function of the validated IR

`project-graph.py render [--format mermaid|html] [--focus NODE] [--depth N] [--kind K]
[--min-confidence TIER] [--out PATH]`

- **mermaid** — `flowchart LR`, confidence encoded in edge style: `-->` extracted,
  `-.->` inferred, `-.-> |?|` ambiguous. Node shape by `kind`. God-nodes get a class.
- **html** — one self-contained file: the same graph as inline SVG + a JSON island, plus
  click-to-highlight neighbours and a text filter. Stdlib string templating, no CDN, no JS
  framework. Theme-aware via `prefers-color-scheme`.
- `--focus X --depth 2` bounds output so a 20k-node graph stays legible (and cheap).

Refuses to render a graph that fails `verify` unless `--allow-unverified` is passed.

## Phase 3 — `diff`: before/after on architecture, not on text

`project-graph.py diff --against OTHER.json [--format text|mermaid]`

Reports `+node` / `-node` / `+edge` / `-edge` / `~node` (hash changed). Mermaid output
classes additions and removals so the reviewer sees the shape of the change. Exit 0 identical
· 1 differences · 2 unreadable · 3 missing graph.

## Phase 4 — `impact`: the objective Tier-2 routing trigger

`project-graph.py impact --ops PLAN.ops.json`

Maps every `path` in an ops.json to a graph node, then reports for each: fan-in, fan-out,
god-node flag, and whether the touched set spans more than one top-level package. Exits 1 —
"architecture touched, route to `reviewer`" — when any touched node is a hub or the set
crosses a module boundary; 0 otherwise. This replaces the judgment call in CLAUDE.md's
Tier-2 rule ("reviewer ONLY if architecture is touched") with a computed answer.

## Phase 5 — wiring and docs

- `codebase-mapping/SKILL.md`: a "Rendering and review" section — `verify` before trusting a
  graph, `render --format html` for a shareable page (publish it as an Artifact; that is
  idea 4, no code needed), `diff` for before/after.
- `planner.md`: run `impact` on its own ops.json and record the verdict in the plan.
- `explore.md` / `refactor-cleaner.md`: prefer `verify` before acting on a stale graph.
- CHANGELOG `[Unreleased]`, `.ai/CHANGELOG_AI.md`, `.ai/SESSION_STATE.md`.

## Testing (behavioural, per CLAUDE.md)

Extend `tests/test_project_graph.py` against the real script as a subprocess:

1. `verify` exits 1 and names the node when a file-backed node is deleted from disk.
2. `verify` exits 1 on a dangling edge endpoint.
3. `verify` exits 1 on an `extracted` edge whose source file never mentions the target.
4. `render --format mermaid` emits one line per edge with the right arrow per tier.
5. `render --focus a --depth 1` excludes a node two hops away.
6. `render` refuses (exit 1) on a graph that fails `verify`, and proceeds with `--allow-unverified`.
7. `render --format html` writes a file that contains no `http://`/`https://` reference (self-contained).
8. `diff` exits 0 against itself, 1 after adding an edge, and names `+edge`.
9. `impact` exits 1 when the ops.json touches a god-node, 0 for a leaf file.
10. Mutation proof: break each new gate's condition and assert the test goes red.

## Risks

- **mypy now covers `.claude/operations/scripts`** (widened by the gate-scope plan) — every
  new function needs annotations or the DoD gate fails.
- **Context floor**: new SKILL.md prose must keep `check-context-floor.py --check` green.
- Rendering is the largest new surface; keep the HTML template under ~120 lines and assert
  self-containment in a test rather than eyeballing it.

## Definition of Done

`pytest -q` · `ruff check` · `mypy` · `gen-docs --check` · `gen-registry --check` ·
`gen-model-policy --check` · `check-context-floor --check` · `shellcheck` — all green;
CHANGELOG + `.ai/` updated; conventional commit; adversarial `code-reviewer` pass.
