"""Locks and races around `worktree-manager.py reap` / `remove` / `create` (TEST-CASES.md group K, V01-V06, I03).

Two different locks are in play and they must not be confused:
  * the git worktree lock (`git worktree lock --reason "claudekit agent slug=<slug> ts=<epoch>"`),
    set by `create`; it marks a LIVE agent. Its age (the ts in the reason) is the only liveness
    signal: the pid of the short-lived `create` process proves nothing (R1);
  * the RegistryLock file `.claude/locks/worktree-manager.lock` that serializes mutations.

Races are made deterministic with the `_checkpoint` seam: tests copy the manager and make
`_checkpoint(name, **ctx)` run code at a named point of the lifecycle.
"""
import json
import os
import subprocess
import time

from _worktree_fixtures import git, seam_script, wt_env  # noqa: F401  (fixture)


def kept_reason(proc, name):
    for line in proc.stdout.splitlines():
        if line.startswith(f"kept {name}:"):
            return line.split(":", 1)[1].strip()
    return None


def registry_slugs(env):
    raw = env.registry_bytes()
    return [e["slug"] for e in json.loads(raw)["worktrees"]] if raw else []


def relock(env, slug, reason):
    path = str(env.wt(slug))
    git(env.root, "worktree", "unlock", path, check=False)
    git(env.root, "worktree", "lock", "--reason", reason, path)


class TestConcurrentRuns:
    def test_K01_V05_two_concurrent_reaps_remove_each_item_once(self, wt_env):
        for name in ("a", "b", "c", "d"):
            wt_env.make_wt(name, commits=1)
            wt_env.merge_ff(name)
        first = wt_env.popen("reap", "--yes")
        second = wt_env.popen("reap", "--yes")
        out1, err1 = first.communicate(timeout=120)
        out2, err2 = second.communicate(timeout=120)
        assert first.returncode == 0 and second.returncode == 0, (err1, err2)
        assert "Traceback" not in err1 + err2
        reaped = [ln for ln in (out1 + out2).splitlines() if ln.startswith("reaped ")]
        assert sorted(ln.split()[1] for ln in reaped) == ["a", "b", "c", "d"], reaped
        for name in ("a", "b", "c", "d"):
            assert not wt_env.wt(name).exists() and not wt_env.branch_exists(f"agent/{name}")
        assert registry_slugs(wt_env) == []
        json.loads(wt_env.registry_bytes())  # still valid JSON

    def test_K02_create_waits_for_a_reap_that_holds_the_lock(self, wt_env, tmp_path):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        marker = tmp_path / "in-lock.marker"
        script = seam_script(
            tmp_path,
            'if name == "in-lock":\n'
            f'    open({str(marker)!r}, "w").write("x")\n'
            '    import time\n'
            '    time.sleep(3)',
        )
        reap = wt_env.popen("reap", "--yes", script=script)
        assert wt_env.sleep_until(marker.exists), "reap never reached the lock"
        started = time.time()
        create = wt_env.popen("create", "b")
        time.sleep(1.0)
        assert create.poll() is None, "create ran while reap held the RegistryLock"
        out, err = create.communicate(timeout=60)
        reap.communicate(timeout=60)
        assert create.returncode == 0, err
        assert time.time() - started >= 1.0
        assert reap.returncode == 0
        # the new worktree was created after the reap finished and was not reaped
        assert wt_env.wt("b").exists() and registry_slugs(wt_env) == ["b"]
        assert not wt_env.wt("a").exists()

    def test_V04_create_is_not_blocked_while_reap_is_fetching(self, wt_env, tmp_path):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        marker = tmp_path / "before-fetch.marker"
        script = seam_script(
            tmp_path,
            'if name == "before-fetch":\n'
            f'    open({str(marker)!r}, "w").write("x")\n'
            '    import time\n'
            '    time.sleep(6)',
        )
        reap = wt_env.popen("reap", "--yes", script=script)
        assert wt_env.sleep_until(marker.exists), "reap never reached the fetch"
        create = wt_env.mgr("create", "b", timeout=60)
        still_fetching = reap.poll() is None
        out, err = reap.communicate(timeout=60)
        assert create.returncode == 0, create.stderr
        assert still_fetching, "create had to wait for the reap: the fetch ran under the lock"
        assert reap.returncode == 0, err
        # `b` is brand new, zero commits (so provably merged) but locked as a live agent
        assert wt_env.wt("b").exists()

    def test_K06_stale_registry_lock_file_is_broken_and_the_run_proceeds(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        lock = wt_env.root / ".claude" / "locks" / "worktree-manager.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("1", encoding="utf-8")
        old = time.time() - 3600
        os.utime(lock, (old, old))
        proc = wt_env.mgr("reap", "--yes", timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")

    def test_K07_a_file_appearing_before_removal_is_caught_by_the_recheck(self, wt_env, tmp_path):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        script = seam_script(
            tmp_path,
            'if name == "before-remove":\n'
            '    open(os.path.join(ctx["path"], "late.txt"), "w").write("new work")',
        )
        removed = wt_env.mgr("remove", "a", "--delete-branch", script=script)
        assert removed.returncode == 2, (removed.stdout, removed.stderr)
        assert path.exists() and (path / "late.txt").exists()
        assert wt_env.branch_exists("agent/a")
        reaped = wt_env.mgr("reap", "--yes", script=script)
        assert reaped.returncode == 0, reaped.stderr
        assert wt_env.kept(reaped, "a")
        assert (path / "late.txt").exists() and wt_env.branch_exists("agent/a")

    def test_K08_a_run_killed_after_the_worktree_is_gone_converges_on_rerun(self, wt_env, tmp_path):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        script = seam_script(
            tmp_path,
            'if name == "after-worktree-remove":\n'
            '    import os as _os\n'
            '    _os._exit(137)',
        )
        killed = wt_env.mgr("reap", "--yes", script=script)
        assert killed.returncode != 0
        assert not wt_env.wt("a").exists()
        assert wt_env.branch_exists("agent/a")  # the run died before the branch delete
        again = wt_env.mgr("reap", "--yes", timeout=60)
        assert again.returncode == 0, again.stderr
        assert "Traceback" not in again.stderr
        assert not wt_env.branch_exists("agent/a")
        assert registry_slugs(wt_env) == []

    def test_I03_branch_delete_failure_is_reported_and_the_rerun_completes(self, wt_env, tmp_path):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        script = seam_script(
            tmp_path,
            'if name == "before-branch-delete":\n'
            '    import subprocess as _sp\n'
            '    _sp.run(["git", "-C", str(ctx["root"]), "checkout", "-q", ctx["branch"]],'
            ' check=True)',
        )
        proc = wt_env.mgr("reap", "--yes", script=script)
        assert proc.returncode == 1, (proc.stdout, proc.stderr)
        assert "Traceback" not in proc.stderr
        assert not wt_env.wt("a").exists()
        assert registry_slugs(wt_env) == []  # the registry reflects the removal that DID happen
        assert wt_env.branch_exists("agent/a")
        wt_env.git("checkout", "-q", "main")
        again = wt_env.mgr("reap", "--yes", timeout=60)
        assert again.returncode == 0, again.stderr
        assert not wt_env.branch_exists("agent/a")

    def test_V06_a_commit_after_classification_keeps_the_branch(self, wt_env, tmp_path):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        script = seam_script(
            tmp_path,
            'if name == "after-classify":\n'
            '    import subprocess as _sp\n'
            f'    _sp.run(["git", "-C", {str(path)!r}, "commit", "-q", "--allow-empty", '
            '"-m", "late work"], check=True)',
        )
        proc = wt_env.mgr("reap", "--yes", script=script)
        assert proc.returncode == 0, proc.stderr
        assert wt_env.kept(proc, "a")
        assert path.exists() and wt_env.branch_exists("agent/a")
        assert "late work" in wt_env.git("log", "--format=%s", "agent/a").stdout


class TestWorktreeLocks:
    def test_K03_K09_own_lock_means_a_live_agent_and_is_kept(self, wt_env):
        path = wt_env.make_wt("a", commits=1, locked=True)
        wt_env.merge_ff("a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert kept_reason(proc, "a") == "locked"
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_N13_a_foreign_lock_is_kept_with_its_reason_and_remove_force_refuses(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        relock(wt_env, "a", "in-use")
        proc = wt_env.mgr("reap", "--yes", "--break-stale-locks")
        assert proc.returncode == 0, proc.stderr
        assert kept_reason(proc, "a") == "locked: in-use"
        assert path.exists()
        forced = wt_env.mgr("remove", "a", "--force")
        assert forced.returncode == 2
        assert "in-use" in forced.stderr
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_V01_a_fresh_own_lock_is_kept_even_with_break_stale_locks(self, wt_env):
        path = wt_env.make_wt("a", commits=1, locked=True)
        wt_env.merge_ff("a")
        # the creator process is long gone: that must not matter (R1)
        proc = wt_env.mgr("reap", "--yes", "--break-stale-locks")
        assert proc.returncode == 0, proc.stderr
        assert kept_reason(proc, "a") == "locked"
        assert path.exists()

    def test_V02_K05_an_old_own_lock_is_stale_and_broken_only_on_request(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        relock(wt_env, "a", "claudekit agent slug=a ts=1")
        plain = wt_env.mgr("reap", "--yes")
        assert plain.returncode == 0, plain.stderr
        assert kept_reason(plain, "a") == "stale-lock"
        assert path.exists()
        broken = wt_env.mgr("reap", "--yes", "--break-stale-locks")
        assert broken.returncode == 0, broken.stderr
        assert wt_env.reaped(broken, "a")
        assert not path.exists() and not wt_env.branch_exists("agent/a")

    def test_V02_dirty_or_unmerged_stale_locks_are_still_kept(self, wt_env):
        dirty = wt_env.make_wt("d", commits=1, dirty=True)
        wt_env.merge_ff("d")
        unmerged = wt_env.make_wt("u", commits=1)
        relock(wt_env, "d", "claudekit agent slug=d ts=1")
        relock(wt_env, "u", "claudekit agent slug=u ts=1")
        proc = wt_env.mgr("reap", "--yes", "--break-stale-locks")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.kept(proc, "d") and wt_env.kept(proc, "u")
        assert dirty.exists() and unmerged.exists()
        assert wt_env.branch_exists("agent/d") and wt_env.branch_exists("agent/u")

    def test_V03_remove_unlocks_its_own_lock_but_refuses_a_foreign_one(self, wt_env):
        own = wt_env.make_wt("own", locked=True)
        removed = wt_env.mgr("remove", "own")
        assert removed.returncode == 0, removed.stderr
        assert not own.exists()
        foreign = wt_env.make_wt("foreign")
        relock(wt_env, "foreign", "someone else is working here")
        refused = wt_env.mgr("remove", "foreign")
        assert refused.returncode == 2
        assert "someone else" in refused.stderr
        assert foreign.exists()
        assert subprocess.run(
            ["git", "-C", str(wt_env.root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True).stdout.count("locked") == 1
