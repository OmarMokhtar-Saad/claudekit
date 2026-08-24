"""Corpus lint rules for the prompt assets themselves.

The DoD gates every *derived* artifact -- counts, the registry, the model policy, the
context floor -- but nothing gated the prose. Task 008 batch 4 adds the three rules the
spec named, and the shape of each is chosen so a clean run means something:

* `command-budget` is a RATCHET, not a cliff. The spec's target was <=40 lines for every
  command. Measured on 2026-08-24: 0 of 55 commands met it, min 47, median 129, max 466,
  and 5138 of 7338 lines would have to be rewritten to comply. A gate the corpus cannot
  satisfy is a gate someone turns off, so the target binds NEW commands and forbids
  existing ones from growing past a recorded baseline. Every command that shrinks
  tightens its own baseline automatically.
* `duplicate-triggers` flags nothing because the corpus is genuinely clean -- batch 2
  merged five names away to reach that state. It is a regression guard.
* `skill-agent-costume` is silent for a DIFFERENT reason, and the distinction matters:
  two skills really do grant `Agent` (`gan-harness`, `opensource-pipeline`) and are
  waived by name in the baseline. Silent-by-waiver is not the same as clean, and an
  earlier draft of this docstring conflated them -- the third place the same false
  claim had to be corrected, after `lint.py`'s own text and the plan. Class:
  `claim-not-corrected-everywhere-it-was-made`.
* Both are mutation-proven in `tests/test_lint.py`, because a rule whose passing state
  is indistinguishable from a rule that does not run is worthless.

Stdlib only, py3.9-compatible (CLAUDE.md hard rule 8).
"""

import json
import os
import re
from itertools import combinations

#: A command added after the ratchet was recorded must fit the spec's target.
NEW_COMMAND_BUDGET = 40

#: Jaccard overlap on description keywords above which two skills are competing to
#: answer the same prompt. 0.5 is deliberately loose, and the number is EXECUTED rather
#: than estimated: measured 2026-08-24 across all 71 skills with a description, the
#: closest pairs are a FOUR-WAY TIE at **0.1538** (`receiving-code-review` <->
#: `requesting-code-review` among them), and zero pairs reach 0.25. So 0.5 flags a genuine collision rather than
#: family resemblance, with roughly 3x headroom above the closest legitimate pair.
#: Re-derive with:
#:   python3 -c "from claudekit import lint; import itertools, os; \
#:     d={p: lint._keywords(lint._field(lint._read(p), lint._DESC_RE)) \
#:        for p in lint.skill_files('.')}; \
#:     print(max(len(d[a]&d[b])/len(d[a]|d[b]) \
#:       for a,b in itertools.combinations(d,2) if d[a] and d[b]))"
TRIGGER_OVERLAP = 0.5

BASELINE_NAME = "lint-baseline.json"

_STOPWORDS = frozenset("""
a an and are as at any be before after by can for from has have in into is it its of on
or that the this to use used uses using when with within without you your need needs
""".split())

_DESC_RE = re.compile(r'(?m)^description:[ \t]*["\']?(.*?)["\']?[ \t]*$')

#: `allowed-tools` appears in TWO forms in this corpus, and reading only the first is a
#: false negative that review caught: `gan-harness` and `opensource-pipeline` both
#: declare it as a YAML block list containing `Agent`, so a same-line-only regex
#: captured "" for each and the rule skipped the exact grant it exists to find.
_ALLOWED_TOOLS_INLINE_RE = re.compile(r'(?m)^allowed-tools:[ \t]*(\S.*?)[ \t]*$')
_ALLOWED_TOOLS_BLOCK_RE = re.compile(
    r'(?m)^allowed-tools:[ \t]*(?:#[^\n]*)?\n((?:[ \t]*-[ \t]*[^\n]+\n?)+)')


class Finding:
    """One rule violation. `rule` is the stable identifier a waiver would name."""

    __slots__ = ("rule", "path", "message")

    def __init__(self, rule, path, message):
        self.rule = rule
        self.path = path
        self.message = message

    def __str__(self):
        return "[%s] %s: %s" % (self.rule, self.path, self.message)


def _frontmatter(text):
    """The frontmatter block, or "" when the file has none.

    Split on the closing fence rather than reading a fixed number of lines: a skill
    with a long `description:` pushes `allowed-tools:` past any line cap, and a rule
    that stops reading early is a rule that can be evaded by adding prose.
    """
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    return text[4:end] if end != -1 else text


def _field(text, regex):
    match = regex.search(_frontmatter(text))
    return match.group(1).strip() if match else ""


def _normalise_tool(raw):
    """One tool name, stripped of the YAML punctuation it may arrive wrapped in.

    Written after probing the parser rather than reasoning about it: an inline flow
    list (`[Agent, Read]`), a quoted value (`"Read, Agent"`), a quoted block item
    (`- "Agent"`) and a trailing `# comment` each produced a token like `[Agent` or
    `Agent"` or `Agent # why`, none of which equalled "Agent" -- four silent evasions
    of a rule whose entire job is not being evaded.
    """
    name = raw.split("#", 1)[0]
    return name.strip().strip("[]").strip().strip("\"'").strip()


#: Valid-YAML forms `declared_tools` does NOT read, verified absent from the corpus
#: (0 occurrences each) rather than assumed away: a flow list split across lines, a
#: CRLF block list, a blank line before the first block item, a duplicate
#: `allowed-tools` key (this reads the first, YAML takes the last), and a scoped grant
#: like `Agent(*)`. Listed so the next reader knows the boundary is a measured choice,
#: not an oversight. A skill author determined to hold `Agent` can also just take a
#: waiver, so hardening further buys little.
_KNOWN_UNPARSED_FORMS = (
    "multiline flow list", "CRLF block list", "blank line before first item",
    "duplicate allowed-tools key", "scoped grant such as Agent(*)",
)


def declared_tools(text):
    """Every tool named by `allowed-tools`, in either YAML form.

    Returns a set. Both forms are read because the corpus uses both -- see the regex
    comment above for the false negative that reading only one produced.
    """
    front = _frontmatter(text)
    tools = set()

    block = _ALLOWED_TOOLS_BLOCK_RE.search(front)
    if block:
        for line in block.group(1).splitlines():
            name = _normalise_tool(line.strip().lstrip("-"))
            if name:
                tools.add(name)

    inline = _ALLOWED_TOOLS_INLINE_RE.search(front)
    if inline:
        for raw in inline.group(1).replace("|", ",").split(","):
            name = _normalise_tool(raw)
            if name:
                tools.add(name)
    return tools


def _keywords(description):
    words = re.findall(r"[a-z][a-z0-9-]{2,}", description.lower())
    return {w for w in words if w not in _STOPWORDS}


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _line_count(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def command_files(root):
    base = os.path.join(root, ".claude", "commands")
    if not os.path.isdir(base):
        return []
    return sorted(os.path.join(base, n) for n in os.listdir(base) if n.endswith(".md"))


def skill_files(root):
    base = os.path.join(root, ".claude", "skills")
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "SKILL.md")
        if os.path.isfile(path):
            out.append(path)
    return out


def baseline_path(root):
    return os.path.join(root, ".claude", BASELINE_NAME)


def load_baseline(root):
    path = baseline_path(root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        # Fail LOUD, not open: an unreadable baseline means every command looks new,
        # and a 466-line command silently "passing" a 40-line budget is the failure
        # mode this rule exists to prevent.
        raise RuntimeError("%s exists but is not readable JSON" % path)
    budget = data.get("command_lines")
    return budget if isinstance(budget, dict) else {}


def load_waivers(root):
    """Skill names allowed to hold a spawning tool, from the baseline file.

    Waived by NAME, never by pattern: a glob waiver would silently cover the next
    skill someone adds, which is the failure this rule exists to prevent.
    """
    path = baseline_path(root)
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise RuntimeError("%s exists but is not readable JSON" % path)
    waivers = data.get("skill_agent_waivers")
    if isinstance(waivers, dict):
        return set(waivers)
    return set(waivers) if isinstance(waivers, list) else set()


def write_baseline(root, counts, waivers=None):
    if waivers is None:
        # Re-recording the ratchet must never silently drop a waiver: that would turn
        # `--update-baseline` into a way to un-document two real violations.
        try:
            existing = load_waivers(root)
        except RuntimeError:
            existing = set()
        waivers = {name: "carried by --update-baseline; reason not re-stated"
                   for name in sorted(existing)}
    payload = {
        "note": ("Ratchet for ck lint's command-budget rule. A command listed here may "
                 "not grow past its recorded count; one that is not listed must fit "
                 "NEW_COMMAND_BUDGET. Shrinking is always allowed and re-recording "
                 "tightens the ratchet -- run `ck lint --update-baseline` after a "
                 "deliberate reduction."),
        "new_command_budget": NEW_COMMAND_BUDGET,
        "command_lines": dict(sorted(counts.items())),
        "skill_agent_waivers": waivers,
    }
    with open(baseline_path(root), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def current_command_lines(root):
    return {os.path.basename(p): _line_count(p) for p in command_files(root)}


def check_command_budget(root):
    """Ratchet: new commands meet the budget, existing ones may not grow."""
    findings = []
    baseline = load_baseline(root)
    for path in command_files(root):
        name = os.path.basename(path)
        lines = _line_count(path)
        if name in baseline:
            allowed = baseline[name]
            if lines > allowed:
                findings.append(Finding(
                    "command-budget", os.path.relpath(path, root),
                    "grew to %d lines; the ratchet allows %d. Trim it, or run "
                    "`ck lint --update-baseline` if the growth is deliberate."
                    % (lines, allowed)))
        elif lines > NEW_COMMAND_BUDGET:
            findings.append(Finding(
                "command-budget", os.path.relpath(path, root),
                "is a new command at %d lines; new commands must fit %d. Existing "
                "commands are held at their recorded size instead, because 0 of 55 "
                "met this target when the rule landed."
                % (lines, NEW_COMMAND_BUDGET)))
    return findings


#: Tools that let a skill spawn another agent.
SPAWNING_TOOLS = ("Agent", "Task")


def check_skill_agent_costume(root):
    """A skill granted the Agent tool is an agent wearing a skill's frontmatter.

    Skills are loaded INTO an agent's context; one that can spawn agents inverts that
    and routes around `.claude/agents/_shared/INVOCATION.md`, where spawning is scoped.

    Two skills in this corpus already do it, and they are WAIVED by name in
    `.claude/lint-baseline.json` rather than hidden: both are genuine orchestration
    prose, converting them is agent-corpus work this rule's batch does not own, and a
    rule that failed the DoD on day one would be turned off. Same ratchet shape as the
    command budget -- record what exists, block what is new.
    """
    findings = []
    waived = load_waivers(root)
    for path in skill_files(root):
        name = os.path.basename(os.path.dirname(path))
        tools = declared_tools(_read(path))
        offending = sorted(t for t in tools if t in SPAWNING_TOOLS)
        if not offending:
            continue
        if name in waived:
            continue
        findings.append(Finding(
            "skill-agent-costume", os.path.relpath(path, root),
            "grants %s. A skill that can spawn agents belongs in .claude/agents/, "
            "where INVOCATION.md scopes what it may spawn. If this is deliberate, add "
            "it to `skill_agent_waivers` in .claude/%s with a reason."
            % (" and ".join(offending), BASELINE_NAME)))
    return findings


def check_duplicate_triggers(root):
    """Two skills competing to answer the same prompt is a mis-routing hazard.

    This is the rule task 008 batch 2 existed to satisfy by hand; keeping it as a gate
    is what stops the corpus drifting back.
    """
    findings = []
    keywords = {}
    for path in skill_files(root):
        description = _field(_read(path), _DESC_RE)
        if description:
            keywords[path] = _keywords(description)

    for left, right in combinations(sorted(keywords), 2):
        a, b = keywords[left], keywords[right]
        if not a or not b:
            continue
        overlap = len(a & b) / float(len(a | b))
        if overlap >= TRIGGER_OVERLAP:
            findings.append(Finding(
                "duplicate-triggers", os.path.relpath(left, root),
                "description overlaps %s by %.0f%% (shared: %s). Two skills competing "
                "for one prompt is the mis-routing hazard task 008 batch 2 removed by "
                "merging five names away." % (
                    os.path.relpath(right, root), overlap * 100,
                    ", ".join(sorted(a & b)[:6]))))
    return findings


RULES = {
    "command-budget": check_command_budget,
    "skill-agent-costume": check_skill_agent_costume,
    "duplicate-triggers": check_duplicate_triggers,
}


def run(root, only=None):
    findings = []
    for name, check in sorted(RULES.items()):
        if only and name not in only:
            continue
        findings.extend(check(root))
    return findings
