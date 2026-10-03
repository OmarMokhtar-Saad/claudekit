#!/usr/bin/env python3
"""Single-owner rule gate: every rule is stated in full in exactly one file.

`.claude/rule-owners.json` maps each duty/rule to ONE owner file, the marker terms that
make a file a statement of that rule, and the extra files allowed to repeat it (generated
mirrors, pointers). This script exits 1 when:

  * the map is unreadable, an id repeats, or a rule lacks owner/markers;
  * the owner file is missing, or lacks a marker (the rule was reworded or moved);
  * a scanned file other than the owner contains ALL of a rule's markers and is not in
    `allowed` (the rule is owned in two places);
  * an `allowed` glob matches no file (stale exemption);
  * two rules with different owners share an identical marker set (two owners, one rule).

Usage:
    python3 scripts/check-rule-owners.py             # exit 1 on any finding
    python3 scripts/check-rule-owners.py --check     # accepted for gate symmetry; ignored
    python3 scripts/check-rule-owners.py --root DIR  # check another tree (used by tests)
    python3 scripts/check-rule-owners.py --json      # findings as JSON

Stdlib only. Markers match case-insensitively on whitespace-collapsed text.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
MAP_REL = Path(".claude") / "rule-owners.json"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _glob(root: Path, patterns) -> set:
    found = set()
    for pat in patterns:
        found.update(p.relative_to(root).as_posix() for p in root.glob(pat) if p.is_file())
    return found


def check(root: Path) -> list:
    """Return a list of finding strings; empty means the map holds."""
    try:
        spec = json.loads((root / MAP_REL).read_text(encoding="utf-8"))
        rules = spec["rules"]
        scan = spec["scan"]
        if not isinstance(rules, list) or not isinstance(scan, list):
            raise TypeError("`rules` and `scan` must be lists")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"{MAP_REL}: unreadable or malformed ({exc})"]

    findings = []
    scanned = _glob(root, scan)
    text = {}
    for rel in scanned:
        try:
            text[rel] = _norm((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

    seen_ids, by_markers = set(), {}
    for rule in rules:
        rid = rule.get("id") if isinstance(rule, dict) else None
        owner = rule.get("owner") if isinstance(rule, dict) else None
        markers = rule.get("markers") if isinstance(rule, dict) else None
        if not rid or not owner or not markers or not isinstance(markers, list):
            findings.append(f"rule {rid or rule!r}: needs id, owner and a non-empty markers list")
            continue
        if rid in seen_ids:
            findings.append(f"rule {rid}: id appears twice")
        seen_ids.add(rid)

        key = tuple(sorted(_norm(m) for m in markers))
        other = by_markers.setdefault(key, (rid, owner))
        if other[0] != rid and other[1] != owner:
            findings.append(f"rule {rid}: same markers as {other[0]} but a different owner "
                            f"({owner} vs {other[1]}): one rule, two owners")

        owner_path = root / owner
        if not owner_path.is_file():
            findings.append(f"rule {rid}: owner file {owner} does not exist")
            continue
        body = text.get(owner)
        if body is None:
            body = _norm(owner_path.read_text(encoding="utf-8", errors="replace"))
        for m in markers:
            if _norm(m) not in body:
                findings.append(f"rule {rid}: owner {owner} lacks marker {m!r} (drift)")

        allowed_globs = rule.get("allowed") or []
        allowed = _glob(root, allowed_globs)
        for pat in allowed_globs:
            if not _glob(root, [pat]):
                findings.append(f"rule {rid}: allowed glob {pat!r} matches no file (stale)")
        for rel, body in sorted(text.items()):
            if rel == owner or rel in allowed:
                continue
            if all(_norm(m) in body for m in markers):
                findings.append(f"rule {rid}: also stated in {rel} (owner is {owner}); "
                                "remove the copy or list it in `allowed`")
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="accepted for gate symmetry; ignored")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    args = ap.parse_args(argv)
    findings = check(Path(args.root))
    if args.json:
        sys.stdout.write(json.dumps({"ok": not findings, "findings": findings}, indent=2) + "\n")
    elif findings:
        sys.stdout.write("FAIL: rule-owner map\n" + "\n".join(f"  - {f}" for f in findings) + "\n")
    else:
        sys.stdout.write("OK: every rule has exactly one owner\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
