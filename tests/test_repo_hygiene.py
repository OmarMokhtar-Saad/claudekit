"""Behavioural coverage for repo-hygiene.py (plan-repo-hygiene-gates, phase B).

Each case is a safety property whose absence would lose a user's work. The
worktree-guard tests live in test_worktree_guard.py and ship with the guard.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HYGIENE = ROOT / ".claude" / "operations" / "scripts" / "repo-hygiene.py"

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, timeout=60)


# --- repo-hygiene safety properties ----------------------------------------
@pytest.fixture
def scratch_repo(tmp_path):
    """A real repo in tmp_path. Never the repo under test: an arity probe that
    ran `git <sub> <opt>` with cwd=REPO once destroyed uncommitted work."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f").write_text("1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def run_hygiene(repo, *args):
    return subprocess.run([sys.executable, str(HYGIENE), "--repo", str(repo)] + list(args),
                          capture_output=True, text=True, timeout=120)


def test_report_is_read_only(scratch_repo):
    _git(scratch_repo, "branch", "feature")
    before = _git(scratch_repo, "branch").stdout
    assert run_hygiene(scratch_repo, "report").returncode == 0
    assert _git(scratch_repo, "branch").stdout == before


def test_clean_without_yes_mutates_nothing(scratch_repo):
    _git(scratch_repo, "branch", "merged-one")
    before = _git(scratch_repo, "branch").stdout
    out = run_hygiene(scratch_repo, "clean")
    assert out.returncode == 0
    assert _git(scratch_repo, "branch").stdout == before, "dry run deleted a branch"


def test_unmerged_branch_is_never_deleted(scratch_repo):
    _git(scratch_repo, "checkout", "-qb", "unmerged")
    (scratch_repo / "g").write_text("2")
    _git(scratch_repo, "add", "-A")
    _git(scratch_repo, "commit", "-qm", "work")
    _git(scratch_repo, "checkout", "-q", "main")
    run_hygiene(scratch_repo, "clean", "--yes")
    assert "unmerged" in _git(scratch_repo, "branch").stdout


def test_max_deletions_refuses_before_mutating(scratch_repo):
    for i in range(6):
        _git(scratch_repo, "branch", f"b{i}")
    before = _git(scratch_repo, "branch").stdout
    out = run_hygiene(scratch_repo, "clean", "--yes", "--max-deletions", "2")
    assert out.returncode == 2
    assert _git(scratch_repo, "branch").stdout == before, "mutated despite exceeding the bound"


def test_oneline_is_silent_on_a_healthy_repo(scratch_repo):
    out = run_hygiene(scratch_repo, "report", "--oneline")
    assert out.returncode == 0
    assert out.stdout.strip() == "", f"noise on a healthy repo: {out.stdout!r}"
