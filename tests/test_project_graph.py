"""Behavioral contract of .claude/operations/scripts/project-graph.py.

The script stores an agent-built codebase graph at .claude/project-graph.json
and answers structural queries so agents stop re-grepping. Contract under test:

- build validates agent JSON (exit 2 with per-record messages), computes
  hash/loc itself, refuses overwrite without --force (exit 1), and --merge
  replaces only incoming node ids plus edges touching them.
- query/path/hubs answer from the stored graph; a miss or absent graph exits 3
  (the caller's signal to fall back to grep).
- stale re-hashes file-backed nodes and exits 1 listing CHANGED/MISSING nodes.
- the codebase-mapping and context-priming SKILL.md twins (.claude/skills vs
  templates/skills) stay byte-identical.

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
# asset twins stay in lockstep
# ---------------------------------------------------------------------------

class TestSkillTwinsIdentical:
    def _pair(self, name):
        live = REPO / ".claude" / "skills" / name / "SKILL.md"
        template = REPO / "templates" / "skills" / name / "SKILL.md"
        return live.read_bytes(), template.read_bytes()

    def test_codebase_mapping_twins_identical(self):
        live, template = self._pair("codebase-mapping")
        assert live == template

    def test_context_priming_twins_identical(self):
        live, template = self._pair("context-priming")
        assert live == template
