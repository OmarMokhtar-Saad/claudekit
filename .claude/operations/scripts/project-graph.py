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

Exit codes:
  0  success (stale: graph is fresh)
  1  refused (build over an existing graph without --force) or stale nodes found
  2  usage or validation error (bad JSON, schema violation, size guard, traversal)
  3  no graph file, or query/path found no match -> caller falls back to grep

Edge confidence tiers: `extracted` (explicit statement observed in source),
`inferred` (deduced from naming/convention/framework wiring), `ambiguous`
(dynamic dispatch, reflection, string-built target). A path's overall
confidence is its weakest hop. Python stdlib only, Python 3.9+.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    if error:
        err(error)
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
    fan_in: Dict[str, int] = {i: 0 for i in nodes}
    fan_out: Dict[str, int] = {i: 0 for i in nodes}
    for edge in graph.get("edges", []):
        if edge.get("from") in fan_out:
            fan_out[edge["from"]] += 1
        if edge.get("to") in fan_in:
            fan_in[edge["to"]] += 1

    ranked = sorted(nodes, key=lambda i: (-(fan_in[i] + fan_out[i]), i))[:args.top]
    rows = []
    for i, node_id in enumerate(ranked, 1):
        total = fan_in[node_id] + fan_out[node_id]
        loc = nodes[node_id].get("loc") or 0
        god = total >= args.threshold or (fan_in[node_id] >= GOD_FAN_IN and loc >= GOD_LOC)
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

    adjacency: Dict[str, List[dict]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["from"], []).append(edge)
    queue = deque([(src, [])])
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
