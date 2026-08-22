"""Behavioral tests for scripts/check-plan-artifacts.py.

Each test runs the real script as a subprocess and asserts on its exit code and
output -- the gate is proven to bind by mutating the artifact it guards.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-plan-artifacts.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def write_pair(tmp_path, plan_body, paths):
    plan = tmp_path / "plan-demo.md"
    plan.write_text(plan_body, encoding="utf-8")
    ops = tmp_path / "ops-demo.json"
    ops.write_text(
        json.dumps(
            {
                "plan": "demo",
                "operations": [
                    {"type": "file_create", "path": p, "content": "x"} for p in paths
                ],
            }
        ),
        encoding="utf-8",
    )
    return ops


def test_passes_when_plan_names_every_path(tmp_path):
    ops = write_pair(tmp_path, "writes src/a.py and tests/test_a.py\n",
                     ["src/a.py", "tests/test_a.py"])
    result = run(str(ops))
    assert result.returncode == 0, result.stderr


def test_fails_when_plan_omits_a_path(tmp_path):
    ops = write_pair(tmp_path, "writes src/a.py\n", ["src/a.py", "tests/test_a.py"])
    result = run(str(ops))
    assert result.returncode == 1
    assert "tests/test_a.py" in result.stderr


def test_no_plan_is_not_drift(tmp_path):
    ops = tmp_path / "ops-orphan.json"
    ops.write_text(
        json.dumps({"plan": "orphan",
                    "operations": [{"type": "file_create", "path": "a.py",
                                    "content": "x"}]}),
        encoding="utf-8",
    )
    assert run(str(ops)).returncode == 0


def test_legacy_files_format_is_checked(tmp_path):
    plan = tmp_path / "plan-legacy.md"
    plan.write_text("nothing named here\n", encoding="utf-8")
    ops = tmp_path / "ops-legacy.json"
    ops.write_text(
        json.dumps({"plan": "legacy",
                    "files": [{"path": "src/b.py",
                               "edits": [{"find": "a", "replace": "b"}]}]}),
        encoding="utf-8",
    )
    result = run(str(ops))
    assert result.returncode == 1
    assert "src/b.py" in result.stderr


def test_missing_config_is_reported(tmp_path):
    result = run(str(tmp_path / "nope.json"))
    assert result.returncode == 1
    assert "no such file" in result.stderr


def test_basename_counts_as_naming_the_artifact(tmp_path):
    """A plan that calls the file by name has named it -- the full path is not required."""
    ops = write_pair(tmp_path, "adds dispatch_resolve.py beside the hook\n",
                     [".claude/hooks/dispatch_resolve.py"])
    result = run(str(ops))
    assert result.returncode == 0, result.stderr


def test_unmentioned_artifact_still_fails(tmp_path):
    """The class being mechanised: the artifact appears nowhere in the plan."""
    ops = write_pair(tmp_path, "adds a hook\n", [".claude/hooks/dispatch_resolve.py"])
    result = run(str(ops))
    assert result.returncode == 1
    assert "dispatch_resolve.py" in result.stderr
