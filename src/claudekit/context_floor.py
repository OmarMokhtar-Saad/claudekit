"""The always-on context floor — one measurement, two callers.

Why this module exists
----------------------
``scripts/check-context-floor.py`` measured the floor for CI, but it is not
shipped into a user's project, so ``ck skill new`` could not consult it. The
options were to duplicate the measurement (a second number that would drift
from the gate's number the first time either changed) or to move the one
measurement into the installable package and let the script call it. This is
that move: the script is now a thin CLI over these functions, so the number CI
gates on and the number a generator refuses on are the same number by
construction, not by agreement.

The budgets and their history live here for the same reason — a budget quoted
in two files is a budget that will be raised in one of them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

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
BUDGETS: Dict[str, int] = {
    "agent descriptions": 10000,
    "skill descriptions": 9000,
    "command descriptions": 6000,
    "CLAUDE.md": 31000,
    "pipeline agent bodies": 43000,
}

CLAUDE_MD_MULTIPLIER = 4  # main context + 3 pipeline subagent injections
PIPELINE_AGENTS = ("planner.md", "reviewer.md", "implementer.md")

#: The category `ck skill new` charges a new skill's description against.
SKILL_CATEGORY = "skill descriptions"


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


def measure(root: Path) -> Dict[str, int]:
    """Chars of always-on context under ``root``.

    Missing sources count zero rather than raising: a user project installed in
    ``--minimal`` mode has no skills directory, and a generator that crashed
    there would be a worse outcome than one that reports a floor of zero for a
    category that genuinely contributes nothing.
    """
    root = Path(root)
    sizes = {k: 0 for k in BUDGETS}
    for f in sorted((root / ".claude" / "agents").glob("*.md")):
        sizes["agent descriptions"] += len(description_span(frontmatter(f.read_text())))
    for f in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        fm = frontmatter(f.read_text())
        if model_invisible(fm):
            continue  # never enters a model's context, so it is not part of the floor
        sizes[SKILL_CATEGORY] += len(description_span(fm))
    for f in sorted((root / ".claude" / "commands").glob("*.md")):
        sizes["command descriptions"] += len(description_span(frontmatter(f.read_text())))
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        sizes["CLAUDE.md"] = len(claude_md.read_text()) * CLAUDE_MD_MULTIPLIER
    for name in PIPELINE_AGENTS:
        agent_file = root / ".claude" / "agents" / name
        if agent_file.exists():
            sizes["pipeline agent bodies"] += len(agent_file.read_text())
    return sizes


def failures(sizes: Dict[str, int]) -> Tuple[str, ...]:
    """Category names that are over budget."""
    return tuple(name for name, size in sizes.items() if size > BUDGETS[name])


def floor_remedy(root: Path) -> str:
    """Name a command the reader actually has.

    In this repo the floor gate is ``scripts/check-context-floor.py``. An
    installed user project does not ship that script, and pointing a refusal at
    a file the reader does not have turns it into a dead end -- so there the
    remedy is ``ck doctor``, which reports the same categories.
    """
    if (Path(root) / "scripts" / "check-context-floor.py").is_file():
        return "python3 scripts/check-context-floor.py"
    return "ck doctor"


def check_new_skill(root: Path, description: str, *,
                    invisible: bool = False) -> Tuple[Optional[str], Tuple[str, ...]]:
    """``(refusal or None, other over-budget categories)``.

    Only an overage in :data:`SKILL_CATEGORY` refuses -- that is the one category
    a new skill charges. Refusing on *any* over-budget category (the first draft)
    meant a project with an oversized CLAUDE.md could not create a skill at all,
    for a reason the skill did not cause; a gate that blocks unrelated work is a
    gate people switch off. The other overages come back as warnings, so they
    are still said out loud while somebody is looking.

    A model-invisible skill costs zero always-on context, so it is admitted
    without charge -- the same rule :func:`measure` already applies. Any other
    skill is charged the exact chars its description will add, and the refusal
    quotes current / added / projected / budget, because "over budget" without
    the numbers tells the author nothing about how much to trim.
    """
    sizes = measure(root)
    current = sizes[SKILL_CATEGORY]
    budget = BUDGETS[SKILL_CATEGORY]
    warnings = tuple(name for name in failures(sizes) if name != SKILL_CATEGORY)
    if current > budget:
        return (
            f"context floor: '{SKILL_CATEGORY}' is already {current} chars of "
            f"{budget} — {current - budget} over, so nothing may be added to it. "
            f"Trim an existing description first: {floor_remedy(root)}"
        ), warnings
    if invisible:
        return None, warnings
    added = len(description)
    projected = current + added
    if projected > budget:
        return (
            f"context floor: '{SKILL_CATEGORY}' is {current} chars of {budget}; this "
            f"description adds {added}, projecting {projected} — {projected - budget} "
            f"over. Shorten the description to at most {budget - current} chars, mark "
            f"the skill --invisible (disable-model-invocation, costs no always-on "
            f"context), or get owner sign-off to raise the budget in "
            f"src/claudekit/context_floor.py."
        ), warnings
    return None, warnings
