"""Behavioural proof that `gen-plan-index.py` DERIVES plan state from evidence.

Every test builds a throwaway tree, runs the real script as a subprocess, and
asserts on the state it reports. Nothing touches the repo's own `.claude/plans/`
or mutates real git history -- each fixture is its own `git init` under `tmp_path`.

There are three states: `open`, `executed` (a `Plan-Id:` trailer commit) and
`legacy` (archived, no trailer). Approval records are local and gitignored, so
they are never an input: the index must read the same in a fresh clone.
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "gen-plan-index.py")

PLAN_BODY = "# Implementation Plan: fixture\n\nBody.\n"


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
    (root / ".claude" / "reports" / "reviews").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "gen-plan-index.py")
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


def commit_with_trailer(root, slug="fixture-plan"):
    (root / "touched.txt").write_text("changed\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", f"feat: do the thing\n\nPlan-Id: {slug}\n")


# --- open ---------------------------------------------------------------------

def test_plan_without_a_trailer_is_open(tree):
    assert state_of(tree) == "open"


def test_an_approval_record_does_not_change_the_state(tree):
    """Approval is local; it must never reach the committed index."""
    record = tree / ".claude" / "reports" / "reviews" / "fixture-plan.plan.json"
    record.write_text("{}\n")
    assert state_of(tree) == "open"


# --- Plan-Id trailer ----------------------------------------------------------

def test_plan_id_trailer_commit_yields_executed(tree):
    commit_with_trailer(tree)
    assert state_of(tree) == "executed"


def test_a_commit_without_the_trailer_is_not_executed(tree):
    """Pins that the trailer, not the mere existence of history, is the evidence."""
    (tree / "touched.txt").write_text("changed\n")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "feat(fixture): no trailer here")
    assert state_of(tree) != "executed"


# --- the --check gate ---------------------------------------------------------

def test_check_reds_when_index_is_stale_and_greens_after_regen(tree):
    assert run(tree).returncode == 0
    assert run(tree, "--check").returncode == 0

    commit_with_trailer(tree)  # the tree changed; INDEX.md now describes the past
    stale = run(tree, "--check")
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert "out of date" in stale.stderr

    assert run(tree).returncode == 0
    assert run(tree, "--check").returncode == 0


def test_check_reds_on_a_hand_edited_index(tree):
    """The header says never hand-edit; the gate is what makes that true."""
    assert run(tree).returncode == 0
    index = tree / ".claude" / "plans" / "INDEX.md"
    index.write_text(index.read_text().replace("`open`", "`executed`"))
    assert run(tree, "--check").returncode == 1


# --- archive / legacy ---------------------------------------------------------

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


# --- tracked vs working tree --------------------------------------------------
# INDEX.md is committed and gated in CI, so it derives from what the REPO holds.

def test_untracked_plan_gets_no_row_once_plans_are_tracked(tree):
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "chore: track the fixture plan")
    (tree / ".claude" / "plans" / "plan-scratch-draft.md").write_text(PLAN_BODY)
    assert run(tree).returncode == 0
    index = (tree / ".claude" / "plans" / "INDEX.md").read_text()
    assert "plan-scratch-draft.md" not in index
    assert "plan-fixture-plan.md" in index


def test_filter_stays_off_without_a_git_repo(tmp_path):
    """An installed user project is often not a repo at all."""
    root = tmp_path / "nogit"
    (root / "scripts").mkdir(parents=True)
    (root / ".claude" / "plans" / "archive").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "gen-plan-index.py")
    (root / ".claude" / "plans" / "plan-fixture-plan.md").write_text(PLAN_BODY)
    assert not (root / ".git").exists()
    assert state_of(root) == "open"
