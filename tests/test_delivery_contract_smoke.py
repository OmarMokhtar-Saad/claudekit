"""Zero-LLM-cost regression test for the "paths, never payloads" delivery contract
(plan-token-waste-workflow-fixes.md). A fake `claude` stub stands in for the real
opus spawn -- what's under test is the *transport*: does the surrounding shell
plumbing keep a large fake plan/ops payload off stdout and on disk, regardless of
what the model itself said. Runs the actual scripts (extract-json-from-plan.py,
validate-config-json.py) against a realistic ~40KB payload, matching the size of
the originally observed leak.

`/plan`'s scripted bash block is extracted from the real command file and
executed, so it exercises the literal current text.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS_DIR = os.path.join(REPO_ROOT, ".claude", "operations", "scripts")
PLAN_MD = os.path.join(REPO_ROOT, ".claude", "commands", "plan.md")

FAKE_OPS = {
    "plan": "toy-smoke-test",
    "operations": [
        {
            "type": "file_create",
            "path": "src/toy_smoke.py",
            # Padded content to land the whole payload near the ~40KB scale of the
            # originally observed leak (ops-hardening-implementer-contract.json).
            "content": "def toy():\n    return 1\n" + ("# padding line\n" * 1500),
        }
    ],
}
FAKE_PAYLOAD_MARKER = "UNIQUE-FAKE-PLAN-BODY-MARKER-DO-NOT-ECHO"


def _fake_plan_doc():
    # NOTE: plan.md's documented contract intentionally echoes the plan's first 3
    # non-blank lines to stdout as the summary -- that's the spec, not a leak. The
    # marker goes in the padded body (line 5+), which must NEVER reach stdout.
    body = (
        "# Implementation Plan: Toy Task\n\n"
        "## Overview\nThis is a fake planner response used only to test transport.\n\n"
        + (f"Filler prose line ({FAKE_PAYLOAD_MARKER}) padding the plan body.\n" * 400)
        + "\n```json\n" + json.dumps(FAKE_OPS) + "\n```\n"
    )
    return body


def _make_stub_claude(bin_dir, stdout_text):
    """A `claude` on PATH that ignores its args/stdin and just prints stdout_text --
    standing in for a real `claude -p --agent planner` spawn."""
    stub = os.path.join(bin_dir, "claude")
    with open(stub, "w") as f:
        f.write("#!/bin/sh\ncat <<'STUB_EOF'\n" + stdout_text + "\nSTUB_EOF\n")
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _extract_scripted_bash_block(markdown_text):
    """Pull the ```bash fence under the scripted `--deep` mechanism out of plan.md --
    tests the ACTUAL current command text, not a hand-copied mirror that can drift.

    The heading moved under `--deep` on 2026-09-19 (the default path is now inline,
    written by the parent session). Splitting on the OLD heading raised IndexError
    here rather than naming the drift, so the split is asserted before it is used."""
    heading = "### `--deep` mechanism B — scripted (claude -p)"
    assert heading in markdown_text, (
        "plan.md no longer carries %r; the scripted spawn this test covers was "
        "renamed or removed" % heading)
    section = markdown_text.split(heading, 1)[1]
    match = re.search(r"```bash\n(.*?)```", section, re.S)
    assert match, "plan.md's scripted invocation block structure changed"
    return match.group(1)


def _prepare_fake_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude" / "plans").mkdir(parents=True)
    shutil.copytree(SCRIPTS_DIR, repo / ".claude" / "operations" / "scripts")
    return repo


def test_plan_scripted_path_keeps_stdout_small_and_files_valid(tmp_path):
    repo = _prepare_fake_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_stub_claude(str(bin_dir), _fake_plan_doc())

    script = _extract_scripted_bash_block(open(PLAN_MD).read())

    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["ARGUMENTS"] = "toy smoke-test task"

    result = subprocess.run(
        ["bash", "-c", script], cwd=str(repo), env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    plans_dir = repo / ".claude" / "plans"
    plan_files = list(plans_dir.glob("plan-*.md"))
    assert len(plan_files) == 1, list(plans_dir.iterdir())
    ops_files = list(plans_dir.glob("*.ops.json"))
    assert len(ops_files) == 1, list(plans_dir.iterdir())

    # The fake ~40KB payload landed on disk...
    assert FAKE_PAYLOAD_MARKER in plan_files[0].read_text()
    assert json.loads(ops_files[0].read_text())["plan"] == "toy-smoke-test"

    # ...but never reached stdout: the marker and the padded body are absent, and
    # total stdout stays near the plan's documented ≤15-line / small-summary limit,
    # regardless of the ~40KB input.
    assert FAKE_PAYLOAD_MARKER not in result.stdout
    assert "padding line" not in result.stdout
    assert len(result.stdout) < 2000, result.stdout
    non_blank_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(non_blank_lines) <= 15, result.stdout


ARCHIVE_DIR_NAME = "archive"


def _queued_ops_configs(plans_dir):
    """Every queued ops config under `plans_dir`, INCLUDING the `ops-<slug>/` form.

    The first version of this listed `os.listdir(plans_dir)` and kept the entries
    where `os.path.isfile`, i.e. **top-level files only** -- which is the one shape
    no config in this repo has used since the multi-config directory convention
    started. Measured when that was found, 2026-08-24 on `cfc8a09`: **0** top-level
    configs, **50** in 16 `ops-*/` subdirectories, **35 of them already failing
    validation**. The gate had been scanning an empty set and passing vacuously
    while the exact condition it exists to report accumulated underneath it.

    `archive/` is pruned BY NAME, deliberately and not as an accident of the walk:
    spent and stale configs belong there (see its README), and their anchors are
    consumed by their own edits, so validating them would report every archived
    config forever.

    Takes the directory as an argument so the widening can be proven against a
    constructed tree instead of depending on the real repo happening to contain a
    violation -- which is the failure mode this function is the fix for.
    """
    found = []
    for root, dirs, files in os.walk(plans_dir):
        dirs[:] = sorted(d for d in dirs if d != ARCHIVE_DIR_NAME)
        found.extend(os.path.join(root, f) for f in files if f.endswith(".json"))
    return sorted(found)


def test_the_queued_ops_scan_reaches_subdirectories(tmp_path):
    """The mutation proof for `_queued_ops_configs`, on a throwaway tree.

    Red against the top-level-only version: `ops-x/bad.json` would not be returned.
    Also pins the other half -- an archived config must NOT be returned, or the
    gate below would report every spent config in the repo's history.
    """
    plans = tmp_path / "plans"
    top = plans / "top.json"
    nested = plans / "ops-x" / "bad.json"
    archived = plans / ARCHIVE_DIR_NAME / "ops-y" / "bad.json"
    deep = plans / "ops-z" / "sub" / "deeper.json"
    for path in (top, nested, archived, deep):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    # A non-config file must not be picked up just for living in the tree.
    (plans / "plan-x.md").write_text("# not a config", encoding="utf-8")

    found = _queued_ops_configs(str(plans))
    top, nested, archived, deep = (str(p) for p in (top, nested, archived, deep))

    assert nested in found, "the scan does not reach ops-<slug>/ -- the whole defect"
    assert top in found, "a top-level config must still be scanned"
    assert deep in found, "the walk must not stop at one level of nesting"
    assert archived not in found, "archive/ must stay pruned, or every spent config reports"
    assert not any(p.endswith(".md") for p in found)


def test_queued_ops_configs_validate_against_head():
    """Every queued (non-archived) ops config in .claude/plans/ must validate against
    the current tree. A stale config -- authored against files that have since changed --
    fails at execution time at best, or silently re-applies superseded text at worst
    (found live 2026-07-31: an archived config's replacement text would have reintroduced
    the `PLAN TO REVIEW: $PLAN_CONTENT` payload leak). Spent or stale configs belong in
    .claude/plans/archive/ (see its README), which this test deliberately skips.

    See `_queued_ops_configs` for why this once scanned nothing at all."""
    plans_dir = os.path.join(REPO_ROOT, ".claude", "plans")
    failures = []
    for path in _queued_ops_configs(plans_dir):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "validate-config-json.py"), path],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            rel = os.path.relpath(path, plans_dir)
            detail = (result.stdout.strip().splitlines()[-1] if result.stdout.strip()
                      else result.stderr.strip())
            failures.append(f"{rel}: {detail}")
    assert not failures, (
        "queued ops config(s) no longer validate against HEAD -- regenerate via /plan "
        "or move to .claude/plans/archive/ with a README entry:\n" + "\n".join(failures)
    )

def test_the_protected_guard_has_a_differential_gate_and_it_is_wired():
    """The REJECT->ALLOW banner covered only ONE of the repo's two deny-decisions.

    `check-validator-differential.py` pins MODULE_PATH to the command validator, so
    `shared.is_protected_file` -- the guard deciding whether an ops config may delete
    a file -- had no differential gate, and the first change to widen it passed CI
    green. Asserted on the CI file as well as the script's existence: a gate that
    exists but is not run is not a gate.
    """
    script = os.path.join(REPO_ROOT, "scripts", "check-protected-differential.py")
    assert os.path.isfile(script), "the protected-file differential gate is missing"
    assert os.access(script, os.X_OK), "gate is not executable"

    with open(os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml"),
              encoding="utf-8") as fh:
        ci = fh.read()
    assert "check-protected-differential.py" in ci, "gate exists but CI never runs it"
    assert "--require-baseline" in ci.split("check-protected-differential.py")[1][:120], (
        "gate runs without --require-baseline, so an unresolvable baseline passes it")


def test_the_protected_differential_gate_catches_an_identity_doc_regression(tmp_path):
    """The gate must FAIL when an identity document loses protection. Run against a
    mutated copy of the guard, because a gate proven only on the happy path is the
    shape this repo has shipped twice."""
    shared = os.path.join(REPO_ROOT, ".claude", "operations", "scripts", "shared.py")
    with open(shared, encoding="utf-8") as fh:
        original = fh.read()
    assert '    "README.md",\n' in original
    mutated = original.replace('    "README.md",\n', '', 1)
    with open(shared, "w", encoding="utf-8") as fh:
        fh.write(mutated)
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "scripts",
                                          "check-protected-differential.py"),
             "--baseline", "main"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=120)
    finally:
        with open(shared, "w", encoding="utf-8") as fh:
            fh.write(original)
    if "SKIP:" in result.stdout:
        import pytest
        pytest.skip("no usable baseline in this checkout: " + result.stdout.strip())
    assert result.returncode != 0, (
        "an identity document lost protection and the gate passed:\n" + result.stdout)
    assert "README.md" in result.stdout
