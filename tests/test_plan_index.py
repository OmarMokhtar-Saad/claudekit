"""Behavioural proof that `gen-plan-index.py` DERIVES plan state from evidence.

Every test builds a throwaway tree, runs the real script as a subprocess, and
asserts on the state it reports. Nothing asserts on internal structure, and
nothing touches the repo's own `.claude/plans/` or mutates real git history --
each fixture is its own `git init` under `tmp_path`.

Two of these are mutation proofs rather than happy paths, because both failure
modes are silent by nature:

  * `test_mutating_ops_json_flips_approved_to_drifted` -- an index that reported
    `approved` from the mere PRESENCE of a record would pass a plain approved-case
    test. Changing the ops.json after approval is the only thing that tells the
    two apart, and `review-record.py check` must actually bind for the flip to
    happen.
  * `test_backup_manifest_alone_never_yields_executed` -- `backups/` is gitignored,
    so treating a manifest as proof of execution would make INDEX.md lie on a
    fresh clone while looking perfectly correct on the machine that ran it.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "gen-plan-index.py")
REVIEW_RECORD = os.path.join(
    REPO_ROOT, ".claude", "operations", "scripts", "review-record.py")

PLAN_BODY = "# Implementation Plan: fixture\n\nBody.\n"
OPS = {
    "plan": "fixture-plan",
    "operations": [
        {"type": "file_create", "path": "src/fixture.py", "content": "x = 1\n"},
    ],
}


def git(root, *args):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "f@example.com",
        "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "f@example.com",
        "GIT_CONFIG_GLOBAL": os.path.join(str(root), ".gitconfig-none"),
        "GIT_CONFIG_SYSTEM": os.path.join(str(root), ".gitconfig-none"),
    })
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, env=env, check=True)


@pytest.fixture()
def tree(tmp_path):
    """An isolated repo carrying the script under test and one fixture plan."""
    root = tmp_path / "tree"
    (root / "scripts").mkdir(parents=True)
    (root / ".claude" / "plans" / "archive").mkdir(parents=True)
    (root / ".claude" / "operations" / "scripts").mkdir(parents=True)
    (root / ".claude" / "reports" / "reviews").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "gen-plan-index.py")
    shutil.copy(REVIEW_RECORD,
                root / ".claude" / "operations" / "scripts" / "review-record.py")
    (root / ".claude" / "plans" / "plan-fixture-plan.md").write_text(PLAN_BODY)
    git(root, "init", "-q", "-b", "main")
    return root


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "gen-plan-index.py"), *args],
        cwd=str(root), capture_output=True, text=True,
    )


def state_of(root, plan_rel="plan-fixture-plan.md"):
    """The state the generator reports for one plan, read from INDEX.md."""
    assert run(root).returncode == 0
    index = (root / ".claude" / "plans" / "INDEX.md").read_text()
    for line in index.splitlines():
        if f"`.claude/plans/{plan_rel}`" in line:
            return line.split("|")[2].strip().strip("`")
    raise AssertionError(f"{plan_rel} missing from INDEX.md:\n{index}")


def write_ops(root, payload=None):
    ops = root / ".claude" / "plans" / "ops-fixture-plan.json"
    ops.write_text(json.dumps(payload or OPS, indent=2) + "\n")
    return ops


def approve(root, ops):
    """Bind an APPROVED verdict to the current bytes of ops.json."""
    result = subprocess.run(
        [sys.executable,
         str(root / ".claude" / "operations" / "scripts" / "review-record.py"),
         "write", str(root / ".claude" / "plans" / "plan-fixture-plan.md"), str(ops),
         "--score", "95", "--decision", "APPROVED"],
        cwd=str(root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- 11: no ops.json ---------------------------------------------------------

def test_plan_without_ops_json_is_not_started(tree):
    assert state_of(tree) == "not_started"


# --- 12: approved, and the mutation proof that it binds ----------------------

def test_ops_json_with_approved_record_is_approved(tree):
    approve(tree, write_ops(tree))
    assert state_of(tree) == "approved"


def test_mutating_ops_json_flips_approved_to_drifted(tree):
    ops = write_ops(tree)
    approve(tree, ops)
    assert state_of(tree) == "approved"

    mutated = json.loads(json.dumps(OPS))
    mutated["operations"].append(
        {"type": "file_create", "path": "src/sneaked_in.py", "content": "y = 2\n"})
    write_ops(tree, mutated)

    assert state_of(tree) == "drifted", (
        "an ops.json changed after approval must never read as approved")
    stale = run(tree, "--check")
    assert "DRIFTED" in stale.stderr, stale.stderr


def test_ops_json_without_a_record_is_planned(tree):
    write_ops(tree)
    assert state_of(tree) == "planned"


def test_a_non_authorising_verdict_is_revise_not_approved(tree):
    ops = write_ops(tree)
    result = subprocess.run(
        [sys.executable,
         str(tree / ".claude" / "operations" / "scripts" / "review-record.py"),
         "write", str(tree / ".claude" / "plans" / "plan-fixture-plan.md"), str(ops),
         "--score", "62", "--decision", "REVISE"],
        cwd=str(tree), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert state_of(tree) == "revise"


# --- 13: Plan-Id trailer ----------------------------------------------------

def test_plan_id_trailer_commit_yields_executed(tree):
    write_ops(tree)
    (tree / "touched.txt").write_text("changed\n")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m",
        "feat(fixture): do the thing\n\nPlan-Id: fixture-plan\n")
    assert state_of(tree) == "executed"


def test_a_commit_without_the_trailer_is_not_executed(tree):
    """Pins that the trailer, not the mere existence of history, is the evidence."""
    write_ops(tree)
    (tree / "touched.txt").write_text("changed\n")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "feat(fixture): no trailer here")
    assert state_of(tree) != "executed"


# --- 14: the --check gate ---------------------------------------------------

def test_check_reds_when_index_is_stale_and_greens_after_regen(tree):
    assert run(tree).returncode == 0
    assert run(tree, "--check").returncode == 0

    write_ops(tree)  # the tree changed; INDEX.md now describes the past
    stale = run(tree, "--check")
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert "out of date" in stale.stderr
    assert "says not_started, should be planned" in stale.stderr, stale.stderr

    assert run(tree).returncode == 0
    assert run(tree, "--check").returncode == 0


def test_check_reds_on_a_hand_edited_index(tree):
    """The header says never hand-edit; the gate is what makes that true."""
    assert run(tree).returncode == 0
    index = tree / ".claude" / "plans" / "INDEX.md"
    index.write_text(index.read_text().replace("`not_started`", "`executed`"))
    assert run(tree, "--check").returncode == 1


# --- 15: the gitignored backups/ manifest ------------------------------------

def test_backup_manifest_alone_never_yields_executed(tree):
    (tree / ".gitignore").write_text("backups/\n")
    backup = tree / "backups" / "ops-fixture-plan-20260824-120000-000001"
    backup.mkdir(parents=True)
    (backup / "manifest.json").write_text('{"plan": "fixture-plan"}\n')
    write_ops(tree)

    assert state_of(tree) == "planned", (
        "a gitignored backup manifest is a local hint, never proof of execution")
    index = (tree / ".claude" / "plans" / "INDEX.md").read_text()
    assert "local run detected" not in index, (
        "the advisory is machine-local; in INDEX.md it would red --check in CI")
    assert "local run detected" in run(tree).stdout


# --- archive / legacy -------------------------------------------------------

def test_archived_plan_without_a_trailer_is_legacy(tree):
    src = tree / ".claude" / "plans" / "plan-fixture-plan.md"
    dest = tree / ".claude" / "plans" / "archive" / "plan-old-thing.md"
    shutil.copy(src, dest)
    assert state_of(tree, "archive/plan-old-thing.md") == "legacy"


def test_archived_plan_with_a_trailer_is_executed_not_legacy(tree):
    dest = tree / ".claude" / "plans" / "archive" / "plan-old-thing.md"
    dest.write_text(PLAN_BODY)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "chore: land it\n\nPlan-Id: old-thing\n")
    assert state_of(tree, "archive/plan-old-thing.md") == "executed"
