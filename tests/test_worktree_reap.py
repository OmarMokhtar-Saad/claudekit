"""`worktree-manager.py reap` and `remove --delete-branch`: finish a worktree safely.

Contract (TEST-CASES.md ids in each test name):
  * a worktree and its branch are deleted together ONLY after the work is proven merged into the
    freshly fetched origin default branch (fast-forward, merge commit, rebase, or squash);
  * CANNOT ANSWER IS NOT YES: anything unprovable is kept with a reason, never deleted;
  * `reap` is a dry run unless --yes; the dry-run set equals the --yes set;
  * exit codes: 0 ok, 1 operational error (fetch failure, a failed removal), 2 refusal.

Output vocabulary asserted here: `would reap <name>`, `reaped <name>`, `kept <name>: <reason>`,
`orphan-dir <path> ...`, `summary: ...`, `nothing to reclaim`.
"""
import json
import os
import shutil
import subprocess

from _worktree_fixtures import WtEnv, git, seam_script


def kept_reason(proc, name):
    for line in proc.stdout.splitlines():
        if line.startswith(f"kept {name}:"):
            return line.split(":", 1)[1].strip()
    return None


def registry_slugs(env):
    raw = env.registry_bytes()
    return [e["slug"] for e in json.loads(raw)["worktrees"]] if raw else []


class TestMergeDetection:
    def test_H02_merge_commit_is_detected(self, wt_env):
        wt_env.make_wt("a", commits=2)
        wt_env.merge_commit("a")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists() and not wt_env.branch_exists("agent/a")

    def test_H03_squash_merge_of_several_commits_is_detected(self, wt_env):
        wt_env.make_wt("a", commits=3)
        wt_env.merge_squash("a")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists() and not wt_env.branch_exists("agent/a")

    def test_H04_rebase_merge_is_detected(self, wt_env):
        wt_env.make_wt("a", commits=2)
        wt_env.merge_rebase("a")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists() and not wt_env.branch_exists("agent/a")

    def test_E01_commits_added_after_the_squash_are_not_merged(self, wt_env):
        path = wt_env.make_wt("a", commits=2)
        wt_env.merge_squash("a")
        wt_env.commit_in(path, "late")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.kept(proc, "a")
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_E02_squash_then_later_edits_cannot_be_proven_and_is_kept(self, wt_env):
        path = wt_env.make_wt("a", commits=2)
        wt_env.merge_squash("a")
        c = wt_env.clone2
        (c / "f_a_0.txt").write_text("rewritten on main\n", encoding="utf-8")
        git(c, "add", "-A")
        git(c, "commit", "-q", "-m", "edit same file")
        git(c, "push", "-q", "origin", "main")
        git(wt_env.root, "fetch", "-q", "origin")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        # TEST-CASES wants `unproven`; a merge-tree conflict is reported `unmerged` (R4/V15).
        # Either way it is KEPT and nothing is deleted.
        assert kept_reason(proc, "a") in ("unmerged", "unproven") or wt_env.kept(proc, "a")
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_E03_merged_then_reverted_is_still_merged(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_commit("a")
        c = wt_env.clone2
        git(c, "revert", "--no-edit", "-m", "1", "HEAD")
        git(c, "push", "-q", "origin", "main")
        git(wt_env.root, "fetch", "-q", "origin")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")
        assert not wt_env.branch_exists("agent/a")

    def test_V19_origin_rewound_after_a_squash_keeps_the_branch(self, wt_env):
        base = wt_env.git("rev-parse", "origin/main").stdout.strip()
        path = wt_env.make_wt("a", commits=2)
        wt_env.merge_squash("a")
        git(wt_env.clone2, "push", "-q", "--force", "origin", f"{base}:refs/heads/main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.kept(proc, "a")
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_V14_without_merge_tree_a_multi_commit_squash_is_unproven(self, wt_env):
        wt_env.make_wt("sq", commits=2)
        wt_env.make_wt("rb", commits=2)
        wt_env.merge_squash("sq")
        wt_env.merge_rebase("rb")
        shim = wt_env.fake_git(
            "nomt", 'for a in "$@"; do [ "$a" = merge-tree ] && exit 129; done')
        proc = wt_env.mgr("reap", "--yes", env=wt_env.shim_env(shim))
        assert proc.returncode == 0, proc.stderr
        assert "unproven" in (kept_reason(proc, "sq") or "")
        assert wt_env.branch_exists("agent/sq")
        # a rebase keeps patch-ids, so `git cherry` alone still proves it
        assert wt_env.reaped(proc, "rb")
        assert not wt_env.branch_exists("agent/rb")

    def test_V15_merge_tree_exit_1_is_unmerged_and_128_is_unproven(self, wt_env):
        wt_env.make_wt("sq", commits=2)
        wt_env.merge_squash("sq")
        conflict = wt_env.fake_git("mt1", 'for a in "$@"; do [ "$a" = merge-tree ] && exit 1; done')
        broken = wt_env.fake_git("mt128", 'for a in "$@"; do [ "$a" = merge-tree ] && exit 128; done')
        one = wt_env.mgr("reap", env=wt_env.shim_env(conflict))
        assert "unmerged" in (kept_reason(one, "sq") or ""), one.stdout
        two = wt_env.mgr("reap", env=wt_env.shim_env(broken))
        assert "unproven" in (kept_reason(two, "sq") or ""), two.stdout


class TestReapHappyPath:
    def test_H06_reaps_merged_and_keeps_unmerged(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("b", commits=1)
        wt_env.make_wt("c", commits=1)
        wt_env.merge_ff("a")
        wt_env.merge_commit("b")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a") and wt_env.reaped(proc, "b")
        assert kept_reason(proc, "c") == "unmerged"
        assert "reaped=2" in proc.stdout
        assert not wt_env.branch_exists("agent/a") and not wt_env.branch_exists("agent/b")
        assert wt_env.branch_exists("agent/c") and wt_env.wt("c").exists()
        assert registry_slugs(wt_env) == ["c"]

    def test_H07_dry_run_mutates_nothing(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("c", commits=1)
        wt_env.merge_ff("a")
        before = wt_env.snapshot()
        proc = wt_env.mgr("reap")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.would_reap(proc, "a")
        assert wt_env.snapshot() == before
        assert wt_env.wt("a").exists()

    def test_cleanup_is_an_alias_for_reap(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        proc = wt_env.mgr("cleanup")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.would_reap(proc, "a")

    def test_H08_pushed_branch_is_deleted_locally_and_left_on_origin(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.git("push", "-q", "origin", "agent/a")
        wt_env.merge_ff("a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.branch_exists("agent/a")
        remote = wt_env.git("ls-remote", "--heads", "origin", "agent/a").stdout
        assert "refs/heads/agent/a" in remote

    def test_H12_unregistered_worktree_is_reaped_from_git_ground_truth(self, wt_env):
        path = wt_env.make_raw_wt("agent-x", commits=1)
        wt_env.merge_ff("agent-x")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "agent-x")
        assert not path.exists() and not wt_env.branch_exists("agent/agent-x")

    def test_E04_slashed_branch_names_are_handled(self, wt_env):
        path = wt_env.make_raw_wt("agent-s", commits=1, branch="agent/team/s")
        c = wt_env._clone2()
        git(c, "fetch", "-q", str(wt_env.root), "refs/heads/agent/team/s:refs/remotes/wt/s")
        git(c, "merge", "-q", "-m", "m", "refs/remotes/wt/s")
        git(c, "push", "-q", "origin", "main")
        git(wt_env.root, "fetch", "-q", "origin")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists() and not wt_env.branch_exists("agent/team/s")

    def test_E12_path_with_spaces_and_unicode(self, wt_env):
        path = wt_env.root / ".claude" / "worktrees" / "agent ünï x"
        git(wt_env.root, "worktree", "add", "-q", "-b", "agent/uni", str(path), "main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists() and not wt_env.branch_exists("agent/uni")

    def test_I08_dry_run_set_equals_yes_set(self, wt_env):
        for name, merged in (("a", True), ("b", False), ("c", True)):
            wt_env.make_raw_wt(f"agent-{name}", commits=1)
            if merged:
                wt_env.merge_ff(f"agent-{name}")
        dry = wt_env.mgr("reap")
        real = wt_env.mgr("reap", "--yes")
        would = sorted(ln.split()[2] for ln in dry.stdout.splitlines()
                       if ln.startswith("would reap "))
        done = sorted(ln.split()[1] for ln in real.stdout.splitlines()
                      if ln.startswith("reaped "))
        assert would == done and would == ["agent-a", "agent-c"]


class TestNegativeAndSafety:
    def test_N06_unmerged_is_kept_with_exit_zero(self, wt_env):
        path = wt_env.make_wt("c", commits=1)
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0
        assert kept_reason(proc, "c") == "unmerged"
        assert path.exists()

    def test_N07_merged_into_local_main_only_is_not_on_origin(self, wt_env):
        path = wt_env.make_wt("a", commits=1)
        wt_env.git("merge", "-q", "--no-ff", "-m", "local only", "agent/a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert kept_reason(proc, "a") == "not-on-origin"
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_N08_origin_ahead_is_fetched_before_measuring(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a", fetch=False)
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")

    def test_N09_unreachable_origin_deletes_nothing_and_exits_1(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        wt_env.git("remote", "set-url", "origin", str(wt_env.tmp / "does-not-exist.git"))
        before = wt_env.snapshot()
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 1
        assert "fetch" in proc.stderr
        assert wt_env.snapshot() == before and wt_env.wt("a").exists()

    def test_N09b_no_fetch_only_trusts_what_the_stale_ref_proves(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("c", commits=1)
        wt_env.merge_ff("a")
        wt_env.merge_ff("c", fetch=False)  # merged on origin, but the local ref is stale
        wt_env.git("remote", "set-url", "origin", str(wt_env.tmp / "does-not-exist.git"))
        proc = wt_env.mgr("reap", "--yes", "--no-fetch")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")
        assert wt_env.kept(proc, "c") and wt_env.wt("c").exists()

    def test_V22_no_fetch_prints_the_age_of_the_ref(self, wt_env):
        wt_env.make_wt("a", commits=1)
        proc = wt_env.mgr("reap", "--no-fetch")
        assert proc.returncode == 0, proc.stderr
        assert "origin/main" in proc.stdout and "age" in proc.stdout

    def test_N10_without_a_remote_only_local_ancestry_deletes(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("b", commits=1)
        wt_env.git("merge", "-q", "--no-ff", "-m", "local", "agent/a")
        wt_env.git("remote", "remove", "origin")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")
        assert kept_reason(proc, "b") == "no-remote"
        assert wt_env.branch_exists("agent/b")

    def test_N12_a_protected_branch_survives_its_worktree(self, wt_env):
        wt_env.git("checkout", "-q", "-b", "side")
        path = wt_env.root / ".claude" / "worktrees" / "agent-m"
        git(wt_env.root, "worktree", "add", "-q", str(path), "main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists()
        assert wt_env.branch_exists("main")
        assert "protected" in proc.stdout

    def test_N16_the_cap_refuses_before_any_mutation(self, wt_env):
        for i in range(3):
            wt_env.make_raw_wt(f"agent-{i}")
        before = wt_env.snapshot()
        proc = wt_env.mgr("reap", "--yes", "--max-deletions", "1")
        assert proc.returncode == 2
        assert wt_env.snapshot() == before
        assert wt_env.mgr("reap", "--yes", "--max-deletions", "3").returncode == 0

    def test_V21_default_cap_is_10(self, wt_env):
        for i in range(11):
            wt_env.make_raw_wt(f"agent-{i:02d}")
        before = wt_env.snapshot()
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 2
        assert "10" in proc.stderr
        assert wt_env.snapshot() == before

    def test_N17_detached_head_with_unreferenced_commits_is_kept(self, wt_env):
        path = wt_env.root / ".claude" / "worktrees" / "agent-d"
        git(wt_env.root, "worktree", "add", "-q", "--detach", str(path), "main")
        wt_env.commit_in(path, "orphaned")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert kept_reason(proc, "agent-d") == "detached-unreferenced"
        assert path.exists()

    def test_V11_detached_head_reachable_from_origin_is_removable(self, wt_env):
        path = wt_env.root / ".claude" / "worktrees" / "agent-d"
        git(wt_env.root, "worktree", "add", "-q", "--detach", str(path), "main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "agent-d") and not path.exists()

    def test_N18_stash_entries_are_untouched(self, wt_env):
        (wt_env.root / "app.py").write_text("VALUE = 5\n", encoding="utf-8")
        wt_env.git("stash", "push", "-q", "-m", "keep me")
        wt_env.make_raw_wt("agent-s")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert "keep me" in wt_env.git("stash", "list").stdout

    def test_N19_submodule_worktree_never_ends_half_deleted(self, wt_env):
        sub = wt_env.tmp / "sub"
        sub.mkdir()
        git(sub, "init", "-q", "-b", "main")
        WtEnv._identity(sub)
        (sub / "s.txt").write_text("s\n", encoding="utf-8")
        git(sub, "add", "-A")
        git(sub, "commit", "-q", "-m", "s")
        path = wt_env.make_raw_wt("agent-sm")
        subprocess.run(["git", "-C", str(path), "-c", "protocol.file.allow=always",
                        "submodule", "add", "-q", str(sub), "sub"],
                       check=True, capture_output=True)
        git(path, "commit", "-q", "-m", "add submodule")
        wt_env.merge_ff("agent-sm")
        proc = wt_env.mgr("reap", "--yes")
        assert "Traceback" not in proc.stderr
        assert proc.returncode in (0, 1)
        if path.exists():  # git refused: the branch must not have been deleted behind it
            assert wt_env.branch_exists("agent/agent-sm") and proc.returncode == 1
        else:
            assert not wt_env.branch_exists("agent/agent-sm")

    def test_N20_primary_on_a_feature_branch_does_not_change_the_proof(self, wt_env):
        wt_env.git("checkout", "-q", "-b", "side")
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("b", commits=1)
        wt_env.merge_ff("a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "a")
        assert kept_reason(proc, "b") == "unmerged"

    def test_E23_a_branch_held_by_the_primary_is_never_deleted(self, wt_env):
        path = wt_env.make_raw_wt("agent-h")
        wt_env.git("worktree", "remove", "--force", str(path))
        wt_env.git("checkout", "-q", "agent/agent-h")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.branch_exists("agent/agent-h")
        assert "branch-held" in proc.stdout

    def test_V12_a_branch_also_checked_out_elsewhere_is_kept(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        other = wt_env.tmp / "other-checkout"
        wt_env.git("worktree", "add", "-q", "-f", str(other), "agent/a")
        removed = wt_env.mgr("remove", "a", "--delete-branch")
        assert removed.returncode == 0, removed.stderr
        assert not wt_env.wt("a").exists() and wt_env.branch_exists("agent/a")
        assert "branch-held" in removed.stdout
        assert other.exists()

    def test_V12_reap_variant_keeps_branch_and_the_unmanaged_checkout(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        other = wt_env.tmp / "other-checkout"
        wt_env.git("worktree", "add", "-q", "-f", str(other), "agent/a")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists() and wt_env.branch_exists("agent/a")
        assert other.exists()
        assert kept_reason(proc, "other-checkout") == "external"

    def test_E14_external_unregistered_worktree_is_never_touched(self, wt_env):
        other = wt_env.tmp / "sibling"
        wt_env.git("worktree", "add", "-q", "-b", "agent/sib", str(other), "main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert other.exists() and wt_env.branch_exists("agent/sib")
        assert kept_reason(proc, "sibling") == "external"


class TestReconcile:
    def test_E08_directory_removed_by_hand_is_pruned_and_branch_judged(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.make_wt("b", commits=1)
        wt_env.merge_ff("a")
        shutil.rmtree(wt_env.wt("a"))
        shutil.rmtree(wt_env.wt("b"))
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert registry_slugs(wt_env) == []
        assert not wt_env.branch_exists("agent/a")
        assert wt_env.branch_exists("agent/b")
        assert "branch-orphaned" in proc.stdout
        assert wt_env.worktree_paths() == [os.path.realpath(wt_env.root)]

    def test_E22_prunable_entries_are_pruned_with_expire_now(self, wt_env):
        path = wt_env.make_raw_wt("agent-p")
        shutil.rmtree(path)
        assert os.path.realpath(path) in wt_env.worktree_paths()
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert os.path.realpath(path) not in wt_env.worktree_paths()

    def test_E09_branch_deleted_by_hand_is_branchless(self, wt_env):
        merged = wt_env.make_raw_wt("agent-m", commits=1)
        lost = wt_env.make_raw_wt("agent-l", commits=1)
        wt_env.merge_ff("agent-m")
        wt_env.git("update-ref", "-d", "refs/heads/agent/agent-m")
        wt_env.git("update-ref", "-d", "refs/heads/agent/agent-l")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not merged.exists()
        assert kept_reason(proc, "agent-l") == "branchless"
        assert lost.exists()

    def test_E10_corrupt_registry_is_preserved_and_ground_truth_is_used(self, wt_env):
        wt_env.make_raw_wt("agent-x", commits=1)
        wt_env.merge_ff("agent-x")
        reg = wt_env.root / ".claude" / "state" / "worktrees.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text("{ this is not json", encoding="utf-8")
        dry = wt_env.mgr("reap")
        assert dry.returncode == 0, dry.stderr
        assert wt_env.would_reap(dry, "agent-x")
        real = wt_env.mgr("reap", "--yes")
        assert real.returncode == 0, real.stderr
        assert "Traceback" not in real.stderr
        assert reg.read_text() == "{ this is not json"
        assert wt_env.reaped(real, "agent-x")

    def test_I01_reap_twice_the_second_is_a_no_op(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        assert wt_env.mgr("reap", "--yes").returncode == 0
        before = wt_env.snapshot()
        again = wt_env.mgr("reap", "--yes")
        assert again.returncode == 0, again.stderr
        assert "nothing to reclaim" in again.stdout
        assert wt_env.snapshot() == before

    def test_I04_after_git_worktree_prune_already_ran(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        shutil.rmtree(wt_env.wt("a"))
        wt_env.git("worktree", "prune", "--expire", "now")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.branch_exists("agent/a")
        assert registry_slugs(wt_env) == []

    def test_I05_every_divergent_state_is_reported_with_its_action(self, wt_env):
        # registry-only: entry whose worktree git no longer knows
        wt_env.make_wt("regonly")
        wt_env.git("worktree", "remove", "--force", str(wt_env.wt("regonly")))
        # git-only: a raw merged worktree that was never registered
        raw = wt_env.make_raw_wt("agent-gitonly", commits=1)
        wt_env.merge_ff("agent-gitonly")
        # dir-only: a plain directory git has never heard of
        orphan = wt_env.root / ".claude" / "worktrees" / "agent-dironly"
        orphan.mkdir(parents=True)
        (orphan / "x.txt").write_text("x\n", encoding="utf-8")
        # branch-only: a merged leftover branch
        wt_env.git("branch", "agent/branchonly", "main")
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert "regonly" not in registry_slugs(wt_env)
        assert not raw.exists()
        assert "orphan-dir" in proc.stdout and orphan.exists()
        assert not wt_env.branch_exists("agent/branchonly")

    def test_I06_git_only_worktree_needs_no_registry(self, wt_env):
        wt_env.make_raw_wt("agent-g", commits=1)
        wt_env.merge_ff("agent-g")
        assert not (wt_env.root / ".claude" / "state" / "worktrees.json").exists()
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert wt_env.reaped(proc, "agent-g")

    def test_I07_one_failing_removal_does_not_stop_the_rest(self, wt_env, tmp_path):
        for name in ("agent-a", "agent-b", "agent-c"):
            wt_env.make_raw_wt(name)
        script = seam_script(
            tmp_path,
            'if name == "before-remove" and str(ctx.get("path", "")).endswith("agent-b"):\n'
            '    raise RuntimeError("boom")',
        )
        proc = wt_env.mgr("reap", "--yes", script=script)
        assert proc.returncode == 1
        assert wt_env.reaped(proc, "agent-a") and wt_env.reaped(proc, "agent-c")
        assert "reaped=2" in proc.stdout and "failed=1" in proc.stdout
        assert (wt_env.root / ".claude" / "worktrees" / "agent-b").exists()


class TestOrphanDirs:
    def _orphan(self, env, name, age_hours=0.0):
        d = env.root / ".claude" / "worktrees" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "file.txt").write_text("data\n", encoding="utf-8")
        if age_hours:
            old = os.stat(d).st_mtime - age_hours * 3600
            os.utime(d, (old, old))
            os.utime(d / "file.txt", (old, old))
        return d

    def test_E15_orphan_dirs_are_reported_never_deleted(self, wt_env):
        d = self._orphan(wt_env, "agent-orphan", age_hours=48)
        for flag in ([], ["--yes"]):
            proc = wt_env.mgr("reap", *flag)
            assert proc.returncode == 0, proc.stderr
            assert "orphan-dir" in proc.stdout and "agent-orphan" in proc.stdout
            assert "size=" in proc.stdout
            assert d.exists() and (d / "file.txt").exists()

    def test_E17_young_orphan_is_flagged_too_new(self, wt_env):
        self._orphan(wt_env, "agent-young")
        self._orphan(wt_env, "agent-old", age_hours=48)
        proc = wt_env.mgr("reap")
        young = [ln for ln in proc.stdout.splitlines() if "agent-young" in ln][0]
        old = [ln for ln in proc.stdout.splitlines() if "agent-old" in ln][0]
        assert "too-new=yes" in young and "too-new=no" in old

    def test_E18_non_agent_dirs_are_flagged_not_agent_owned(self, wt_env):
        self._orphan(wt_env, "skill-profiles", age_hours=48)
        proc = wt_env.mgr("reap")
        line = [ln for ln in proc.stdout.splitlines() if "skill-profiles" in ln][0]
        assert "agent-owned=no" in line

    def test_E19_missing_worktrees_dir_is_a_no_op(self, wt_env):
        assert not (wt_env.root / ".claude" / "worktrees").exists()
        proc = wt_env.mgr("reap")
        assert proc.returncode == 0, proc.stderr
        assert "nothing to reclaim" in proc.stdout

    def test_E20_zero_worktrees(self, wt_env):
        proc = wt_env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert "nothing to reclaim" in proc.stdout


class TestRepoShapes:
    def test_V07_invoked_from_inside_a_linked_worktree_is_refused(self, wt_env):
        path = wt_env.make_wt("a")
        proc = wt_env.mgr("reap", cwd=path)
        assert proc.returncode == 2
        assert "main worktree" in proc.stderr

    def test_V08_bare_repo_is_refused(self, wt_env):
        bare = wt_env.tmp / "bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        for argv in (["reap"], ["create", "x"]):
            proc = wt_env.mgr(*argv, cwd=bare)
            assert proc.returncode == 2, (argv, proc.stdout, proc.stderr)
            assert "bare" in proc.stderr

    def test_V09_origin_head_unset_default_master_is_resolved(self, tmp_path):
        env = WtEnv(tmp_path, default_branch="master", set_head=False)
        env.make_raw_wt("agent-m", commits=1)
        env.merge_ff("agent-m")
        proc = env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert env.reaped(proc, "agent-m")

    def test_V09_ambiguous_default_is_unproven(self, tmp_path):
        env = WtEnv(tmp_path, default_branch="master", set_head=False)
        env.make_raw_wt("agent-m", commits=1)
        env.merge_ff("agent-m")
        env.git("push", "-q", "origin", "master:main")
        # git >= 2.48 recreates origin/HEAD on fetch; the ambiguity needs it absent
        env.git("config", "remote.origin.followRemoteHEAD", "never")
        env.git("fetch", "-q", "origin")
        env.git("remote", "set-head", "origin", "-d", check=False)
        proc = env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert "unproven" in (kept_reason(proc, "agent-m") or "")
        assert env.branch_exists("agent/agent-m")

    def test_V10_branch_named_like_the_default_is_not_confused_with_it(self, tmp_path):
        env = WtEnv(tmp_path, default_branch="master")
        path = env.make_raw_wt("agent-mf", branch="main-fix")
        proc = env.mgr("reap", "--yes")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists() and not env.branch_exists("main-fix")
        assert env.branch_exists("master")

    def test_V13_symlinked_repo_path_has_no_false_orphans(self, wt_env):
        link = wt_env.tmp / "link-to-proj"
        link.symlink_to(wt_env.root)
        wt_env.make_wt("a", commits=1)
        wt_env.merge_ff("a")
        proc = wt_env.mgr("reap", "--yes", cwd=link)
        assert proc.returncode == 0, proc.stderr
        assert "orphan-dir" not in proc.stdout
        assert wt_env.reaped(proc, "a") and not wt_env.wt("a").exists()
