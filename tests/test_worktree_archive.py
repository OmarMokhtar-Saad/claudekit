"""`worktree-manager.py remove --archive`: unmerged work is bundled and VERIFIED before anything goes.

Contract (TEST-CASES.md section 4 and V16-V18):
  * archive dir is `.claude/state/worktree-archive/` (git-ignored), file
    `<slug>-<sha8>-<UTC ts>.bundle`, never overwritten (suffix `-2`, `-3`, ...);
  * `git bundle verify` must pass BEFORE the worktree or branch is touched; any archive failure
    deletes nothing and exits 1;
  * a branch with no commits beyond origin/default cannot make a bundle (git refuses an empty
    one), so it is archived as a verified ref `refs/archive/<slug>/<ts>` instead;
  * dirty and untracked work is captured as a WIP commit on `refs/archive/<slug>/wip-<ts>`.

Not covered here, by decision (PLAN.md R-section, cut to v2): `--archive-mode ref` (A02),
`--prune-archives` (A07) and the orphan-directory tarball (A10, E16).
"""
import errno
import glob
import os
import stat
import subprocess

from _worktree_fixtures import git, seam_script, wt_env  # noqa: F401  (fixture)


def archive_dir(env):
    return env.root / ".claude" / "state" / "worktree-archive"


def bundles(env, slug="a"):
    return sorted(glob.glob(str(archive_dir(env) / f"{slug}-*.bundle")))


def fresh_clone(env, name="restore"):
    dest = env.tmp / name
    subprocess.run(["git", "clone", "-q", str(env.origin), str(dest)],
                   check=True, capture_output=True)
    return dest


class TestArchiveBeforeDelete:
    def test_A01_unmerged_work_is_bundled_verified_then_deleted(self, wt_env):
        wt_env.make_wt("a", commits=2)
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        assert proc.returncode == 0, proc.stderr
        files = bundles(wt_env)
        assert len(files) == 1
        assert files[0] in proc.stdout  # the path is printed
        assert os.path.basename(files[0]).startswith("a-")
        assert subprocess.run(["git", "bundle", "verify", files[0]], cwd=str(wt_env.root),
                              capture_output=True).returncode == 0
        assert not wt_env.wt("a").exists() and not wt_env.branch_exists("agent/a")
        # a fresh clone restores both commits from the bundle
        clone = fresh_clone(wt_env)
        git(clone, "fetch", "-q", files[0], "refs/heads/*:refs/recovered/*")
        count = git(clone, "rev-list", "--count",
                    "origin/main..refs/recovered/agent/a").stdout.strip()
        assert count == "2"

    def test_N05_unmerged_force_delete_requires_an_archive(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--force")
        assert proc.returncode == 2
        assert "--archive" in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")
        assert bundles(wt_env) == []

    def test_A03_unwritable_archive_dir_deletes_nothing(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        adir = archive_dir(wt_env)
        adir.mkdir(parents=True)
        adir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        finally:
            adir.chmod(stat.S_IRWXU)
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_A04_a_bundle_that_fails_verification_deletes_nothing(self, wt_env, tmp_path):
        path = wt_env.make_wt("a", commits=1)
        script = seam_script(
            tmp_path, 'if name == "after-bundle":\n'
                      '    open(str(ctx["path"]), "wb").write(b"corrupt")')
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force",
                          script=script)
        assert proc.returncode == 1
        assert "verif" in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_V18_disk_full_while_archiving_deletes_nothing(self, wt_env, tmp_path):
        path = wt_env.make_wt("a", commits=1)
        script = seam_script(
            tmp_path, 'if name == "after-bundle":\n'
                      f'    raise OSError({errno.ENOSPC}, "No space left on device")')
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force",
                          script=script)
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_A05_V17_dirty_and_untracked_work_survives_in_a_wip_commit(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        (path / "app.py").write_text("VALUE = 42\n", encoding="utf-8")
        (path / "notes.txt").write_text("untracked notes\n", encoding="utf-8")
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists() and not wt_env.branch_exists("agent/a")
        files = bundles(wt_env)
        assert len(files) == 1
        clone = fresh_clone(wt_env)
        git(clone, "fetch", "-q", files[0], "refs/archive/*:refs/recovered-archive/*",
            "refs/heads/*:refs/recovered/*")
        refs = git(clone, "for-each-ref", "--format=%(refname)",
                   "refs/recovered-archive/").stdout.split()
        wip = [r for r in refs if "/wip-" in r]
        assert len(wip) == 1, refs
        assert git(clone, "show", f"{wip[0]}:notes.txt").stdout == "untracked notes\n"
        assert git(clone, "show", f"{wip[0]}:app.py").stdout == "VALUE = 42\n"
        assert git(clone, "show", f"{wip[0]}:f_a_0.txt").stdout == "a 0\n"

    def test_A06_archive_lives_under_ignored_state_and_leaves_status_clean(self, wt_env):
        wt_env.make_wt("a", commits=1)
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        assert proc.returncode == 0, proc.stderr
        assert str(archive_dir(wt_env)) in proc.stdout
        assert wt_env.git("status", "--porcelain").stdout == ""

    def test_A08_an_existing_archive_name_is_never_overwritten(self, wt_env):
        wt_env.make_wt("a", commits=1)
        tip = wt_env.git("rev-parse", "agent/a").stdout.strip()
        adir = archive_dir(wt_env)
        adir.mkdir(parents=True)
        stamp = 1700000000
        taken = adir / f"a-{tip[:8]}-20231114T221320Z.bundle"
        taken.write_bytes(b"precious earlier archive")
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force",
                          env={"SOURCE_DATE_EPOCH": str(stamp)})
        assert proc.returncode == 0, proc.stderr
        assert taken.read_bytes() == b"precious earlier archive"
        assert len(bundles(wt_env)) == 2


class TestEmptyAndMerged:
    def test_H11_A09_merged_worktree_with_archive_works(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        tip = wt_env.git("rev-parse", "agent/a").stdout.strip()
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists() and not wt_env.branch_exists("agent/a")
        refs = wt_env.git("for-each-ref", "--format=%(objectname) %(refname)",
                          "refs/archive/a/").stdout.split("\n")
        assert any(line.startswith(tip) for line in refs), refs

    def test_V16_zero_commits_beyond_default_gets_a_verified_ref_archive(self, wt_env):
        wt_env.make_wt("a")
        tip = wt_env.git("rev-parse", "agent/a").stdout.strip()
        proc = wt_env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        assert proc.returncode == 0, proc.stderr
        assert "Traceback" not in proc.stderr
        assert bundles(wt_env) == []  # git refuses an empty bundle; a ref is used instead
        refs = wt_env.git("for-each-ref", "--format=%(objectname) %(refname)",
                          "refs/archive/a/").stdout.split("\n")
        assert any(line.startswith(tip) for line in refs), refs


class TestRecovery:
    def _remove_with_archive(self, env):
        env.make_wt("a", commits=2)
        proc = env.mgr("remove", "a", "--delete-branch", "--archive", "--force")
        assert proc.returncode == 0, proc.stderr
        return bundles(env)[0]

    def test_A11_the_documented_recovery_steps_work(self, wt_env):
        bundle = self._remove_with_archive(wt_env)
        wt_env.git("fetch", "-q", bundle, "refs/heads/*:refs/recovered/*")
        count = wt_env.git("rev-list", "--count",
                           "origin/main..refs/recovered/agent/a").stdout.strip()
        assert count == "2"

    def test_A12_the_same_slug_can_be_recreated_from_the_recovered_ref(self, wt_env):
        bundle = self._remove_with_archive(wt_env)
        wt_env.git("fetch", "-q", bundle, "refs/heads/*:refs/recovered/*")
        proc = wt_env.mgr("create", "a", "--base", "refs/recovered/agent/a")
        assert proc.returncode == 0, proc.stderr
        assert (wt_env.wt("a") / "f_a_1.txt").read_text() == "a 1\n"
