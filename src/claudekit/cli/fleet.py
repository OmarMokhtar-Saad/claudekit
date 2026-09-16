"""``ck fleet`` -- survey and update every kitted project under one root.

Syncing a kit change into the fleet used to be a hand-written script per change,
and the scripts kept regressing to a hardcoded repo list. A list is a silent
omission machine: a project missing from it is indistinguishable from a project
that is up to date. So discovery here is a *property* -- an immediate child of
the root whose ``.claude/`` carries an install manifest -- and never an
enumeration.

Nothing in this module invents state. The manifest already records the
install-time sha256 of every managed path, which is what separates "untouched
downstream" (current == manifest) from "locally modified" (current != manifest);
the kit source supplies the third hash, "what it should be now". All four verbs
are presentation over those three hashes, plus, for ``update``, a loop over the
existing :func:`claudekit.cli.main.cmd_update` -- called as a function, never
through a subprocess, so its backup and preservation behaviour is inherited
rather than re-implemented.

Git mutation is deliberately absent: committing downstream is the owner's step.
``update`` prints the suggested ``git -C <repo> add -A ...`` line instead.
"""

import argparse
import fnmatch
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from claudekit.cli import main as _m


def _resolve_root(raw: Optional[str]) -> Path:
    """The fleet root: ``--root`` if given, else the parent of the cwd."""
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve().parent


def _inside(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(child), str(parent)]) == str(parent)
    except ValueError:  # different drives / unrelated roots
        return False


def _git_dir(repo: Path) -> Optional[Path]:
    """The real git directory for ``repo``, following a worktree pointer file."""
    dotgit = repo / ".git"
    if dotgit.is_dir():
        return dotgit
    if dotgit.is_file():
        try:
            text = dotgit.read_text().strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            return Path(text.split(":", 1)[1].strip())
    return None


def _is_worktree_of(repo: Path, source: Optional[Path]) -> bool:
    """True when ``repo`` is a git worktree whose git dir lives in the source repo.

    A worktree of the kit itself is not a fleet member: updating it would install
    the kit over its own source tree.
    """
    if source is None:
        return False
    gitdir = _git_dir(repo)
    if gitdir is None or not gitdir.is_absolute():
        return False
    try:
        return _inside(gitdir.resolve(), source.resolve())
    except OSError:
        return False


def _branch(repo: Path) -> str:
    """The checked-out branch, read from ``HEAD``. No subprocess, no git dependency."""
    gitdir = _git_dir(repo)
    if gitdir is None:
        return "-"
    head = gitdir / "HEAD"
    try:
        raw = head.read_text().strip()
    except OSError:
        return "?"
    if raw.startswith("ref: refs/heads/"):
        return raw.split("refs/heads/", 1)[1]
    return raw[:8] if raw else "?"


def discover(root: Path, include: Optional[Sequence[str]] = None,
             exclude: Optional[Sequence[str]] = None,
             source: Optional[Path] = None) -> List[Path]:
    """Kitted projects directly under ``root``.

    Membership is the presence of the install manifest under ``<child>/.claude/``.
    The walk never recurses past the immediate children, and it skips backup
    directories, the kit source itself, and worktrees of the source.
    """
    found: List[Path] = []
    if not root.is_dir():
        return found
    try:
        children = sorted(root.iterdir())
    except OSError:
        return found
    for child in children:
        if not child.is_dir() or ".bak-" in child.name:
            continue
        if not (child / ".claude" / _m.MANIFEST_NAME).is_file():
            continue
        if source is not None and child.resolve() == source.resolve():
            continue
        if _is_worktree_of(child, source):
            continue
        if include and not any(fnmatch.fnmatch(child.name, p) for p in include):
            continue
        if exclude and any(fnmatch.fnmatch(child.name, p) for p in exclude):
            continue
        found.append(child)
    return found


def _classify(repo: Path) -> Tuple[List[str], List[str], List[str], dict]:
    """(modified, missing, unchanged, manifest) for one repo."""
    manifest = _m._load_manifest(repo) or {}
    modified, missing, unchanged = _m._classify_manifest(repo, manifest)
    return modified, missing, unchanged, manifest


def _label(rel: str, base: Path, kit: Optional[Path], manifest: dict) -> str:
    """The three-way label ``cmd_diff`` prints, for a file that differs from the manifest."""
    if kit is None:
        return "modified"
    kit_path = kit / rel
    kit_hash = _m._sha256(kit_path) if kit_path.exists() else None
    expected = manifest.get("files", {}).get(rel)
    actual = _m._sha256(base / rel)
    if actual == kit_hash:
        return "kit-updated"
    if kit_hash == expected:
        return "locally modified"
    if kit_hash is not None:
        return "both changed"
    return "modified"


def _hashes(repo: Path) -> Dict[str, Optional[str]]:
    base = _m._manifest_base(repo)
    return {rel: _m._sha256(base / rel) for rel in _m._managed_files(base)}


def _suggest_commit(repo: Path) -> None:
    _m.info(f"    commit it yourself: git -C {repo} add -A .claude .agents .gitignore")


def _fleet_list(repos: List[Path]) -> int:
    print(f"\n  {'REPO':28} {'BRANCH':22} {'VERSION':9} {'MODE':8} DIRTY")
    for repo in repos:
        modified, missing, _unchanged, manifest = _classify(repo)
        dirty = len(modified) + len(missing)
        version = str(manifest.get("version", "?"))
        mode = str(manifest.get("mode", "?"))
        src = str(manifest.get("source_hash") or manifest.get("commit") or "")[:8] or "-"
        print(f"  {repo.name[:28]:28} {_branch(repo)[:22]:22} {version:9} "
              f"{mode:8} {dirty} (src {src})")
    print(f"\n  {len(repos)} kitted project(s).")
    return 0


def _fleet_diff(repos: List[Path], kit: Optional[Path]) -> int:
    for repo in repos:
        modified, missing, unchanged, manifest = _classify(repo)
        base = _m._manifest_base(repo)
        custom = sorted(set(_m._managed_files(base)) - set(manifest.get("files", {})))
        labelled = [(rel, _label(rel, base, kit, manifest)) for rel in modified]
        local = [rel for rel, lab in labelled if lab in ("locally modified", "both changed")]
        stale = [rel for rel, lab in labelled if lab == "kit-updated"]
        print(f"\n  {repo.name}: {len(unchanged)} untouched, {len(local)} locally-modified, "
              f"{len(stale)} kit-updated, {len(missing)} missing, {len(custom)} custom")
        for rel in local:
            _m.warn(f"    locally modified: {rel}")
        for rel in missing:
            _m.err(f"    missing:          {rel}")
    print()
    return 0


def _plan_update(repo: Path) -> Tuple[int, int]:
    """(would-overwrite, would-preserve) for ``--dry-run``: a real plan, not a no-op."""
    modified, missing, _unchanged, manifest = _classify(repo)
    base = _m._manifest_base(repo)
    custom = sorted(set(_m._managed_files(base)) - set(manifest.get("files", {})))
    return len(modified) + len(missing), len(custom)


def _fleet_update(repos: List[Path], dry_run: bool, assume_yes: bool) -> int:
    if dry_run:
        for repo in repos:
            overwrite, preserve = _plan_update(repo)
            print(f"  {repo.name[:28]:28} would overwrite {overwrite}, preserve {preserve}")
        _m.info(f"Dry run: {len(repos)} project(s) would be updated. Re-run without "
                "--dry-run to apply.")
        return 0

    if not assume_yes:
        print("\n  These projects will be re-installed over (each is backed up first):")
        for repo in repos:
            print(f"    {repo}")
        resp = input(f"Update {len(repos)} project(s)? [y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            _m.info("Aborted.")
            return 0

    failures = 0
    for repo in repos:
        before = _hashes(repo)
        rc = _m.cmd_update(argparse.Namespace(target=str(repo), yes=True))
        after = _hashes(repo)
        written = sum(1 for rel, h in after.items() if before.get(rel) != h)
        preserved = sum(1 for rel, h in after.items()
                        if rel in before and before[rel] == h)
        if rc != 0:
            failures += 1
            _m.err(f"  {repo.name[:28]:28} FAILED (exit {rc})")
            continue
        print(f"  {repo.name[:28]:28} written {written}, preserved {preserved}, "
              f"skipped 0")
        _suggest_commit(repo)
    if failures:
        _m.err(f"{failures} of {len(repos)} project(s) failed to update.")
        return 1
    _m.ok(f"Updated {len(repos)} project(s).")
    return 0


def _fleet_verify(repos: List[Path], kit: Optional[Path]) -> int:
    if kit is None:
        _m.err("Cannot find ClaudeKit source. Set CLAUDEKIT_HOME or run from the repo.")
        return 1
    drifted = 0
    for repo in repos:
        base = _m._manifest_base(repo)
        manifest = _m._load_manifest(repo) or {}
        stale: List[str] = []
        gone: List[str] = []
        local = 0
        for rel, expected in sorted(manifest.get("files", {}).items()):
            kit_path = kit / rel
            if not kit_path.exists():
                continue          # the kit no longer ships it; not this check's business
            path = base / rel
            if not path.exists():
                gone.append(rel)
                continue
            actual = _m._sha256(path)
            if actual != expected:
                local += 1        # locally modified: allowed, the manifest says so
            elif actual != _m._sha256(kit_path):
                stale.append(rel)  # untouched downstream, but not the current kit
        if stale or gone:
            drifted += 1
            _m.err(f"  {repo.name}: {len(stale)} stale, {len(gone)} missing "
                   f"({local} locally modified, allowed)")
            for rel in stale[:15]:
                print(f"      stale:   {rel}")
            for rel in gone[:15]:
                print(f"      missing: {rel}")
        else:
            _m.ok(f"  {repo.name}: byte-identical to source "
                  f"({local} locally modified, allowed)")
    if drifted:
        _m.err(f"{drifted} project(s) drifted from the kit source.")
        return 1
    _m.ok(f"All {len(repos)} project(s) match the kit source.")
    return 0


def cmd_fleet(args: argparse.Namespace) -> int:
    """Survey or update every kitted project under a root."""
    source = _m.find_claudekit_root()
    kit = (source / ".claude") if source is not None else None
    root = _resolve_root(getattr(args, "root", None))
    repos = discover(root, getattr(args, "include", None),
                     getattr(args, "exclude", None), source)
    if not repos:
        _m.warn(f"No kitted projects found under {root} "
                f"(a project counts when it has .claude/{_m.MANIFEST_NAME}).")
        return 0
    action = args.action
    if action == "list":
        return _fleet_list(repos)
    if action == "diff":
        return _fleet_diff(repos, kit)
    if action == "update":
        return _fleet_update(repos, bool(getattr(args, "dry_run", False)),
                             bool(getattr(args, "yes", False)))
    return _fleet_verify(repos, kit)
