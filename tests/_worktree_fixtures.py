"""Shared fixtures for the worktree-manager lifecycle tests (reap / archive / concurrency).

Every test builds REAL temp git repos under pytest's tmp_path and never touches the repo under
test. The layout is:

    <tmp>/proj        primary checkout (branch main, one commit, pushed to origin)
    <tmp>/origin.git  bare origin
    <tmp>/clone2      second clone used to land work on origin (merge_* helpers)

`WtEnv.make_wt` creates a worktree through the manager (`create`) and then UNLOCKS it: that is the
state of a finished agent. `create` itself locks every worktree it makes (a live agent), and the
lock tests ask for that explicitly with ``locked=True``.

The module is Python 3.9-compatible. Test files import the `wt_env` fixture from here.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "worktree-manager.py"


def clean_env(extra: Optional[dict] = None) -> dict:
    env = dict(os.environ)
    for name in list(env):
        if name.startswith("GIT_") or name == "CLAUDEKIT_PROJECT_ROOT":
            env.pop(name)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        env.update(extra)
    return env


def git(cwd, *args, check=True, env=None):
    return subprocess.run(
        ["git", "-C", str(cwd)] + list(args),
        capture_output=True, text=True, timeout=120, check=check,
        env=clean_env(env),
    )


def mutate_script(dst: Path, find: str, replace: str, tag: str = "mutant") -> Path:
    """Copy the manager to *dst*/_mutant_<tag>.py with one unique anchor replaced."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count(find) == 1, f"mutation anchor {tag!r} is not unique ({src.count(find)})"
    out = Path(dst) / f"_mutant_{tag}.py"
    out.write_text(src.replace(find, replace), encoding="utf-8")
    return out


# The seam the manager exposes to tests: a no-op `_checkpoint(name, **ctx)`. Tests copy the script
# and replace this one line to run code at a named point of the lifecycle.
SEAM_ANCHOR = "    del name, ctx\n"


def seam_script(dst: Path, body: str, tag: str = "seam") -> Path:
    """A manager copy whose `_checkpoint` runs *body* (may use `name` and `ctx`)."""
    indented = "".join("    " + line + "\n" for line in body.strip("\n").splitlines())
    return mutate_script(dst, SEAM_ANCHOR, SEAM_ANCHOR + indented, tag)


class WtEnv:
    def __init__(self, tmp: Path, default_branch: str = "main", set_head: bool = True) -> None:
        self.tmp = tmp
        self.default = default_branch
        self.root = tmp / "proj"
        self.origin = tmp / "origin.git"
        self.clone2 = tmp / "clone2"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", default_branch)
        self._identity(self.root)
        (self.root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(
            ".worktrees/\n.claude/worktrees/\n.claude/state/\n.claude/locks/\n"
            ".claude/settings.local.json\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        subprocess.run(["git", "init", "-q", "--bare", "-b", default_branch, str(self.origin)],
                       check=True, capture_output=True, env=clean_env())
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-q", "origin", default_branch)
        git(self.root, "fetch", "-q", "origin")
        if set_head:
            git(self.root, "remote", "set-head", "origin", default_branch)

    # -- plumbing ---------------------------------------------------------------------------
    @staticmethod
    def _identity(path) -> None:
        git(path, "config", "user.email", "t@example.com")
        git(path, "config", "user.name", "t")

    def git(self, *args, cwd=None, check=True):
        return git(cwd or self.root, *args, check=check)

    def mgr(self, *args, cwd=None, script=None, env=None, timeout=120):
        return subprocess.run(
            [sys.executable, str(script or SCRIPT)] + [str(a) for a in args],
            capture_output=True, text=True, cwd=str(cwd or self.root),
            env=clean_env(env), timeout=timeout,
        )

    def popen(self, *args, cwd=None, script=None, env=None):
        return subprocess.Popen(
            [sys.executable, str(script or SCRIPT)] + [str(a) for a in args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(cwd or self.root), env=clean_env(env),
        )

    # -- worktrees --------------------------------------------------------------------------
    def wt(self, slug: str) -> Path:
        return self.root / ".worktrees" / slug

    def commit_in(self, path: Path, tag: str, n: int = 1) -> None:
        for i in range(n):
            (Path(path) / f"f_{tag}_{i}.txt").write_text(f"{tag} {i}\n", encoding="utf-8")
            git(path, "add", "-A")
            git(path, "commit", "-q", "-m", f"{tag} change {i}")

    def make_wt(self, slug: str, commits: int = 0, dirty: bool = False,
                locked: bool = False, base: Optional[str] = None) -> Path:
        args = ["create", slug] + (["--base", base] if base else [])
        proc = self.mgr(*args)
        assert proc.returncode == 0, proc.stderr
        path = self.wt(slug)
        if not locked:
            git(self.root, "worktree", "unlock", str(path), check=False)
        self.commit_in(path, slug, commits)
        if dirty:
            (path / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
        return path

    def make_raw_wt(self, name: str, commits: int = 0, parent: str = ".claude/worktrees",
                    branch: Optional[str] = None) -> Path:
        """A worktree made with raw `git worktree add` (never registered)."""
        path = self.root / parent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        git(self.root, "worktree", "add", "-q", "-b", branch or f"agent/{name}", str(path),
            self.default)
        self.commit_in(path, name, commits)
        return path

    def branch_exists(self, name: str) -> bool:
        return git(self.root, "rev-parse", "--verify", "--quiet", "refs/heads/" + name,
                   check=False).returncode == 0

    def worktree_paths(self) -> List[str]:
        out = git(self.root, "worktree", "list", "--porcelain").stdout
        return [os.path.realpath(line[9:]) for line in out.splitlines()
                if line.startswith("worktree ")]

    def registry_bytes(self) -> bytes:
        path = self.root / ".claude" / "state" / "worktrees.json"
        return path.read_bytes() if path.exists() else b""

    def snapshot(self) -> tuple:
        branches = git(self.root, "for-each-ref", "refs/heads").stdout
        return (tuple(sorted(self.worktree_paths())), branches, self.registry_bytes())

    # -- landing work on origin ---------------------------------------------------------------
    def _clone2(self) -> Path:
        if not self.clone2.exists():
            subprocess.run(["git", "clone", "-q", str(self.origin), str(self.clone2)],
                           check=True, capture_output=True, env=clean_env())
            self._identity(self.clone2)
        git(self.clone2, "fetch", "-q", "origin")
        git(self.clone2, "checkout", "-q", self.default)
        git(self.clone2, "reset", "-q", "--hard", "origin/" + self.default)
        return self.clone2

    def _land(self, slug: str, how: str, fetch: bool = True) -> None:
        c = self._clone2()
        ref = f"refs/remotes/wt/{slug}"
        git(c, "fetch", "-q", str(self.root), f"refs/heads/agent/{slug}:{ref}")
        if how == "ff":
            git(c, "merge", "-q", "-m", f"merge {slug}", ref)
        elif how == "merge":
            git(c, "merge", "-q", "--no-ff", "-m", f"merge {slug}", ref)
        elif how == "squash":
            git(c, "merge", "-q", "--squash", ref)
            git(c, "commit", "-q", "-m", f"squash {slug}")
        elif how == "rebase":
            shas = git(c, "rev-list", "--reverse", f"HEAD..{ref}").stdout.split()
            if shas:
                git(c, "cherry-pick", *shas)
        else:
            raise AssertionError(how)
        git(c, "push", "-q", "origin", self.default)
        if fetch:
            git(self.root, "fetch", "-q", "origin")

    def merge_ff(self, slug, fetch=True):
        self._land(slug, "ff", fetch)

    def merge_commit(self, slug, fetch=True):
        self._land(slug, "merge", fetch)

    def merge_squash(self, slug, fetch=True):
        self._land(slug, "squash", fetch)

    def merge_rebase(self, slug, fetch=True):
        self._land(slug, "rebase", fetch)

    def advance_origin(self, name: str = "other", text: str = "x\n") -> None:
        """Land an unrelated commit on origin's default branch."""
        c = self._clone2()
        (c / f"{name}.txt").write_text(text, encoding="utf-8")
        git(c, "add", "-A")
        git(c, "commit", "-q", "-m", f"advance {name}")
        git(c, "push", "-q", "origin", self.default)
        git(self.root, "fetch", "-q", "origin")

    def fake_git(self, name: str, body: str) -> Path:
        """A PATH shim dir whose `git` runs *body* (sh) before falling through to the real git."""
        real = shutil.which("git")
        d = self.tmp / f"shim-{name}"
        d.mkdir(exist_ok=True)
        shim = d / "git"
        shim.write_text(f"#!/bin/sh\n{body}\nexec {real} \"$@\"\n", encoding="utf-8")
        shim.chmod(0o755)
        return d

    @staticmethod
    def shim_env(shim_dir: Path, **extra) -> dict:
        env = {"PATH": f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
        env.update(extra)
        return env

    @staticmethod
    def kept(proc, slug) -> bool:
        return f"kept {slug}" in proc.stdout

    @staticmethod
    def reaped(proc, slug) -> bool:
        return f"reaped {slug}" in proc.stdout

    @staticmethod
    def would_reap(proc, slug) -> bool:
        return f"would reap {slug}" in proc.stdout

    @staticmethod
    def sleep_until(predicate, timeout=20.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if predicate():
                return True
            time.sleep(0.05)
        return False


@pytest.fixture()
def wt_env(tmp_path):
    return WtEnv(tmp_path)
