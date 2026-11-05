#!/usr/bin/env python3
"""Derive each plan's lifecycle state from evidence committed to the repo.

Nothing here is hand-maintained. A plan's state is read off two mechanical sources,
in this precedence order:

  1. a git commit carrying a ``Plan-Id: <slug>`` trailer         -> executed
  2. residence in ``.claude/plans/archive/`` with no such commit -> legacy
  3. anything else                                               -> open

Approval records (``review-record.py plan-check``) are local and gitignored, so they
are deliberately NOT an input: the index is a committed, CI-gated file and must derive
the same text in a developer's tree and a fresh clone. ``plan-check`` is the live gate.

``legacy`` is deliberate for the pre-convention plans: inventing a state for them
would put a generated index above the current files, which CLAUDE.md's
evidence-precedence rule forbids.

Usage:
    python3 scripts/gen-plan-index.py            # rewrite .claude/plans/INDEX.md
    python3 scripts/gen-plan-index.py --check     # exit 1 if INDEX.md is stale
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = ROOT / ".claude" / "plans"
ARCHIVE_DIR = PLANS_DIR / "archive"
INDEX_PATH = PLANS_DIR / "INDEX.md"

# Sentinel distinguishing "not looked up yet" from "looked up, no git here".
_TRACKED: Optional[frozenset] = None
_TRACKED_LOOKED_UP = False


def tracked_paths() -> Optional[frozenset]:
    """Absolute paths git tracks, or ``None`` where there is no git to ask.

    INDEX.md is a COMMITTED artifact gated in CI, so it has to derive from what
    the repo contains -- not from what happens to be sitting in someone's
    working tree. Globbing the filesystem counted an untracked scratch
    untracked scratch plan another session had left behind, so the committed
    index was shaped by a file that is not in the repo.

    `--cached` is the right question, not `ls-tree HEAD`: it is the set that
    will be in the next commit, which is what CI checks out. Asking HEAD would
    make the commit that ADDS a plan unable to describe it.

    Fails OPEN. An installed user project is often not a git repo at all, and a
    plan index that empties itself there would be worse than one that counts a
    scratch file. `None` means "do not filter".
    """
    global _TRACKED, _TRACKED_LOOKED_UP
    if _TRACKED_LOOKED_UP:
        return _TRACKED
    _TRACKED_LOOKED_UP = True
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "-z"],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return _TRACKED  # None
    if out.returncode != 0:
        return _TRACKED  # None -- not a repo, or git unavailable
    names = out.stdout.decode("utf-8", "surrogateescape").split("\0")
    _TRACKED = frozenset(str(ROOT / n) for n in names if n)
    return _TRACKED


def is_tracked(path: Path) -> bool:
    """True where git tracks ``path``, or where there is no git to ask."""
    tracked = tracked_paths()
    return tracked is None or str(path) in tracked


def filtering_engaged(plans: List[Path]) -> bool:
    """Whether to drop untracked plans -- only when git tracks plans AT ALL.

    Filtering unconditionally would empty the index in two legitimate places:
    a repo whose `.claude/` is gitignored, and any fresh `git init` where
    nothing has been added yet (every fixture in tests/test_plan_index.py).
    Both would silently report every plan as missing, which is a far worse
    failure than counting one scratch file.

    So the filter engages only where it has evidence to work with: at least one
    plan is tracked, meaning this repo does version its plans, and an untracked
    one beside them is genuinely a stray rather than the norm.
    """
    if tracked_paths() is None:
        return False
    return any(is_tracked(p) for p in plans)

STATE_ORDER = ("open", "executed", "legacy")

HEADER = """# Plan Index

<!-- GENERATED FILE - owned by scripts/gen-plan-index.py; never hand-edit. -->
<!-- Regenerate with: python3 scripts/gen-plan-index.py -->

Every state below is **derived** from evidence committed to the repo -- `Plan-Id:`
git trailers and the archive folder. Nothing here is hand-maintained, and per
CLAUDE.md's evidence-precedence rule this generated index never outranks the
current files. Approval is local: ask `review-record.py plan-check <plan>`.

| State | Means |
|---|---|
| `open` | a plan document exists with no `Plan-Id:` commit yet |
| `executed` | a commit carries a `Plan-Id: <slug>` trailer |
| `legacy` | archived with no `Plan-Id:` commit -- pre-convention, state unknowable |
"""

_TRAILER_RE = re.compile(r"^\s*Plan-Id:\s*(\S+)\s*$", re.M)


def executed_slugs() -> set:
    """Slugs named by a ``Plan-Id:`` trailer anywhere in history.

    ONE git invocation, parsed in process. One subprocess per plan would be ~79
    process spawns for a fact a single log already carries.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--format=%B"],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
    except OSError:
        return set()
    if out.returncode != 0:
        return set()
    return {m.strip() for m in _TRAILER_RE.findall(out.stdout)}


def plan_files() -> List[Path]:
    plans = sorted(PLANS_DIR.glob("plan-*.md"))
    plans += sorted(ARCHIVE_DIR.glob("plan-*.md"))
    # An untracked draft is not part of the
    # repo, so it does not get a row in a committed, CI-gated index.
    if not filtering_engaged(plans):
        return plans
    return [p for p in plans if is_tracked(p)]


def slug_of(plan: Path) -> str:
    stem = plan.stem
    return stem[5:] if stem.startswith("plan-") else stem


def classify(plan: Path, done: set) -> str:
    if slug_of(plan) in done:
        return "executed"
    return "legacy" if ARCHIVE_DIR in plan.parents else "open"


def render(rows: List[Tuple[str, str]]) -> str:
    """INDEX.md text from (plan path, state) rows."""
    tally: Dict[str, int] = {}
    for _, state in rows:
        tally[state] = tally.get(state, 0) + 1

    lines = [HEADER, "## Summary", "", "| State | Plans |", "|---|---:|"]
    for state in STATE_ORDER:
        if state in tally:
            lines.append(f"| `{state}` | {tally[state]} |")
    lines.append(f"| **total** | **{len(rows)}** |")
    lines += ["", "## Plans", "", "| Plan | State |", "|---|---|"]
    for rel, state in rows:
        lines.append(f"| `{rel}` | `{state}` |")
    lines.append("")
    return "\n".join(lines)


def build() -> Tuple[str, List[Tuple[str, str]]]:
    done = executed_slugs()
    rows = [(plan.relative_to(ROOT).as_posix(), classify(plan, done)) for plan in plan_files()]
    # Archived plans sort last, then by path: stable output regardless of glob order.
    rows.sort(key=lambda r: ("archive/" in r[0], r[0]))
    return render(rows), rows


def parse_rows(text: str) -> Dict[str, str]:
    """Plan -> state as recorded in an existing INDEX.md, for the drift report."""
    out: Dict[str, str] = {}
    for m in re.finditer(r"^\|\s*`([^`]+)`\s*\|\s*`([a-z_]+)`\s*\|", text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv

    new_text, rows = build()
    old_text = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""

    if check:
        if new_text == old_text:
            print(f"OK: .claude/plans/INDEX.md is current ({len(rows)} plans).")
            rc = 0
        else:
            print("ERROR: .claude/plans/INDEX.md is out of date. "
                  "Run: python3 scripts/gen-plan-index.py", file=sys.stderr)
            was = parse_rows(old_text)
            now = dict(rows)
            for rel in sorted(set(was) | set(now)):
                before, after = was.get(rel, "-"), now.get(rel, "-")
                if before != after:
                    print(f"  {rel}: says {before}, should be {after}", file=sys.stderr)
            rc = 1
        return rc

    if new_text != old_text:
        INDEX_PATH.write_text(new_text, encoding="utf-8")
        print(f"Updated .claude/plans/INDEX.md ({len(rows)} plans).")
    else:
        print(f".claude/plans/INDEX.md already current ({len(rows)} plans).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
