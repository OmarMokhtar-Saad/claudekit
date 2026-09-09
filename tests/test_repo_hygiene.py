"""Behavioural coverage for repo-hygiene.py (plan-repo-hygiene-gates, phase B).

Each case is a safety property whose absence would lose a user's work. The
worktree-guard tests live in test_worktree_guard.py and ship with the guard.
"""
import importlib.util
import subprocess
import sys
import tempfile
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

def test_a_sibling_worktree_outside_the_root_is_never_offered():
    """Deliberate sibling layouts (../.ck-main) are outside the root and are
    someone's working tree; only the ephemeral temp-dir class is reclaimable.

    Regression: the first version classified EVERY outside-root worktree as
    junk, which offered ClaudeKit's own `.ck-main` for deletion.

    This drives the predicate directly rather than through a fixture, and that
    is not a shortcut: pytest's `tmp_path` is itself under the system temp root,
    so a "sibling" built there is genuinely ephemeral and the integration-level
    version of this test could only ever confirm the bug it is meant to catch.
    """
    spec = importlib.util.spec_from_file_location("hygiene_under_test", HYGIENE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert not mod._under_tempdir(Path("/Users/someone/IdeaProjects/.ck-main"))
    assert not mod._under_tempdir(Path("/Users/someone/proj-wt/feature"))
    assert mod._under_tempdir(Path(tempfile.mkdtemp()) / "wt")
    # A path merely SHARING a prefix with a temp root is not inside it.
    assert not mod._under_tempdir(Path("/tmpfoo/wt"))

def test_clean_selects_from_the_ephemeral_set_not_the_outside_set():
    """Bind the WIRING, not just the predicate.

    The predicate test above passes even when `ephemeral` is computed as plain
    `outside` -- it never reaches cmd_clean's selection. A mutation proved that:
    reverting the fix left the suite green. This asserts the selection itself,
    which is the line the regression actually lived on.
    """
    src = HYGIENE.read_text(encoding="utf-8")
    sel = src[src.index("wt_targets = "):]
    sel = sel[:sel.index("\n\n")]
    assert "worktrees_ephemeral" in sel, "clean no longer selects from the ephemeral set"
    assert "worktrees_outside_root" not in sel, (
        "clean selects every outside-root worktree again -- a deliberate sibling "
        "worktree would be offered for deletion"
    )
    assert '_under_tempdir(p)' in src, "the ephemeral classification lost its temp-dir test"



def test_an_ephemeral_worktree_is_offered(scratch_repo):
    """The reclaimable class: under a temp dir, whose parent dies with its session."""
    eph = Path(tempfile.mkdtemp()) / "wt"
    _git(scratch_repo, "worktree", "add", "-b", "eph", str(eph))
    out = run_hygiene(scratch_repo, "clean")
    assert "STRANDED" in run_hygiene(scratch_repo, "report").stdout or str(eph) in out.stdout
    assert str(eph) in out.stdout, "an ephemeral worktree was not offered for removal"

