#!/usr/bin/env python3
"""repo-hygiene.py — report and (opt-in) reclaim git sprawl. Language-agnostic.

WHY. Measured in a real repo over four days: 36 worktrees under a cap of 5
(25 of them in `/private/tmp/.../scratchpad/` paths whose sessions had ended),
81 branches of which 75 were already merged into the default branch, 910 MB of
checked-out trees against a 218 MB .git, and 3 unpushed commits on the default
branch. Nothing in the toolchain reported any of it, so every new session
oriented itself in the wreckage and added one more branch and one more tree.

`report` is READ-ONLY and always safe. `clean` mutates and therefore:
  * acts only on what `report` listed, re-derived in the same run;
  * requires --yes; without it, it prints what it WOULD do and exits 0;
  * refuses to delete an unmerged branch, a dirty worktree, or the branch or
    worktree you are standing in;
  * is bounded by --max-deletions (default 25) -- a runaway cleanup is worse
    than the sprawl it reclaims.

Exit codes: 0 ok, 1 operational error, 2 refusal/threshold breach (--strict).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

WORKTREE_CAP = 5
MERGED_BRANCH_WARN = 10
DEFAULT_MAX_DELETIONS = 25
PROTECTED_BRANCHES = {"main", "master", "develop", "HEAD"}


def _tempdirs() -> List[str]:
    """Directories whose contents are ephemeral by construction.

    Both the symlinked and resolved spellings: on macOS TMPDIR is under /var,
    which is a symlink to /private/var, and git reports the resolved path while
    the environment hands out the unresolved one.
    """
    seen, out = set(), []
    for d in (tempfile.gettempdir(), "/tmp", "/var/folders", os.environ.get("TMPDIR") or ""):
        if not d:
            continue
        for form in (d, os.path.realpath(d)):
            f = form.rstrip("/")
            if f and f not in seen:
                seen.add(f)
                out.append(f)
    return out


def _under_tempdir(p: Path) -> bool:
    real = os.path.realpath(str(p))
    return any(real == t or real.startswith(t + "/") for t in _tempdirs())


def git(root: Path, args: List[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root)] + args,
        capture_output=True, text=True, timeout=120, check=check,
    )


def repo_root(start: Optional[str] = None) -> Path:
    proc = subprocess.run(
        ["git", "-C", start or os.getcwd(), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print("repo-hygiene: not inside a git repository", file=sys.stderr)
        raise SystemExit(1)
    return Path(proc.stdout.strip())


def default_branch(root: Path) -> str:
    """The branch merges are measured against. origin/HEAD, else a local guess."""
    proc = git(root, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"])
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().rsplit("/", 1)[-1]
    for cand in ("main", "master", "develop"):
        if git(root, ["rev-parse", "--verify", "--quiet", cand]).returncode == 0:
            return cand
    return "HEAD"


def worktrees(root: Path) -> List[Dict[str, str]]:
    """Every worktree git knows about -- the ground truth, not a registry."""
    out = git(root, ["worktree", "list", "--porcelain"]).stdout
    rows: List[Dict[str, str]] = []
    cur: Dict[str, str] = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                rows.append(cur)
            cur = {"path": line[len("worktree "):], "branch": "", "detached": "no"}
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].rsplit("/", 1)[-1]
        elif line.strip() == "detached":
            cur["detached"] = "yes"
    if cur:
        rows.append(cur)
    for row in rows:
        p = Path(row["path"])
        outside = root not in p.parents and p != root
        row["outside_root"] = "yes" if outside else "no"
        # An "outside" worktree is not automatically junk. A deliberate sibling
        # layout (../.ck-main, ../repo-wt/feature) is outside the root and is
        # someone's working tree. What is reclaimable is the EPHEMERAL kind: a
        # worktree under a temp directory, whose parent is deleted when the
        # session that made it ends, leaving git metadata that `git worktree
        # prune` can never reach. Only that class is offered for removal.
        row["ephemeral"] = "yes" if (outside and _under_tempdir(p)) else "no"
        row["exists"] = "yes" if p.is_dir() else "no"
        row["primary"] = "yes" if p == root else "no"
        dirty = git(p, ["status", "--porcelain"]) if p.is_dir() else None
        row["dirty"] = "yes" if (dirty and dirty.stdout.strip()) else "no"
    return rows


def merged_branches(root: Path, base: str) -> List[str]:
    out = git(root, ["branch", "--merged", base, "--format=%(refname:short)"]).stdout
    held = {r["branch"] for r in worktrees(root) if r["branch"]}
    return [b.strip() for b in out.splitlines()
            if b.strip() and b.strip() not in PROTECTED_BRANCHES and b.strip() != base
            and b.strip() not in held]


def unpushed(root: Path, base: str) -> int:
    proc = git(root, ["rev-list", "--count", f"origin/{base}..{base}"])
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def survey(root: Path) -> Dict:
    base = default_branch(root)
    wts = worktrees(root)
    return {
        "root": str(root),
        "default_branch": base,
        "worktrees": wts,
        "worktree_count": len(wts),
        "worktrees_outside_root": [w for w in wts if w["outside_root"] == "yes"],
        "worktrees_ephemeral": [w for w in wts if w["ephemeral"] == "yes"],
        "merged_branches": merged_branches(root, base),
        "branch_total": len([b for b in git(root, ["branch", "--format=%(refname:short)"]).stdout.splitlines() if b.strip()]),
        "unpushed": unpushed(root, base),
    }


def cmd_report(args: argparse.Namespace) -> int:
    root = repo_root(args.repo)
    s = survey(root)
    if args.oneline:
        # The one line session-start prints, and ONLY when something tripped.
        # Silent on a healthy repo: a clean project pays no context for this.
        parts = []
        if s["worktree_count"] > WORKTREE_CAP:
            parts.append(f"{s['worktree_count']} worktrees (cap {WORKTREE_CAP})")
        if len(s["merged_branches"]) > MERGED_BRANCH_WARN:
            parts.append(f"{len(s['merged_branches'])} merged branches undeleted")
        if s["unpushed"] > 0:
            parts.append(f"{s['unpushed']} unpushed on {s['default_branch']}")
        if parts:
            print("  Hygiene: " + "; ".join(parts) + " — /worktree report")
        return 0
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print(f"repo-hygiene: {s['root']}  (default branch: {s['default_branch']})")
        print(f"  worktrees ............ {s['worktree_count']}"
              + ("  <-- OVER CAP" if s["worktree_count"] > WORKTREE_CAP else ""))
        for w in s["worktrees_outside_root"]:
            kind = "STRANDED in a temp dir" if w["ephemeral"] == "yes" else "outside repo root"
            print(f"      {kind}: {w['path']}"
                  + ("  (dirty)" if w["dirty"] == "yes" else ""))
        print(f"  branches ............. {s['branch_total']} "
              f"({len(s['merged_branches'])} merged into {s['default_branch']} and undeleted)"
              + ("  <-- CLEAN UP" if len(s["merged_branches"]) > MERGED_BRANCH_WARN else ""))
        print(f"  unpushed on {s['default_branch']} ..... {s['unpushed']}")
        if s["merged_branches"]:
            print("  reclaimable branches: " + ", ".join(s["merged_branches"][:12])
                  + (" ..." if len(s["merged_branches"]) > 12 else ""))
    tripped = (s["worktree_count"] > WORKTREE_CAP
               or len(s["merged_branches"]) > MERGED_BRANCH_WARN
               or s["unpushed"] > 0)
    return 2 if (args.strict and tripped) else 0


def cmd_clean(args: argparse.Namespace) -> int:
    root = repo_root(args.repo)
    s = survey(root)
    current = git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    # Only the ephemeral class. A sibling worktree outside the root is
    # deliberate infrastructure in some layouts and is never offered here.
    wt_targets = [w for w in s["worktrees_ephemeral"]
                  if w["primary"] == "no" and w["dirty"] == "no"]
    # Merged-ness is measured against the LOCAL base tip. When that base has
    # commits origin has never seen, "merged into main" does not mean "safe to
    # delete": if main is later reset to origin/main (an ordinary recovery),
    # the deleted branch's commits are reachable only via reflog. Review found
    # this; the tool already computes `unpushed`, so it can refuse itself.
    if s["unpushed"] > 0:
        print(f"repo-hygiene: {s['default_branch']} has {s['unpushed']} unpushed commit(s); "
              f"branch deletion is withheld until they are pushed "
              f"(merged-into-local is not merged-into-origin). Worktrees are still reclaimable.",
              file=sys.stderr)
        br_targets = []
    else:
        br_targets = [b for b in s["merged_branches"] if b != current]
    total = len(wt_targets) + len(br_targets)

    if total == 0:
        print("repo-hygiene: nothing to reclaim")
        return 0
    if total > args.max_deletions:
        print(f"repo-hygiene: {total} deletions exceeds --max-deletions "
              f"({args.max_deletions}); raise it deliberately or clean in batches",
              file=sys.stderr)
        return 2

    for w in wt_targets:
        print(f"  worktree remove  {w['path']}")
    for b in br_targets:
        print(f"  branch  delete   {b}")
    if not args.yes:
        print(f"\nrepo-hygiene: DRY RUN -- {total} item(s) above would be removed. "
              "Re-run with --yes to apply.")
        return 0

    failed = 0
    for w in wt_targets:
        if git(root, ["worktree", "remove", w["path"]]).returncode != 0:
            print(f"repo-hygiene: could not remove worktree {w['path']}", file=sys.stderr)
            failed += 1
    git(root, ["worktree", "prune"])
    for b in br_targets:
        # -d (never -D): git itself refuses an unmerged branch. The merged-ness
        # test above is a filter, not the safety property.
        if git(root, ["branch", "-d", b]).returncode != 0:
            print(f"repo-hygiene: could not delete branch {b} (unmerged?)", file=sys.stderr)
            failed += 1
    print(f"repo-hygiene: reclaimed {total - failed}/{total} item(s)")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Report and reclaim git sprawl.")
    ap.add_argument("--repo", help="repository path (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rep = sub.add_parser("report", help="read-only sprawl report")
    p_rep.add_argument("--json", action="store_true")
    p_rep.add_argument("--oneline", action="store_true",
                       help="one line, printed only if a threshold tripped (session-start)")
    p_rep.add_argument("--strict", action="store_true",
                       help="exit 2 when a threshold is tripped (for CI)")
    p_rep.set_defaults(func=cmd_report)

    p_cln = sub.add_parser("clean", help="reclaim merged branches and stray worktrees")
    p_cln.add_argument("--yes", action="store_true", help="apply (without it: dry run)")
    p_cln.add_argument("--max-deletions", type=int, default=DEFAULT_MAX_DELETIONS)
    p_cln.set_defaults(func=cmd_clean)

    args = ap.parse_args()
    try:
        return args.func(args)
    except subprocess.TimeoutExpired:
        print("repo-hygiene: a git command timed out", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
