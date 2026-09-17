"""`worktree-manager.py remove` refuses to delete work that has not landed.

The predecessor ranged from `base_sha`, the sha pinned at create time, which
asks "does this branch have commits at all" -- yes for every working branch,
and still yes after the work is merged. So removal could never be earned and
`--force` was the only route, which trains the operator to force every time.

Containment is `ref..branch`: an empty range IS containment. And when no
containment ref resolves at all, CANNOT ANSWER IS NOT YES -- the old code read
the empty output as "merged" and deleted the checkout with exit 0.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WTM = REPO / ".claude" / "operations" / "scripts" / "worktree-manager.py"


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=check)


def run(args, project, script: Path = WTM):
    return subprocess.run([sys.executable, str(script), *args], cwd=str(project),
                          capture_output=True, text=True)


@pytest.fixture()
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@example.com")
    git(p, "config", "user.name", "t")
    (p / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    return p


def commit_in(wt: Path, text: str):
    (wt / "app.py").write_text(text, encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")


class TestContainment:
    def test_create_records_the_base_as_a_branch_name(self, project):
        assert run(["create", "feat"], project).returncode == 0
        reg = json.loads((project / ".claude" / "state" / "worktrees.json").read_text())
        assert reg["worktrees"][0]["base_branch"] == "main"

    def test_merged_work_can_be_removed_without_force(self, project):
        assert run(["create", "feat"], project).returncode == 0
        wt = project / ".worktrees" / "feat"
        commit_in(wt, "VALUE = 2\n")
        git(project, "merge", "-q", "--no-ff", "-m", "merge", "agent/feat")
        proc = run(["remove", "feat"], project)
        assert proc.returncode == 0, proc.stderr
        assert not wt.exists()

    def test_unmerged_work_is_refused_and_the_ref_is_named(self, project):
        assert run(["create", "feat"], project).returncode == 0
        commit_in(project / ".worktrees" / "feat", "VALUE = 3\n")
        proc = run(["remove", "feat"], project)
        assert proc.returncode == 2
        assert "not contained in main" in proc.stderr
        assert run(["remove", "feat", "--force"], project).returncode == 0

    def test_unresolvable_ref_refuses_rather_than_deleting(self, project):
        assert run(["create", "feat"], project).returncode == 0
        reg_path = project / ".claude" / "state" / "worktrees.json"
        reg = json.loads(reg_path.read_text())
        # A sha base whose branch was deleted, plus a detached primary: nothing
        # resolves, so nothing can be asked.
        reg["worktrees"][0]["base_branch"] = ""
        reg["worktrees"][0]["base"] = "HEAD"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        head = git(project, "rev-parse", "HEAD").stdout.strip()
        git(project, "checkout", "-q", "--detach", head)
        proc = run(["remove", "feat"], project)
        assert proc.returncode == 2, proc.stdout
        assert "cannot tell what" in proc.stderr
        assert (project / ".worktrees" / "feat").exists()

    def test_remote_tracking_base_resolves_to_its_local_branch(self, project, tmp_path):
        remote = tmp_path / "remote.git"
        git(project, "init", "-q", "--bare", str(remote))
        git(project, "remote", "add", "origin", str(remote))
        git(project, "push", "-q", "origin", "main")
        git(project, "fetch", "-q", "origin")
        assert run(["create", "feat", "--base", "origin/main"], project).returncode == 0
        reg = json.loads((project / ".claude" / "state" / "worktrees.json").read_text())
        assert reg["worktrees"][0]["base_branch"] == "main"
        proc = run(["remove", "feat"], project)
        assert proc.returncode == 0, proc.stderr


class TestMutationControls:
    """Break containment the way it was broken before, and require the tests
    above to flip."""

    @pytest.fixture()
    def mutant(self, tmp_path):
        made = []

        def _make(find: str, replace: str, tag: str) -> Path:
            src = WTM.read_text(encoding="utf-8")
            assert src.count(find) == 1, f"mutation anchor {tag!r} is not unique"
            dst = tmp_path / f"_mutant_{tag}.py"
            dst.write_text(src.replace(find, replace), encoding="utf-8")
            made.append(dst)
            return dst

        return _make

    def test_ranging_from_base_sha_makes_removal_unearnable(self, project, mutant):
        mutated = mutant(
            '        ["log", "--oneline", "--end-of-options", f"{ref}..{entry[\'branch\']}"],',
            '        ["log", "--oneline", "--end-of-options", f"{entry.get(\'base_sha\', ref)}..HEAD"],',
            "basesha",
        )
        assert run(["create", "feat"], project).returncode == 0
        wt = project / ".worktrees" / "feat"
        commit_in(wt, "VALUE = 2\n")
        git(project, "merge", "-q", "--no-ff", "-m", "merge", "agent/feat")
        proc = run(["remove", "feat"], project, script=mutated)
        assert proc.returncode == 2, (
            "the mutant allowed removal: the merged-is-removable test is not "
            "caused by the containment range")

    def test_empty_ref_read_as_containment_deletes_the_checkout(self, project, mutant):
        mutated = mutant(
            "            if not ref and not args.force:",
            "            if False:",
            "cannotanswer",
        )
        assert run(["create", "feat"], project).returncode == 0
        reg_path = project / ".claude" / "state" / "worktrees.json"
        reg = json.loads(reg_path.read_text())
        reg["worktrees"][0]["base_branch"] = ""
        reg["worktrees"][0]["base"] = "HEAD"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        git(project, "checkout", "-q", "--detach",
            git(project, "rev-parse", "HEAD").stdout.strip())
        proc = run(["remove", "feat"], project, script=mutated)
        assert proc.returncode == 0 and not (project / ".worktrees" / "feat").exists(), (
            "the cannot-answer guard is not load-bearing")
