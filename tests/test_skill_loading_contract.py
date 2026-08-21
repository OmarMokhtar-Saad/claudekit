"""A sentence in the entrypoint is not a load.

ChaosEngine's lifecycle rule, made mechanical: if a behaviour is mandatory at a
lifecycle moment, the mechanism must actually register it. Prose in a prompt is
not enforcement.

The concrete failure this pins was live in the corpus until 2026-08-21. Fifteen
skills carried `disable-model-invocation: true`, which removes them from the
Skill tool's listing entirely, while agents' "Skill Loading" sections named them
anyway: **8 as mandatory** (including `execute-operations-config`, the
implementer's Iron Law mechanism, and `validate-operations-config`, the
reviewer's) and **7 as on-demand** (five of them the coordinator's adaptive
aids). Every one of those loads was dead prose.

Both classes are enforced, deliberately. A mandatory load that cannot execute
breaks a stated contract; an on-demand "load when the trigger fires" that can
never fire is arguably worse, because the prompt reads as a capability the
agent does not have. The failure message names the class so a regression is
actionable rather than merely detected.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
SKILLS_DIR = os.path.join(ROOT, ".claude", "skills")

SECTION_RE = re.compile(
    r"## (?:Skill Loading|Mandatory Skill Loading)\n(.*?)(?=\n## |\n---)", re.S)
# Bolded subsection headers inside that section. The corpus writes
# "**Mandatory (load before any work, in order):**" and
# "**On demand (load when the trigger fires ...):**" -- note the SPACE in
# "On demand". An earlier version of this analysis matched "On-demand" with a
# hyphen, matched nothing, and silently classified every skill as mandatory.
# A parser that cannot fail loudly produces a confident wrong answer.
HEADER_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)
SKILL_RE = re.compile(r"\*\*([a-z0-9][a-z0-9-]*)\*\*")
INVISIBLE_RE = re.compile(r"(?m)^disable-model-invocation:[ \t]*true[ \t]*$")


def model_invisible_skills():
    """Skills the Skill tool will not list, so no agent can invoke them."""
    invisible = set()
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            head = handle.read()
        match = re.match(r"(?s)\A---\n(.*?)\n---\n", head)
        if match and INVISIBLE_RE.search(match.group(1)):
            invisible.add(name)
    return invisible


def load_class(header):
    if header.lower().startswith("mandatory"):
        return "mandatory"
    return "on-demand" if "demand" in header.lower() else "unclassified"


def declared_loads():
    """(agent, skill, class) for every skill an agent's prompt tells it to load."""
    pairs = []
    for fname in sorted(os.listdir(AGENTS_DIR)):
        path = os.path.join(AGENTS_DIR, fname)
        if not fname.endswith(".md") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        if not text.startswith("---\n"):
            continue
        section = SECTION_RE.search(text)
        if not section:
            continue
        body = section.group(1)
        headers = list(HEADER_RE.finditer(body))
        if not headers:
            for skill in sorted(set(SKILL_RE.findall(body))):
                pairs.append((fname[:-3], skill, "unclassified"))
            continue
        for index, header in enumerate(headers):
            end = headers[index + 1].start() if index + 1 < len(headers) else len(body)
            segment = body[header.end():end]
            for skill in sorted(set(SKILL_RE.findall(segment))):
                pairs.append((fname[:-3], skill, load_class(header.group(1))))
    return pairs


class DeclaredLoadsMustBeExecutable(unittest.TestCase):
    def test_no_agent_is_told_to_load_a_skill_it_cannot_invoke(self):
        invisible = model_invisible_skills()
        dead = ["%s -> %s (%s)" % (agent, skill, klass)
                for agent, skill, klass in declared_loads() if skill in invisible]
        self.assertEqual(dead, [], "\n".join(
            ["agents instructed to load skills that are not in the Skill tool's "
             "listing (`disable-model-invocation: true`). Either un-flag the "
             "skill or delete the instruction — a load that cannot happen is "
             "worse than no instruction, because the prompt reads as if it did:"]
            + dead))

    def test_every_declared_load_names_a_skill_that_exists(self):
        """The adjacent failure: an instruction to load something deleted."""
        missing = ["%s -> %s" % (agent, skill) for agent, skill, _k in declared_loads()
                   if not os.path.isfile(os.path.join(SKILLS_DIR, skill, "SKILL.md"))]
        self.assertEqual(missing, [])

    def test_the_check_actually_has_a_corpus_to_check(self):
        """Guards the vacuous case: a regex that silently stops matching turns
        this whole file green while enforcing nothing."""
        loads = declared_loads()
        self.assertGreater(len(loads), 20)
        classes = {klass for _a, _s, klass in loads}
        self.assertIn("mandatory", classes)
        self.assertIn("on-demand", classes,
                      "the subsection parser matched nothing — see HEADER_RE's note")
        self.assertGreater(len(model_invisible_skills()), 0,
                           "if nothing is flagged the invariant is untested, not satisfied")


class TheFloorChargesOnlyForWhatEntersContext(unittest.TestCase):
    """The measurement bug found alongside the contradiction.

    `check-context-floor.py` charged for all 76 skill descriptions, including
    the ~33 no model can see — inflating that category by ~3.9k chars. An
    inflated floor is not a conservative one; it gates on noise while hiding
    real headroom, which matters because CLAUDE.md is at its own limit.
    """

    def test_invisible_skills_are_excluded_from_the_floor(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_context_floor", os.path.join(ROOT, "scripts", "check-context-floor.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        invisible = model_invisible_skills()
        self.assertTrue(invisible, "no flagged skills — nothing to exclude")
        sample = os.path.join(SKILLS_DIR, sorted(invisible)[0], "SKILL.md")
        with open(sample, encoding="utf-8") as handle:
            frontmatter = module.frontmatter(handle.read())
        self.assertTrue(module.model_invisible(frontmatter))

        visible_total = module.measure()["skill descriptions"]
        every_description = 0
        for name in sorted(os.listdir(SKILLS_DIR)):
            path = os.path.join(SKILLS_DIR, name, "SKILL.md")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as handle:
                every_description += len(
                    module.description_span(module.frontmatter(handle.read())))
        self.assertLess(visible_total, every_description,
                        "the floor must not charge for skills no model can see")


if __name__ == "__main__":
    unittest.main()
