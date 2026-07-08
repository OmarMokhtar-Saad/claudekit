"""Behavioral tests for extract-json-from-plan.py — the headless delivery
contract: planners can't write into .claude/ when spawned via claude -p, so
commands extract the ops config from planner stdout."""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..",
                      ".claude", "operations", "scripts", "extract-json-from-plan.py")

OPS = {"plan": "add-stats", "operations": [
    {"type": "file_create", "path": "src/stats.py", "content": "def mean(v):\n    ..."}]}


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, timeout=30)


def test_extracts_from_json_fence(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan\n\nSteps...\n\n```json\n" + json.dumps(OPS) + "\n```\n")
    out = tmp_path / "ops.json"
    r = _run(str(plan), "--output", str(out))
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text())["plan"] == "add-stats"


def test_extracts_despite_mixed_fences(tmp_path):
    # Regression: an unlabeled/markdown fence BEFORE the json fence used to
    # mis-pair the fence regex and shadow the real config (found against real
    # planner output in the 2026-07-08 E2E run).
    plan = tmp_path / "plan.md"
    plan.write_text(
        "Intro prose.\n\n```markdown\n# The plan doc\nSome steps.\n```\n\n"
        "And the config:\n\n```json\n" + json.dumps(OPS) + "\n```\n")
    r = _run(str(plan))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["operations"][0]["path"] == "src/stats.py"


def test_extracts_bare_json_without_fences(tmp_path):
    plan = tmp_path / "raw.md"
    plan.write_text("Planner said:\n" + json.dumps(OPS) + "\ndone.")
    r = _run(str(plan))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["plan"] == "add-stats"


def test_no_ops_config_exits_one(tmp_path):
    plan = tmp_path / "empty.md"
    plan.write_text("# A plan with no config\n\n```json\n{\"not\": \"ops\"}\n```\n")
    r = _run(str(plan))
    assert r.returncode == 1
    assert "no valid ops config" in r.stderr


def test_missing_file_exits_two(tmp_path):
    r = _run(str(tmp_path / "nope.md"))
    assert r.returncode == 2
