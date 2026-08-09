#!/usr/bin/env python3
"""Worktree lifecycle manager for parallel agent execution.

One branch = one worktree = one agent. This script owns the lifecycle so
agents never improvise git worktree commands:

    create <slug> [--base <ref>] [--copy <path> ...] [--json]
    list   [--json]
    remove <slug> [--force]
    prune

Design contract (see .claude/plans/plan-worktree-multi-agent.md):
  * Worktrees live at .worktrees/<slug> with branch agent/<slug>.
  * Registry at .claude/state/worktrees.json stores repo-relative paths only
    (both locations are git-ignored; nothing here may ship).
  * Slugs are validated (^[a-z0-9][a-z0-9-]{0,40}$); git is always invoked in
    list form with user-supplied refs verified via rev-parse first.
  * .claude/settings.local.json is copied into new worktrees when present.
    Secrets (.env etc.) are NEVER copied unless explicitly listed via --copy.
  * At most MAX_WORKTREES concurrent worktrees (returns collapse past 4-5
    parallel agents; keep merges tractable).
  * Registry writes are atomic (tempfile + os.replace) under an exclusive
    lock file; a lock older than LOCK_STALE_SECS is treated as crashed and
    broken once.

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
from pathlib import Path
from typing import Any, Dict, List, Optional

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
MAX_WORKTREES = 5
LOCK_STALE_SECS = 300
WORKTREES_DIR = ".worktrees"
BRANCH_PREFIX = "agent/"
DEFAULT_COPY = [".claude/settings.local.json"]
REGISTRY_VERSION = 1


def fail(msg: str, code: int) -> "int":
    print(f"worktree-manager: {msg}", file=sys.stderr)
    return code


def run_git(root: Path, args: List[str], check: bool = True) -> "subprocess.CompletedProcess[str]":
    proc = subprocess.run(
        ["git", "-C", str(root)] + args,
        capture_output=True, text=True, timeout=60,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc


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


def registry_path(root: Path) -> Path:
    return root / ".claude" / "state" / "worktrees.json"


def lock_path(root: Path) -> Path:
    return root / ".claude" / "locks" / "worktree-manager.lock"


class RegistryLock:
    """Exclusive lock via O_CREAT|O_EXCL; a lock older than LOCK_STALE_SECS
    is assumed to belong to a crashed run and is broken once."""

    def __init__(self, root: Path) -> None:
        self.path = lock_path(root)

    def __enter__(self) -> "RegistryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in (1, 2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    continue  # lock vanished between open and stat; retry
                if age > LOCK_STALE_SECS and attempt == 1:
                    self.path.unlink(missing_ok=True)  # stale: break once
                    continue
                raise RuntimeError(
                    f"another worktree-manager run holds {self.path}"
                ) from exc
        raise RuntimeError(f"could not acquire lock {self.path}")

    def __exit__(self, *exc_info: object) -> None:
        self.path.unlink(missing_ok=True)


def load_registry(root: Path) -> Dict[str, Any]:
    path = registry_path(root)
    if not path.exists():
        return {"version": REGISTRY_VERSION, "worktrees": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


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


def cmd_create(args: argparse.Namespace) -> int:
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
        registry = load_registry(root)
        if any(entry["slug"] == slug for entry in registry["worktrees"]):
            return fail(f"worktree {slug!r} already registered", 2)
        if len(registry["worktrees"]) >= MAX_WORKTREES:
            return fail(
                f"{MAX_WORKTREES} worktrees already registered; "
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
    live = run_git(root, ["worktree", "list", "--porcelain"], check=False).stdout
    live_paths = {line[len("worktree "):] for line in live.splitlines()
                  if line.startswith("worktree ")}
    rows = []
    for entry in registry["worktrees"]:
        wt_path = root / entry["path"]
        rows.append({**entry, "live": str(wt_path) in live_paths})
    if args.json:
        print(json.dumps(rows, indent=2))
    elif not rows:
        print("no registered worktrees")
    else:
        for row in rows:
            status = "live" if row["live"] else "MISSING (run prune)"
            print(f"{row['slug']:<20} {row['branch']:<30} {row['path']:<30} {status}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    root = primary_root()
    with RegistryLock(root):
        registry = load_registry(root)
        entry = next((e for e in registry["worktrees"] if e["slug"] == args.slug), None)
        if entry is None:
            return fail(f"worktree {args.slug!r} not in registry", 2)
        wt_path = root / entry["path"]
        if wt_path.resolve() == root.resolve():
            return fail("refusing to remove the primary worktree", 2)
        if wt_path.exists():
            dirty = run_git(wt_path, ["status", "--porcelain"], check=False).stdout.strip()
            if dirty and not args.force:
                return fail(f"{entry['path']} has uncommitted changes (use --force)", 2)
            base_sha = entry.get("base_sha", entry["base"])
            unmerged = run_git(
                wt_path,
                ["log", "--oneline", "--end-of-options", f"{base_sha}..HEAD"],
                check=False,
            ).stdout.strip()
            if unmerged and not args.force:
                return fail(
                    f"{entry['branch']} has commits not contained in "
                    f"{entry['base']} (merge first, or use --force)", 2,
                )
            # Our guards above are the real gate; git's own removal check
            # would refuse over ignored local files (.worktree-env, copied
            # settings.local.json), which are disposable by design.
            remove_args = ["worktree", "remove", "--force", "--", str(wt_path)]
            try:
                run_git(root, remove_args)
            except RuntimeError as exc:
                return fail(str(exc), 1)
        registry["worktrees"] = [e for e in registry["worktrees"]
                                 if e["slug"] != args.slug]
        save_registry(root, registry)
    print(f"removed {entry['path']} (branch {entry['branch']} kept for merge/cleanup)")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    root = primary_root()
    with RegistryLock(root):
        run_git(root, ["worktree", "prune"], check=False)
        live = run_git(root, ["worktree", "list", "--porcelain"], check=False).stdout
        live_paths = {line[len("worktree "):] for line in live.splitlines()
                      if line.startswith("worktree ")}
        registry = load_registry(root)
        kept, dropped = [], []
        for entry in registry["worktrees"]:
            if str(root / entry["path"]) in live_paths:
                kept.append(entry)
            else:
                dropped.append(entry["slug"])
        registry["worktrees"] = kept
        save_registry(root, registry)
    print(f"pruned {len(dropped)} stale entr{'y' if len(dropped) == 1 else 'ies'}: "
          f"{', '.join(dropped) if dropped else 'none'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
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

    p_remove = sub.add_parser("remove", help="remove a worktree (branch is kept)")
    p_remove.add_argument("slug")
    p_remove.add_argument("--force", action="store_true")
    p_remove.set_defaults(func=cmd_remove)

    p_prune = sub.add_parser("prune", help="reconcile registry with git worktree list")
    p_prune.set_defaults(func=cmd_prune)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        return fail(str(exc), 1)


if __name__ == "__main__":
    sys.exit(main())
