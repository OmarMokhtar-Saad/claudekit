"""Behavioral contract of .claude/operations/scripts/worktree-manager.py.

The script owns the worktree-per-agent lifecycle: create .worktrees/<slug> on
branch agent/<slug>, track it in the git-ignored registry
.claude/state/worktrees.json, and guard removal. Contract under test:

- create validates slugs/refs/--copy sources (exit 2), copies
  .claude/settings.local.json by default but NEVER .env, writes .worktree-env,
  caps concurrency at 5, and refuses duplicates.
- remove refuses dirty trees, commits not contained in the base, and the
  primary worktree (exit 2); --force overrides the first two only.
- prune reconciles the registry with `git worktree list`.
- the registry path is git-ignored, stores repo-relative paths, and writes
  are atomic (no partial file on failure) under a lock.
- an ops.json executed via execute-json-ops.py with cwd = the worktree root
  writes inside the worktree and cannot escape it (the isolation proof).

All invocations run the real script as a subprocess against a temp git repo
via CLAUDEKIT_PROJECT_ROOT, asserting exit codes and on-disk artifacts.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "worktree-manager.py"
OPS_SCRIPT = REPO / ".claude" / "operations" / "scripts" / "execute-json-ops.py"


def run(args, project, cwd=None):
    env = dict(os.environ)
    env["CLAUDEKIT_PROJECT_ROOT"] = str(project)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, env=env, timeout=60,
        cwd=str(cwd or project),
    )


def git(project, *args):
    return subprocess.run(
        ["git", "-C", str(project)] + list(args),
        capture_output=True, text=True, timeout=60, check=True,
    )


@pytest.fixture()
def project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude" / "state").mkdir(parents=True)
    (proj / "src").mkdir()
    (proj / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (proj / ".gitignore").write_text(
        ".worktrees/\n.claude/state/\n.claude/locks/\n"
        ".claude/settings.local.json\n.env\n",
        encoding="utf-8",
    )
    local = proj / ".claude" / "settings.local.json"
    local.write_text('{"env": {"ECC_HOOK_PROFILE": "minimal"}}\n', encoding="utf-8")
    local.chmod(0o600)
    (proj / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")
    git(proj, "init", "-q", "-b", "main")
    git(proj, "config", "user.email", "test@test")
    git(proj, "config", "user.name", "test")
    git(proj, "add", "-A")
    git(proj, "commit", "-q", "-m", "init")
    return proj


class TestCreate:
    def test_create_makes_worktree_branch_registry_and_env(self, project):
        proc = run(["create", "feature-x", "--json"], project)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        wt = project / ".worktrees" / "feature-x"
        assert wt.is_dir()
        assert out["root"] == str(wt)
        assert out["branch"] == "agent/feature-x"
        head = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        assert head == "agent/feature-x"
        registry = json.loads(
            (project / ".claude" / "state" / "worktrees.json").read_text())
        assert registry["worktrees"][0]["path"] == ".worktrees/feature-x"
        env = (wt / ".worktree-env").read_text()
        assert "WORKTREE_SLUG=feature-x" in env
        assert "WORKTREE_PORT_OFFSET=10" in env

    def test_create_copies_local_settings_with_mode_but_not_env(self, project):
        assert run(["create", "feature-x"], project).returncode == 0
        wt = project / ".worktrees" / "feature-x"
        copied = wt / ".claude" / "settings.local.json"
        assert copied.exists()
        assert stat.S_IMODE(copied.stat().st_mode) == 0o600
        assert not (wt / ".env").exists()

    def test_create_copies_env_only_when_explicit(self, project):
        proc = run(["create", "feature-x", "--copy", ".env"], project)
        assert proc.returncode == 0, proc.stderr
        assert (project / ".worktrees" / "feature-x" / ".env").exists()

    def test_create_rejects_traversal_slug(self, project):
        proc = run(["create", "../escape"], project)
        assert proc.returncode == 2
        assert not (project.parent / "escape").exists()

    def test_create_rejects_bad_slugs(self, project):
        for slug in ["UPPER", "has space", "-leading", "a" * 60]:
            assert run(["create", slug], project).returncode == 2

    def test_create_rejects_duplicate_slug(self, project):
        assert run(["create", "feature-x"], project).returncode == 0
        proc = run(["create", "feature-x"], project)
        assert proc.returncode == 2
        assert "already" in proc.stderr

    def test_create_rejects_flag_like_and_unresolvable_base(self, project):
        assert run(["create", "feature-x", "--base", "--exec=evil"],
                   project).returncode == 2
        assert run(["create", "feature-y", "--base", "no-such-ref"],
                   project).returncode == 2

    def test_create_rejects_copy_escaping_repo(self, project):
        outside = project.parent / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        assert run(["create", "feature-x", "--copy", str(outside)],
                   project).returncode == 2
        link = project / "sneaky"
        link.symlink_to(outside)
        git(project, "add", "-A")
        git(project, "commit", "-q", "-m", "link")
        assert run(["create", "feature-x", "--copy", "sneaky"],
                   project).returncode == 2

    def test_create_enforces_max_five(self, project):
        for i in range(5):
            assert run(["create", f"unit-{i}"], project).returncode == 0
        proc = run(["create", "unit-5"], project)
        assert proc.returncode == 2
        assert "5" in proc.stderr


class TestListRemovePrune:
    def test_list_json_reports_live_status(self, project):
        run(["create", "feature-x"], project)
        rows = json.loads(run(["list", "--json"], project).stdout)
        assert rows[0]["slug"] == "feature-x"
        assert rows[0]["live"] is True

    def test_remove_clean_worktree(self, project):
        run(["create", "feature-x"], project)
        proc = run(["remove", "feature-x"], project)
        assert proc.returncode == 0, proc.stderr
        assert not (project / ".worktrees" / "feature-x").exists()
        registry = json.loads(
            (project / ".claude" / "state" / "worktrees.json").read_text())
        assert registry["worktrees"] == []
        # branch is kept for the merge phase
        branches = git(project, "branch", "--list", "agent/feature-x").stdout
        assert "agent/feature-x" in branches

    def test_remove_refuses_dirty_without_force(self, project):
        run(["create", "feature-x"], project)
        wt = project / ".worktrees" / "feature-x"
        (wt / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        assert run(["remove", "feature-x"], project).returncode == 2
        assert run(["remove", "feature-x", "--force"], project).returncode == 0

    def test_remove_refuses_unmerged_commits_without_force(self, project):
        run(["create", "feature-x"], project)
        wt = project / ".worktrees" / "feature-x"
        (wt / "src" / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "unmerged work")
        proc = run(["remove", "feature-x"], project)
        assert proc.returncode == 2
        assert "not contained" in proc.stderr
        assert run(["remove", "feature-x", "--force"], project).returncode == 0

    def test_prune_drops_stale_registry_entries(self, project):
        run(["create", "feature-x"], project)
        run(["create", "feature-y"], project)
        # simulate a crashed agent: directory deleted behind our back
        import shutil
        shutil.rmtree(project / ".worktrees" / "feature-x")
        proc = run(["prune"], project)
        assert proc.returncode == 0
        registry = json.loads(
            (project / ".claude" / "state" / "worktrees.json").read_text())
        slugs = [e["slug"] for e in registry["worktrees"]]
        assert slugs == ["feature-y"]


class TestRegistryHygiene:
    def test_registry_and_worktrees_are_git_ignored(self, project):
        run(["create", "feature-x"], project)
        for path in [".claude/state/worktrees.json", ".worktrees/feature-x"]:
            proc = subprocess.run(
                ["git", "-C", str(project), "check-ignore", "-q", path],
                capture_output=True, timeout=30,
            )
            assert proc.returncode == 0, f"{path} is not git-ignored"

    def test_registry_stores_relative_paths_only(self, project):
        run(["create", "feature-x"], project)
        raw = (project / ".claude" / "state" / "worktrees.json").read_text()
        assert str(project) not in raw

    def test_lock_is_released_after_create(self, project):
        run(["create", "feature-x"], project)
        assert not (project / ".claude" / "locks" / "worktree-manager.lock").exists()

    def test_repo_gitignore_covers_state_and_worktrees(self):
        gitignore = (REPO / ".gitignore").read_text()
        assert ".worktrees/" in gitignore
        assert ".claude/state/" in gitignore


class TestIsolationProof:
    """The Iron Law path inside a worktree: execute-json-ops.py run with
    cwd = worktree root writes inside the worktree and cannot escape it."""

    def _ops(self, wt, target):
        config = wt / "ops.json"
        config.write_text(json.dumps({
            "plan": "isolation-proof",
            "files": [{
                "path": target,
                "edits": [{"find": "VALUE = 1", "replace": "VALUE = 99"}],
            }],
        }), encoding="utf-8")
        return config

    def test_ops_execute_inside_worktree(self, project):
        run(["create", "feature-x"], project)
        wt = project / ".worktrees" / "feature-x"
        config = self._ops(wt, "src/app.py")
        proc = subprocess.run(
            [sys.executable, str(OPS_SCRIPT), str(config)],
            capture_output=True, text=True, cwd=str(wt), timeout=60,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "VALUE = 99" in (wt / "src" / "app.py").read_text()
        # main tree untouched
        assert "VALUE = 1" in (project / "src" / "app.py").read_text()

    def test_ops_cannot_escape_worktree(self, project):
        run(["create", "feature-x"], project)
        wt = project / ".worktrees" / "feature-x"
        config = self._ops(wt, "../../src/app.py")
        proc = subprocess.run(
            [sys.executable, str(OPS_SCRIPT), str(config)],
            capture_output=True, text=True, cwd=str(wt), timeout=60,
        )
        assert proc.returncode != 0
        assert "VALUE = 1" in (project / "src" / "app.py").read_text()



# ---------------------------------------------------------------------------------------------
# Worktree lifecycle: `remove --delete-branch`, create-time lock, install, CLI surface.
# Case IDs refer to ~/plans/worktree-cleanup-2026-10-06/claudekit/TEST-CASES.md.
# ---------------------------------------------------------------------------------------------
class TestRemoveDeleteBranch:
    def test_H01_fast_forward_merged_is_removed_with_its_branch(self, wt_env):
        wt_env.make_wt("a", commits=2)
        wt_env.merge_ff("a")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists()
        assert not wt_env.branch_exists("agent/a")
        assert json.loads(wt_env.registry_bytes())["worktrees"] == []
        assert wt_env.worktree_paths() == [os.path.realpath(wt_env.root)]
        assert "deleted" in proc.stdout

    def test_H05_zero_commits_clean_is_deleted(self, wt_env):
        wt_env.make_wt("a")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists()
        assert not wt_env.branch_exists("agent/a")

    def test_H09_remove_without_flag_keeps_the_branch(self, wt_env):
        wt_env.make_wt("a", commits=1)
        wt_env.git("merge", "-q", "--no-ff", "-m", "merge", "agent/a")
        proc = wt_env.mgr("remove", "a")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists()
        assert wt_env.branch_exists("agent/a")
        assert "kept" in proc.stdout

    def test_N01_modified_tracked_file_is_refused(self, wt_env):
        path = wt_env.make_wt("a")
        (path / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 2
        assert path.exists() and wt_env.branch_exists("agent/a")
        assert json.loads(wt_env.registry_bytes())["worktrees"][0]["slug"] == "a"

    def test_N02_untracked_file_counts_as_dirty(self, wt_env):
        path = wt_env.make_wt("a", dirty=True)
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 2
        assert path.exists() and wt_env.branch_exists("agent/a")

    def test_N03_ignored_files_do_not_block_removal(self, wt_env):
        path = wt_env.make_wt("a")
        # .worktree-env and the copied settings.local.json are ignored by design
        (path / ".claude").mkdir(exist_ok=True)
        (path / ".claude" / "settings.local.json").write_text("{}\n", encoding="utf-8")
        assert (path / ".worktree-env").exists()
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 0, proc.stderr
        assert not path.exists() and not wt_env.branch_exists("agent/a")

    def test_N11_a_registry_entry_pointing_at_the_primary_is_refused(self, wt_env):
        wt_env.make_wt("a")
        reg = json.loads(wt_env.registry_bytes())
        reg["worktrees"][0]["path"] = "."
        (wt_env.root / ".claude" / "state" / "worktrees.json").write_text(
            json.dumps(reg), encoding="utf-8")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 2
        assert (wt_env.root / "app.py").exists() and (wt_env.root / ".git").exists()

    def test_N14_invoked_from_inside_the_target_is_refused(self, wt_env):
        path = wt_env.make_wt("a")
        proc = wt_env.mgr("remove", "a", cwd=path)
        assert proc.returncode == 2
        assert "primary" in proc.stderr
        assert path.exists()

    def test_N15_traversal_slug_is_refused(self, wt_env):
        proc = wt_env.mgr("remove", "../x", "--delete-branch")
        assert proc.returncode == 2
        assert "Traceback" not in proc.stderr

    def test_E11_registry_path_escaping_the_repo_is_refused(self, wt_env):
        outside = wt_env.tmp / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("precious\n", encoding="utf-8")
        wt_env.make_wt("a")
        reg = json.loads(wt_env.registry_bytes())
        reg["worktrees"][0]["path"] = "../outside"
        (wt_env.root / ".claude" / "state" / "worktrees.json").write_text(
            json.dumps(reg), encoding="utf-8")
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 2
        assert (outside / "keep.txt").read_text() == "precious\n"

    def test_I02_second_remove_says_not_in_registry_without_a_traceback(self, wt_env):
        wt_env.make_wt("a")
        assert wt_env.mgr("remove", "a", "--delete-branch").returncode == 0
        proc = wt_env.mgr("remove", "a", "--delete-branch")
        assert proc.returncode == 2
        assert "not in registry" in proc.stderr
        assert "Traceback" not in proc.stderr


class TestCreateLocks:
    def test_K04_create_locks_the_worktree_and_remove_unlocks_it(self, wt_env):
        assert wt_env.mgr("create", "a").returncode == 0
        porcelain = wt_env.git("worktree", "list", "--porcelain").stdout
        locked = [ln for ln in porcelain.splitlines() if ln.startswith("locked")]
        assert locked, porcelain
        assert "claudekit agent" in locked[0] and "slug=a" in locked[0]
        proc = wt_env.mgr("remove", "a")
        assert proc.returncode == 0, proc.stderr
        assert not wt_env.wt("a").exists()

    def test_list_reports_locked_and_merged(self, wt_env):
        wt_env.make_wt("a", commits=1, locked=True)
        wt_env.make_wt("b", commits=1)
        wt_env.merge_ff("b")
        rows = {r["slug"]: r for r in json.loads(wt_env.mgr("list", "--json").stdout)}
        assert rows["a"]["locked"] is True and rows["b"]["locked"] is False
        assert rows["a"]["merged"] == "unmerged"
        assert rows["b"]["merged"] == "merged"

    def test_prune_expires_prunable_entries_immediately(self, wt_env):
        import shutil
        wt_env.make_wt("a")
        shutil.rmtree(wt_env.wt("a"))
        assert wt_env.mgr("prune").returncode == 0
        assert os.path.realpath(wt_env.wt("a")) not in wt_env.worktree_paths()


class TestCompatibility:
    def test_X01_script_is_python39_syntax(self):
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 9))
        assert not [n for n in ast.walk(tree) if type(n).__name__ == "Match"]
        src = SCRIPT.read_text(encoding="utf-8")
        assert "from __future__" not in src or "annotations" not in src

    def test_X10_help_for_the_new_flags_exits_zero(self, wt_env):
        for argv in (["remove", "--help"], ["reap", "--help"], ["cleanup", "--help"]):
            proc = wt_env.mgr(*argv)
            assert proc.returncode == 0, (argv, proc.stderr)
        assert "--delete-branch" in wt_env.mgr("remove", "--help").stdout
        assert "--archive" in wt_env.mgr("remove", "--help").stdout
        out = wt_env.mgr("reap", "--help").stdout
        for flag in ("--yes", "--max-deletions", "--no-fetch", "--min-age",
                     "--break-stale-locks"):
            assert flag in out

    def test_E21_git_too_old_for_worktree_lock_is_a_clear_error(self, wt_env):
        shim = wt_env.fake_git(
            "old", 'if [ "$1" = "--version" ]; then echo "git version 2.10.0"; exit 0; fi')
        proc = wt_env.mgr("list", env=wt_env.shim_env(shim))
        assert proc.returncode == 1
        assert "2.17" in proc.stderr

    def test_X02_installed_copy_runs_reap_dry(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(target)], check=True)
        install = REPO / "install.sh"
        done = subprocess.run(["bash", str(install), str(target), "--minimal", "--force"],
                              capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr
        installed = target / ".claude" / "operations" / "scripts" / "worktree-manager.py"
        proc = subprocess.run([sys.executable, str(installed), "reap"], cwd=str(target),
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert "nothing to reclaim" in proc.stdout

    def test_X03_an_older_installed_copy_is_replaced_by_reinstall(self, tmp_path):
        import hashlib
        target = tmp_path / "target"
        target.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(target)], check=True)
        install = REPO / "install.sh"
        assert subprocess.run(["bash", str(install), str(target), "--minimal", "--force"],
                              capture_output=True, text=True, timeout=180).returncode == 0
        installed = target / ".claude" / "operations" / "scripts" / "worktree-manager.py"
        installed.write_text("#!/usr/bin/env python3\n# old copy without reap\n",
                             encoding="utf-8")
        assert subprocess.run(["bash", str(install), str(target), "--minimal", "--force"],
                              capture_output=True, text=True, timeout=180).returncode == 0
        assert (hashlib.sha256(installed.read_bytes()).hexdigest()
                == hashlib.sha256(SCRIPT.read_bytes()).hexdigest())

    def test_X09_ruff_and_mypy_are_clean_on_the_manager(self):
        import shutil
        ran = False
        for tool, argv in (
            ("ruff", ["check", "--no-cache", str(SCRIPT)]),
            ("mypy", [str(SCRIPT)]),
        ):
            exe = shutil.which(tool, path=os.path.dirname(sys.executable))
            if not exe:
                continue
            ran = True
            proc = subprocess.run([exe] + argv, capture_output=True, text=True,
                                  cwd=str(REPO), timeout=300)
            assert proc.returncode == 0, f"{tool}: {proc.stdout}{proc.stderr}"
        if not ran:
            pytest.skip("neither ruff nor mypy is installed in this interpreter's env")
