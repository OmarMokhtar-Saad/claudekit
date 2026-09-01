#!/usr/bin/env python3
"""project-graph.py - project-local, machine-queryable codebase graph.

Stores a dependency graph of the project at `.claude/project-graph.json` so
agents (explore, planner, refactor-cleaner) can answer structural questions -
"what depends on X", "how does A reach B", "which files are over-coupled" -
without re-reading the codebase every session. The graph is produced by the
codebase-mapping skill (the LLM reads any language and emits nodes/edges);
this script owns validation, integrity (hashes, line counts) and queries.

Subcommands:
  build    validate + store agent-supplied nodes/edges (computes hash/loc)
  query    direct dependents/dependencies of a node
  hubs     fan-in/fan-out ranking; flags god-node candidates
  path     BFS route between two nodes with per-hop confidence
  stale    re-hash file-backed nodes; report what changed since mapping
  impact   blast radius of a plan's ops.json; exit 1 = route to reviewer
  diff     structural delta between the stored graph and another graph JSON
  render   mermaid or self-contained HTML view of the (verified) graph
  verify   check the stored graph against the working tree (anti-hallucination)

Exit codes:
  0  success (stale: graph is fresh)
  1  refused (build over an existing graph without --force), stale nodes found,
     or verify violations (missing node, dangling/degenerate/unsupported edge)
  2  usage or validation error (bad JSON, schema violation, size guard, traversal)
  3  no graph file, or query/path found no match -> caller falls back to grep

Per-subcommand exit codes (the shared shape: 0 = nothing to report, 1 = something
actionable, 2 = bad input, 3 = no graph to work from):
  verify   1 = violations found
  render   1 = the graph fails verify; pass --allow-unverified to override
  diff     0 = identical, 1 = differences found (informational, like diff(1) -
           not an error), 2 = unreadable --against, 3 = no stored graph
  impact   1 = a touched node is a hub/god-node, the touched set crosses a
           top-level package boundary, or a path is absent from the graph
           -> route to the reviewer; 2 = unreadable ops.json

Edge confidence tiers: `extracted` (explicit statement observed in source),
`inferred` (deduced from naming/convention/framework wiring), `ambiguous`
(dynamic dispatch, reflection, string-built target). A path's overall
confidence is its weakest hop. Python stdlib only, Python 3.9+.
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_NODES = 20_000
MAX_EDGES = 100_000
HASH_CHUNK = 64 * 1024
NODE_KINDS = {"file", "class", "module", "package", "dir", "external", "other"}
EDGE_TYPES = {"import", "call", "inherit", "implement", "reference", "config", "test", "other"}
CONFIDENCE_ORDER = ("extracted", "inferred", "ambiguous")  # strongest -> weakest
DRIVE_RE = re.compile(r"^[A-Za-z]:")
DEFAULT_TOP = 15
DEFAULT_THRESHOLD = 25
GOD_FAN_IN = 15
GOD_LOC = 1000
DEFAULT_MAX_DEPTH = 8
DEFAULT_QUERY_LIMIT = 50
DEFAULT_RENDER_DEPTH = 2
MAX_SUPPORT_BYTES = 2 * 1024 * 1024


def project_root() -> Path:
    """Repo root: explicit env override, else git toplevel, else cwd."""
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


def graph_path() -> Path:
    env = os.environ.get("CLAUDEKIT_GRAPH_PATH")
    if env:
        return Path(env)
    return project_root() / ".claude" / "project-graph.json"


def path_part(node_id: str) -> str:
    """The filesystem path of a node id (`src/Foo.java#Bar` -> `src/Foo.java`)."""
    return node_id.split("#", 1)[0]


def invalid_path_reason(rel: str, root: Path) -> Optional[str]:
    """Reject ids that could escape the project root. Returns a reason or None."""
    if not rel:
        return "empty path"
    if rel.startswith("/") or rel.startswith("\\"):
        return "absolute path"
    if "\\" in rel:
        return "backslash in path (use POSIX separators)"
    if DRIVE_RE.match(rel):
        return "drive-letter path"
    if any(seg == ".." for seg in rel.split("/")):
        return "'..' path segment"
    resolved = os.path.normpath(os.path.join(str(root), rel))
    if not (resolved == str(root) or resolved.startswith(str(root) + os.sep)):
        return "path escapes project root"
    return None


def sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    except OSError:
        return None


def count_lines(path: Path) -> Optional[int]:
    try:
        with open(path, "rb") as fh:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(HASH_CHUNK), b""))
    except OSError:
        return None


def load_graph() -> Optional[dict]:
    target = graph_path()
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def err(message: str) -> None:
    print(message, file=sys.stderr)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def validate(data: dict, root: Path) -> List[str]:
    """Return every schema violation, each naming the offending record."""
    problems: List[str] = []
    if not isinstance(data, dict):
        return ["input: top level must be a JSON object"]
    if data.get("version") != SCHEMA_VERSION:
        problems.append("version: must be %d" % SCHEMA_VERSION)
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list):
        return problems + ["nodes: must be a list"]
    if not isinstance(edges, list):
        return problems + ["edges: must be a list"]
    if len(nodes) > MAX_NODES:
        problems.append("nodes: %d exceeds the %d limit - coarsen to file granularity "
                        "or shard by top-level directory" % (len(nodes), MAX_NODES))
    if len(edges) > MAX_EDGES:
        problems.append("edges: %d exceeds the %d limit - coarsen to file granularity "
                        "or shard by top-level directory" % (len(edges), MAX_EDGES))
    if problems:
        return problems

    seen: Dict[str, int] = {}
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            problems.append("nodes[%d]: must be an object" % i)
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            problems.append("nodes[%d].id: missing or empty" % i)
            continue
        if node_id in seen:
            problems.append("nodes[%d].id: duplicate of nodes[%d] (%r)" % (i, seen[node_id], node_id))
        else:
            seen[node_id] = i
        kind = node.get("kind", "file")
        if kind not in NODE_KINDS:
            problems.append("nodes[%d].kind: %r not in %s" % (i, kind, sorted(NODE_KINDS)))
        if kind != "external":
            reason = invalid_path_reason(path_part(node_id), root)
            if reason:
                problems.append("nodes[%d].id: %s (%r)" % (i, reason, node_id))

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            problems.append("edges[%d]: must be an object" % i)
            continue
        for key in ("from", "to"):
            ref = edge.get(key)
            if not isinstance(ref, str) or not ref:
                problems.append("edges[%d].%s: missing or empty" % (i, key))
            elif ref not in seen:
                problems.append("edges[%d].%s: dangling reference %r - emit a node stub "
                                "(kind: external for third-party targets)" % (i, key, ref))
        etype = edge.get("type", "reference")
        if etype not in EDGE_TYPES:
            problems.append("edges[%d].type: %r not in %s" % (i, etype, sorted(EDGE_TYPES)))
        confidence = edge.get("confidence")
        if confidence not in CONFIDENCE_ORDER:
            problems.append("edges[%d].confidence: %r not in %s"
                            % (i, confidence, list(CONFIDENCE_ORDER)))
    return problems


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def read_input(source: str) -> Tuple[Optional[dict], Optional[str]]:
    """Read the agent-supplied JSON from a file or stdin. Returns (data, error)."""
    try:
        if source == "-":
            raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
        else:
            path = Path(source)
            if not path.is_file():
                return None, "build: input file not found: %s" % source
            if path.stat().st_size > MAX_INPUT_BYTES:
                return None, ("build: input exceeds %d MB - coarsen to file granularity "
                              "or shard by top-level directory" % (MAX_INPUT_BYTES // (1024 * 1024)))
            raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "build: cannot read input: %s" % exc
    if len(raw.encode("utf-8", errors="ignore")) > MAX_INPUT_BYTES:
        return None, ("build: input exceeds %d MB - coarsen to file granularity "
                      "or shard by top-level directory" % (MAX_INPUT_BYTES // (1024 * 1024)))
    try:
        return json.loads(raw), None
    except ValueError as exc:
        return None, "build: invalid JSON: %s" % exc


def enrich_nodes(nodes: List[dict], root: Path) -> None:
    """Compute hash and loc for file-backed nodes; the agent never supplies them."""
    for node in nodes:
        if node.get("kind", "file") == "external":
            node.pop("hash", None)
            node.pop("loc", None)
            continue
        file_path = root / path_part(node["id"])
        if file_path.is_file():
            node["hash"] = sha256_file(file_path)
            loc = count_lines(file_path)
            if loc is not None:
                node["loc"] = loc
        else:
            err("build: warning - file not found for node %r (hash: null)" % node["id"])
            node["hash"] = None


def merge_graphs(existing: dict, incoming: dict) -> dict:
    """Replace incoming node ids and every edge touching them; keep the rest."""
    incoming_ids = {n["id"] for n in incoming["nodes"]}
    kept_nodes = [n for n in existing.get("nodes", []) if n.get("id") not in incoming_ids]
    kept_edges = [e for e in existing.get("edges", [])
                  if e.get("from") not in incoming_ids and e.get("to") not in incoming_ids]
    merged = dict(existing)
    merged["nodes"] = kept_nodes + incoming["nodes"]
    merged["edges"] = kept_edges + incoming["edges"]
    return merged


def cmd_build(args: argparse.Namespace) -> int:
    root = project_root()
    data, error = read_input(args.input)
    if error or data is None:
        err(error or "build: input produced no graph data")
        return 2
    problems = validate(data, root)
    if problems:
        err("build: %d validation error(s):" % len(problems))
        for problem in problems:
            err("  " + problem)
        return 2
    if args.check:
        print("CHECK OK: %d node(s), %d edge(s)" % (len(data["nodes"]), len(data["edges"])))
        return 0

    target = graph_path()
    if args.merge:
        existing = load_graph()
        if existing is None:
            err("build: --merge requires an existing graph at %s" % target)
            return 3
        data = merge_graphs(existing, data)
        # Re-validate the merged whole: a merge must not resurrect dangling edges.
        problems = validate(data, root)
        if problems:
            err("build: merge produced an invalid graph (%d error(s)):" % len(problems))
            for problem in problems:
                err("  " + problem)
            return 2
    elif target.exists() and not args.force:
        err("build: REFUSED - %s already exists (use --force to replace, "
            "--merge for a partial refresh)." % target)
        return 1

    enrich_nodes(data["nodes"], root)
    data["version"] = SCHEMA_VERSION
    data["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["tool"] = "claudekit/project-graph"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print("BUILT %s: %d node(s), %d edge(s)" % (target, len(data["nodes"]), len(data["edges"])))
    return 0


# ---------------------------------------------------------------------------
# query helpers
# ---------------------------------------------------------------------------

def resolve_node(graph: dict, needle: str) -> Tuple[Optional[str], List[str]]:
    """Exact id match, else unique suffix/basename match. Returns (id, candidates)."""
    ids = [n["id"] for n in graph.get("nodes", [])]
    if needle in ids:
        return needle, []
    candidates = [i for i in ids
                  if i.endswith("/" + needle) or path_part(i).rsplit("/", 1)[-1] == needle
                  or i.endswith(needle)]
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def node_index(graph: dict) -> Dict[str, dict]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def confidence_rank(tier: str) -> int:
    return CONFIDENCE_ORDER.index(tier) if tier in CONFIDENCE_ORDER else len(CONFIDENCE_ORDER)


def format_edge(edge: dict, direction: str) -> str:
    other = edge["from"] if direction == "in" else edge["to"]
    arrow = "<-" if direction == "in" else "->"
    return "  %s %-55s %-10s [%s]" % (arrow, other, edge.get("type", "?"),
                                      edge.get("confidence", "?").upper())


def cmd_query(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - fall back to grep" % graph_path())
        return 3
    node_id, candidates = resolve_node(graph, args.node)
    if node_id is None:
        if candidates:
            print("GRAPH: %d candidates for %r - re-run with an exact id:" % (len(candidates), args.node))
            for c in candidates[:20]:
                print("  " + c)
            return 0
        print("GRAPH: no match for %r - fall back to grep" % args.node)
        return 3

    max_rank = confidence_rank(args.min_confidence)
    incoming, outgoing = [], []
    for edge in graph.get("edges", []):
        if args.edge_type and edge.get("type") != args.edge_type:
            continue
        if confidence_rank(edge.get("confidence", "ambiguous")) > max_rank:
            continue
        if edge.get("to") == node_id and args.direction in ("in", "both"):
            incoming.append(edge)
        if edge.get("from") == node_id and args.direction in ("out", "both"):
            outgoing.append(edge)

    if args.format == "json":
        print(json.dumps({"node": node_index(graph).get(node_id),
                          "in": incoming[:args.limit], "out": outgoing[:args.limit]}, indent=1))
        return 0

    node = node_index(graph).get(node_id, {})
    hash_prefix = (node.get("hash") or "")[:19]
    print("%s  (kind=%s loc=%s %s)" % (node_id, node.get("kind", "?"),
                                       node.get("loc", "?"), hash_prefix))
    if args.direction in ("in", "both"):
        print("dependents (%d):" % len(incoming))
        for edge in incoming[:args.limit]:
            print(format_edge(edge, "in"))
    if args.direction in ("out", "both"):
        print("dependencies (%d):" % len(outgoing))
        for edge in outgoing[:args.limit]:
            print(format_edge(edge, "out"))
    return 0


def cmd_hubs(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - fall back to grep" % graph_path())
        return 3
    nodes = node_index(graph)
    if not nodes:
        print("GRAPH: empty graph")
        return 3
    fan_in, fan_out = fan_counts(graph)

    ranked = sorted(nodes, key=lambda i: (-(fan_in[i] + fan_out[i]), i))[:args.top]
    rows: List[Dict[str, Any]] = []
    for i, node_id in enumerate(ranked, 1):
        total = fan_in[node_id] + fan_out[node_id]
        loc = nodes[node_id].get("loc") or 0
        god = is_god_node(fan_in[node_id], fan_out[node_id], loc, args.threshold)
        rows.append({"rank": i, "id": node_id, "fan_in": fan_in[node_id],
                     "fan_out": fan_out[node_id], "total": total, "loc": loc,
                     "god_node": god})
    if args.format == "json":
        print(json.dumps(rows, indent=1))
        return 0
    print("%-4s %-55s %6s %7s %6s %6s  %s" % ("#", "node", "fan_in", "fan_out", "total", "loc", "flag"))
    for row in rows:
        print("%-4d %-55s %6d %7d %6d %6d  %s"
              % (row["rank"], row["id"], row["fan_in"], row["fan_out"], row["total"],
                 row["loc"], "GOD-NODE" if row["god_node"] else ""))
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - fall back to grep" % graph_path())
        return 3
    src, src_cands = resolve_node(graph, args.src)
    dst, dst_cands = resolve_node(graph, args.dst)
    for label, resolved, cands, raw in (("from", src, src_cands, args.src),
                                        ("to", dst, dst_cands, args.dst)):
        if resolved is None:
            if cands:
                print("GRAPH: %d candidates for %s=%r - re-run with an exact id" % (len(cands), label, raw))
                return 0
            print("GRAPH: no match for %s=%r - fall back to grep" % (label, raw))
            return 3

    if src is None or dst is None:  # unreachable: the loop above already returned
        return 3
    adjacency = adjacency_map(graph)
    queue: Deque[Tuple[str, List[dict]]] = deque([(src, [])])
    visited = {src}
    found: Optional[List[dict]] = None
    while queue:
        current, trail = queue.popleft()
        if len(trail) >= args.max_depth:
            continue
        for edge in adjacency.get(current, []):
            nxt = edge["to"]
            if nxt in visited:
                continue
            new_trail = trail + [edge]
            if nxt == dst:
                found = new_trail
                queue.clear()
                break
            visited.add(nxt)
            queue.append((nxt, new_trail))
    if found is None:
        print("GRAPH: no path %s -> %s within depth %d" % (src, dst, args.max_depth))
        return 3

    weakest = max(found, key=lambda e: confidence_rank(e.get("confidence", "ambiguous")))
    if args.format == "json":
        print(json.dumps({"path": found,
                          "confidence": weakest.get("confidence", "ambiguous")}, indent=1))
        return 0
    print("PATH (%d hop(s), confidence=%s):" % (len(found), weakest.get("confidence", "?").upper()))
    print("  " + src)
    for edge in found:
        print("  -> %-55s %-10s [%s]" % (edge["to"], edge.get("type", "?"),
                                         edge.get("confidence", "?").upper()))
    return 0


def cmd_stale(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - run the codebase-mapping skill to build one" % graph_path())
        return 3
    root = project_root()
    changed, missing, unhashed = [], [], []
    for node in graph.get("nodes", []):
        if node.get("kind", "file") == "external":
            continue
        node_id = node.get("id", "")
        file_path = root / path_part(node_id)
        stored = node.get("hash")
        if stored is None:
            unhashed.append(node_id)
            continue
        if not file_path.is_file():
            missing.append(node_id)
            continue
        if sha256_file(file_path) != stored:
            changed.append(node_id)

    report = [("CHANGED", changed), ("MISSING", missing), ("UNHASHED", unhashed)]
    total = sum(len(v) for _, v in report)
    if args.format == "json":
        print(json.dumps({k.lower(): v for k, v in report}, indent=1))
        return 1 if total else 0
    if not total:
        print("GRAPH: fresh (generated %s)" % graph.get("generated", "?"))
        return 0
    print("GRAPH: %d stale node(s) since %s:" % (total, graph.get("generated", "?")))
    for label, items in report:
        for node_id in items:
            print("  %-9s %s" % (label, node_id))
    print("Re-map the listed files and run: project-graph.py build --merge --input -")
    return 1
# ---------------------------------------------------------------------------
# impact
# ---------------------------------------------------------------------------

def is_god_node(fan_in: int, fan_out: int, loc: int,
                threshold: int = DEFAULT_THRESHOLD) -> bool:
    """The one god-node rule, shared by `hubs` and `impact` so they cannot disagree."""
    return (fan_in + fan_out) >= threshold or (fan_in >= GOD_FAN_IN and loc >= GOD_LOC)


def top_package(rel: str) -> str:
    """Top-level package of a path (`src/cli/main.py` -> `src`)."""
    head = rel.split("/", 1)[0]
    return head or rel


def read_ops(source: str, root: Path) -> Tuple[Optional[dict], Optional[str]]:
    """Read a plan's ops.json under the same guards `build` applies to its input."""
    # realpath, not normpath: normpath is textual, so a symlink *inside* the root
    # pointing outside it passes a startswith() test and turns --ops into a
    # read-and-echo primitive for arbitrary files.
    real_root = os.path.realpath(str(root))
    resolved = os.path.realpath(os.path.join(str(root), source))
    if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
        return None, "impact: --ops path escapes the project root: %s" % source
    target = Path(resolved)
    if not target.is_file():
        return None, "impact: ops file not found: %s" % source
    try:
        if target.stat().st_size > MAX_INPUT_BYTES:
            return None, ("impact: ops file exceeds %d MB - split the plan"
                          % (MAX_INPUT_BYTES // (1024 * 1024)))
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "impact: cannot read ops file: %s" % exc
    if len(raw.encode("utf-8", errors="ignore")) > MAX_INPUT_BYTES:
        return None, ("impact: ops file exceeds %d MB - split the plan"
                      % (MAX_INPUT_BYTES // (1024 * 1024)))
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, "impact: invalid JSON: %s" % exc
    if not isinstance(data, dict):
        return None, "impact: top level must be a JSON object"
    return data, None


def ops_paths(data: dict) -> Tuple[List[str], Optional[str]]:
    """Ordered, de-duplicated `path` values. Operations without one (run_command) are skipped."""
    operations = data.get("operations")
    if not isinstance(operations, list):
        return [], "impact: 'operations' must be a list"
    paths: List[str] = []
    for i, operation in enumerate(operations):
        if not isinstance(operation, dict):
            return [], "impact: operations[%d]: must be an object" % i
        value = operation.get("path")
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            return [], "impact: operations[%d].path: must be a non-empty string" % i
        if value not in paths:
            paths.append(value)
    return paths, None


def cmd_impact(args: argparse.Namespace) -> int:
    root = project_root()
    data, error = read_ops(args.ops, root)
    if error or data is None:
        err(error or "impact: ops file produced no data")
        return 2
    paths, path_error = ops_paths(data)
    if path_error:
        err(path_error)
        return 2
    for rel in paths:
        reason = invalid_path_reason(rel, root)
        if reason:
            err("impact: operations path %s (%r)" % (reason, rel))
            return 2
    if not paths:
        print("IMPACT: no file operations in %s - nothing to score" % args.ops)
        return 0

    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - impact is unknown; route to reviewer" % graph_path())
        return 3
    nodes = node_index(graph)
    by_path: Dict[str, str] = {}
    for node_id in nodes:
        by_path.setdefault(path_part(node_id), node_id)
    fan_in, fan_out = fan_counts(graph)

    rows: List[Dict[str, Any]] = []
    packages: List[str] = []
    flagged: List[str] = []
    unknown: List[str] = []
    for rel in paths:
        package = top_package(rel)
        if package not in packages:
            packages.append(package)
        mapped = by_path.get(rel)
        if mapped is None:
            # An unmapped path is NOT a leaf: the graph simply does not know this file.
            # Reporting it as zero-coupling would launder ignorance into a pass, so it
            # is surfaced as UNKNOWN and escalates on its own.
            unknown.append(rel)
            rows.append({"path": rel, "node": None, "fan_in": None, "fan_out": None,
                         "loc": None, "god_node": None, "status": "UNKNOWN"})
            continue
        loc = nodes[mapped].get("loc") or 0
        god = is_god_node(fan_in[mapped], fan_out[mapped], loc, args.threshold)
        if god:
            flagged.append(mapped)
        rows.append({"path": rel, "node": mapped, "fan_in": fan_in[mapped],
                     "fan_out": fan_out[mapped], "loc": loc, "god_node": god,
                     "status": "GOD-NODE" if god else "OK"})

    cross_package = len(packages) > 1
    escalate = bool(flagged or unknown or cross_package)
    reasons: List[str] = []
    if flagged:
        reasons.append("%d god-node(s): %s" % (len(flagged), ", ".join(flagged)))
    if unknown:
        reasons.append("%d path(s) absent from the graph: %s" % (len(unknown), ", ".join(unknown)))
    if cross_package:
        reasons.append("touched set spans %d top-level packages" % len(packages))

    if args.format == "json":
        print(json.dumps({"touched": rows, "packages": packages,
                          "cross_package": cross_package, "god_nodes": flagged,
                          "unknown": unknown, "escalate": escalate,
                          "reasons": reasons}, indent=1))
        return 1 if escalate else 0

    print("%-55s %6s %7s %6s  %s" % ("path", "fan_in", "fan_out", "loc", "flag"))
    for row in rows:
        if row["status"] == "UNKNOWN":
            print("%-55s %6s %7s %6s  %s" % (row["path"], "-", "-", "-", "UNKNOWN"))
        else:
            print("%-55s %6d %7d %6d  %s"
                  % (row["path"], row["fan_in"], row["fan_out"], row["loc"],
                     "GOD-NODE" if row["god_node"] else ""))
    print("packages touched (%d): %s" % (len(packages), ", ".join(packages)))
    if escalate:
        print("IMPACT: architecture touched - route to reviewer (%s)" % "; ".join(reasons))
        return 1
    print("IMPACT: local change - no hub, single package, every path mapped")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

EdgeKey = Tuple[str, str, str, str]
MERMAID_ID_RE = re.compile(r"[^A-Za-z0-9_]")
MERMAID_ID_MAX = 40
MAX_REPORTED_PROBLEMS = 20


def resolve_against(source: str, root: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Confine --against to the project root, with build's traversal rules."""
    rel = source
    if os.path.isabs(source):
        try:
            rel = os.path.relpath(os.path.realpath(source), os.path.realpath(str(root)))
        except ValueError:
            return None, "diff: --against is not under the project root: %s" % source
        rel = rel.replace(os.sep, "/")
    reason = invalid_path_reason(rel, root)
    if reason:
        return None, "diff: --against %s (%r)" % (reason, source)
    # invalid_path_reason is textual, so re-check the *resolved* path: a symlink
    # inside the root that points outside it survives every string-level test.
    real_root = os.path.realpath(str(root))
    resolved = os.path.realpath(str(root / rel))
    if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
        return None, "diff: --against resolves outside the project root: %s" % source
    # Return the RESOLVED path, as read_ops does: handing back `root / rel` would
    # traverse the symlink a second time at open, so re-pointing it after the
    # check wins the race. Check and open must name the same inode.
    return Path(resolved), None


def read_against(source: str, root: Path) -> Tuple[Optional[dict], Optional[str]]:
    """Read a comparison graph under build's size guards. Returns (data, error)."""
    target, reason = resolve_against(source, root)
    if target is None:
        return None, reason or "diff: --against could not be resolved"
    try:
        if not target.is_file():
            return None, "diff: --against file not found: %s" % source
        if target.stat().st_size > MAX_INPUT_BYTES:
            return None, ("diff: --against exceeds %d MB - compare a coarser graph"
                          % (MAX_INPUT_BYTES // (1024 * 1024)))
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "diff: cannot read --against: %s" % exc
    if len(raw.encode("utf-8", errors="ignore")) > MAX_INPUT_BYTES:
        return None, ("diff: --against exceeds %d MB - compare a coarser graph"
                      % (MAX_INPUT_BYTES // (1024 * 1024)))
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, "diff: --against is not valid JSON: %s" % exc
    if not isinstance(data, dict):
        return None, "diff: --against top level must be a JSON object"
    return data, None


def edge_key(edge: dict) -> EdgeKey:
    """Edge identity: endpoints, type and confidence - a retiering is a change."""
    return (str(edge.get("from", "")), str(edge.get("to", "")),
            str(edge.get("type", "reference")), str(edge.get("confidence", "")))


def edge_index(graph: dict) -> Dict[EdgeKey, dict]:
    return {edge_key(e): e for e in graph.get("edges", []) if isinstance(e, dict)}


def diff_graphs(before: dict, after: dict) -> Dict[str, List[Any]]:
    """Structural delta before -> after. `~node` means the stored hash moved."""
    old_nodes = node_index(before)
    new_nodes = node_index(after)
    old_edges = edge_index(before)
    new_edges = edge_index(after)
    return {
        "added_nodes": sorted(set(new_nodes) - set(old_nodes)),
        "removed_nodes": sorted(set(old_nodes) - set(new_nodes)),
        "changed_nodes": sorted(i for i in set(old_nodes) & set(new_nodes)
                                if old_nodes[i].get("hash") != new_nodes[i].get("hash")),
        "added_edges": [new_edges[k] for k in sorted(set(new_edges) - set(old_edges))],
        "removed_edges": [old_edges[k] for k in sorted(set(old_edges) - set(new_edges))],
    }


def describe_edge(edge: dict) -> str:
    return "%s -> %s [%s/%s]" % (edge.get("from", "?"), edge.get("to", "?"),
                                 edge.get("type", "?"), edge.get("confidence", "?"))


def mermaid_diff(delta: Dict[str, List[Any]]) -> List[str]:
    """Additions, removals and hash changes as one classed flowchart."""
    lines: List[str] = [
        "flowchart LR",
        "  classDef added stroke:#2da44e,stroke-width:2px;",
        "  classDef removed stroke:#cf222e,stroke-width:2px,stroke-dasharray:4 3;",
        "  classDef changed stroke:#bf8700,stroke-width:2px;",
    ]
    handles: Dict[str, str] = {}

    def handle(node_id: str) -> str:
        known = handles.get(node_id)
        if known is not None:
            return known
        name = "n%d_%s" % (len(handles), MERMAID_ID_RE.sub("_", node_id)[:MERMAID_ID_MAX])
        handles[node_id] = name
        return name

    for css, ids in (("added", delta["added_nodes"]),
                     ("removed", delta["removed_nodes"]),
                     ("changed", delta["changed_nodes"])):
        for raw_id in ids:
            node_id = str(raw_id)
            lines.append('  %s["%s"]:::%s' % (handle(node_id), node_id.replace('"', "'"), css))
    for edge in delta["added_edges"]:
        lines.append("  %s -->|+ %s| %s" % (handle(str(edge.get("from", ""))),
                                            edge.get("type", "?"),
                                            handle(str(edge.get("to", "")))))
    for edge in delta["removed_edges"]:
        lines.append("  %s -.->|- %s| %s" % (handle(str(edge.get("from", ""))),
                                             edge.get("type", "?"),
                                             handle(str(edge.get("to", "")))))
    return lines


def cmd_diff(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - run the codebase-mapping skill to build one" % graph_path())
        return 3
    root = project_root()
    other, error = read_against(args.against, root)
    if other is None:
        err(error or "diff: --against produced no graph data")
        return 2
    problems = validate(other, root)
    if problems:
        err("diff: --against is not a valid graph (%d error(s)):" % len(problems))
        for problem in problems[:MAX_REPORTED_PROBLEMS]:
            err("  " + problem)
        return 2

    delta = diff_graphs(other, graph)
    node_changes = (len(delta["added_nodes"]) + len(delta["removed_nodes"])
                    + len(delta["changed_nodes"]))
    edge_changes = len(delta["added_edges"]) + len(delta["removed_edges"])
    if args.format == "mermaid":
        for line in mermaid_diff(delta):
            print(line)
        return 1 if node_changes or edge_changes else 0
    if not (node_changes or edge_changes):
        print("DIFF: identical (%d node(s), %d edge(s))"
              % (len(graph.get("nodes", [])), len(graph.get("edges", []))))
        return 0
    print("DIFF: %s -> stored graph %s" % (args.against, graph_path()))
    for node_id in delta["removed_nodes"]:
        print("  -node  %s" % node_id)
    for node_id in delta["added_nodes"]:
        print("  +node  %s" % node_id)
    for node_id in delta["changed_nodes"]:
        print("  ~node  %s (hash changed)" % node_id)
    for edge in delta["removed_edges"]:
        print("  -edge  %s" % describe_edge(edge))
    for edge in delta["added_edges"]:
        print("  +edge  %s" % describe_edge(edge))
    print("DIFF: %d node change(s), %d edge change(s)" % (node_changes, edge_changes))
    return 1


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def reference_token(node_id: str) -> str:
    """The token a source file must contain to textually support an edge to node_id.

    `src/Foo.java#Bar` -> `Bar` (the fragment is the more specific claim);
    `src/b.py` -> `b` (basename, extension stripped).
    """
    if "#" in node_id:
        return node_id.split("#", 1)[1]
    base = path_part(node_id).rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def read_source(path: Path) -> Optional[str]:
    """Bounded text of a source file; None when it cannot be read at all."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_SUPPORT_BYTES)
    except OSError:
        return None
    return raw.decode("utf-8", errors="ignore")


def collect_violations(graph: dict, root: Path, strict: bool = False) -> List[Tuple[str, str]]:
    """Every way the stored graph disagrees with the working tree, as (label, detail).

    Unlike `validate`, which gates the agent's JSON against the schema, this gates the
    agent's *claims* against disk: nodes must exist, endpoints must be declared, and an
    `extracted` edge must leave a textual trace in its own source file. The support test
    is a cheap, language-agnostic falsifier - it catches invented edges, it does not
    prove real ones - so only `extracted` is checked by default; `--strict` extends it
    to `inferred`.
    """
    violations: List[Tuple[str, str]] = []
    node_ids = set()
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            continue
        node_ids.add(node_id)
        if node.get("kind", "file") == "external":
            continue
        if not (root / path_part(node_id)).is_file():
            violations.append(("MISSING NODE",
                               "%s: no file at %s" % (node_id, path_part(node_id))))

    sources: Dict[str, Optional[str]] = {}
    seen_edges = set()
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or not src or not dst:
            continue
        etype = edge.get("type", "reference")
        tier = edge.get("confidence", "ambiguous")
        undeclared = [side for side, ref in (("from", src), ("to", dst)) if ref not in node_ids]
        # One defect, one line: a dangling/degenerate edge is not also support-checked.
        if undeclared:
            violations.append(("DANGLING EDGE", "%s -> %s: %s not a declared node"
                               % (src, dst, "/".join(undeclared))))
            continue
        if src == dst:
            violations.append(("DEGENERATE EDGE", "%s -> %s: self-edge" % (src, dst)))
            continue
        key = (src, dst, etype)
        if key in seen_edges:
            violations.append(("DEGENERATE EDGE",
                               "%s -> %s (%s): duplicate edge" % (src, dst, etype)))
            continue
        seen_edges.add(key)
        if tier != "extracted" and not (strict and tier == "inferred"):
            continue
        if src not in sources:
            sources[src] = read_source(root / path_part(src))
        text = sources[src]
        if text is None:
            continue  # unreadable source: already reported as MISSING NODE
        token = reference_token(dst)
        if token not in text:
            label = "UNSUPPORTED EXTRACTED EDGE" if tier == "extracted" else "UNSUPPORTED INFERRED EDGE"
            violations.append((label, "%s -> %s: %r never appears in %s (substring check: aliased imports and generated sources can false-positive)"
                               % (src, dst, token, path_part(src))))
    return violations


def cmd_verify(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - run the codebase-mapping skill to build one" % graph_path())
        return 3
    violations = collect_violations(graph, project_root(), bool(args.strict))
    if not violations:
        print("VERIFY OK%s: %d node(s), %d edge(s)"
              % (" (strict)" if args.strict else "", len(graph.get("nodes", [])),
                 len(graph.get("edges", []))))
        return 0
    print("VERIFY: %d violation(s):" % len(violations))
    for label, detail in violations:
        print("  %-26s %s" % (label, detail))
    print("Fix the graph: re-map the offending files, then project-graph.py build --merge --input -")
    return 1


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

MERMAID_ARROW = {"extracted": "-->", "inferred": "-.->", "ambiguous": "-.->|?|"}
MERMAID_SHAPE = {
    "file": ("[", "]"),
    "class": ("([", "])"),
    "module": ("[[", "]]"),
    "package": ("[(", ")]"),
    "dir": ("[/", "/]"),
    "external": ("((", "))"),
    "other": ("{{", "}}"),
}

# One file, no network: the page is the artifact. Any external URL here would
# make a shared render depend on a CDN that may be unreachable or hostile, so
# tests assert this template contains no http(s) reference at all.
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>project graph</title>
<style>
:root { color-scheme: light dark; --bg:#fff; --fg:#111; --edge:#888; --hi:#c0392b; }
@media (prefers-color-scheme: dark) { :root { --bg:#111; --fg:#eee; --edge:#777; } }
body { background:var(--bg); color:var(--fg); font:13px/1.4 system-ui,sans-serif;
       margin:0; padding:1rem; }
h1 { font-size:15px; font-weight:600; }
#filter { width:22rem; padding:.3rem; margin-bottom:.5rem; }
text { fill:var(--fg); font-size:10px; pointer-events:none; }
path.edge { stroke:var(--edge); fill:none; }
path.edge.inferred { stroke-dasharray:5 4; }
path.edge.ambiguous { stroke-dasharray:2 4; }
g.node { cursor:pointer; }
g.node circle { fill:var(--bg); stroke:var(--fg); }
g.node.god circle { stroke:var(--hi); stroke-width:3px; }
g.node.sel circle { fill:var(--hi); }
.dim { opacity:.12; }
</style></head><body>
<h1>project graph &mdash; %(count)d node(s), %(edges)d edge(s)</h1>
<input id="filter" type="search" placeholder="filter nodes by text">
<svg id="g" viewBox="0 0 %(w)d %(h)d" width="100%%">
%(svg)s
</svg>
<script id="data" type="application/json">%(json)s</script>
<script>
const DATA = JSON.parse(document.getElementById("data").textContent);
const svg = document.getElementById("g");
const nodes = Array.prototype.slice.call(svg.querySelectorAll("g.node"));
const edges = Array.prototype.slice.call(svg.querySelectorAll("path.edge"));
function reset() {
  nodes.forEach(function (n) { n.classList.remove("dim", "sel"); });
  edges.forEach(function (e) { e.classList.remove("dim"); });
}
function highlight(id) {
  const near = new Set([id]);
  DATA.edges.forEach(function (e) {
    if (e.from === id) { near.add(e.to); }
    if (e.to === id) { near.add(e.from); }
  });
  nodes.forEach(function (n) {
    n.classList.toggle("dim", !near.has(n.dataset.id));
    n.classList.toggle("sel", n.dataset.id === id);
  });
  edges.forEach(function (e) {
    e.classList.toggle("dim", e.dataset.from !== id && e.dataset.to !== id);
  });
}
nodes.forEach(function (n) {
  n.addEventListener("click", function (ev) {
    ev.stopPropagation();
    if (n.classList.contains("sel")) { reset(); } else { highlight(n.dataset.id); }
  });
});
svg.addEventListener("click", reset);
document.getElementById("filter").addEventListener("input", function (ev) {
  const q = ev.target.value.trim().toLowerCase();
  reset();
  if (!q) { return; }
  nodes.forEach(function (n) {
    n.classList.toggle("dim", n.dataset.id.toLowerCase().indexOf(q) === -1);
  });
  edges.forEach(function (e) { e.classList.add("dim"); });
});
</script>
</body></html>
"""


def adjacency_map(graph: dict, undirected: bool = False) -> Dict[str, List[dict]]:
    """Outgoing edges per node id; also incoming when `undirected`."""
    adjacency: Dict[str, List[dict]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["from"], []).append(edge)
        if undirected:
            adjacency.setdefault(edge["to"], []).append(edge)
    return adjacency


def fan_counts(graph: dict) -> Tuple[Dict[str, int], Dict[str, int]]:
    """(fan_in, fan_out) per declared node id; edges to undeclared ids are ignored."""
    nodes = node_index(graph)
    fan_in: Dict[str, int] = {i: 0 for i in nodes}
    fan_out: Dict[str, int] = {i: 0 for i in nodes}
    for edge in graph.get("edges", []):
        if edge.get("from") in fan_out:
            fan_out[edge["from"]] += 1
        if edge.get("to") in fan_in:
            fan_in[edge["to"]] += 1
    return fan_in, fan_out


def god_nodes(graph: dict, threshold: int = DEFAULT_THRESHOLD) -> Set[str]:
    """Ids `hubs` would flag GOD-NODE - via is_god_node, so the views never disagree."""
    nodes = node_index(graph)
    fan_in, fan_out = fan_counts(graph)
    flagged: Set[str] = set()
    for node_id, node in nodes.items():
        loc = node.get("loc") or 0
        # One predicate, three call sites (hubs, impact, render): change the rule
        # in is_god_node and every view moves with it.
        if is_god_node(fan_in[node_id], fan_out[node_id], loc, threshold):
            flagged.add(node_id)
    return flagged


def nodes_within(graph: dict, start: str, depth: int) -> Set[str]:
    """Ids within `depth` hops of `start`, following edges in either direction.

    `path` walks edge trails to answer "how does A reach B"; this answers "what
    sits near X", which is a ball, not a trail. They share one adjacency builder.
    """
    adjacency = adjacency_map(graph, undirected=True)
    reached: Set[str] = {start}
    queue: Deque[Tuple[str, int]] = deque([(start, 0)])
    while queue:
        current, dist = queue.popleft()
        if dist >= depth:
            continue
        for edge in adjacency.get(current, []):
            for nxt in (edge["from"], edge["to"]):
                if nxt not in reached:
                    reached.add(nxt)
                    queue.append((nxt, dist + 1))
    return reached


def select_subgraph(graph: dict, focus: Optional[str], depth: int,
                    kind: Optional[str], min_confidence: str) -> Tuple[List[dict], List[dict]]:
    """The rendered slice: focus ball, then kind filter, then confidence floor."""
    all_nodes: List[dict] = graph.get("nodes", [])
    keep = {n["id"] for n in all_nodes}
    if focus is not None:
        keep &= nodes_within(graph, focus, depth)
    if kind:
        # The focus node always survives its own diagram, whatever its kind.
        keep = {n["id"] for n in all_nodes if n["id"] in keep
                and (n.get("kind", "file") == kind or n["id"] == focus)}
    nodes = [n for n in all_nodes if n["id"] in keep]
    max_rank = confidence_rank(min_confidence)
    edges = [e for e in graph.get("edges", [])
             if e.get("from") in keep and e.get("to") in keep
             and confidence_rank(e.get("confidence", "ambiguous")) <= max_rank]
    return nodes, edges


def render_mermaid(nodes: List[dict], edges: List[dict], gods: Set[str]) -> str:
    """`flowchart LR`; shape encodes kind, arrow style encodes confidence."""
    alias = {n["id"]: "n%d" % i for i, n in enumerate(nodes)}
    lines = ["flowchart LR", "  classDef god stroke:#c0392b,stroke-width:3px;"]
    for node in nodes:
        open_b, close_b = MERMAID_SHAPE.get(node.get("kind", "file"), MERMAID_SHAPE["other"])
        label = node["id"].replace('"', "'")
        lines.append("  %s%s\"%s\"%s" % (alias[node["id"]], open_b, label, close_b))
    for edge in edges:
        arrow = MERMAID_ARROW.get(edge.get("confidence", "ambiguous"),
                                  MERMAID_ARROW["ambiguous"])
        lines.append("  %s %s %s" % (alias[edge["from"]], arrow, alias[edge["to"]]))
    flagged = sorted(i for i in gods if i in alias)
    if flagged:
        lines.append("  class %s god;" % ",".join(alias[i] for i in flagged))
    return "\n".join(lines) + "\n"


def circular_layout(nodes: List[dict]) -> Dict[str, Tuple[float, float]]:
    """Deterministic ring layout - no physics, no dependency, stable across runs."""
    count = max(len(nodes), 1)
    radius = max(120.0, 22.0 * count / math.pi)
    positions: Dict[str, Tuple[float, float]] = {}
    for i, node in enumerate(nodes):
        angle = 2.0 * math.pi * i / count
        positions[node["id"]] = (radius * math.cos(angle), radius * math.sin(angle))
    return positions


def render_html(nodes: List[dict], edges: List[dict], gods: Set[str]) -> str:
    """One self-contained page: inline SVG + a JSON island + click/filter behaviour."""
    positions = circular_layout(nodes)
    span = max([abs(x) for x, _ in positions.values()] or [120.0]) + 140.0
    parts: List[str] = []
    for edge in edges:
        x1, y1 = positions[edge["from"]]
        x2, y2 = positions[edge["to"]]
        parts.append('<path class="edge %s" d="M %.1f %.1f L %.1f %.1f" '
                     'data-from="%s" data-to="%s"/>'
                     % (escape(str(edge.get("confidence", "ambiguous")), quote=True),
                        x1 + span, y1 + span, x2 + span, y2 + span,
                        escape(edge["from"], quote=True), escape(edge["to"], quote=True)))
    for node in nodes:
        x, y = positions[node["id"]]
        label = path_part(node["id"]).rsplit("/", 1)[-1] or node["id"]
        parts.append('<g class="node%s" data-id="%s"><circle cx="%.1f" cy="%.1f" r="7"/>'
                     '<text x="%.1f" y="%.1f" text-anchor="middle">%s</text></g>'
                     % (" god" if node["id"] in gods else "",
                        escape(node["id"], quote=True), x + span, y + span,
                        x + span, y + span - 12.0, escape(label)))
    # `</` cannot appear inside a <script> body, island or not.
    island = json.dumps({"nodes": nodes, "edges": edges}).replace("</", "<\\/")
    return HTML_TEMPLATE % {"count": len(nodes), "edges": len(edges),
                            "w": int(2 * span), "h": int(2 * span),
                            "svg": "\n".join(parts), "json": island}


def cmd_render(args: argparse.Namespace) -> int:
    graph = load_graph()
    if graph is None:
        print("GRAPH: no graph at %s - run the codebase-mapping skill to build one" % graph_path())
        return 3
    if not args.allow_unverified:
        violations = collect_violations(graph, project_root())
        if violations:
            err("render: REFUSED - the graph fails verify (%d violation(s)):" % len(violations))
            for violation in violations[:20]:
                err("  %s: %s" % violation)
            err("Re-map the graph (project-graph.py verify) or pass --allow-unverified "
                "to render it anyway.")
            return 1

    focus: Optional[str] = None
    if args.focus:
        focus, candidates = resolve_node(graph, args.focus)
        if focus is None:
            if candidates:
                print("GRAPH: %d candidates for --focus %r - re-run with an exact id"
                      % (len(candidates), args.focus))
                for c in candidates[:20]:
                    print("  " + c)
                return 0
            print("GRAPH: no match for --focus %r - fall back to grep" % args.focus)
            return 3

    nodes, edges = select_subgraph(graph, focus, args.depth, args.kind, args.min_confidence)
    gods = god_nodes(graph)
    output = (render_html(nodes, edges, gods) if args.format == "html"
              else render_mermaid(nodes, edges, gods))
    if args.out:
        out_path = Path(args.out)
        try:
            if out_path.parent:
                out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
        except OSError as exc:
            err("render: cannot write %s: %s" % (out_path, exc))
            return 2
        print("RENDERED %s: %d node(s), %d edge(s)" % (out_path, len(nodes), len(edges)))
        return 0
    sys.stdout.write(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project-local, machine-queryable codebase graph.")
    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("build", help="validate + store agent-supplied nodes/edges")
    build.add_argument("--input", required=True, help="JSON file, or '-' for stdin")
    build.add_argument("--check", action="store_true", help="validate only, write nothing")
    build.add_argument("--force", action="store_true", help="replace an existing graph")
    build.add_argument("--merge", action="store_true",
                       help="partial refresh: replace incoming node ids + their edges")
    build.set_defaults(func=cmd_build)

    query = sub.add_parser("query", help="dependents/dependencies of a node")
    query.add_argument("node", help="exact id or unique suffix/basename")
    query.add_argument("--direction", choices=("in", "out", "both"), default="both")
    query.add_argument("--edge-type", dest="edge_type", choices=sorted(EDGE_TYPES))
    query.add_argument("--min-confidence", dest="min_confidence",
                       choices=CONFIDENCE_ORDER, default="ambiguous",
                       help="include edges at this tier or stronger")
    query.add_argument("--format", choices=("text", "json"), default="text")
    query.add_argument("--limit", type=int, default=DEFAULT_QUERY_LIMIT)
    query.set_defaults(func=cmd_query)

    hubs = sub.add_parser("hubs", help="fan-in/fan-out ranking; god-node flags")
    hubs.add_argument("--top", type=int, default=DEFAULT_TOP)
    hubs.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                      help="GOD-NODE when fan_in+fan_out >= threshold")
    hubs.add_argument("--format", choices=("text", "json"), default="text")
    hubs.set_defaults(func=cmd_hubs)

    path = sub.add_parser("path", help="BFS route between two nodes")
    path.add_argument("src")
    path.add_argument("dst")
    path.add_argument("--max-depth", dest="max_depth", type=int, default=DEFAULT_MAX_DEPTH)
    path.add_argument("--format", choices=("text", "json"), default="text")
    path.set_defaults(func=cmd_path)

    stale = sub.add_parser("stale", help="re-hash nodes; report changes since mapping")
    stale.add_argument("--format", choices=("text", "json"), default="text")
    stale.set_defaults(func=cmd_stale)
    impact = sub.add_parser("impact", help="blast radius of a plan's ops.json")
    impact.add_argument("--ops", required=True, help="path to a plan's ops.json")
    impact.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help="GOD-NODE when fan_in+fan_out >= threshold")
    impact.add_argument("--format", choices=("text", "json"), default="text")
    impact.set_defaults(func=cmd_impact)

    diff = sub.add_parser("diff", help="compare the stored graph with another graph JSON")
    diff.add_argument("--against", required=True,
                      help="graph JSON to compare against (path under the project root)")
    diff.add_argument("--format", choices=("text", "mermaid"), default="text")
    diff.set_defaults(func=cmd_diff)

    render = sub.add_parser("render", help="mermaid or self-contained HTML view of the graph")
    render.add_argument("--format", choices=("mermaid", "html"), default="mermaid")
    render.add_argument("--focus", help="exact id or unique suffix; bounds output with --depth")
    render.add_argument("--depth", type=int, default=DEFAULT_RENDER_DEPTH,
                        help="hops from --focus to include (default %d)" % DEFAULT_RENDER_DEPTH)
    render.add_argument("--kind", choices=sorted(NODE_KINDS), help="keep only nodes of this kind")
    render.add_argument("--min-confidence", dest="min_confidence",
                        choices=CONFIDENCE_ORDER, default="ambiguous",
                        help="include edges at this tier or stronger")
    render.add_argument("--out", help="write to PATH instead of stdout")
    render.add_argument("--allow-unverified", dest="allow_unverified", action="store_true",
                        help="render even when the graph fails verify")
    render.set_defaults(func=cmd_render)

    verify = sub.add_parser("verify", help="check the stored graph against the working tree")
    verify.add_argument("--strict", action="store_true",
                        help="also require textual support for `inferred` edges; the support test is a\n                             substring check, so aliased imports and generated sources\n                             can false-positive")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
