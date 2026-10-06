#!/usr/bin/env python3
"""Worktree lifecycle manager for parallel agent execution.

One branch = one worktree = one agent. This script owns the lifecycle so
agents never improvise git worktree commands:

    create <slug> [--base <ref>] [--copy <path> ...] [--json]
    list   [--json]
    remove <slug> [--force] [--delete-branch] [--archive]
    reap   [--yes] [--max-deletions N] [--no-fetch] [--min-age H]
           [--break-stale-locks]            (alias: cleanup)
    prune

Design contract (see .claude/plans/plan-worktree-multi-agent.md):
  * Worktrees live at .worktrees/<slug> with branch agent/<slug>; every
    `create` locks the worktree (`claudekit agent slug=<slug> ts=<epoch>`)
    because a fresh worktree is a live agent.
  * Registry at .claude/state/worktrees.json stores repo-relative paths only
    (both locations are git-ignored; nothing here may ship).
  * Slugs are validated (^[a-z0-9][a-z0-9-]{0,40}$); git is always invoked in
    list form with user-supplied refs verified via rev-parse first.
  * .claude/settings.local.json is copied into new worktrees when present.
    Secrets (.env etc.) are NEVER copied unless explicitly listed via --copy.
  * At most MAX_WORKTREES concurrent worktrees (returns collapse past 4-5
    parallel agents; keep merges tractable).
  * Mutations are serialized by an exclusive lock file; a lock older than
    LOCK_STALE_SECS, or whose owner pid is dead, is broken. Waiters poll for
    up to LOCK_WAIT_SECS. Registry writes are atomic (tempfile + os.replace).

Finishing a worktree (`reap`, `remove --delete-branch`):
  * A worktree and its branch are deleted TOGETHER, and only after the work
    is PROVEN merged into the freshly fetched refs/remotes/origin/<default>:
    ancestor, else `git cherry` with no unapplied patch, else a clean
    `git merge-tree --write-tree` whose result tree equals the default
    branch tree. CANNOT ANSWER IS NOT YES: anything unprovable is kept.
  * `reap` is a dry run unless --yes. The fetch and classification run with
    no lock; the lock is taken only to mutate, and every item is re-verified
    under it (still listed, unlocked, clean, same tip, still merged).
  * The pid in a worktree lock reason is the short-lived `create` process, so
    it proves nothing. Own locks are only ever judged by AGE (`ts=`).
  * Orphan directories (not known to git) are REPORTED, never deleted.
  * `remove --delete-branch --force --archive` bundles unmerged work under
    .claude/state/worktree-archive/ and verifies it before deleting anything.

Exit codes: 0 ok, 1 operational error, 2 validation refusal.
"""

import argparse
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
OWN_LOCK_RE = re.compile(r"^claudekit agent slug=\S+ ts=(\d+)\s*$")
MAX_WORKTREES = 5
LOCK_STALE_SECS = 300
LOCK_WAIT_SECS = 30
WORKTREES_DIR = ".worktrees"
BRANCH_PREFIX = "agent/"
DEFAULT_COPY = [".claude/settings.local.json"]
REGISTRY_VERSION = 1
MIN_GIT = (2, 17)
DEFAULT_MAX_DELETIONS = 10
MQ_PREFIX = "mq-"
MQ_MIN_AGE_HOURS = 0.5  # merge-queue worktrees: own lock stale after 30 minutes
DEFAULT_MIN_AGE_HOURS = 24.0
DEFAULT_CANDIDATES = ("main", "master", "develop", "trunk")
PROTECTED_BRANCHES = frozenset(DEFAULT_CANDIDATES)
SCOPE_DIRS = (".worktrees", ".claude/worktrees")
ARCHIVE_DIR = ".claude/state/worktree-archive"
ZERO_SHA = "0" * 40


def _checkpoint(name: str, **ctx: Any) -> None:
    """Test seam: a named point of the lifecycle. A no-op in production."""
    del name, ctx


def fail(msg: str, code: int) -> "int":
    print(f"worktree-manager: {msg}", file=sys.stderr)
    return code


def run_git(root: Any, args: List[str], check: bool = True,
            env: Optional[Dict[str, str]] = None,
            timeout: int = 60) -> "subprocess.CompletedProcess[str]":
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(root)] + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=full_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git {' '.join(args)}: timed out after {timeout}s") from exc
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc


def check_git_version() -> Optional[str]:
    """None when git is new enough (or its version cannot be parsed)."""
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "git is not available"
    match = re.search(r"(\d+)\.(\d+)", out)
    if match and (int(match.group(1)), int(match.group(2))) < MIN_GIT:
        return (f"git {match.group(1)}.{match.group(2)} is too old: "
                f"worktree-manager needs git >= {MIN_GIT[0]}.{MIN_GIT[1]}")
    return None


def start_dir() -> Path:
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    return Path(env) if env else Path.cwd()


def primary_root() -> Path:
    """Primary repo root (not a linked worktree): env override, else derived
    from the git common dir so this works when invoked inside a worktree."""
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError("not inside a git repository")
    common = Path(proc.stdout.strip()).resolve()
    return common.parent


def guard_not_bare() -> Optional[int]:
    proc = run_git(start_dir(), ["rev-parse", "--is-bare-repository"], check=False)
    if proc.returncode == 0 and proc.stdout.strip() == "true":
        return fail("this is a bare repository: worktree-manager needs a normal "
                    "checkout (run it from the repository's main worktree)", 2)
    return None


def guard_main_worktree() -> Optional[int]:
    """reap must run from the main worktree, never from a linked one."""
    start = start_dir()
    git_dir = run_git(start, ["rev-parse", "--absolute-git-dir"], check=False)
    common = run_git(start, ["rev-parse", "--git-common-dir"], check=False)
    if git_dir.returncode != 0 or common.returncode != 0:
        return fail("not inside a git repository", 2)
    common_path = Path(common.stdout.strip())
    if not common_path.is_absolute():
        common_path = start / common_path
    if os.path.realpath(git_dir.stdout.strip()) != os.path.realpath(str(common_path)):
        return fail("reap must run from the main worktree, not from a linked worktree "
                    "(cd to the primary checkout and re-run)", 2)
    return None


def registry_path(root: Path) -> Path:
    return root / ".claude" / "state" / "worktrees.json"


def lock_path(root: Path) -> Path:
    return root / ".claude" / "locks" / "worktree-manager.lock"


class RegistryLock:
    """Exclusive lock via O_CREAT|O_EXCL. Waiters poll up to LOCK_WAIT_SECS.
    A lock older than LOCK_STALE_SECS, or whose recorded pid is dead, is
    broken (the process was killed mid-run)."""

    def __init__(self, root: Path) -> None:
        self.path = lock_path(root)
        self.held = False

    def _break_if_stale(self) -> bool:
        try:
            before = self.path.stat()
        except OSError:
            return True  # vanished: retry the create
        stale = time.time() - before.st_mtime > LOCK_STALE_SECS
        if not stale:
            try:
                pid = int(self.path.read_text(encoding="utf-8").strip() or "0")
            except (OSError, ValueError):
                pid = 0
            if pid > 0:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    stale = True
                except OSError:
                    pass
        if not stale:
            return False
        try:
            now = self.path.stat()
            if (now.st_ino, now.st_mtime_ns) == (before.st_ino, before.st_mtime_ns):
                self.path.unlink()
        except OSError:
            pass
        return True

    def __enter__(self) -> "RegistryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + LOCK_WAIT_SECS
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
                if self._break_if_stale():
                    continue
                if time.time() >= deadline:
                    raise RuntimeError(
                        f"another worktree-manager run holds {self.path}"
                    ) from exc
                time.sleep(0.1)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.held = True
            return self

    def __exit__(self, *exc_info: object) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False


def load_registry(root: Path) -> Dict[str, Any]:
    path = registry_path(root)
    if not path.exists():
        return {"version": REGISTRY_VERSION, "worktrees": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"registry {path} is unreadable ({exc}); "
                           "fix or remove it, nothing was changed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("worktrees"), list):
        raise RuntimeError(f"registry {path} has an unexpected shape; nothing was changed")
    return data


def save_registry(root: Path, registry: Dict[str, Any]) -> None:
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".worktrees-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_copy_source(root: Path, rel: str) -> Optional[Path]:
    """A --copy source must be a repo-relative path whose real location stays
    inside the repo root. Returns the resolved source or None if absent."""
    if "\x00" in rel:
        raise ValueError("null byte in --copy path")
    if os.path.isabs(rel):
        raise ValueError(f"--copy must be repo-relative, got absolute: {rel}")
    candidate = root / rel
    if not candidate.exists():
        return None
    resolved = candidate.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"--copy escapes the repo root: {rel}")
    return resolved


def next_index(registry: Dict[str, Any]) -> int:
    used = {entry["index"] for entry in registry["worktrees"]}
    index = 1
    while index in used:
        index += 1
    return index


# ---------------------------------------------------------------------------
# git ground truth: worktrees, locks, merge proof
# ---------------------------------------------------------------------------
@dataclass
class WtRow:
    path: str
    head: str = ""
    branch: str = ""
    detached: bool = False
    bare: bool = False
    locked: bool = False
    lock_reason: str = ""
    prunable: bool = False


def list_worktrees(root: Path) -> List[WtRow]:
    """`git worktree list --porcelain`; the first row is the main worktree."""
    out = run_git(root, ["worktree", "list", "--porcelain"], check=False).stdout
    rows: List[WtRow] = []
    cur: Optional[WtRow] = None
    for line in out.splitlines():
        if not line.strip():
            cur = None
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = WtRow(path=val)
            rows.append(cur)
        elif cur is None:
            continue
        elif key == "HEAD":
            cur.head = val
        elif key == "branch":
            cur.branch = val[len("refs/heads/"):] if val.startswith("refs/heads/") else val
        elif key == "detached":
            cur.detached = True
        elif key == "bare":
            cur.bare = True
        elif key == "locked":
            cur.locked = True
            cur.lock_reason = val
        elif key == "prunable":
            cur.prunable = True
    return rows


def find_row(rows: List[WtRow], path: Any) -> Optional[WtRow]:
    real = os.path.realpath(str(path))
    for row in rows:
        if os.path.realpath(row.path) == real:
            return row
    return None


def live_worktree_paths(root: Path) -> set:
    """Every worktree git itself knows about -- the ground truth the cap counts.

    The registry only records worktrees created THROUGH this manager. A raw
    `git worktree add` never registers, so a registry-only count could not see
    it and the cap was silently bypassable. git is the source of truth; the
    registry stays the metadata store.

    Paths are realpath-normalized on BOTH sides before comparison (on macOS
    /tmp is a symlink); a mismatch would silently fail to exclude the primary
    row and quietly restore the 5->4 off-by-one.
    """
    return {os.path.realpath(row.path) for row in list_worktrees(root)}


def lock_kind(row: WtRow, min_age_secs: float, now: float) -> Tuple[str, str]:
    """``(kind, detail)``: none | live | stale | foreign.

    The pid of the creating process is deliberately NOT consulted: it is a
    short-lived `create`, dead the moment the agent starts, so "pid dead"
    would call every live agent stale. Only the age (`ts=`) counts.
    """
    if not row.locked:
        return "none", ""
    match = OWN_LOCK_RE.match(row.lock_reason)
    if not match:
        return "foreign", row.lock_reason
    age = now - int(match.group(1))
    return ("stale" if age > min_age_secs else "live"), row.lock_reason


def is_ancestor(root: Path, commit: str, ref: str) -> Optional[bool]:
    proc = run_git(root, ["merge-base", "--is-ancestor", commit, ref], check=False)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


@dataclass
class Baseline:
    """What "merged" is measured against."""
    mode: str = "none"          # origin | local | none
    sha: str = ""
    name: str = ""              # display name, e.g. origin/main
    default_name: str = ""      # e.g. main
    local_ref: str = ""         # local default branch (for not-on-origin)
    problem: str = ""           # why nothing can be proven


def _rev(root: Any, ref: str) -> str:
    proc = run_git(root, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def resolve_baseline(root: Path) -> Baseline:
    """Merged is measured ONLY against refs/remotes/origin/<default>, or the
    local default branch when the repo has no origin at all."""
    remotes = run_git(root, ["remote"], check=False).stdout.split()
    local_default = ""
    for cand in DEFAULT_CANDIDATES:
        if _rev(root, "refs/heads/" + cand):
            local_default = cand
            break
    if not local_default:
        head = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if head.returncode == 0 and head.stdout.strip() not in ("", "HEAD"):
            local_default = head.stdout.strip()
    base = Baseline(local_ref=("refs/heads/" + local_default) if local_default else "")
    if "origin" not in remotes:
        base.mode = "local"
        if not local_default:
            base.problem = "no origin remote and no local default branch"
            return base
        base.default_name = local_default
        base.name = local_default
        base.sha = _rev(root, "refs/heads/" + local_default)
        return base
    base.mode = "origin"
    sym = run_git(root, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], check=False)
    default = ""
    if sym.returncode == 0:
        prefix = "refs/remotes/origin/"
        target = sym.stdout.strip()
        if target.startswith(prefix) and _rev(root, target):
            default = target[len(prefix):]
    if not default:
        present = [c for c in DEFAULT_CANDIDATES if _rev(root, f"refs/remotes/origin/{c}")]
        if len(present) == 1:
            default = present[0]
        elif present:
            base.problem = ("ambiguous default branch on origin ("
                            + ", ".join(present) + "); set origin/HEAD")
            return base
        else:
            base.problem = "no origin default branch found (run: git fetch origin)"
            return base
    base.default_name = default
    base.name = "origin/" + default
    base.sha = _rev(root, "refs/remotes/origin/" + default)
    if not base.sha:
        base.problem = f"origin/{default} does not resolve"
    return base


def prove(root: Path, base: Baseline, tip: str) -> Tuple[str, str]:
    """``(state, detail)``; state is merged | unmerged | not-on-origin |
    no-remote | unproven. Only `merged` ever permits a deletion."""
    if base.problem or not base.sha:
        return "unproven", base.problem or "no baseline"
    ancestor = is_ancestor(root, tip, base.sha)
    if ancestor is None:
        return "unproven", "merge-base failed"
    if base.mode == "local":
        return ("merged", "") if ancestor else ("no-remote", "")
    if ancestor:
        return "merged", ""
    state, detail = _prove_by_content(root, base, tip)
    if state == "unmerged" and base.local_ref and is_ancestor(root, tip, base.local_ref):
        return "not-on-origin", ""
    return state, detail


def _prove_by_content(root: Path, base: Baseline, tip: str) -> Tuple[str, str]:
    cherry = run_git(root, ["cherry", base.sha, tip], check=False)
    if cherry.returncode == 0:
        marks = [ln[:1] for ln in cherry.stdout.splitlines() if ln.strip()]
        if marks and "+" not in marks:
            return "merged", ""
    mt = run_git(root, ["merge-tree", "--write-tree", base.sha, tip], check=False)
    if mt.returncode == 0:
        tree = (mt.stdout.splitlines() or [""])[0].strip()
        base_tree = run_git(root, ["rev-parse", "--verify", "--quiet", base.sha + "^{tree}"],
                            check=False).stdout.strip()
        if tree and tree == base_tree:
            return "merged", ""
        return "unmerged", ""
    if mt.returncode == 1:
        return "unmerged", ""
    return "unproven", "merge-tree --write-tree is unavailable or failed"


def branch_tip(root: Path, branch: str) -> str:
    return _rev(root, "refs/heads/" + branch)


def is_protected(branch: str, base: Baseline) -> bool:
    return (branch in PROTECTED_BRANCHES or branch == base.default_name
            or branch.startswith("release/"))


def branch_holders(rows: List[WtRow], branch: str, ignore: Optional[str] = None) -> List[str]:
    skip = os.path.realpath(ignore) if ignore else None
    return [row.path for row in rows
            if row.branch == branch and os.path.realpath(row.path) != skip]


def wt_tip(path: str) -> Tuple[str, bool]:
    """``(tip, branchless)`` of the checkout at *path*."""
    proc = run_git(path, ["rev-parse", "--verify", "--quiet", "HEAD"], check=False)
    if proc.returncode == 0:
        return proc.stdout.strip(), False
    gd = run_git(path, ["rev-parse", "--absolute-git-dir"], check=False)
    if gd.returncode != 0:
        return "", True
    try:
        lines = (Path(gd.stdout.strip()) / "logs" / "HEAD").read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", True
    for line in reversed(lines):
        parts = line.split(" ", 2)
        if len(parts) > 1 and re.fullmatch(r"[0-9a-f]{40}", parts[1]) and parts[1] != ZERO_SHA:
            if _rev(path, parts[1]):
                return parts[1], True
    return "", True


def wt_dirty(path: str, branchless_tip: str = "") -> bool:
    """Uncommitted OR untracked work (ignored files excluded). Cannot answer
    counts as dirty."""
    if branchless_tip:
        diff = run_git(path, ["diff", "--name-only", branchless_tip, "--"], check=False)
        other = run_git(path, ["ls-files", "--others", "--exclude-standard"], check=False)
        if diff.returncode != 0 or other.returncode != 0:
            return True
        return bool(diff.stdout.strip() or other.stdout.strip())
    proc = run_git(path, ["status", "--porcelain", "--untracked-files=all"], check=False)
    return proc.returncode != 0 or bool(proc.stdout.strip())


def cmd_create(args: argparse.Namespace) -> int:
    refusal = guard_not_bare()
    if refusal is not None:
        return refusal
    root = primary_root()
    slug = args.slug
    if "\x00" in slug or not SLUG_RE.match(slug):
        return fail(f"invalid slug {slug!r} (need ^[a-z0-9][a-z0-9-]{{0,40}}$)", 2)
    base = args.base
    if base.startswith("-"):
        return fail(f"invalid base ref {base!r}", 2)
    try:
        copy_sources = {}
        for rel in DEFAULT_COPY + list(args.copy or []):
            resolved = validate_copy_source(root, rel)
            if resolved is not None:
                copy_sources[rel] = resolved
    except ValueError as exc:
        return fail(str(exc), 2)

    with RegistryLock(root):
        _checkpoint("in-lock")
        registry = load_registry(root)
        if any(entry["slug"] == slug for entry in registry["worktrees"]):
            return fail(f"worktree {slug!r} already registered", 2)
        # EXCLUDE the primary checkout: `git worktree list` includes it, and
        # counting it would silently drop the agent budget from 5 to 4.
        live = live_worktree_paths(root) - {os.path.realpath(root)}
        if len(live) >= MAX_WORKTREES:
            return fail(
                f"{MAX_WORKTREES} worktrees already exist ({len(live)} live per git); "
                "merge or remove one first (returns collapse past 4-5 agents)", 2,
            )
        rel_path = f"{WORKTREES_DIR}/{slug}"
        wt_path = root / rel_path
        branch = BRANCH_PREFIX + slug
        try:
            verify = run_git(
                root,
                ["rev-parse", "--verify", "--end-of-options", base + "^{commit}"],
                check=False,
            )
            if verify.returncode != 0:
                return fail(f"base ref {base!r} does not resolve to a commit", 2)
            # Pin the base NOW: "HEAD" is a moving target and would make the
            # unmerged-commits guard in `remove` compare a branch to itself.
            base_sha = verify.stdout.strip()
            if run_git(root, ["rev-parse", "--verify", "--quiet",
                              "--end-of-options", "refs/heads/" + branch],
                       check=False).returncode == 0:
                return fail(f"branch {branch} already exists", 2)
            wt_path.parent.mkdir(parents=True, exist_ok=True)
            run_git(root, ["worktree", "add", "-b", branch,
                           "--", str(wt_path), base])
            # A fresh worktree is a live agent: lock it so no cleanup can take
            # it. The reason carries the creation time, the only liveness
            # signal anyone may use (the pid of this process proves nothing).
            run_git(root, ["worktree", "lock", "--reason",
                           f"claudekit agent slug={slug} ts={int(time.time())}",
                           str(wt_path)])
        except RuntimeError as exc:
            return fail(str(exc), 1)

        # .worktree-env is manager-owned local state; exclude it repo-wide so
        # it never dirties a worktree or blocks `git worktree remove`.
        exclude = Path(run_git(root, ["rev-parse", "--git-common-dir"]).stdout.strip())
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude = exclude / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if ".worktree-env" not in existing:
            with open(exclude, "a", encoding="utf-8") as fh:
                fh.write(".worktree-env\n")

        index = next_index(registry)
        for rel, resolved in copy_sources.items():
            dest = wt_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(resolved), str(dest))  # copy2 preserves mode
        env_file = wt_path / ".worktree-env"
        env_file.write_text(
            f"WORKTREE_SLUG={slug}\n"
            f"WORKTREE_INDEX={index}\n"
            f"WORKTREE_PORT_OFFSET={index * 10}\n",
            encoding="utf-8",
        )
        registry["worktrees"].append({
            "slug": slug,
            "branch": branch,
            "path": rel_path,
            "base": base,
            "base_sha": base_sha,
            # The base as a NAME that still means something later. `base_sha`
            # answers "where did this start", which is not the question
            # `remove` has to ask; "HEAD" answers nothing at all once the
            # primary checkout moves.
            "base_branch": base_branch(root, base),
            "index": index,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        save_registry(root, registry)

    if args.json:
        print(json.dumps({
            "slug": slug, "branch": branch, "root": str(wt_path),
            "index": index, "port_offset": index * 10,
        }))
    else:
        print(f"created {rel_path} on {branch} (index {index})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = primary_root()
    registry = load_registry(root)
    rows_now = list_worktrees(root)
    base = resolve_baseline(root)
    rows = []
    for entry in registry["worktrees"]:
        wt_path = root / entry["path"]
        git_row = find_row(rows_now, wt_path)
        merged = "unknown"
        tip = branch_tip(root, str(entry.get("branch", "")))
        if git_row is not None and tip:
            state, _detail = prove(root, base, tip)
            if state == "merged":
                merged = "merged"
            elif state in ("unmerged", "not-on-origin", "no-remote"):
                merged = "unmerged"
        rows.append({**entry, "live": git_row is not None,
                     "locked": bool(git_row and git_row.locked), "merged": merged})
    if args.json:
        print(json.dumps(rows, indent=2))
    elif not rows:
        print("no registered worktrees")
    else:
        for row in rows:
            status = "live" if row["live"] else "MISSING (run prune)"
            if row["locked"]:
                status += " locked"
            print(f"{row['slug']:<20} {row['branch']:<30} {row['path']:<30} {status}")
    return 0


def is_branch(root: Path, name: str) -> bool:
    """Whether *name* is a local branch in *root*."""
    if not name:
        return False
    return run_git(
        root,
        ["rev-parse", "--verify", "--quiet", "refs/heads/" + name],
        check=False,
    ).returncode == 0


def local_of(root: Path, name: str) -> str:
    """The LOCAL branch *name* stands for, or ``""``.

    A remote-tracking base is the ordinary way to start work from a fetched
    ref, and ``--base origin/main`` recorded nothing usable: ``is_branch``
    accepts ``refs/heads/`` only. A worktree based on ``origin/main`` and merged
    to ``main`` could then never earn removal.
    """
    if is_branch(root, name):
        return name
    for remote in run_git(root, ["remote"], check=False).stdout.split():
        prefix = remote + "/"
        if name.startswith(prefix):
            local = name[len(prefix):]
            if is_branch(root, local):
                return local
    return ""


def base_branch(root: Path, base: str) -> str:
    """The local branch *base* stands for, or ``""``.

    ``HEAD`` and a raw sha are not names anything can be contained in LATER, so
    both fall through to whatever branch the primary checkout is on.

    Two measured traps. ``--end-of-options`` is NOT accepted by
    ``rev-parse --abbrev-ref``, which echoes it into the answer, so it is not
    passed here. And ``--abbrev-ref`` returns a sha UNCHANGED when it cannot
    abbreviate one, so the result is confirmed to be a branch, never assumed.
    ``local_of`` is asked FIRST because it follows git's own refs/heads
    precedence; two resolvers with one job may not disagree.
    """
    name = str(base or "").strip()
    if name and name != "HEAD":
        local = local_of(root, name)
        if local:
            return local
        symbolic = run_git(root, ["rev-parse", "--abbrev-ref", name], check=False)
        resolved = symbolic.stdout.strip() if symbolic.returncode == 0 else ""
        local = local_of(root, resolved)
        if local:
            return local
    current = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    resolved = current.stdout.strip() if current.returncode == 0 else ""
    return resolved if is_branch(root, resolved) else ""


def containment_ref(root: Path, entry: dict) -> str:
    """Where *entry*'s work must have landed, resolved NOW rather than at
    create time.

    The answer has to be a BRANCH. Accepting any candidate that merely resolves
    to a commit brings back the unsatisfiable comparison: an entry whose
    ``base`` is a raw sha would be measured against the point the branch
    started from, which every working branch is ahead of forever.
    """
    for candidate in (entry.get("base_branch"), entry.get("base")):
        name = str(candidate or "").strip()
        if not name or name == "HEAD":
            continue
        local = local_of(root, name)
        if local:
            return local
    return base_branch(root, str(entry.get("base") or "HEAD"))


def unmerged_commits(root: Path, wt_path: Path, entry: dict) -> Tuple[str, str]:
    """``(ref, commits)`` -- what of *entry*'s branch is not yet in *ref*.

    The RANGE is the containment question: ``ref..branch`` lists exactly the
    commits of ``branch`` that ``ref`` does not already have, so an empty range
    IS containment. Ranging from ``base_sha`` -- the sha pinned at create time
    -- asks "does this branch have commits at all": yes for every working
    branch, and still yes after a merge, so removal could never be earned and
    only ``--force`` got past it.
    """
    ref = containment_ref(root, entry)
    if not ref:
        return "", ""
    return ref, run_git(
        wt_path,
        ["log", "--oneline", "--end-of-options", f"{ref}..{entry['branch']}"],
        check=False,
    ).stdout.strip()



# ---------------------------------------------------------------------------
# archive: bundle unmerged work and VERIFY it before anything is deleted
# ---------------------------------------------------------------------------
def archive_work(root: Path, slug: str, branch: str, wt_path: Optional[Path],
                 base: Baseline) -> str:
    """Bundle *branch* (plus a WIP commit for uncommitted work) under
    ARCHIVE_DIR and verify it. Returns what was archived (a path or a ref).
    Raises RuntimeError/OSError on ANY problem; the caller deletes nothing."""
    adir = root / ARCHIVE_DIR
    try:
        adir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create archive directory {adir}: {exc}") from exc
    if not os.access(str(adir), os.W_OK | os.X_OK):
        raise RuntimeError(f"archive directory {adir} is not writable")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH") or time.time())
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(epoch))
    tip = branch_tip(root, branch)
    if not tip:
        raise RuntimeError(f"branch {branch} does not exist: nothing to archive")

    refs = ["refs/heads/" + branch]
    if wt_path is not None and wt_path.is_dir():
        head, branchless = wt_tip(str(wt_path))
        if wt_dirty(str(wt_path), head if branchless else ""):
            wip = _wip_commit(wt_path, head or tip, slug, stamp)
            refs.append(wip)

    name = f"{slug}-{tip[:8]}-{stamp}"
    bundle = adir / f"{name}.bundle"
    counter = 2
    while bundle.exists():
        bundle = adir / f"{name}-{counter}.bundle"
        counter += 1
    cmd = ["bundle", "create", str(bundle)] + refs
    if base.sha:
        cmd += ["--not", base.sha]
    proc = run_git(root, cmd, check=False, timeout=300)
    if proc.returncode != 0:
        bundle.unlink(missing_ok=True)
        if "empty bundle" not in proc.stderr.lower():
            raise RuntimeError(f"git bundle create failed: {proc.stderr.strip()}")
        # Nothing beyond the default branch: git refuses an empty bundle, so
        # the tip is pinned by a verified ref instead.
        ref = f"refs/archive/{slug}/{stamp}"
        run_git(root, ["update-ref", ref, tip])
        if branch_ref_sha(root, ref) != tip:
            raise RuntimeError(f"archive ref {ref} could not be verified")
        print(f"archived: {ref} (no commits beyond {base.name or 'the default branch'})")
        return ref
    _checkpoint("after-bundle", path=str(bundle))
    verify = run_git(root, ["bundle", "verify", str(bundle)], check=False, timeout=300)
    if verify.returncode != 0:
        bundle.unlink(missing_ok=True)
        raise RuntimeError(f"bundle verification failed for {bundle}: "
                           f"{verify.stderr.strip()}; nothing was deleted")
    print(f"archived: {bundle}")
    return str(bundle)


def branch_ref_sha(root: Path, ref: str) -> str:
    return _rev(root, ref)


def _wip_commit(wt_path: Path, head: str, slug: str, stamp: str) -> str:
    """Snapshot ALL work (tracked changes and untracked files, never ignored
    ones) of *wt_path* as a commit on refs/archive/<slug>/wip-<ts>, through a
    throwaway index so the worktree's own index is untouched."""
    gd = run_git(wt_path, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    tmpdir = tempfile.mkdtemp(dir=gd, prefix="archive-index-")
    try:
        env = {"GIT_INDEX_FILE": os.path.join(tmpdir, "index")}
        run_git(wt_path, ["add", "-A"], env=env)
        tree = run_git(wt_path, ["write-tree"], env=env).stdout.strip()
        ident: Dict[str, str] = {}
        if run_git(wt_path, ["config", "user.name"], check=False).returncode != 0:
            ident = {"GIT_AUTHOR_NAME": "worktree-manager",
                     "GIT_AUTHOR_EMAIL": "worktree-manager@localhost",
                     "GIT_COMMITTER_NAME": "worktree-manager",
                     "GIT_COMMITTER_EMAIL": "worktree-manager@localhost"}
        commit = run_git(wt_path, ["commit-tree", tree, "-p", head, "-m",
                                   f"wip: uncommitted work of {slug} archived by worktree-manager"],
                         env=ident or None).stdout.strip()
        ref = f"refs/archive/{slug}/wip-{stamp}"
        run_git(wt_path, ["update-ref", ref, commit])
        return ref
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def delete_branch_step(root: Path, branch: str, base: Baseline, archived: bool) -> Tuple[str, bool]:
    """Delete *branch* unless it is protected or checked out somewhere.
    Returns ``(message, ok)``; ok is False only when git refused the delete."""
    if is_protected(branch, base):
        return f"branch {branch} kept (protected)", True
    holders = branch_holders(list_worktrees(root), branch)
    if holders:
        return f"branch {branch} kept (branch-held by {holders[0]})", True
    if not branch_tip(root, branch):
        return f"branch {branch} was already gone", True
    _checkpoint("before-branch-delete", root=str(root), branch=branch)
    proc = run_git(root, ["branch", "-D", "--", branch], check=False)
    if proc.returncode != 0:
        return f"branch {branch} NOT deleted: {proc.stderr.strip()}", False
    how = "archived" if archived else f"merged into {base.name}"
    return f"branch {branch} deleted ({how})", True


def unlock_own(root: Path, row: Optional[WtRow], path: Path) -> None:
    if row is not None and row.locked and OWN_LOCK_RE.match(row.lock_reason):
        run_git(root, ["worktree", "unlock", str(path)], check=False)


def drop_registry(root: Path, path: Path, slug: str) -> None:
    registry = load_registry(root)
    real = os.path.realpath(str(path))
    registry["worktrees"] = [
        e for e in registry["worktrees"]
        if not (e.get("slug") == slug or os.path.realpath(str(root / e["path"])) == real)
    ]
    save_registry(root, registry)


def cwd_inside(path: Path) -> bool:
    try:
        cwd = os.path.realpath(os.getcwd())
    except OSError:
        return False
    real = os.path.realpath(str(path))
    return cwd == real or cwd.startswith(real + os.sep)


def cmd_remove(args: argparse.Namespace) -> int:
    root = primary_root()
    with RegistryLock(root):
        _checkpoint("in-lock")
        registry = load_registry(root)
        entry = next((e for e in registry["worktrees"] if e["slug"] == args.slug), None)
        if entry is None:
            return fail(f"worktree {args.slug!r} not in registry", 2)
        wt_path = root / entry["path"]
        real = os.path.realpath(str(wt_path))
        real_root = os.path.realpath(str(root))
        if real == real_root:
            return fail("refusing to remove the primary worktree", 2)
        if not real.startswith(real_root + os.sep):
            return fail(f"refusing to remove {entry['path']}: it resolves outside the "
                        "repository", 2)
        if cwd_inside(wt_path):
            return fail("refusing to remove the worktree you are standing in; "
                        "cd to the primary checkout and re-run", 2)
        branch = str(entry.get("branch", ""))
        slug = str(entry["slug"])
        rows = list_worktrees(root)
        row = find_row(rows, wt_path)
        if row is not None and row.locked and not OWN_LOCK_RE.match(row.lock_reason):
            return fail(f"{entry['path']} is locked: {row.lock_reason or 'no reason given'} "
                        "(even --force will not remove a foreign lock; unlock it yourself)", 2)
        exists = wt_path.is_dir()
        base = resolve_baseline(root)
        dirty = False
        if exists:
            tip, branchless = wt_tip(str(wt_path))
            dirty = wt_dirty(str(wt_path), tip if branchless else "")
            if dirty and not args.force:
                return fail(f"{entry['path']} has uncommitted changes (use --force)", 2)

        if args.delete_branch and branch_tip(root, branch):
            state, detail = prove(root, base, branch_tip(root, branch))
            if state != "merged":
                if not (args.force and args.archive):
                    why = state if not detail else f"{state}: {detail}"
                    return fail(f"{branch} is not merged into {base.name or 'the default branch'} "
                                f"({why}); use --force --archive to bundle it first, "
                                "then delete", 2)
            elif dirty and args.force and not args.archive:
                return fail(f"{entry['path']} has uncommitted changes that --delete-branch "
                            "--force would destroy; add --archive", 2)
            if dirty and not args.archive:
                return fail(f"{entry['path']} has uncommitted changes; add --archive", 2)
        elif not args.delete_branch and exists and not args.force:
            ref, unmerged = unmerged_commits(root, wt_path, entry)
            if not ref and not args.force:
                named = str(entry.get("base_branch") or entry.get("base") or "")
                cause = (f"its base was recorded as {named!r}"
                         if named and named != "HEAD"
                         else "no base branch was recorded for it")
                return fail(
                    f"cannot tell what {entry['branch']} should be contained "
                    f"in: {cause}, and this checkout is not on a branch to "
                    "fall back to. Check out the base branch here and re-run, "
                    "or use --force.", 2)
            if unmerged:
                return fail(f"{entry['branch']} has commits not contained in "
                            f"{ref} (merge first, or use --force):\n{unmerged}", 2)

        archived = False
        if args.archive and branch_tip(root, branch):
            archive_work(root, slug, branch, wt_path if exists else None, base)
            archived = True
        if exists:
            _checkpoint("before-remove", path=str(wt_path))
            if not args.force and wt_dirty(str(wt_path)):
                return fail(f"{entry['path']} changed while removing (uncommitted work "
                            "appeared); nothing was removed", 2)
            unlock_own(root, row, wt_path)
            run_git(root, ["worktree", "remove", "--force", "--", str(wt_path)])
            _checkpoint("after-worktree-remove")
        else:
            run_git(root, ["worktree", "prune", "--expire", "now"], check=False)
        drop_registry(root, wt_path, slug)

        if not args.delete_branch:
            print(f"removed {entry['path']} (branch {branch} kept for merge/cleanup)")
            return 0
        message, ok = delete_branch_step(root, branch, base, archived)
        if not ok:
            return fail(f"removed {entry['path']}; {message}", 1)
        print(f"removed {entry['path']}; {message}")
        return 0


# ---------------------------------------------------------------------------
# reap: classify with no lock, mutate under the lock, re-verify every item
# ---------------------------------------------------------------------------
@dataclass
class Item:
    name: str
    kind: str                       # wt | gone | sweep
    path: str = ""
    slug: str = ""
    branch: str = ""
    tip: str = ""
    lock_state: str = ""            # the lock reason seen at classification
    action: str = "keep"            # reap | keep
    reason: str = ""
    note: str = ""
    unlock: bool = False
    gone: bool = False
    delete_branch: bool = False
    notes: List[str] = field(default_factory=list)


def _reason(state: str, detail: str) -> str:
    if state == "unproven":
        return f"unproven ({detail})" if detail else "unproven"
    return state


def _scopes(root: Path) -> List[str]:
    real_root = os.path.realpath(str(root))
    return [os.path.join(real_root, s) for s in SCOPE_DIRS]


def _in_scope(root: Path, path: str) -> bool:
    real = os.path.realpath(path)
    return any(real.startswith(s + os.sep) for s in _scopes(root))


def _branch_note(root: Path, it: Item, base: Baseline, rows: List[WtRow],
                 ignore: Optional[str]) -> None:
    """Decide whether the branch of a reapable item may be deleted with it."""
    if is_protected(it.branch, base):
        it.note = "protected"
    elif branch_holders(rows, it.branch, ignore=ignore):
        it.note = "branch-held"
    else:
        it.delete_branch = True


def _classify_gone(root: Path, base: Baseline, it: Item, rows: List[WtRow]) -> None:
    it.gone = True
    tip = branch_tip(root, it.branch) if it.branch else ""
    it.tip = tip
    if not tip:
        it.action = "reap"
        return
    state, _detail = prove(root, base, tip)
    if state == "merged":
        it.action = "reap"
        _branch_note(root, it, base, rows, it.path)
    else:
        it.reason = "branch-orphaned"


def _classify_live(root: Path, base: Baseline, it: Item, row: WtRow,
                   rows: List[WtRow]) -> None:
    tip, branchless = wt_tip(row.path)
    it.tip = tip
    if wt_dirty(row.path, tip if branchless else ""):
        it.reason = "dirty"
        return
    if branchless:
        state, _detail = prove(root, base, tip) if tip else ("unproven", "")
        if state == "merged":
            it.action = "reap"
        else:
            it.reason = "branchless"
        return
    state, detail = prove(root, base, tip)
    if row.detached or not row.branch:
        if state == "merged":
            it.action = "reap"
            return
        contains = run_git(root, ["for-each-ref", "--contains", tip, "--format=%(refname)"],
                           check=False).stdout.strip()
        it.reason = _reason(state, detail) if contains else "detached-unreferenced"
        return
    it.branch = row.branch
    if state == "merged":
        it.action = "reap"
        _branch_note(root, it, base, rows, row.path)
    else:
        it.reason = _reason(state, detail)


def classify(root: Path, base: Baseline, rows: List[WtRow], registry: Dict[str, Any],
             args: argparse.Namespace, now: float) -> Tuple[List[Item], List[str]]:
    real_root = os.path.realpath(str(root))
    by_path = {os.path.realpath(str(root / e["path"])): e for e in registry["worktrees"]}
    min_age = args.min_age * 3600.0
    items: List[Item] = []
    listed = set()
    for row in rows:
        real = os.path.realpath(row.path)
        listed.add(real)
        if real == real_root or row.bare:
            continue
        entry = by_path.get(real)
        slug = str(entry["slug"]) if entry else ""
        it = Item(name=slug or os.path.basename(row.path.rstrip("/")), kind="wt",
                  path=row.path, slug=slug, branch=row.branch,
                  lock_state=row.lock_reason if row.locked else "")
        items.append(it)
        if not _in_scope(root, row.path):
            it.reason = "external"
            continue
        row_age = min_age
        base_name = os.path.basename(row.path.rstrip("/"))
        if base_name.startswith(MQ_PREFIX) or slug.startswith(MQ_PREFIX):
            row_age = min(min_age, MQ_MIN_AGE_HOURS * 3600.0)
        kind, detail = lock_kind(row, row_age, now)
        if kind == "live":
            it.reason = "locked"
            continue
        if kind == "foreign":
            it.reason = f"locked: {detail}" if detail else "locked"
            continue
        if row.prunable or not os.path.isdir(row.path):
            it.kind = "gone"
            _classify_gone(root, base, it, rows)
        else:
            _classify_live(root, base, it, row, rows)
        if kind == "stale":
            if args.break_stale_locks and it.action == "reap":
                it.unlock = True
            else:
                it.action, it.reason, it.note = "keep", "stale-lock", ""
                it.delete_branch = False

    for real, entry in by_path.items():
        if real in listed or not _in_scope(root, real):
            continue
        it = Item(name=str(entry["slug"]), kind="gone", path=real, slug=str(entry["slug"]),
                  branch=str(entry.get("branch", "")))
        items.append(it)
        _classify_gone(root, base, it, rows)

    seen = {it.branch for it in items if it.branch}
    held_elsewhere = {r.branch: r.path for r in rows if r.branch}
    heads = run_git(root, ["for-each-ref", "--format=%(refname:short)",
                           "refs/heads/" + BRANCH_PREFIX], check=False).stdout.split()
    for branch in heads:
        if branch in seen:
            continue
        tip = branch_tip(root, branch)
        state, _detail = prove(root, base, tip) if tip else ("unproven", "")
        if state != "merged":
            continue
        it = Item(name=branch, kind="sweep", branch=branch, tip=tip)
        if branch in held_elsewhere:
            it.reason = "branch-held"
        else:
            it.action = "reap"
            it.delete_branch = True
        items.append(it)

    orphans: List[str] = []
    for scope in _scopes(root):
        if not os.path.isdir(scope):
            continue
        for child in sorted(os.listdir(scope)):
            full = os.path.join(scope, child)
            if not os.path.isdir(full) or os.path.realpath(full) in listed:
                continue
            size = 0
            for dirpath, _dirs, files in os.walk(full):
                for fname in files:
                    try:
                        size += os.lstat(os.path.join(dirpath, fname)).st_size
                    except OSError:
                        pass
            try:
                age = max(0.0, now - os.stat(full).st_mtime) / 3600.0
            except OSError:
                age = 0.0
            agent = child.startswith("agent-") or os.path.basename(scope) == ".worktrees"
            orphans.append(f"orphan-dir {full} size={size} age={age:.1f}h "
                           f"agent-owned={'yes' if agent else 'no'} "
                           f"too-new={'yes' if age < args.min_age else 'no'}")
    return items, orphans


def _lenient_registry(root: Path) -> Tuple[Dict[str, Any], bool]:
    try:
        return load_registry(root), True
    except RuntimeError as exc:
        print(f"worktree-manager: warning: {exc}; the registry will not be written",
              file=sys.stderr)
        return {"version": REGISTRY_VERSION, "worktrees": []}, False


def _describe(it: Item, base: Baseline) -> str:
    if it.delete_branch:
        return f" (branch {it.branch} deleted)"
    if it.note:
        return f" (branch {it.branch} kept: {it.note})"
    return ""


def _reap_one(root: Path, base: Baseline, it: Item, reg_ok: bool,
              args: argparse.Namespace) -> Tuple[str, str]:
    """Re-verify and reap one item under the lock. Returns ``(status, text)``;
    status is reaped | kept | skip. May raise RuntimeError/OSError."""
    rows = list_worktrees(root)
    if it.kind == "sweep":
        tip = branch_tip(root, it.branch)
        if not tip:
            return "skip", ""
        if tip != it.tip:
            return "kept", "changed"
        if branch_holders(rows, it.branch):
            return "kept", "branch-held"
        if prove(root, base, tip)[0] != "merged":
            return "kept", "unmerged"
        message, ok = delete_branch_step(root, it.branch, base, False)
        if not ok:
            raise RuntimeError(message)
        return "reaped", f" ({message})"

    path = Path(it.path)
    row = find_row(rows, path)
    if it.kind == "gone":
        if row is not None and (row.locked != bool(it.lock_state)
                                or (row.locked and row.lock_reason != it.lock_state)):
            return "kept", "changed"
        if row is not None and path.is_dir() and not row.prunable:
            return "kept", "changed"
        if it.action == "reap" and it.branch and branch_tip(root, it.branch) != it.tip:
            return "kept", "changed"
        if it.action == "reap" and it.tip and prove(root, base, it.tip)[0] != "merged":
            return "kept", "changed"
        unlock_own(root, row, path)
        run_git(root, ["worktree", "prune", "--expire", "now"], check=False)
        if reg_ok:
            drop_registry(root, path, it.slug)
        if it.action != "reap":
            return "kept", it.reason
        if not it.delete_branch:
            return "reaped", _describe(it, base)
        message, ok = delete_branch_step(root, it.branch, base, False)
        if not ok:
            raise RuntimeError(message)
        return "reaped", f" ({message})"

    if row is None:
        return "skip", ""
    if (row.lock_reason if row.locked else "") != it.lock_state:
        return "kept", "changed"
    tip, branchless = wt_tip(it.path)
    if tip != it.tip:
        return "kept", "changed"
    if wt_dirty(it.path, tip if branchless else ""):
        return "kept", "dirty"
    if prove(root, base, tip)[0] != "merged":
        return "kept", "unmerged"
    _checkpoint("before-remove", path=it.path)
    if wt_dirty(it.path, tip if branchless else ""):
        return "kept", "dirty"
    unlock_own(root, row, path)
    run_git(root, ["worktree", "remove", "--force", "--", it.path])
    _checkpoint("after-worktree-remove")
    if reg_ok:
        drop_registry(root, path, it.slug)
    if not it.branch:
        return "reaped", ""
    if not it.delete_branch:
        return "reaped", _describe(it, base)
    message, ok = delete_branch_step(root, it.branch, base, False)
    if not ok:
        raise RuntimeError(message)
    return "reaped", f" ({message})"


def cmd_reap(args: argparse.Namespace) -> int:
    refusal = guard_not_bare() or guard_main_worktree()
    if refusal is not None:
        return refusal
    root = primary_root()
    remotes = run_git(root, ["remote"], check=False).stdout.split()
    if "origin" in remotes and not args.no_fetch:
        _checkpoint("before-fetch")
        try:
            fetch = run_git(root, ["fetch", "--prune", "origin"], check=False, timeout=60)
        except RuntimeError as exc:
            return fail(f"fetch failed ({exc}); nothing was changed", 1)
        if fetch.returncode != 0:
            return fail(f"fetch failed: {fetch.stderr.strip()}; nothing was changed "
                        "(use --no-fetch to measure against the last fetched origin)", 1)
    base = resolve_baseline(root)
    now = time.time()
    if "origin" in remotes and args.no_fetch and base.sha:
        stamp = run_git(root, ["log", "-1", "--format=%ct", base.sha], check=False).stdout.strip()
        age = (now - int(stamp)) / 3600.0 if stamp.isdigit() else 0.0
        print(f"no-fetch: measuring against {base.name} at {base.sha[:8]} (age {age:.1f}h)")

    registry, reg_ok = _lenient_registry(root)
    items, orphans = classify(root, base, list_worktrees(root), registry, args, now)
    _checkpoint("after-classify", root=str(root))

    to_reap = [it for it in items if it.action == "reap"]
    if args.yes and len(to_reap) > args.max_deletions:
        return fail(f"{len(to_reap)} items would be reaped, more than --max-deletions "
                    f"{args.max_deletions}; review the dry run and raise the cap "
                    "deliberately", 2)

    reaped = failed = kept = 0
    for it in items:
        if it.action == "keep":
            kept += 1
            print(f"kept {it.name}: {it.reason}")
        elif not args.yes:
            print(f"would reap {it.name}{_describe(it, base)}")
    if args.yes and (to_reap or any(i.gone for i in items)):
        with RegistryLock(root):
            _checkpoint("in-lock")
            for it in items:
                if it.action == "keep" and not it.gone:
                    continue
                if it.action == "keep" and it.reason != "branch-orphaned":
                    continue
                try:
                    status, text = _reap_one(root, base, it, reg_ok, args)
                except (RuntimeError, OSError) as exc:
                    failed += 1
                    print(f"failed {it.name}: {exc}", file=sys.stderr)
                    continue
                if status == "reaped":
                    reaped += 1
                    print(f"reaped {it.name}{text}")
                elif status == "kept":
                    if it.action == "keep":
                        continue  # orphaned branch: already reported as kept
                    kept += 1
                    print(f"kept {it.name}: {text}")
    for line in orphans:
        print(line)
    if not to_reap:
        print("nothing to reclaim")
    if args.yes:
        print(f"summary: reaped={reaped} failed={failed} kept={kept}")
    return 1 if failed else 0


def cmd_prune(args: argparse.Namespace) -> int:
    root = primary_root()
    with RegistryLock(root):
        # `create` locks every worktree and git never prunes a locked entry, so
        # a crashed agent's missing directory would stay listed forever. An
        # explicit `prune` lifts OUR OWN lock on a directory that is gone.
        for row in list_worktrees(root)[1:]:
            if row.locked and not os.path.isdir(row.path):
                unlock_own(root, row, Path(row.path))
        run_git(root, ["worktree", "prune", "--expire", "now"], check=False)
        live = live_worktree_paths(root)
        registry = load_registry(root)
        kept, dropped = [], []
        for entry in registry["worktrees"]:
            if os.path.realpath(str(root / entry["path"])) in live:
                kept.append(entry)
            else:
                dropped.append(entry["slug"])
        registry["worktrees"] = kept
        save_registry(root, registry)
    print(f"pruned {len(dropped)} stale entr{'y' if len(dropped) == 1 else 'ies'}: "
          f"{', '.join(dropped) if dropped else 'none'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    problem = check_git_version()
    if problem:
        return fail(problem, 1)
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="create .worktrees/<slug> + branch agent/<slug>")
    p_create.add_argument("slug")
    p_create.add_argument("--base", default="HEAD")
    p_create.add_argument("--copy", action="append", default=[],
                          help="extra repo-relative file to copy in (e.g. --copy .env)")
    p_create.add_argument("--json", action="store_true")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="list registered worktrees")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="remove a worktree (branch kept unless "
                                             "--delete-branch)")
    p_remove.add_argument("slug")
    p_remove.add_argument("--force", action="store_true")
    p_remove.add_argument("--delete-branch", action="store_true",
                          help="also delete the branch once proven merged into origin")
    p_remove.add_argument("--archive", action="store_true",
                          help="bundle the branch (and uncommitted work) first; with "
                               "--delete-branch --force this is how unmerged work is dropped")
    p_remove.set_defaults(func=cmd_remove)

    p_reap = sub.add_parser("reap", aliases=["cleanup"],
                            help="remove worktrees+branches proven merged (dry run "
                                 "unless --yes)")
    p_reap.add_argument("--yes", action="store_true", help="actually delete")
    p_reap.add_argument("--max-deletions", type=int, default=DEFAULT_MAX_DELETIONS)
    p_reap.add_argument("--no-fetch", action="store_true")
    p_reap.add_argument("--min-age", type=float, default=DEFAULT_MIN_AGE_HOURS,
                        help="hours: lock staleness and orphan 'too-new' threshold")
    p_reap.add_argument("--break-stale-locks", action="store_true")
    p_reap.set_defaults(func=cmd_reap)

    p_prune = sub.add_parser("prune", help="reconcile registry with git worktree list")
    p_prune.set_defaults(func=cmd_prune)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (RuntimeError, OSError) as exc:
        return fail(str(exc), 1)


if __name__ == "__main__":
    sys.exit(main())
