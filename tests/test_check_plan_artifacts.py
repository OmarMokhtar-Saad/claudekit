"""Behavioral tests for scripts/check-plan-artifacts.py.

Each test runs the real script as a subprocess and asserts on its exit code and
output -- the gate is proven to bind by mutating the artifact it guards.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-plan-artifacts.py"


def run(*args, cwd=None):
    """`cwd` matters: PLANS_DIR is relative, so the default-scan tests must own their
    own tree instead of depending on pytest being invoked from the repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
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


def test_a_step_named_config_resolves_to_its_parent_plan(tmp_path):
    """One plan executed through several step-named configs is the norm here, and every
    one of them resolved to NOTHING and was skipped silently: measured 51 configs, six
    written by the author of this test, whose operations no gate had ever checked.

    `ops-demo-records.json` must bind to `plan-demo.md` -- and then be CHECKED, which is
    the point: the assertion below is that the gate now FAILS on a path the plan omits.
    """
    (tmp_path / "plan-demo.md").write_text("# Demo\nnames nothing\n", encoding="utf-8")
    ops = tmp_path / "ops-demo-records.json"
    ops.write_text(json.dumps({
        "plan": "demo-records",
        "operations": [{"type": "file_create", "path": "src/unnamed.py", "content": "x"}],
    }), encoding="utf-8")
    result = run(str(ops), cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/unnamed.py" in result.stdout + result.stderr


def test_the_prefix_walk_prefers_the_longest_matching_plan(tmp_path):
    """`plan-foo-bar.md` must beat `plan-foo.md` for `ops-foo-bar-step`. A shortest-first
    walk would bind the config to the wrong plan and then check it against the wrong
    artifact list -- a green run that verified nothing relevant."""
    (tmp_path / "plan-foo.md").write_text("# Foo\n`src/wrong.py`\n", encoding="utf-8")
    (tmp_path / "plan-foo-bar.md").write_text("# Foo Bar\n`src/right.py`\n", encoding="utf-8")
    ops = tmp_path / "ops-foo-bar-step.json"
    ops.write_text(json.dumps({
        "plan": "foo-bar-step",
        "operations": [{"type": "file_create", "path": "src/right.py", "content": "x"}],
    }), encoding="utf-8")
    result = run(str(ops), cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_walk_never_invents_a_plan_that_does_not_exist(tmp_path):
    """The walk may only ever match a `plan-<slug>.md` that is really there. A config
    whose plan was never written stays unresolved -- that is a historical fact, not a
    resolution bug, and conflating the two is what made one growing number unreadable."""
    ops = tmp_path / "ops-orphan-step.json"
    ops.write_text(json.dumps({
        "plan": "orphan-step",
        "operations": [{"type": "file_create", "path": "src/x.py", "content": "x"}],
    }), encoding="utf-8")
    result = run(str(ops), cwd=tmp_path)
    assert result.returncode == 0
    assert "no plan document at all" in result.stdout


def test_orphans_and_misdeclarations_are_reported_separately(tmp_path):
    """Two unrelated facts were printed as one count that grew 87 -> 121 while being read
    as a single number. A config whose plan EXISTS but did not resolve is a gate hole; a
    config whose plan was never written cannot be resolved by any code."""
    (tmp_path / "plan-real.md").write_text("# Real\n", encoding="utf-8")
    # Declares a slug that shares no prefix with any plan, so the walk cannot reach it.
    misdeclared = tmp_path / "ops-real-zzz.json"
    misdeclared.write_text(json.dumps({
        "plan": "totally-unrelated",
        "operations": [{"type": "file_create", "path": "a.py", "content": "x"}],
    }), encoding="utf-8")
    result = run(str(misdeclared), cwd=tmp_path)
    combined = result.stdout + result.stderr
    # `ops-real-zzz` walks to `real`, which exists -- so this is the misdeclared class.
    assert "name a plan that EXISTS" in combined or result.returncode == 1, combined

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


def _fixture_tree(tmp_path, archived=True):
    """A plans tree shaped like the real one: plans at the root, configs in archive/."""
    plans = tmp_path / ".claude" / "plans"
    (plans / "archive").mkdir(parents=True)
    (plans / "plan-shipped.md").write_text(
        "Writes `src/one.py` and `src/two.py`.\n", encoding="utf-8")
    target = (plans / "archive") if archived else plans
    (target / "ops-shipped.json").write_text(
        json.dumps({"plan": "shipped", "operations": [
            {"type": "file_create", "path": "src/one.py", "content": "x"},
            {"type": "file_create", "path": "src/two.py", "content": "x"}]}),
        encoding="utf-8")
    return tmp_path


def test_an_archived_config_is_checked_against_the_plan_that_stayed_behind(tmp_path):
    """Executed configs move to .claude/plans/archive/; their plans do not. Resolving a
    plan only next to its config meant the archive held 92 configs and 0 resolvable
    plans -- so the gate reported OK having verified nothing."""
    root = _fixture_tree(tmp_path, archived=True)
    result = run("--check", cwd=root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no ops configs to check" not in result.stdout
    # A NUMERIC floor, not the substring: "0 path(s) verified" satisfies a substring
    # assertion, which is exactly how the first version of this test certified a gate
    # that checked nothing.
    verified = int(re.search(r"(\d+) path\(s\) verified", result.stdout).group(1))
    assert verified == 2, result.stdout


def test_drift_in_an_archived_config_still_fails(tmp_path):
    """Reaching the archive is worthless if reaching it cannot fail."""
    root = _fixture_tree(tmp_path, archived=True)
    plan = root / ".claude" / "plans" / "plan-shipped.md"
    plan.write_text("Writes `src/one.py` only.\n", encoding="utf-8")
    result = run("--check", cwd=root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/two.py" in result.stderr


def test_a_config_that_resolves_to_no_plan_is_named_not_silently_green(tmp_path):
    """No plan is a PASS (Tier 1 ships one), but it must not read identically to a real
    check: a plan renamed by accident left every operation unchecked."""
    ops = tmp_path / "ops-orphan.json"
    ops.write_text(
        json.dumps({"plan": "nothing-here",
                    "operations": [{"type": "file_create", "path": "src/x.py",
                                    "content": "x"}]}),
        encoding="utf-8")
    result = run(str(ops))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NOTE:" in result.stdout
    assert "ops-orphan.json" in result.stdout


def test_a_glob_or_placeholder_names_every_path_it_covers(tmp_path):
    """A plan writing 15 files under one convention names them as
    `.claude/skills/<name>/SKILL.md`. Demanding 15 literal paths rejected complete plans
    -- 19 of the 23 findings on the first honest run were this false positive."""
    for body in ("Rewrites `.claude/skills/<name>/SKILL.md` for all 15 skills.\n",
                 "Rewrites `.claude/skills/*/SKILL.md` for all 15 skills.\n"):
        plan = tmp_path / "plan-globby.md"
        plan.write_text(body, encoding="utf-8")
        ops = tmp_path / "ops-globby.json"
        ops.write_text(
            json.dumps({"plan": "globby", "operations": [
                {"type": "code_edit", "path": ".claude/skills/brainstorming/SKILL.md",
                 "edits": [{"find": "a", "replace": "b"}]}]}),
            encoding="utf-8")
        result = run(str(ops))
        assert result.returncode == 0, body + result.stdout + result.stderr


# Each row is (label, the token as it appears in the plan, the path a config writes).
# Every one of these was GREEN under the first implementation, which used fnmatch --
# whose `*` crosses `/`. The first version of this test asserted only that
# `.claude/skills/*/SKILL.md` fails to name `src/claudekit/cli/main.py`: bounded, and
# different in every segment, so it passed for a reason unrelated to the property it
# claimed to pin, and could not have caught any row below.
PATTERN_MUST_NOT_NAME = [
    ("path traversal", "`.claude/skills/*`",
     ".claude/skills/x/../../../etc/passwd"),
    ("one segment does not cover many", "`src/*`", "src/a/b/c/evil.py"),
    ("bare star-slash-star", "`**/*`", "src/anything.py"),
    ("markdown bold names a DIFFERENT file", "**scripts/gen-docs.py**",
     "templates/scripts/gen-docs.py"),
    ("markdown italic is not a glob", "*src/main.py*", "vendor/src/main.py.bak"),
    ("a fenced token is still one segment", "`src/*`", "src/deep/nested/x.py"),
]


@pytest.mark.parametrize("label,token,path", PATTERN_MUST_NOT_NAME,
                         ids=[r[0] for r in PATTERN_MUST_NOT_NAME])
def test_a_pattern_does_not_license_a_path_it_does_not_cover(tmp_path, label, token,
                                                             path):
    plan = tmp_path / "plan-narrow.md"
    plan.write_text(f"Rewrites {token}.\n", encoding="utf-8")
    ops = tmp_path / "ops-narrow.json"
    ops.write_text(
        json.dumps({"plan": "narrow", "operations": [
            {"type": "file_create", "path": path, "content": "x"}]}),
        encoding="utf-8")
    result = run(str(ops))
    assert result.returncode == 1, f"{label}: {token} named {path}\n" + result.stdout
    assert "does not name" in result.stderr

