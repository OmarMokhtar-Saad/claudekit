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
import re
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


def names_path(plan_text: str, path: str) -> bool:
    """True when `plan_text` names `path`, by full path or by basename as a whole token.

    A plan that calls the file `dispatch_resolve.py` has named it; demanding the full
    repository path would train authors to paste prefixes rather than describe the
    artifact, and would cry wolf on plans that are in fact complete. The finding this
    mechanises is the artifact going UNMENTIONED, so the basename is the right token.

    WHOLE token, not a substring, on BOTH branches: plain `in` let a token match inside
    a longer path or filename, so `tests/test_mcp_probe.py` satisfied `mcp_probe.py`, and
    `templates/scripts/gen-docs.py` satisfied `scripts/gen-docs.py` -- a plan naming a
    DIFFERENT file passed. A preceding word character, `.`, `-` or `/` disqualifies.
    """
    for token in (path, path.rsplit("/", 1)[-1]):
        # BOTH branches are guarded. Tightening only the basename was the first attempt
        # and it was worse than no fix: `scripts/gen-docs.py` was satisfied by a plan
        # naming `templates/scripts/gen-docs.py` -- a DIFFERENT file -- while the
        # accompanying test certified the class as closed. A trailing `.` is excluded
        # too, so `main.py.tmpl` does not name `main.py`.
        # The trailing `.` exclusion is CONDITIONAL. Excluding every following `.`
        # rejected ordinary sentence-final prose -- "the change edits
        # scripts/gen-docs.py." stopped naming the file -- and 12 of the 67 plan
        # documents already write artifact names that way, so the gate would have
        # reddened CI on correct plans. A gate that cries wolf is a gate the next author
        # routes around, which costs more than the hole it closes. So: a `.` disqualifies
        # only when a filename character follows it (`main.py.tmpl`), not when the
        # sentence simply ends.
        if re.search(r"(?<![\w./-])%s(?![\w-])(?!\.[A-Za-z0-9])" % re.escape(token),
                     plan_text):
            return True
    return False


def resolve_plan(ops_path: Path, cfg: Optional[dict] = None) -> Optional[Path]:
    """Find the plan.md that owns this config, by the slug conventions in use here.

    The config's own `plan` field is consulted as well as its filename, because the
    executor resolves candidates that way too (`execute-json-ops.py:_approval_slugs`
    reads the ops filename first, then the `plan` field). Filename-only resolution
    left every config whose declared plan differs from its filename UNCHECKED while
    reporting OK: `ops-mcp-probe.json` declares `"plan": "mcp-probe-addendum"`, so
    both of its operations were invisible here. Returning None is still a PASS -- a
    config with no plan is a Tier 1 routing fact, not drift.
    """
    name = ops_path.name
    if name.endswith(".ops.json"):
        slug = name[: -len(".ops.json")]
    elif name.startswith("ops-"):
        slug = name[len("ops-") : -len(".json")]
    else:
        slug = name[: -len(".json")]
    slug = slug[len("plan-") :] if slug.startswith("plan-") else slug
    # The declared value is a SLUG, never a path fragment: it is joined to
    # `ops_path.parent`, so `"../x"` escaped .claude/plans and an absolute value
    # discarded the parent entirely -- letting an author point this gate at any file
    # that happens to mention their paths and get a green run with nothing checked.
    declared = (cfg or {}).get("plan") or ""
    if declared and (Path(declared).name != declared
                     or not re.fullmatch(r"[A-Za-z0-9._-]+", declared)):
        declared = ""
    # Same normalisation the executor applies: `execute-json-ops.py:_approval_slugs`
    # strips BOTH prefixes. Stripping only the filename-derived slug left a config
    # declaring `"plan": "ops-foo"` resolving to nothing, and passing with every
    # operation unchecked -- one step short of the hole this resolution closes.
    for prefix in ("plan-", "ops-"):
        if declared.startswith(prefix):
            declared = declared[len(prefix):]
    slugs = [slug] + ([declared] if declared and declared != slug else [])
    for candidate_slug in slugs:
        for candidate in (f"plan-{candidate_slug}.md", f"{candidate_slug}.md"):
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

    plan_path = resolve_plan(ops_path, cfg)
    if plan_path is None:
        # No plan is a routing fact, not drift: Tier 1 ships a config with no plan.
        return []

    if not (cfg.get("operations") or cfg.get("files")):
        # A config that reaches here carries a plan, so it is a reviewed change; an
        # absent, empty or RENAMED operations key would otherwise satisfy this check by
        # iterating nothing, which is the vacuous-gate shape this repo has shipped twice.
        return [f"{ops_path}: declares a plan but no operations - an empty or renamed "
                f"key would pass this check by writing nothing"]

    # A writing op with no `path` is a skip, not a pass. The schema validator rejects
    # a renamed key upstream, but this gate also runs standalone in CI, where nothing
    # else would notice.
    writing = [o for o in (cfg.get("operations") or cfg.get("files") or [])
               if isinstance(o, dict) and o.get("type") in ("file_create", "code_edit")]
    pathless = sorted({o.get("type") for o in writing if not o.get("path")})
    if pathless:
        return [f"{ops_path}: writing operation(s) carry no path "
                f"({', '.join(pathless)}) - nothing to check them against"]

    plan_text = plan_path.read_text(encoding="utf-8")
    missing = [p for p in target_paths(cfg) if not names_path(plan_text, p)]
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
