"""The skill/command listing must fit the budget Claude Code is configured to give it.

`skillListingBudgetFraction` is the portion of the context window Claude Code spends
presenting skills; past it, it keeps skill NAMES and silently drops descriptions for the
least-used skills. Default 0.01. Primary sources, quotes and the measurement that motivated
raising it: `.claude/reports/research/skill-listing-budget-2026-09-06.md`.

What this gates, stated exactly: the measured `description` + `when_to_use` text of every
skill and command, against `declared fraction x CONTEXT_WINDOW_TOKENS`. It measures the
files directly rather than borrowing `context_floor.BUDGETS`, because those budgets exempt
`disable-model-invocation` skills and exclude `when_to_use` — a different question, gated
separately by `scripts/check-context-floor.py`. This one is a ratchet: the listing may not
grow past what the setting buys.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SETTINGS = REPO / ".claude" / "settings.json"

# ASSUMPTION, not a verified fact: the docs express the setting as a fraction and never in
# tokens, so every absolute token figure here rests on this number.
CONTEXT_WINDOW_TOKENS = 200_000
CHARS_PER_TOKEN = 4            # the usual rough English ratio; also an assumption
DEFAULT_FRACTION = 0.01        # documented Claude Code default
MAX_DESC_CHARS_DEFAULT = 1536  # documented per-skill cap on description + when_to_use
FIELDS = ("description", "when_to_use")


def _settings():
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def _frontmatter(text):
    m = re.match(r"(?s)\A---\n(.*?)\n---\n", text)
    return m.group(1) if m else ""


def _field(fm, name):
    m = re.search(r"(?m)^%s:[ \t]*[\"']?(.*?)[\"']?[ \t]*$" % name, fm)
    if m and m.group(1) not in ("", "|", ">", "|-", ">-"):
        return m.group(1)
    m = re.search(r"(?ms)^%s:[ \t]*[|>]-?\n(.*?)(?=^\S|\Z)" % name, fm)
    return m.group(1) if m else ""


def _listed_files():
    return (sorted((REPO / ".claude" / "skills").glob("*/SKILL.md"))
            + sorted((REPO / ".claude" / "commands").glob("*.md")))


def _listing_chars():
    total = 0
    for path in _listed_files():
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        total += sum(len(_field(fm, name)) for name in FIELDS)
    return total


def test_fraction_is_declared_and_above_the_default():
    fraction = _settings().get("skillListingBudgetFraction")
    assert fraction is not None, (
        "skillListingBudgetFraction is unset, so Claude Code uses 0.01 (2,000 tokens at "
        "the assumed 200k window) and silently drops skill descriptions past it")
    assert fraction > DEFAULT_FRACTION


def test_measured_listing_fits_the_declared_fraction():
    fraction = _settings()["skillListingBudgetFraction"]
    measured_tokens = _listing_chars() / CHARS_PER_TOKEN
    allowed_tokens = fraction * CONTEXT_WINDOW_TOKENS
    assert measured_tokens <= allowed_tokens, (
        f"skill + command description/when_to_use text measures {measured_tokens:.0f} "
        f"tokens but skillListingBudgetFraction={fraction} buys only "
        f"{allowed_tokens:.0f} at the assumed {CONTEXT_WINDOW_TOKENS:,}-token window. "
        "Claude Code will drop descriptions. Trim the descriptions, or raise the "
        "fraction with the measurement recorded in "
        ".claude/reports/research/skill-listing-budget-2026-09-06.md")


def test_no_single_entry_exceeds_the_per_skill_cap():
    cap = _settings().get("skillListingMaxDescChars", MAX_DESC_CHARS_DEFAULT)
    over = []
    for path in _listed_files():
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        size = sum(len(_field(fm, name)) for name in FIELDS)
        if size > cap:
            over.append((path.name, size))
    assert not over, f"description + when_to_use over the {cap}-char cap: {over}"


def test_max_desc_chars_is_declared():
    assert _settings().get("skillListingMaxDescChars"), (
        "skillListingMaxDescChars unset; Claude Code truncates at its 1536 default")
