"""Behavioral contract of `project-graph.py impact` (parent plan phase 4).

`impact --ops PLAN.ops.json` is the objective form of CLAUDE.md's Tier-2 rule
"reviewer ONLY if architecture is touched". Contract under test:

- exit 1 = architecture touched: a touched node is a hub/god-node, the touched
  set crosses a top-level package boundary, or a path is absent from the graph.
- exit 0 = a single-package change over mapped, low-coupling files.
- exit 2 = the ops.json is unreadable (missing, malformed, oversized, or a path
  that escapes the project root) - the same guards `build` applies to its input.
- exit 3 = no stored graph, so impact cannot be computed at all.

An UNKNOWN path escalates on purpose: the graph not knowing a file is ignorance,
not evidence of low impact. Everything runs the real script as a subprocess
against a temp project via CLAUDEKIT_PROJECT_ROOT / CLAUDEKIT_GRAPH_PATH.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "project-graph.py"


def run(args, project, graph=None):
    env = dict(os.environ)
    env["CLAUDEKIT_PROJECT_ROOT"] = str(project)
    if graph is not None:
        env["CLAUDEKIT_GRAPH_PATH"] = str(graph)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, env=env, timeout=60,
    )


def make_project(tmp_path):
    """src/hub.py with 25 dependents (>= DEFAULT_THRESHOLD), src/leaf.py, lib/other.py."""
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "lib").mkdir(parents=True)
    (project / "src" / "hub.py").write_text("HUB = 1\n", encoding="utf-8")
    (project / "src" / "leaf.py").write_text("LEAF = 1\n", encoding="utf-8")
    (project / "lib" / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
    nodes = [{"id": "src/hub.py", "kind": "file"},
             {"id": "src/leaf.py", "kind": "file"},
             {"id": "lib/other.py", "kind": "file"}]
    edges = []
    for i in range(25):
        caller = "src/dep%02d.py" % i
        (project / "src" / ("dep%02d.py" % i)).write_text("import hub\n", encoding="utf-8")
        nodes.append({"id": caller, "kind": "file"})
        edges.append({"from": caller, "to": "src/hub.py",
                      "type": "import", "confidence": "extracted"})
    return project, {"version": 1, "nodes": nodes, "edges": edges}


def build_graph(tmp_path):
    project, data = make_project(tmp_path)
    graph = tmp_path / "graph.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "build", "--input", "-", "--force"],
        capture_output=True, text=True, timeout=60, input=json.dumps(data),
        env={**os.environ, "CLAUDEKIT_PROJECT_ROOT": str(project),
             "CLAUDEKIT_GRAPH_PATH": str(graph)},
    )
    assert result.returncode == 0, result.stderr
    return project, graph


def write_ops(project, name, paths):
    ops = {"plan": "probe",
           "operations": [{"type": "code_edit", "path": p,
                           "edits": [{"find": "x", "replace": "y"}]} for p in paths]}
    target = project / name
    target.write_text(json.dumps(ops), encoding="utf-8")
    return name  # relative to the project root, like a real plan path


class TestImpactVerdicts:
    def test_god_node_escalates(self, tmp_path):
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "hub.ops.json", ["src/hub.py"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "GOD-NODE" in result.stdout
        assert "route to reviewer" in result.stdout

    def test_leaf_in_one_package_passes(self, tmp_path):
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "leaf.ops.json", ["src/leaf.py"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "GOD-NODE" not in result.stdout
        assert "local change" in result.stdout

    def test_cross_package_escalates(self, tmp_path):
        """Both files are leaves; crossing a module boundary alone is enough."""
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "cross.ops.json", ["src/leaf.py", "lib/other.py"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "spans 2 top-level packages" in result.stdout

    def test_unknown_path_escalates_and_is_not_reported_as_a_leaf(self, tmp_path):
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "new.ops.json", ["src/brand_new.py"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "UNKNOWN" in result.stdout
        assert "absent from the graph" in result.stdout
        # zeros would read as "leaf"; the row must carry dashes instead
        row = [ln for ln in result.stdout.splitlines() if "src/brand_new.py" in ln][0]
        assert " 0 " not in row

    def test_json_format_carries_the_verdict(self, tmp_path):
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "hub.ops.json", ["src/hub.py"])
        result = run(["impact", "--ops", ops, "--format", "json"], project, graph)
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["escalate"] is True
        assert payload["god_nodes"] == ["src/hub.py"]
        assert payload["unknown"] == []

    def test_threshold_override_changes_the_verdict(self, tmp_path):
        """The god-node rule is shared with `hubs`, including its --threshold knob."""
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "leaf.ops.json", ["src/leaf.py"])
        assert run(["impact", "--ops", ops], project, graph).returncode == 0
        hot = write_ops(project, "hot.ops.json", ["src/hub.py"])
        assert run(["impact", "--ops", hot, "--threshold", "1000"],
                   project, graph).returncode == 0


class TestImpactRejections:
    def test_malformed_ops_json_exits_2(self, tmp_path):
        project, graph = build_graph(tmp_path)
        (project / "bad.ops.json").write_text("{not json", encoding="utf-8")
        result = run(["impact", "--ops", "bad.ops.json"], project, graph)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "invalid JSON" in result.stderr

    def test_missing_ops_file_exits_2(self, tmp_path):
        project, graph = build_graph(tmp_path)
        result = run(["impact", "--ops", "nope.ops.json"], project, graph)
        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_operations_must_be_a_list(self, tmp_path):
        project, graph = build_graph(tmp_path)
        (project / "shape.ops.json").write_text(json.dumps({"operations": {}}),
                                                encoding="utf-8")
        result = run(["impact", "--ops", "shape.ops.json"], project, graph)
        assert result.returncode == 2
        assert "'operations' must be a list" in result.stderr

    def test_ops_path_escaping_the_root_is_refused(self, tmp_path):
        project, graph = build_graph(tmp_path)
        (tmp_path / "outside.ops.json").write_text(json.dumps({"operations": []}),
                                                   encoding="utf-8")
        result = run(["impact", "--ops", "../outside.ops.json"], project, graph)
        assert result.returncode == 2
        assert "escapes the project root" in result.stderr

    def test_operation_path_traversal_is_refused(self, tmp_path):
        project, graph = build_graph(tmp_path)
        ops = write_ops(project, "evil.ops.json", ["../../etc/passwd"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 2
        assert "'..' path segment" in result.stderr

    def test_no_graph_exits_3(self, tmp_path):
        project, graph = build_graph(tmp_path)
        graph.unlink()
        ops = write_ops(project, "leaf.ops.json", ["src/leaf.py"])
        result = run(["impact", "--ops", ops], project, graph)
        assert result.returncode == 3, result.stdout + result.stderr
        assert "no graph" in result.stdout
