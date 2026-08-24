"""Task 008 batch 3 cluster 3: the two per-language reviewers become SKILLS.

`python-reviewer` and `typescript-reviewer` were agents; they are now checklists that
`code-reviewer` loads when the diff contains matching extensions. A separate agent meant
a separate spawn, a separate context and a separate report to reconcile, for review
criteria belonging to whichever reviewer is already reading the diff.

**This is the FIRST cross-namespace alias**, and the case `renamedAgents` object-valued
targets exist for: `kind: skill` sends the validator to `.claude/skills/` instead of
`.claude/agents/`. A bare-name alias map could not have expressed it -- which is exactly
why batch 3 phase 0 refused to reuse the skills-only `renamed` map.

**Routing is NOT demonstrated unchanged** -- the eval cassettes do not exist. What is
proven: the content carried whole, both names resolve, and code-reviewer declares the
conditional load. Not proven: that an invoker who would have spawned python-reviewer now
gets an equivalent review.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".claude", "skills")
AGENTS = os.path.join(ROOT, ".claude", "agents")

MOVED = [
    ("python-reviewer", "python-review-checklist"),
    ("typescript-reviewer", "typescript-review-checklist"),
]

PYTHON_UNION = [
    'Bare `except:` — catches SystemExit and KeyboardInterrupt:',
    'Context managers for resources:',
    'Enumerate instead of range(len(...)):',
    'Missing annotations on public functions:',
    'Python Reviewer',
    'SQL injection via string formatting:',
    'Shell injection:',
    'String concatenation in loops:',
    'Swallowing exceptions:',
    'Unnecessary list creation:',
    'Unsafe binary deserialization of untrusted data:',
    'Using `Optional` correctly (Python 3.10+ use `X | None`):',
    '`Optional`',
    '`X | None`',
    '`except:`',
    '`in`',
    'collection.append',
    'cursor.execute',
    'e.g',
    'f.close',
    'f.read',
    'file.txt',
    'json.loads',
    'logger.error',
    'logger.exception',
    'my_dict.keys',
    'subprocess.run',
    'Mutable Default Arguments',
    'Type Hints',
    'Exception Handling',
    'Pythonic Idioms',
    'Security Issues',
    'Performance Patterns',
    'Automated Checks',
]

TYPESCRIPT_UNION = [
    'CRITICAL',
    'Floating promises',
    'HIGH',
    'MEDIUM',
    'Missing error typing:',
    'Missing explicit return types on public APIs:',
    'Missing null/undefined handling:',
    'Overly broad types:',
    'Prefer interfaces for objects, types for unions/intersections:',
    'Promise.all',
    'Re-exporting anti-patterns:',
    'Sequential awaits when parallel is possible:',
    'Type assertions without validation:',
    'TypeScript Reviewer',
    'Unconstrained generics:',
    '`any`',
    '`any` abuse',
    'console.error',
    'd.ts',
    'e.message',
    'item.id',
    'items.find',
    'items.reduce',
    'response.data',
    'user.profile',
    'user.profile.name.toUpperCase',
    'Type Safety',
    'Async/Await Patterns',
    'Interface and Type Design',
    'Generics and Constraints',
    'Module and Export Patterns',
    'Severity Levels',
]


def _skill(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()


class TestTheAgentsBecameSkills:
    @pytest.mark.parametrize("old,new", MOVED)
    def test_the_agent_is_gone(self, old, new):
        assert not os.path.isfile(os.path.join(AGENTS, old + ".md"))

    @pytest.mark.parametrize("old,new", MOVED)
    def test_the_skill_exists(self, old, new):
        assert os.path.isfile(os.path.join(SKILLS, new, "SKILL.md"))

    @pytest.mark.parametrize("fragment", PYTHON_UNION)
    def test_the_python_checklist_carried_everything(self, fragment):
        assert fragment in _skill("python-review-checklist"), fragment

    @pytest.mark.parametrize("fragment", TYPESCRIPT_UNION)
    def test_the_typescript_checklist_carried_everything(self, fragment):
        assert fragment in _skill("typescript-review-checklist"), fragment

    @pytest.mark.parametrize("old,new", MOVED)
    def test_each_skill_says_what_loads_it_and_when(self, old, new):
        """A checklist nobody loads is dead prose. The trigger has to be stated IN the
        skill, not only in the agent that loads it."""
        body = _skill(new)
        assert "code-reviewer" in body
        assert "diff under review contains" in body


class TestCodeReviewerActuallyLoadsThem:
    def test_both_are_declared_as_conditional_loads(self):
        with open(os.path.join(AGENTS, "code-reviewer.md"), encoding="utf-8") as fh:
            body = fh.read()
        for _old, new in MOVED:
            assert new in body, new

    def test_they_are_on_demand_not_mandatory(self):
        """Preloading both for a diff touching neither language burns context for
         nothing -- which is what that section of the agent says."""
        with open(os.path.join(AGENTS, "code-reviewer.md"), encoding="utf-8") as fh:
            body = fh.read()
        on_demand = body.index("**On demand")
        for _old, new in MOVED:
            assert body.index(new) > on_demand, new

    def test_the_registry_records_the_dependency(self):
        path = os.path.join(SKILLS, "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        rows = {s["id"]: s for s in registry["skills"]}
        for _old, new in MOVED:
            assert "code-reviewer" in rows[new]["usedBy"], new


class TestTheCrossNamespaceAliasWorks:
    @pytest.mark.parametrize("old,new", MOVED)
    def test_the_alias_targets_a_SKILL_not_an_agent(self, old, new):
        """kind=skill is the whole reason renamedAgents takes an object. If this said
        `agent`, gen-registry would look in .claude/agents/ and reject it."""
        path = os.path.join(SKILLS, "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        assert registry["renamedAgents"][old] == {"to": new, "kind": "skill"}

    def test_the_mechanism_now_carries_both_kinds(self):
        """Phase 0 built for this and clusters 1-2 only exercised kind=agent. A
        map that never used its second kind is a map whose second kind is untested."""
        path = os.path.join(SKILLS, "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        kinds = {spec["kind"] for spec in registry["renamedAgents"].values()}
        assert kinds == {"agent", "skill"}, kinds
