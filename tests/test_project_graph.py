"""Behavioral contract of .claude/operations/scripts/project-graph.py.

The script stores an agent-built codebase graph at .claude/project-graph.json
and answers structural queries so agents stop re-grepping. Contract under test:

- build validates agent JSON (exit 2 with per-record messages), computes
  hash/loc itself, refuses overwrite without --force (exit 1), and --merge
  replaces only incoming node ids plus edges touching them.
- query/path/hubs answer from the stored graph; a miss or absent graph exits 3
  (the caller's signal to fall back to grep).
- stale re-hashes file-backed nodes and exits 1 listing CHANGED/MISSING nodes.
- render emits mermaid (arrow style per confidence tier) or one self-contained
  HTML file, bounded by --focus/--depth, and refuses a graph that fails verify
  unless --allow-unverified is passed.
- the codebase-mapping and context-keeper skills have exactly one copy each
  (task 008 batch 1 deleted the templates/skills twins).

All invocations run the real script as a subprocess against a temp project via
CLAUDEKIT_PROJECT_ROOT / CLAUDEKIT_GRAPH_PATH, asserting exit codes and on-disk
artifacts - not prose.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "project-graph.py"
RENDER_MODULE = REPO / ".claude" / "operations" / "scripts" / "project_graph_render.py"


def run(args, project, graph=None, stdin=None):
    env = dict(os.environ)
    env["CLAUDEKIT_PROJECT_ROOT"] = str(project)
    if graph is not None:
        env["CLAUDEKIT_GRAPH_PATH"] = str(graph)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, env=env, input=stdin, timeout=60,
    )


def make_project(tmp_path):
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text("import b\nimport c\n", encoding="utf-8")
    (project / "src" / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (project / "src" / "c.py").write_text("VALUE = 2\n", encoding="utf-8")
    return project


def sample_input(**overrides):
    data = {
        "version": 1,
        "nodes": [
            {"id": "src/a.py", "kind": "file"},
            {"id": "src/b.py", "kind": "file"},
            {"id": "src/c.py", "kind": "file"},
        ],
        "edges": [
            {"from": "src/a.py", "to": "src/b.py", "type": "import", "confidence": "extracted"},
            {"from": "src/a.py", "to": "src/c.py", "type": "import", "confidence": "inferred"},
        ],
    }
    data.update(overrides)
    return data


def build_graph(project, graph, data=None):
    payload = json.dumps(data or sample_input())
    result = run(["build", "--input", "-", "--force"], project, graph, stdin=payload)
    assert result.returncode == 0, result.stderr
    return result


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

class TestBuild:
    def test_happy_path_computes_hash_and_loc(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        result = run(["build", "--input", "-"], project, graph, stdin=json.dumps(sample_input()))
        assert result.returncode == 0, result.stderr
        stored = json.loads(graph.read_text(encoding="utf-8"))
        assert stored["generated"]
        node = {n["id"]: n for n in stored["nodes"]}["src/a.py"]
        assert node["hash"].startswith("sha256:")
        assert node["loc"] == 2

    def test_check_validates_without_writing(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        result = run(["build", "--check", "--input", "-"], project, graph,
                     stdin=json.dumps(sample_input()))
        assert result.returncode == 0
        assert not graph.exists()

    def test_input_from_file(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        payload = tmp_path / "input.json"
        payload.write_text(json.dumps(sample_input()), encoding="utf-8")
        result = run(["build", "--input", str(payload)], project, graph)
        assert result.returncode == 0, result.stderr
        assert graph.exists()

    def test_refuses_overwrite_without_force(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["build", "--input", "-"], project, graph, stdin=json.dumps(sample_input()))
        assert result.returncode == 1
        assert "--force" in result.stderr

    def test_merge_replaces_only_incoming_nodes(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        incoming = {
            "version": 1,
            "nodes": [{"id": "src/a.py", "kind": "file"}],
            "edges": [{"from": "src/a.py", "to": "src/a.py",
                       "type": "reference", "confidence": "ambiguous"}],
        }
        result = run(["build", "--merge", "--input", "-"], project, graph,
                     stdin=json.dumps(incoming))
        assert result.returncode == 0, result.stderr
        stored = json.loads(graph.read_text(encoding="utf-8"))
        ids = {n["id"] for n in stored["nodes"]}
        assert ids == {"src/a.py", "src/b.py", "src/c.py"}
        # Both old edges touched src/a.py, so only the incoming edge survives.
        assert len(stored["edges"]) == 1
        assert stored["edges"][0]["type"] == "reference"

    def test_merge_without_existing_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        result = run(["build", "--merge", "--input", "-"], project, graph,
                     stdin=json.dumps(sample_input()))
        assert result.returncode == 3

    def test_missing_file_node_gets_null_hash(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = sample_input()
        data["nodes"].append({"id": "src/ghost.py", "kind": "file"})
        build_graph(project, graph, data)
        stored = json.loads(graph.read_text(encoding="utf-8"))
        ghost = {n["id"]: n for n in stored["nodes"]}["src/ghost.py"]
        assert ghost["hash"] is None


class TestBuildRejections:
    def _expect_2(self, tmp_path, data, fragment):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        result = run(["build", "--input", "-"], project, graph, stdin=json.dumps(data))
        assert result.returncode == 2, result.stdout + result.stderr
        assert fragment in result.stderr
        assert not graph.exists()

    def test_dangling_edge(self, tmp_path):
        data = sample_input(edges=[{"from": "src/a.py", "to": "src/nope.py",
                                    "type": "import", "confidence": "extracted"}])
        self._expect_2(tmp_path, data, "dangling")

    def test_bad_confidence(self, tmp_path):
        data = sample_input(edges=[{"from": "src/a.py", "to": "src/b.py",
                                    "type": "import", "confidence": "certain"}])
        self._expect_2(tmp_path, data, "confidence")

    def test_traversal_id(self, tmp_path):
        data = sample_input(nodes=[{"id": "../etc/passwd", "kind": "file"}], edges=[])
        self._expect_2(tmp_path, data, "'..'")

    def test_absolute_path_id(self, tmp_path):
        data = sample_input(nodes=[{"id": "/etc/passwd", "kind": "file"}], edges=[])
        self._expect_2(tmp_path, data, "absolute")

    def test_duplicate_node_id(self, tmp_path):
        data = sample_input()
        data["nodes"].append({"id": "src/a.py", "kind": "file"})
        self._expect_2(tmp_path, data, "duplicate")

    def test_bad_edge_type(self, tmp_path):
        data = sample_input(edges=[{"from": "src/a.py", "to": "src/b.py",
                                    "type": "uses", "confidence": "extracted"}])
        self._expect_2(tmp_path, data, "type")

    def test_wrong_version(self, tmp_path):
        self._expect_2(tmp_path, sample_input(version=2), "version")

    def test_node_count_guard(self, tmp_path):
        nodes = [{"id": "f%d" % i, "kind": "external"} for i in range(20_001)]
        self._expect_2(tmp_path, sample_input(nodes=nodes, edges=[]), "limit")

    def test_invalid_json(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        result = run(["build", "--input", "-"], project, graph, stdin="{not json")
        assert result.returncode == 2
        assert "JSON" in result.stderr


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

class TestQuery:
    def test_exact_hit_lists_both_directions(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["query", "src/b.py"], project, graph)
        assert result.returncode == 0
        assert "src/a.py" in result.stdout
        assert "EXTRACTED" in result.stdout

    def test_suffix_match(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["query", "b.py"], project, graph)
        assert result.returncode == 0
        assert "src/b.py" in result.stdout

    def test_miss_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["query", "zzz.py"], project, graph)
        assert result.returncode == 3
        assert "grep" in result.stdout

    def test_no_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        result = run(["query", "a.py"], project, tmp_path / "missing.json")
        assert result.returncode == 3

    def test_direction_in_filters(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["query", "src/a.py", "--direction", "in"], project, graph)
        assert result.returncode == 0
        assert "dependents (0)" in result.stdout
        assert "dependencies" not in result.stdout

    def test_min_confidence_filters(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["query", "src/a.py", "--direction", "out",
                      "--min-confidence", "extracted"], project, graph)
        assert result.returncode == 0
        assert "src/b.py" in result.stdout
        assert "src/c.py" not in result.stdout  # inferred edge filtered out


# ---------------------------------------------------------------------------
# hubs
# ---------------------------------------------------------------------------

class TestHubs:
    def test_star_center_ranks_first(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = {
            "version": 1,
            "nodes": [{"id": "hub", "kind": "external"}] + [
                {"id": "leaf%d" % i, "kind": "external"} for i in range(4)],
            "edges": [{"from": "leaf%d" % i, "to": "hub",
                       "type": "import", "confidence": "extracted"} for i in range(4)],
        }
        build_graph(project, graph, data)
        result = run(["hubs", "--format", "json"], project, graph)
        assert result.returncode == 0
        rows = json.loads(result.stdout)
        assert rows[0]["id"] == "hub"
        assert rows[0]["fan_in"] == 4
        assert rows[0]["fan_out"] == 0

    def test_threshold_flags_god_node(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["hubs", "--threshold", "2", "--format", "json"], project, graph)
        rows = json.loads(result.stdout)
        top = rows[0]
        assert top["id"] == "src/a.py"  # fan_out 2
        assert top["god_node"] is True

    def test_no_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        result = run(["hubs"], project, tmp_path / "missing.json")
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

class TestPath:
    def _chain(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = {
            "version": 1,
            "nodes": [{"id": n, "kind": "external"} for n in ("a", "b", "c", "island")],
            "edges": [
                {"from": "a", "to": "b", "type": "call", "confidence": "extracted"},
                {"from": "b", "to": "c", "type": "call", "confidence": "ambiguous"},
            ],
        }
        build_graph(project, graph, data)
        return project, graph

    def test_path_reports_weakest_confidence(self, tmp_path):
        project, graph = self._chain(tmp_path)
        result = run(["path", "a", "c"], project, graph)
        assert result.returncode == 0
        assert "confidence=AMBIGUOUS" in result.stdout

    def test_disconnected_exits_3(self, tmp_path):
        project, graph = self._chain(tmp_path)
        result = run(["path", "a", "island"], project, graph)
        assert result.returncode == 3

    def test_max_depth_blocks_long_path(self, tmp_path):
        project, graph = self._chain(tmp_path)
        result = run(["path", "a", "c", "--max-depth", "1"], project, graph)
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# stale
# ---------------------------------------------------------------------------

class TestStale:
    def test_fresh_graph_exits_0(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["stale"], project, graph)
        assert result.returncode == 0
        assert "fresh" in result.stdout

    def test_changed_file_exits_1(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        (project / "src" / "b.py").write_text("VALUE = 999\n", encoding="utf-8")
        result = run(["stale"], project, graph)
        assert result.returncode == 1
        assert "CHANGED" in result.stdout
        assert "src/b.py" in result.stdout
        assert "--merge" in result.stdout

    def test_missing_file_exits_1(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        (project / "src" / "c.py").unlink()
        result = run(["stale"], project, graph)
        assert result.returncode == 1
        assert "MISSING" in result.stdout

    def test_no_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        result = run(["stale"], project, tmp_path / "missing.json")
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

class TestDiff:
    def _before_copy(self, project, graph, name="before.json"):
        """Snapshot the stored graph inside the project (--against is root-confined)."""
        copy = project / name
        copy.write_text(graph.read_text(encoding="utf-8"), encoding="utf-8")
        return copy

    def test_identical_graph_exits_0(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        self._before_copy(project, graph)
        result = run(["diff", "--against", "before.json"], project, graph)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "identical" in result.stdout

    def test_added_edge_exits_1_and_names_it(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        self._before_copy(project, graph)
        data = sample_input()
        data["edges"].append({"from": "src/b.py", "to": "src/c.py",
                              "type": "call", "confidence": "extracted"})
        build_graph(project, graph, data)
        result = run(["diff", "--against", "before.json"], project, graph)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "+edge" in result.stdout
        assert "src/b.py -> src/c.py" in result.stdout

    def test_removed_node_and_hash_change_reported(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        self._before_copy(project, graph)
        (project / "src" / "b.py").write_text("VALUE = 999\n", encoding="utf-8")
        data = sample_input()
        data["nodes"] = [n for n in data["nodes"] if n["id"] != "src/c.py"]
        data["edges"] = [e for e in data["edges"] if e["to"] != "src/c.py"]
        build_graph(project, graph, data)
        result = run(["diff", "--against", "before.json"], project, graph)
        assert result.returncode == 1
        assert "-node  src/c.py" in result.stdout
        assert "~node  src/b.py" in result.stdout
        assert "-edge" in result.stdout

    def test_mermaid_classes_additions_and_removals(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        self._before_copy(project, graph)
        data = sample_input()
        data["nodes"].append({"id": "src/d.py", "kind": "file"})
        data["edges"].append({"from": "src/a.py", "to": "src/d.py",
                              "type": "import", "confidence": "extracted"})
        data["edges"] = [e for e in data["edges"] if e["to"] != "src/c.py"]
        build_graph(project, graph, data)
        result = run(["diff", "--against", "before.json", "--format", "mermaid"], project, graph)
        assert result.returncode == 1
        assert "flowchart LR" in result.stdout
        assert ":::added" in result.stdout
        # The class must be DECLARED, not merely referenced: mermaid renders an
        # undefined class as unstyled, so asserting only the `:::added` usage
        # accepts output where every add/remove looks identical.
        assert "classDef added" in result.stdout
        assert "classDef removed" in result.stdout
        assert "-->|+ import|" in result.stdout
        assert "-.->|- import|" in result.stdout

    def test_mermaid_marks_changed_nodes(self, tmp_path):
        """The third class needs its own fixture: added/removed come from the edge
        delta, but `changed` only fires when a node's stored hash moves, so a test
        built on edges alone leaves the whole branch unverified."""
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        self._before_copy(project, graph)
        (project / "src" / "b.py").write_text("VALUE = 999\n", encoding="utf-8")
        build_graph(project, graph, sample_input())
        result = run(["diff", "--against", "before.json", "--format", "mermaid"], project, graph)
        assert result.returncode == 1
        assert "classDef changed" in result.stdout
        assert ":::changed" in result.stdout

    def test_malformed_against_exits_2(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        (project / "bad.json").write_text("{not json", encoding="utf-8")
        result = run(["diff", "--against", "bad.json"], project, graph)
        assert result.returncode == 2
        assert "JSON" in result.stderr

    def test_invalid_schema_against_exits_2(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        (project / "bad.json").write_text(
            json.dumps({"version": 2, "nodes": [], "edges": []}), encoding="utf-8")
        result = run(["diff", "--against", "bad.json"], project, graph)
        assert result.returncode == 2
        assert "version" in result.stderr

    def test_missing_against_exits_2(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["diff", "--against", "nope.json"], project, graph)
        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_traversal_against_rejected(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["diff", "--against", "../escape.json"], project, graph)
        assert result.returncode == 2
        assert "--against" in result.stderr

    def test_no_stored_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        (project / "before.json").write_text(json.dumps(sample_input()), encoding="utf-8")
        result = run(["diff", "--against", "before.json"], project, tmp_path / "missing.json")
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

class TestRender:
    """render is a pure function of the stored graph: the same IR in, the same
    mermaid/HTML out. Every assertion below reads the rendered artifact, not the
    script's prose. --allow-unverified is passed wherever the test is about
    rendering rather than about the verify gate, so these stay independent of
    Phase 1's violation wording."""

    def _graph(self, tmp_path):
        project = make_project(tmp_path)
        (project / "src" / "d.py").write_text("VALUE = 3\n", encoding="utf-8")
        graph = tmp_path / "graph.json"
        data = {
            "version": 1,
            "nodes": [{"id": "src/%s.py" % n, "kind": "file"} for n in ("a", "b", "c", "d")],
            "edges": [
                {"from": "src/a.py", "to": "src/b.py",
                 "type": "import", "confidence": "extracted"},
                {"from": "src/a.py", "to": "src/c.py",
                 "type": "import", "confidence": "inferred"},
                {"from": "src/b.py", "to": "src/d.py",
                 "type": "call", "confidence": "ambiguous"},
            ],
        }
        build_graph(project, graph, data)
        return project, graph

    def _arrows(self, stdout):
        return [ln.strip().split()[1] for ln in stdout.splitlines()
                if ln.startswith("  n") and " n" in ln[3:]]

    def test_mermaid_one_line_per_edge_with_tier_arrow(self, tmp_path):
        project, graph = self._graph(tmp_path)
        result = run(["render", "--allow-unverified"], project, graph)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[0] == "flowchart LR"
        arrows = self._arrows(result.stdout)
        assert len(arrows) == 3
        assert arrows.count("-->") == 1          # extracted
        assert arrows.count("-.->") == 1         # inferred
        assert arrows.count("-.->|?|") == 1      # ambiguous

    def test_focus_depth_1_excludes_two_hop_node(self, tmp_path):
        project, graph = self._graph(tmp_path)
        result = run(["render", "--allow-unverified", "--focus", "src/a.py",
                      "--depth", "1"], project, graph)
        assert result.returncode == 0, result.stderr
        assert "src/b.py" in result.stdout
        assert "src/d.py" not in result.stdout   # two hops from src/a.py

    def test_focus_depth_2_includes_two_hop_node(self, tmp_path):
        project, graph = self._graph(tmp_path)
        result = run(["render", "--allow-unverified", "--focus", "src/a.py",
                      "--depth", "2"], project, graph)
        assert result.returncode == 0, result.stderr
        assert "src/d.py" in result.stdout

    def test_min_confidence_drops_weaker_edges(self, tmp_path):
        project, graph = self._graph(tmp_path)
        result = run(["render", "--allow-unverified", "--min-confidence", "extracted"],
                     project, graph)
        assert result.returncode == 0, result.stderr
        assert self._arrows(result.stdout) == ["-->"]

    def test_god_node_gets_a_mermaid_class(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = {
            "version": 1,
            "nodes": [{"id": "hub", "kind": "external"}] + [
                {"id": "leaf%d" % i, "kind": "external"} for i in range(30)],
            "edges": [{"from": "leaf%d" % i, "to": "hub",
                       "type": "import", "confidence": "extracted"} for i in range(30)],
        }
        build_graph(project, graph, data)
        result = run(["render", "--allow-unverified"], project, graph)
        assert result.returncode == 0, result.stderr
        assert "classDef god" in result.stdout
        assert [ln for ln in result.stdout.splitlines() if ln.startswith("  class ")]

    def test_html_output_is_self_contained(self, tmp_path):
        project, graph = self._graph(tmp_path)
        out = tmp_path / "graph.html"
        result = run(["render", "--allow-unverified", "--format", "html",
                      "--out", str(out)], project, graph)
        assert result.returncode == 0, result.stderr
        page = out.read_text(encoding="utf-8")
        assert "http://" not in page
        assert "https://" not in page
        assert "<svg" in page
        assert 'id="data"' in page                    # the JSON island
        assert "prefers-color-scheme" in page         # theme-aware
        assert page.count("<script") == 2             # island + behaviour, nothing else

    def test_html_json_island_parses(self, tmp_path):
        project, graph = self._graph(tmp_path)
        out = tmp_path / "graph.html"
        run(["render", "--allow-unverified", "--format", "html", "--out", str(out)],
            project, graph)
        page = out.read_text(encoding="utf-8")
        island = page.split('<script id="data" type="application/json">', 1)[1]
        island = island.split("</script>", 1)[0].replace("<\\/", "</")
        assert len(json.loads(island)["edges"]) == 3

    def test_clean_graph_renders_without_the_override(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["render"], project, graph)
        assert result.returncode == 0, result.stderr

    def test_refuses_unverified_graph_unless_overridden(self, tmp_path):
        project, graph = self._graph(tmp_path)
        (project / "src" / "d.py").unlink()   # a file-backed node no longer resolves
        refused = run(["render"], project, graph)
        assert refused.returncode == 1
        assert "src/d.py" in refused.stderr
        allowed = run(["render", "--allow-unverified"], project, graph)
        assert allowed.returncode == 0, allowed.stderr
        assert "src/d.py" in allowed.stdout

    def test_no_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        result = run(["render"], project, tmp_path / "missing.json")
        assert result.returncode == 3

    def test_unknown_focus_exits_3(self, tmp_path):
        project, graph = self._graph(tmp_path)
        result = run(["render", "--allow-unverified", "--focus", "zzz.py"], project, graph)
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# session-start hook reports graph status (none / fresh / STALE)
# ---------------------------------------------------------------------------

HOOK = REPO / ".claude" / "hooks" / "session-start.sh"


class TestSessionStartGraphStatus:
    def _hook_project(self, tmp_path):
        project = tmp_path / "proj"
        scripts = project / ".claude" / "operations" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "project-graph.py").write_bytes(SCRIPT.read_bytes())
        # The presentation layer is a sibling import, so a tree with only the
        # script in it cannot start. Copying it here is what proves the split
        # did not break deployment -- install.sh ships operations/scripts/*.py,
        # which covers the new module, but this fixture builds its own tree.
        (scripts / "project_graph_render.py").write_bytes(RENDER_MODULE.read_bytes())
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        (project / "f.py").write_text("x = 1\n", encoding="utf-8")
        return project

    def _run_hook(self, project):
        result = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True,
                                cwd=str(project), timeout=60)
        assert result.returncode == 0
        return result.stdout

    def _build(self, project):
        payload = json.dumps({"version": 1,
                              "nodes": [{"id": "f.py", "kind": "file"}], "edges": []})
        subprocess.run(
            [sys.executable, str(project / ".claude/operations/scripts/project-graph.py"),
             "build", "--input", "-"],
            input=payload, capture_output=True, text=True, timeout=60,
            cwd=str(project),
            env={**os.environ, "CLAUDEKIT_PROJECT_ROOT": str(project)}, check=True)

    def test_no_graph_reports_none(self, tmp_path):
        project = self._hook_project(tmp_path)
        assert "Graph: none" in self._run_hook(project)

    def test_fresh_graph_reported(self, tmp_path):
        project = self._hook_project(tmp_path)
        self._build(project)
        assert "Graph: fresh" in self._run_hook(project)

    def test_changed_file_reports_stale(self, tmp_path):
        project = self._hook_project(tmp_path)
        self._build(project)
        (project / "f.py").write_text("x = 2\n", encoding="utf-8")
        out = self._run_hook(project)
        assert "Graph: STALE" in out
        assert "--merge" in out

class TestSkillHasOneCopy:
    """These two skills used to be maintained as byte-identical twins in
    `.claude/skills/` and `templates/skills/`. Task 008 batch 1 deleted the
    second tree, so the invariant is now "exactly one copy", not "two that
    match" -- a twin test would pass vacuously against a missing file."""

    def _copies(self, name):
        return [p for p in (REPO / ".claude" / "skills" / name / "SKILL.md",
                            REPO / "templates" / "skills" / name / "SKILL.md")
                if p.is_file()]

    def test_codebase_mapping_has_exactly_one_copy(self):
        assert [p.name for p in self._copies("codebase-mapping")] == ["SKILL.md"]

    def test_context_keeper_has_exactly_one_copy(self):
        assert [p.name for p in self._copies("context-keeper")] == ["SKILL.md"]


# ---------------------------------------------------------------------------
# verify - the stored graph vs. the working tree (anti-hallucination gate)
# ---------------------------------------------------------------------------

def write_graph(graph, data):
    """Write a graph file directly, bypassing `build` validation.

    Some verify violations (a dangling endpoint) are exactly what `build` refuses, so
    they can only be staged by writing the stored artifact by hand.
    """
    graph.write_text(json.dumps(data), encoding="utf-8")


class TestVerify:
    def test_clean_graph_exits_0(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        result = run(["verify"], project, graph)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "VERIFY OK" in result.stdout

    def test_no_graph_exits_3(self, tmp_path):
        project = make_project(tmp_path)
        result = run(["verify"], project, tmp_path / "missing.json")
        assert result.returncode == 3

    def test_deleted_file_reports_missing_node(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        build_graph(project, graph)
        (project / "src" / "c.py").unlink()
        result = run(["verify"], project, graph)
        assert result.returncode == 1
        assert "MISSING NODE" in result.stdout
        assert "src/c.py" in result.stdout

    def test_dangling_endpoint_reports_dangling_edge(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        write_graph(graph, {
            "version": 1,
            "nodes": [{"id": "src/a.py", "kind": "file"}],
            "edges": [{"from": "src/a.py", "to": "src/ghost.py",
                       "type": "import", "confidence": "extracted"}],
        })
        result = run(["verify"], project, graph)
        assert result.returncode == 1
        assert "DANGLING EDGE" in result.stdout
        assert "src/ghost.py" in result.stdout

    def test_unsupported_extracted_edge_exits_1(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = sample_input()
        # src/b.py is `VALUE = 1` - it never mentions `c`, so this claim is invented.
        data["edges"].append({"from": "src/b.py", "to": "src/c.py",
                              "type": "import", "confidence": "extracted"})
        build_graph(project, graph, data)
        result = run(["verify"], project, graph)
        assert result.returncode == 1
        assert "UNSUPPORTED EXTRACTED EDGE" in result.stdout
        assert "src/b.py" in result.stdout

    def test_self_edge_is_degenerate(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = sample_input()
        data["edges"].append({"from": "src/a.py", "to": "src/a.py",
                              "type": "reference", "confidence": "ambiguous"})
        build_graph(project, graph, data)
        result = run(["verify"], project, graph)
        assert result.returncode == 1
        assert "DEGENERATE EDGE" in result.stdout
        assert "self-edge" in result.stdout

    def test_duplicate_edge_is_degenerate(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = sample_input()
        data["edges"].append({"from": "src/a.py", "to": "src/b.py",
                              "type": "import", "confidence": "extracted"})
        build_graph(project, graph, data)
        result = run(["verify"], project, graph)
        assert result.returncode == 1
        assert "duplicate edge" in result.stdout

    def test_inferred_support_only_checked_under_strict(self, tmp_path):
        project = make_project(tmp_path)
        graph = tmp_path / "graph.json"
        data = sample_input()
        data["edges"].append({"from": "src/b.py", "to": "src/c.py",
                              "type": "import", "confidence": "inferred"})
        build_graph(project, graph, data)
        lenient = run(["verify"], project, graph)
        assert lenient.returncode == 0, lenient.stdout + lenient.stderr
        strict = run(["verify", "--strict"], project, graph)
        assert strict.returncode == 1
        assert "UNSUPPORTED INFERRED EDGE" in strict.stdout
