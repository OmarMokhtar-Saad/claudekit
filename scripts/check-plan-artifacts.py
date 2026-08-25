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
    return _names_by_pattern(plan_text, path)


def _names_by_pattern(plan_text: str, path: str) -> bool:
    """True when the plan describes `path` with a GLOB or `<placeholder>` covering it.

    A plan that writes 15 files under one convention names them honestly as
    `.claude/skills/<name>/SKILL.md`, or 4 as `evals/definitions/*.json` -- both stated
    with their count in the ops table. Demanding 15 literal paths rejects a complete,
    reviewable description and trains authors to paste enumerations, which is the
    cry-wolf failure this gate's own comments warn about. Measured when the gate first
    reached the archive: of 23 findings, 19 were this false positive and 4 were real.

    `*` matches WITHIN one path segment only, and the match is anchored. Both matter,
    and the first version of this function got both wrong by using `fnmatch`, whose `*`
    crosses `/`: `.claude/skills/*` then named `.claude/skills/x/../../../etc/passwd`
    and `src/*` named `src/a/b/c/evil.py`. A token that STARTS or ENDS with `*` is
    rejected outright -- that is markdown emphasis, not a path pattern, and treating
    `**scripts/gen-docs.py**` as a glob reopened the closed class `names_path` documents
    above (a plan naming `templates/scripts/gen-docs.py` satisfying `scripts/gen-docs.py`
    -- a DIFFERENT file). 38 of 76 plan documents contain emphasis-shaped tokens.
    """
    for token in re.findall(r"[\w./<>*-]*[<*][\w./<>*-]*", plan_text):
        if "/" not in token or token.startswith("*") or token.endswith("*"):
            continue
        pattern = re.sub(r"<[^<>/]*>", "*", token)
        if "*" not in pattern:
            continue
        rx = "".join("[^/]*" if ch == "*" else re.escape(ch) for ch in pattern)
        if re.fullmatch(rx, path):
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
    # A HYPHEN-BOUNDARY PREFIX WALK, longest first. One plan is routinely executed
    # through several configs named after their STEP -- `ops-triage-refresh-records.json`
    # against `plan-triage-refresh.md` -- and every one of those resolved to nothing and
    # was skipped SILENTLY. Measured: 51 configs, six of them written by the author of
    # this comment, whose operations no gate had ever checked.
    #
    # Bounded, not loose: each candidate must match an existing `plan-<slug>.md` EXACTLY
    # at a hyphen boundary, and the longest prefix wins, so `plan-foo-bar.md` beats
    # `plan-foo.md` for `ops-foo-bar-step`. `ops-dispatcher-payload.json`'s L1 lesson was
    # about a matcher that stripped one prefix and silently matched nothing; this one can
    # only ever match a plan file that is really there.
    def _prefix_walk(base: str):
        parts = base.split("-")
        for length in range(len(parts) - 1, 0, -1):
            yield "-".join(parts[:length])

    slugs = [slug] + ([declared] if declared and declared != slug else [])
    for base in list(slugs):
        for shorter in _prefix_walk(base):
            if shorter not in slugs:
                slugs.append(shorter)
    for candidate_slug in slugs:
        for candidate in (f"plan-{candidate_slug}.md", f"{candidate_slug}.md"):
            # PLANS_DIR as well as the config's own directory: an EXECUTED config is
            # moved to .claude/plans/archive/ and its plan is NOT -- the plans stay at
            # .claude/plans/. Resolving only against `ops_path.parent` meant the archive
            # held 92 configs and 0 resolvable plans, so widening the scan to reach them
            # verified 15 paths instead of 354. Sibling first, so a config that ships
            # beside its own plan still binds to that one.
            for parent in (ops_path.parent, PLANS_DIR):
                resolved = parent / candidate
                if resolved.exists():
                    return resolved
    return None


def _read(ops_path: Path) -> Optional[dict]:
    """The config as a dict, or None when unreadable or not a JSON object. `check` still
    owns the error MESSAGE for those cases; the caller only needs to know it cannot
    resolve a plan or count paths from them."""
    try:
        cfg = json.loads(ops_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def check(ops_path: Path, cfg: Optional[dict] = None) -> List[str]:
    """Return the problems found for one config; empty list means it passed.

    `cfg` is the already-parsed config when the caller has one (it needs it to count
    paths), so the file is read once rather than three times per config. Passing None
    keeps the standalone contract: this function still owns every error message for a
    config it cannot read.
    """
    if cfg is None:
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
        # rglob, not glob: an EXECUTED config is moved to .claude/plans/archive/, so a
        # top-level-only scan printed `no ops configs to check`, rc 0, on any branch
        # whose configs had all run -- including the CI run that gates the merge.
        configs = sorted(
            set(PLANS_DIR.rglob("ops-*.json")) | set(PLANS_DIR.rglob("*.ops.json"))
        )
    if not configs:
        print("check-plan-artifacts: no ops configs to check")
        return 0

    problems: List[str] = []
    checked_paths = 0
    unresolved: List[str] = []
    for ops_path in configs:
        if not ops_path.exists():
            problems.append(f"{ops_path}: no such file")
            continue
        cfg = _read(ops_path)
        if cfg is None:
            problems.extend(check(ops_path))
            continue
        if resolve_plan(ops_path, cfg) is None:
            # Still a PASS -- Tier 1 legitimately ships a config with no plan. But it
            # must not be INDISTINGUISHABLE from a real check: a plan renamed by
            # accident left every operation unchecked under the same OK line.
            unresolved.append(ops_path.name)
        else:
            checked_paths += len(target_paths(cfg))
        problems.extend(check(ops_path, cfg))

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

    # The PATH count is the honest signal and the number to watch. The run that first
    # reached the archive reported 92 configs and would have reported 0 paths: a config
    # count alone cannot tell a real pass from a gate that checked nothing.
    print(f"check-plan-artifacts: OK ({len(configs)} config(s), "
          f"{checked_paths} path(s) verified)")
    # TWO NUMBERS, NOT ONE. This printed a single "resolved to no plan" count that grew
    # from 87 to 121 while being read as one fact, and it conflates two unrelated things:
    #
    #   * a config whose plan document does NOT EXIST -- 205 of them, spent long ago,
    #     several predating the convention that a plan is written at all. No code can
    #     resolve those, and reporting them as "skipped" makes an unfixable historical
    #     residue look like a growing bug.
    #   * a config whose plan document DOES exist but whose declared slug did not
    #     resolve. That is a real gate hole: operations nobody checked, in a plan that
    #     could have been checked. After the prefix walk above this should be ZERO, so it
    #     is reported separately and loudly.
    #
    # The second number is the one to watch. Making it fatal is a separate, owner-gated
    # decision -- 205 legacy configs must not redden CI for history nobody can change.
    if unresolved:
        orphan, misdeclared = [], []
        known = {p.stem[len("plan-"):] for p in PLANS_DIR.glob("plan-*.md")}
        for name in sorted(unresolved):
            stem = name[: -len(".json")] if name.endswith(".json") else name
            for prefix in ("plan-", "ops-"):
                if stem.startswith(prefix):
                    stem = stem[len(prefix):]
            parts = stem.split("-")
            reachable = any("-".join(parts[:i]) in known
                            for i in range(len(parts), 0, -1))
            (misdeclared if reachable else orphan).append(name)
        if orphan:
            # NAMED, not just counted. `test_a_config_that_resolves_to_no_plan_is_named_
            # not_silently_green` exists because a plan renamed by accident left every
            # operation unchecked and read identically to a real pass -- so a bare count
            # here reintroduced exactly that. Truncated at 12 with the remainder counted:
            # 112 names is not a diagnostic either.
            shown = ", ".join(orphan[:12])
            more = f" (+{len(orphan) - 12} more)" if len(orphan) > 12 else ""
            print(f"NOTE: {len(orphan)} config(s) have no plan document at all "
                  f"(historical; no resolution is possible) and were not checked: "
                  f"{shown}{more}")
        if misdeclared:
            print(f"WARNING: {len(misdeclared)} config(s) name a plan that EXISTS but "
                  f"did not resolve -- these are unchecked operations in a checkable "
                  f"plan: {', '.join(misdeclared)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
