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

def test_a_declared_plan_is_resolved_even_when_the_filename_does_not_match(tmp_path):
    """The hole this closes: filename-only resolution reported OK on every config whose
    `plan` field differs from its filename, leaving its operations unchecked. Live case
    was `ops-mcp-probe.json`, which declares `"plan": "mcp-probe-addendum"`."""
    plan = tmp_path / "plan-addendum-slug.md"
    plan.write_text("names nothing\n", encoding="utf-8")
    ops = tmp_path / "ops-unrelated-name.json"
    ops.write_text(
        json.dumps({"plan": "addendum-slug",
                    "operations": [{"type": "file_create", "path": "src/probe.py",
                                    "content": "x"}]}),
        encoding="utf-8",
    )
    result = run(str(ops))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/probe.py" in result.stderr


def test_a_config_with_no_plan_at_all_still_passes(tmp_path):
    """Deliberate and unchanged: Tier 1 ships a config with no plan. Resolution by the
    `plan` field must not turn that routing fact into a failure."""
    ops = tmp_path / "ops-tier1.json"
    ops.write_text(
        json.dumps({"plan": "nothing-resolves-to-this",
                    "operations": [{"type": "file_create", "path": "a.py",
                                    "content": "x"}]}),
        encoding="utf-8",
    )
    assert run(str(ops)).returncode == 0


def test_a_basename_inside_a_longer_filename_does_not_count(tmp_path):
    """`mcp_probe.py` used to be satisfied by `test_mcp_probe.py` -- plain substring
    matching let an undescribed module pass because a DIFFERENT file's name contained
    it. Whole-token match, so the shorter name must be named in its own right."""
    ops = write_pair(tmp_path, "adds tests/test_mcp_probe.py\n",
                     ["src/claudekit/mcp_probe.py", "tests/test_mcp_probe.py"])
    result = run(str(ops))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/claudekit/mcp_probe.py" in result.stderr
    assert "tests/test_mcp_probe.py" not in result.stderr.split("does not name")[-1]


def test_a_path_named_in_prose_or_by_full_path_still_counts(tmp_path):
    """The converse, and the half that a first attempt got wrong. Tightening the match
    must not start crying wolf on complete plans: a backticked basename, a full path, a
    parenthesised mention, and — the regression this now pins — a name at the END OF A
    SENTENCE all count. Excluding every following `.` broke sentence-final prose, a shape
    12 of the 67 existing plan documents already use."""
    ops = write_pair(
        tmp_path,
        "adds `dispatch_resolve.py`, edits src/claudekit/cli/main.py, and (gen-docs.py).\n"
        "It also rewrites scripts/check-plan-artifacts.py. And tests/test_a.py.\n",
        [".claude/hooks/dispatch_resolve.py", "src/claudekit/cli/main.py",
         "scripts/gen-docs.py", "scripts/check-plan-artifacts.py", "tests/test_a.py"])
    result = run(str(ops))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_config_that_declares_a_plan_but_no_operations_fails(tmp_path):
    """An absent, empty or renamed operations key would otherwise satisfy every
    assertion above by iterating nothing."""
    plan = tmp_path / "plan-empty.md"
    plan.write_text("a plan with prose but a config that writes nothing\n",
                    encoding="utf-8")
    for payload in ({"plan": "empty", "operations": []},
                    {"plan": "empty", "ops": [{"type": "file_create", "path": "a.py"}]},
                    {"plan": "empty"}):
        ops = tmp_path / "ops-empty.json"
        ops.write_text(json.dumps(payload), encoding="utf-8")
        result = run(str(ops))
        assert result.returncode == 1, (payload, result.stdout + result.stderr)
        assert "no operations" in result.stderr, result.stderr


def test_a_plan_naming_a_shadowing_path_does_not_count(tmp_path):
    """The full-path branch's own version of the substring hole, and the sharper half:
    tightening only the basename left `scripts/gen-docs.py` satisfied by a plan naming
    `templates/scripts/gen-docs.py` -- a DIFFERENT file -- while a passing test
    certified the class as closed. That is worse than no fix."""
    ops = write_pair(tmp_path, "edits templates/scripts/gen-docs.py\n",
                     ["scripts/gen-docs.py"])
    result = run(str(ops))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "scripts/gen-docs.py" in result.stderr


def test_a_basename_with_a_longer_extension_does_not_count(tmp_path):
    """`main.py.tmpl` is a template, not `main.py`."""
    ops = write_pair(tmp_path, "renders main.py.tmpl\n", ["src/main.py"])
    assert run(str(ops)).returncode == 1


def test_a_declared_plan_cannot_escape_the_plans_directory(tmp_path):
    """The declared value is a slug, not a path fragment. Joined to the config's parent,
    `../x` pointed the gate at a file outside the plans directory -- any file that
    happens to mention the paths -- and returned green with nothing checked."""
    # No `plan-escape.md`: the filename slug must NOT resolve, or it wins first and the
    # test passes whether or not the escape was blocked -- which is how the first
    # version of this test certified a fix it could not observe. And OUTSIDE.md must NOT
    # name the path, so the unguarded script produces a DIFFERENT outcome (it resolves
    # outside the directory and reports drift) from the guarded one (nothing resolves).
    outside = tmp_path / "OUTSIDE.md"
    outside.write_text("prose that names no artifact\n", encoding="utf-8")
    plans = tmp_path / "plans"
    plans.mkdir()
    ops = plans / "ops-escape.json"
    ops.write_text(
        json.dumps({"plan": "../OUTSIDE",
                    "operations": [{"type": "file_create",
                                    "path": "src/undescribed.py", "content": "x"}]}),
        encoding="utf-8",
    )
    result = run(str(ops))
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "OUTSIDE" not in out, (
        "the declared plan escaped .claude/plans and the gate validated against a file "
        "outside it:\n" + out)


def test_a_declared_plan_is_normalised_like_the_executor_does(tmp_path):
    """`execute-json-ops.py:_approval_slugs` strips both `plan-` and `ops-`. Stripping
    only the filename-derived slug left `"plan": "ops-foo"` resolving to nothing and
    passing with every operation unchecked."""
    plan = tmp_path / "plan-foo.md"
    plan.write_text("names nothing\n", encoding="utf-8")
    ops = tmp_path / "ops-unrelated.json"
    ops.write_text(
        json.dumps({"plan": "ops-foo",
                    "operations": [{"type": "file_create", "path": "src/x.py",
                                    "content": "y"}]}),
        encoding="utf-8",
    )
    result = run(str(ops))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/x.py" in result.stderr


def test_a_writing_operation_with_no_path_is_not_a_silent_skip(tmp_path):
    """The gate runs standalone in CI, where the schema validator is not there to reject
    a renamed path key for it."""
    plan = tmp_path / "plan-pathless.md"
    plan.write_text("prose\n", encoding="utf-8")
    ops = tmp_path / "ops-pathless.json"
    ops.write_text(
        json.dumps({"plan": "pathless",
                    "operations": [{"type": "file_create", "target": "src/x.py"}]}),
        encoding="utf-8",
    )
    result = run(str(ops))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no path" in result.stderr

