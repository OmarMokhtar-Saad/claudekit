#!/usr/bin/env python3
"""project_graph_render.py - presentation layer for project-graph.py.

Split out of `project-graph.py` deliberately: that script's job is validating and
querying an agent-emitted graph, and an HTML/SVG emitter is a different concern
that was doubling the file. `impact` exists to flag exactly this kind of
coupling, so leaving the two fused would have been the tool failing its own test.

Everything here is a pure function of an already-selected node/edge list: no I/O,
no argparse, no graph loading. That is the boundary - callers decide *what* to
draw, this module decides *how*.

Python stdlib only, Python 3.9+.
"""

import json
import math
import re
from html import escape
from typing import Any, Dict, List, Set, Tuple

MERMAID_ID_RE = re.compile(r"[^A-Za-z0-9_]")
MERMAID_ID_MAX = 40


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
        # Display label only: strip any `#fragment`, then take the basename.
        # Deriving it here rather than importing path_part keeps the
        # dependency one-way (project-graph.py -> this module).
        label = node["id"].split("#", 1)[0].rsplit("/", 1)[-1] or node["id"]
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

