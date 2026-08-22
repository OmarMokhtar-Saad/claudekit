#!/usr/bin/env python3
"""
check-plan-artifacts.py - Every path an ops config writes must be named in its plan.

The mechanical form of a finding raised in three consecutive review rounds: a plan
whose prose omits the change's largest new artifact reads as complete while the
reviewer keeps rediscovering the omission. A class at three entries earns a check
(.ai/REVIEW_GUIDE.md, the recurrence ratchet).

Usage:
  check-plan-artifacts.py [ops.json ...]     # default: every ops config in .claude/plans
  check-plan-artifacts.py --check [...]      # alias, for symmetry with the other gates

Exit codes:
  0  every target path is named in its plan (or there was nothing to check)
  1  usage / unreadable config, or a plan omits a path its config writes

Zero third-party dependencies; Python 3.9+.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

PLANS_DIR = Path(".claude/plans")


def target_paths(cfg: dict) -> List[str]:
    """Every filesystem path the config writes. run_command has no path and is skipped."""
    items = cfg.get("operations")
    if items is None:
        items = cfg.get("files", [])
    paths = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    return paths


def resolve_plan(ops_path: Path) -> Optional[Path]:
    """Find the plan.md that owns this config, by the slug conventions in use here."""
    name = ops_path.name
    if name.endswith(".ops.json"):
        slug = name[: -len(".ops.json")]
    elif name.startswith("ops-"):
        slug = name[len("ops-") : -len(".json")]
    else:
        slug = name[: -len(".json")]
    slug = slug[len("plan-") :] if slug.startswith("plan-") else slug
    for candidate in (f"plan-{slug}.md", f"{slug}.md"):
        resolved = ops_path.parent / candidate
        if resolved.exists():
            return resolved
    return None


def check(ops_path: Path) -> List[str]:
    """Return the problems found for one config; empty list means it passed."""
    try:
        cfg = json.loads(ops_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{ops_path}: unreadable ({exc})"]
    if not isinstance(cfg, dict):
        return [f"{ops_path}: not a JSON object"]

    plan_path = resolve_plan(ops_path)
    if plan_path is None:
        # No plan is a routing fact, not drift: Tier 1 ships a config with no plan.
        return []

    plan_text = plan_path.read_text(encoding="utf-8")
    # A plan that calls the file `dispatch_resolve.py` has named it; demanding the full
    # repository path would train authors to paste prefixes rather than describe the
    # artifact, and would cry wolf on plans that are in fact complete. The finding this
    # mechanises is the artifact going UNMENTIONED, so the basename is the right token.
    missing = [
        p for p in target_paths(cfg)
        if p not in plan_text and p.rsplit("/", 1)[-1] not in plan_text
    ]
    return [f"{plan_path}: does not name {p} (written by {ops_path.name})" for p in missing]


def main(argv: List[str]) -> int:
    args = [a for a in argv if a != "--check"]
    if args:
        configs = [Path(a) for a in args]
    else:
        configs = sorted(
            set(PLANS_DIR.glob("ops-*.json")) | set(PLANS_DIR.glob("*.ops.json"))
        )
    if not configs:
        print("check-plan-artifacts: no ops configs to check")
        return 0

    problems: List[str] = []
    for ops_path in configs:
        if not ops_path.exists():
            problems.append(f"{ops_path}: no such file")
            continue
        problems.extend(check(ops_path))

    if problems:
        print("PLAN/CONFIG DRIFT - a plan omits a path its config writes:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nFix the plan (name the artifact), not this check: a plan that hides its "
            "largest artifact cannot be reviewed for it.",
            file=sys.stderr,
        )
        return 1

    print(f"check-plan-artifacts: OK ({len(configs)} config(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
