#!/usr/bin/env python3
"""Derive each plan's lifecycle state from evidence already on disk.

Nothing here is hand-maintained. A plan's state is read off three mechanical
sources, in this precedence order:

  1. a git commit carrying a ``Plan-Id: <slug>`` trailer      -> executed
  2. residence in ``.claude/plans/archive/`` with no such commit -> legacy
  3. ``review-record.py check`` on the plan's ops.json         -> drifted /
     revise / approved  (its typed exit codes are the source of truth: 2 = the
     ops.json changed after approval, 4 = a record exists but its verdict does
     not authorise execution, 0 = APPROVED and matching)
  4. an ops.json exists but there is no record (rc 3)          -> planned
  5. no ops.json anywhere                                      -> not_started

Two honesty constraints are load-bearing:

  * ``drifted`` and ``revise`` are NEVER collapsed into ``approved``. When a plan
    owns several ops configs the WORST verdict wins, because "some part of this
    plan is approved" is not a licence to execute the rest.
  * ``execute-json-ops.py`` writes backups under ``backups/<plan>-<timestamp>/``,
    which is GITIGNORED. A backup manifest is therefore evidence of a *local* run
    only. It is printed as an advisory ``(local run detected)`` line on the
    CONSOLE and is deliberately kept OUT of INDEX.md -- the file would otherwise
    differ between a developer's tree and a fresh CI clone, so ``--check`` would
    red for a reason that has nothing to do with the plans. It can never imply
    ``executed``.

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
REVIEW_RECORD = ROOT / ".claude" / "operations" / "scripts" / "review-record.py"
BACKUPS_DIR = ROOT / "backups"

# `review-record.py check` exit code -> lifecycle state. Anything unexpected
# (usage/IO error, a missing interpreter) resolves to `unknown` rather than to a
# state that reads as progress -- failing closed is the repo's hook convention.
RC_STATE = {0: "approved", 2: "drifted", 3: "planned", 4: "revise"}

# Reported worst-first: the first state present in a plan's evidence set wins.
PRECEDENCE = ("drifted", "revise", "unknown", "planned", "approved")

LOCAL_RUN = "local run detected"

STATE_ORDER = (
    "drifted", "revise", "unknown", "approved", "planned", "executed",
    "not_started", "legacy",
)

HEADER = """# Plan Index

<!-- GENERATED FILE - owned by scripts/gen-plan-index.py; never hand-edit. -->
<!-- Regenerate with: python3 scripts/gen-plan-index.py -->

Every state below is **derived** from evidence on disk -- ops.json presence,
`review-record.py check` verdicts, and `Plan-Id:` git trailers. Nothing here is
hand-maintained, and per CLAUDE.md's evidence-precedence rule this generated
index never outranks the current files.

| State | Means |
|---|---|
| `not_started` | a plan document exists; no ops.json anywhere |
| `planned` | ops.json exists; no review record yet |
| `revise` | a review record exists, but its verdict does not authorise execution |
| `approved` | APPROVED record, and the ops.json still matches the reviewed bytes |
| `drifted` | **the ops.json changed after approval** -- the score does not apply |
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
    return plans


def slug_of(plan: Path) -> str:
    stem = plan.stem
    return stem[5:] if stem.startswith("plan-") else stem


def ops_for(plan: Path) -> List[Path]:
    """Every ops config a plan owns, across all naming conventions in use.

    `resolve_ops()` in review-record.py knows four flat filename forms; this repo
    also stores multi-config plans as an `ops-<slug>/` DIRECTORY, and archives
    both shapes under `archive/`. Missing a form would silently report a planned
    plan as `not_started`, so every form is tried in both directories.
    """
    slug = slug_of(plan)
    stem = plan.stem
    found: List[Path] = []
    for base in (plan.parent, PLANS_DIR, ARCHIVE_DIR):
        if not base.is_dir():
            continue
        for name in (f"{stem}.ops.json", f"ops-{slug}.json",
                     f"{slug}.ops.json", f"{slug}.json"):
            cand = base / name
            if cand.is_file():
                found.append(cand)
        found.extend(p for p in sorted(base.glob(f"ops-{slug}*.json")) if p.is_file())
        for d in sorted(base.glob(f"ops-{slug}*")):
            if d.is_dir():
                found.extend(sorted(d.glob("*.json")))
    uniq: List[Path] = []
    for p in found:
        if p not in uniq:
            uniq.append(p)
    return uniq


def check_state(plan: Path, ops: Path) -> str:
    """State implied by `review-record.py check` for one ops config."""
    if not REVIEW_RECORD.is_file():
        return "unknown"
    try:
        out = subprocess.run(
            [sys.executable, str(REVIEW_RECORD), "check", str(plan), str(ops)],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
    except OSError:
        return "unknown"
    return RC_STATE.get(out.returncode, "unknown")


def local_run(slug: str, ops: List[Path]) -> bool:
    """A gitignored backup manifest whose directory belongs to this plan.

    Advisory ONLY. `backups/` is in .gitignore, so on a fresh clone this is
    always False -- which is exactly why it can never imply `executed`.
    """
    if not BACKUPS_DIR.is_dir():
        return False
    prefixes = [slug + "-"] + [p.stem + "-" for p in ops]
    for d in BACKUPS_DIR.iterdir():
        if not d.is_dir():
            continue
        if any(d.name.startswith(pre) for pre in prefixes):
            if (d / "manifest.json").is_file():
                return True
    return False


def classify(plan: Path, done: set) -> Tuple[str, List[Path], List[str]]:
    slug = slug_of(plan)
    ops = ops_for(plan)
    notes: List[str] = []
    archived = ARCHIVE_DIR in plan.parents

    verdicts = [check_state(plan, o) for o in ops]
    review_state: Optional[str] = None
    for cand in PRECEDENCE:
        if cand in verdicts:
            review_state = cand
            break

    if slug in done:
        state = "executed"
        if review_state in ("drifted", "revise"):
            notes.append(f"executed, but review state is `{review_state}`")
    elif archived:
        state = "legacy"
        if review_state:
            notes.append(f"record says `{review_state}`")
    elif not ops:
        state = "not_started"
    else:
        state = review_state or "unknown"

    if local_run(slug, ops):
        notes.append(LOCAL_RUN)
    return state, ops, notes


def render(rows: List[Tuple[str, str, str, List[Path], List[str]]]) -> str:
    """INDEX.md text. Deliberately excludes the machine-local backups advisory."""
    tally: Dict[str, int] = {}
    for _, _, state, _, _ in rows:
        tally[state] = tally.get(state, 0) + 1

    lines = [HEADER, "## Summary", "", "| State | Plans |", "|---|---:|"]
    for state in STATE_ORDER:
        if state in tally:
            lines.append(f"| `{state}` | {tally[state]} |")
    lines.append(f"| **total** | **{len(rows)}** |")
    lines += ["", "## Plans", "", "| Plan | State | Ops configs | Notes |",
              "|---|---|---:|---|"]
    for rel, _slug, state, ops, notes in rows:
        note = "; ".join(n for n in notes if n != LOCAL_RUN)
        lines.append(f"| `{rel}` | `{state}` | {len(ops)} | {note} |")
    lines.append("")
    return "\n".join(lines)


def build() -> Tuple[str, List[Tuple[str, str, str, List[Path], List[str]]]]:
    done = executed_slugs()
    rows = []
    for plan in plan_files():
        state, ops, notes = classify(plan, done)
        rel = plan.relative_to(ROOT).as_posix()
        rows.append((rel, slug_of(plan), state, ops, notes))
    # Archived plans sort last, then by path: stable output regardless of glob order.
    rows.sort(key=lambda r: ("archive/" in r[0], r[0]))
    return render(rows), rows


def parse_rows(text: str) -> Dict[str, str]:
    """Plan -> state as recorded in an existing INDEX.md, for the drift report."""
    out: Dict[str, str] = {}
    for m in re.finditer(r"^\|\s*`([^`]+)`\s*\|\s*`([a-z_]+)`\s*\|", text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def advise(rows: List[Tuple[str, str, str, List[Path], List[str]]]) -> None:
    """Console-only notes. Nothing here reaches INDEX.md."""
    for rel, _slug, state, _ops, notes in rows:
        if state in ("drifted", "unknown"):
            print(f"WARNING: {rel} is {state.upper()}", file=sys.stderr)
    local = [r[0] for r in rows if LOCAL_RUN in r[4]]
    if local:
        print(f"NOTE: {len(local)} plan(s) have a gitignored backups/ manifest "
              "(local run detected) - advisory only, never proof of execution.")


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
            now = {r[0]: r[2] for r in rows}
            for rel in sorted(set(was) | set(now)):
                before, after = was.get(rel, "-"), now.get(rel, "-")
                if before != after:
                    print(f"  {rel}: says {before}, should be {after}", file=sys.stderr)
            rc = 1
        advise(rows)
        return rc

    if new_text != old_text:
        INDEX_PATH.write_text(new_text, encoding="utf-8")
        print(f"Updated .claude/plans/INDEX.md ({len(rows)} plans).")
    else:
        print(f".claude/plans/INDEX.md already current ({len(rows)} plans).")
    advise(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
