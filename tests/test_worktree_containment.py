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
from _worktree_fixtures import SEAM_ANCHOR, WtEnv, mutate_script

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


class TestLifecycleContainment:
    """TEST-CASES C-group cases on the lifecycle fixtures (real origin, real worktrees)."""

    def test_N04_unmerged_commits_are_refused_naming_ref_and_commits(self, wt_env):
        path = wt_env.make_wt("a", commits=2)
        proc = wt_env.mgr("remove", "a")
        assert proc.returncode == 2
        assert "main" in proc.stderr
        assert "a change 0" in proc.stderr and "a change 1" in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_E06_unknown_base_is_cannot_answer_not_yes(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        reg_path = wt_env.root / ".claude" / "state" / "worktrees.json"
        reg = json.loads(reg_path.read_text())
        reg["worktrees"][0]["base_branch"] = ""
        reg["worktrees"][0]["base"] = "HEAD"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        wt_env.git("checkout", "-q", "--detach", "HEAD")
        proc = wt_env.mgr("remove", "a")
        assert proc.returncode == 2
        assert "cannot tell" in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_E07_base_origin_main_resolves_to_the_default_branch_and_origin_ref(self, wt_env):
        path = wt_env.make_wt("a", commits=1, base="origin/main")
        reg = json.loads((wt_env.root / ".claude" / "state" / "worktrees.json").read_text())
        assert reg["worktrees"][0]["base_branch"] == "main"
        wt_env.merge_ff("a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")
        assert not path.exists() and not wt_env.branch_exists("agent/a")


class TestLifecycleMutationControls:
    """X11: break each safety rule the way it could regress and require the
    behaviour the real script shows to flip."""

    @staticmethod
    def _mutant(env, find, replace, tag, seam=""):
        out = mutate_script(env.tmp, find, replace, tag)
        if seam:
            text = out.read_text(encoding="utf-8")
            assert text.count(SEAM_ANCHOR) == 1
            out.write_text(text.replace(SEAM_ANCHOR, seam + SEAM_ANCHOR), encoding="utf-8")
        return out

    def test_X11a_not_on_origin_read_as_merged_deletes_local_only_work(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.git("merge", "-q", "--no-ff", "-m", "local only", "agent/a")
        mutant = self._mutant(wt_env, '        return "not-on-origin", ""\n',
                              '        return "merged", ""\n', "notonorigin")
        assert wt_env.mgr("reap", "--yes").returncode == 0 and path.exists()  # control
        wt_env.mgr("reap", "--yes", script=mutant)
        assert not path.exists(), "the not-on-origin rule is not load-bearing"

    def test_X11a_unproven_read_as_merged_deletes_unprovable_work(self, tmp_path):
        env = WtEnv(tmp_path, default_branch="master", set_head=False)
        path = env.make_raw_wt("agent-m", commits=1)
        env.merge_ff("agent-m")
        env.git("push", "-q", "origin", "master:main")
        env.git("config", "remote.origin.followRemoteHEAD", "never")
        env.git("fetch", "-q", "origin")
        env.git("remote", "set-head", "origin", "-d", check=False)
        mutant = self._mutant(env, '        return "unproven", base.problem or "no baseline"\n',
                              '        return "merged", ""\n', "unproven")
        assert env.mgr("reap", "--yes").returncode == 0 and path.exists()  # control
        env.mgr("reap", "--yes", script=mutant)
        assert not path.exists(), "the unproven-is-not-merged rule is not load-bearing"

    def test_X11b_ignoring_a_fetch_failure_reaps_against_stale_refs(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        wt_env.git("remote", "set-url", "origin", str(wt_env.tmp / "does-not-exist.git"))
        mutant = self._mutant(wt_env, "    if fetch.returncode != 0:\n",
                              "    if False:\n", "fetchguard")
        assert wt_env.mgr("reap", "--yes").returncode == 1 and path.exists()  # control
        wt_env.mgr("reap", "--yes", script=mutant)
        assert not path.exists(), "the fetch-failure guard is not load-bearing"

    def test_X11c_skipping_bundle_verification_deletes_after_a_corrupt_bundle(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        seam = ('    if name == "after-bundle":\n'
                '        open(str(ctx["path"]), "wb").write(b"corrupt")\n')
        mutant = self._mutant(wt_env, "\n    if verify.returncode != 0:\n        bundle.unlink",
                              "\n    if False:\n        bundle.unlink", "verify", seam=seam)
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force",
                          script=mutant)
        assert proc.returncode == 0 and not path.exists(), (
            "the bundle verification check is not load-bearing")

    def test_X11d_ignoring_worktree_locks_lets_reap_try_a_locked_worktree(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        wt_env.git("worktree", "unlock", str(path), check=False)
        wt_env.git("worktree", "lock", "--reason", "in-use", str(path))
        mutant = self._mutant(wt_env, '    if not row.locked:\n        return "none", ""\n',
                              '    if True:\n        return "none", ""\n', "locks")
        assert "kept a: locked: in-use" in wt_env.mgr("reap", "--yes").stdout  # control
        proc = wt_env.mgr("reap", "--yes", script=mutant)
        assert "locked: in-use" not in proc.stdout, "the lock check is not load-bearing"
