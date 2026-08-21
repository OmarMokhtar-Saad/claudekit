#!/usr/bin/env python3
"""Always-on context floor gate.

Measures the text that is injected into EVERY session's context window before
any work happens: agent frontmatter descriptions, skill descriptions, command
descriptions, and CLAUDE.md. Fails --check when the floor exceeds budget, the
same drift-gate pattern as gen-docs.py --check.

Usage:
    python3 scripts/check-context-floor.py            # print the floor table
    python3 scripts/check-context-floor.py --check    # exit 1 if over budget    python3 scripts/check-context-floor.py --json     # print JSON instead of the table

Budgets are chars (tokens ~ chars/4). Raise a budget only with owner sign-off —
the point of this gate is that the floor never silently grows back.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Budgets set 2026-08-17 after the example-block strip (measured + ~10% headroom).
# "skill descriptions" re-baselined 2026-08-21 (14000 -> 9000) when the category
# stopped charging for model-invisible skills. This is a TIGHTENING, not a raise:
# the old number gated a measurement that counted 3.9k chars of descriptions no
# model can see. Real value at re-baseline was 7811 of 9000.
# "pipeline agent bodies" is the per-spawn floor: the FULL text of the three
# pipeline agents, loaded on every plan->review->implement run. Added after
# review evidence showed this floor grew 4% with nothing failing while only
# the always-on categories were gated.
#
# "CLAUDE.md" is DELIVERY-WEIGHTED (chars x CLAUDE_MD_MULTIPLIER): the file is
# injected into the main context AND re-injected into each of the 3 pipeline
# subagent spawns, so one char there costs ~4x what a char in a single agent
# body costs. The gate measures delivered cost, not file size — otherwise
# moving content out of CLAUDE.md into a consuming agent (a real token win)
# would look like a regression in the tighter category.
BUDGETS = {
    "agent descriptions": 10000,
    "skill descriptions": 9000,
    "command descriptions": 6000,
    "CLAUDE.md": 31000,
    "pipeline agent bodies": 43000,
}

CLAUDE_MD_MULTIPLIER = 4  # main context + 3 pipeline subagent injections
PIPELINE_AGENTS = ("planner.md", "reviewer.md", "implementer.md")


def frontmatter(text: str) -> str:
    m = re.match(r"(?s)\A---\n(.*?)\n---\n", text)
    return m.group(1) if m else ""


def model_invisible(fm: str) -> bool:
    """True if the model never sees this skill listed.

    `disable-model-invocation: true` keeps a skill out of the Skill tool's
    listing entirely, so its description costs zero always-on context. Charging
    for it inflated this floor by ~3.9k chars against skills no model can read -
    and an inflated floor is not a conservative one, it is a wrong one: it hides
    real headroom while gating on noise.
    """
    return bool(re.search(r"(?m)^disable-model-invocation:[ \t]*true[ \t]*$", fm))


def description_span(fm: str) -> str:
    """Extract the description value: quoted single-line or block scalar."""
    m = re.search(r'(?m)^description:[ \t]*["\']?(.*?)["\']?[ \t]*$', fm)
    if m and m.group(1) not in ("", "|", ">", "|-", ">-"):
        return m.group(1)
    # block scalar: indented lines until the next top-level key
    m = re.search(r"(?ms)^description:[ \t]*[|>]-?\n(.*?)(?=^\S|\Z)", fm)
    return m.group(1) if m else ""


def measure() -> "dict[str, int]":
    sizes = {k: 0 for k in BUDGETS}
    for f in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        sizes["agent descriptions"] += len(description_span(frontmatter(f.read_text())))
    for f in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        fm = frontmatter(f.read_text())
        if model_invisible(fm):
            continue  # never enters a model's context, so it is not part of the floor
        sizes["skill descriptions"] += len(description_span(fm))
    for f in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        sizes["command descriptions"] += len(description_span(frontmatter(f.read_text())))
    sizes["CLAUDE.md"] = len((ROOT / "CLAUDE.md").read_text()) * CLAUDE_MD_MULTIPLIER
    for name in PIPELINE_AGENTS:
        agent_file = ROOT / ".claude" / "agents" / name
        if agent_file.exists():
            sizes["pipeline agent bodies"] += len(agent_file.read_text())
    return sizes


def main() -> int:
    args = sys.argv[1:]
    check = "--check" in args
    sizes = measure()
    total = sum(sizes.values())
    budget_total = sum(BUDGETS.values())

    if "--json" in args:
        ok = all(size <= BUDGETS[name] for name, size in sizes.items())
        payload = {"sizes": sizes, "budgets": BUDGETS, "total": total, "ok": ok}
        print(json.dumps(payload, indent=2))
        return 1 if (check and not ok) else 0

    print("Always-on context floor (chars; tokens ~ chars/4)")
    print(f"{'source':<24}{'chars':>8}{'budget':>8}  status")
    failures = []
    for name, size in sizes.items():
        budget = BUDGETS[name]
        ok = size <= budget
        if not ok:
            failures.append(name)
        print(f"{name:<24}{size:>8}{budget:>8}  {'OK' if ok else 'OVER'}")
    print(f"{'TOTAL':<24}{total:>8}{budget_total:>8}  (~{total // 4} tokens)")

    if failures:
        print(
            f"\nFAIL: context floor over budget: {', '.join(failures)}.\n"
            "Trim descriptions (no <example> blocks in frontmatter) or get owner\n"
            "sign-off to raise the budget in scripts/check-context-floor.py.",
            file=sys.stderr,
        )
        return 1 if check else 0
    print("\nOK: context floor within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
