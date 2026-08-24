"""Task 008 batch 3 cluster 5: `tdd-guide` folds into `test-driven-development`.

`tester` ALREADY loaded that skill as role-core, so the agent was a second context
holding rules the test-writer already had. The ordering rule it enforced moves from a
coordinator note ABOUT an agent to a rule INSIDE the skill the test-writer loads --
binding where the work happens rather than where the routing decision is made.

Routing is not demonstrated unchanged; the eval cassettes do not exist.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UNION = [
    'Boundary values',
    'Define capability evaluation',
    'Empty strings/arrays',
    'Error paths',
    'Invalid types',
    'Large data',
    'Minimum thresholds (hard gates):',
    'Never write implementation code before the failing test exists.',
    'Null/undefined inputs',
    'Race conditions',
    'Special characters',
    'UserService.authenticate',
    '`authenticate("", "")`',
    '`authenticate(123, true)`',
    '`authenticate(null, undefined)`',
    '`beforeEach`',
    '`eval-harness`',
    'example.com',
    'rejects.toThrow',
    'result.status',
    'result.user.email',
    'userService.authenticate',
    'The Unbreakable Rule',
    'Required Test Types',
    'The 8 Edge Cases That Must Be Tested',
    'Coverage Requirements',
    'Eval-Driven TDD',
    'Test Anti-Patterns to Avoid',
    'Quality Checklist Before Declaring Done',
    'TDD Session Report',
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


SKILL = ".claude/skills/test-driven-development/SKILL.md"


class TestTheFoldIsComplete:
    def test_the_agent_is_gone(self):
        assert not os.path.isfile(
            os.path.join(ROOT, ".claude", "agents", "tdd-guide.md"))

    @pytest.mark.parametrize("fragment", UNION)
    def test_the_union_survived(self, fragment):
        assert fragment in _read(SKILL), fragment

    def test_the_ordering_rule_moved_into_the_skill(self):
        """The coordinator said "TDD Guide MUST produce tests before Implementer
        writes code". That agent is gone; the constraint is not. It now lives where
        the test-writer will actually read it."""
        body = _read(SKILL)
        assert "before" in body and "implementer" in body.lower()
        assert "RED step" in body

    def test_the_alias_targets_the_skill(self):
        registry = json.loads(_read(".claude/skills/skills-registry.json"))
        assert registry["renamedAgents"]["tdd-guide"] == {
            "to": "test-driven-development", "kind": "skill"}


class TestTheRouteStillReachesTheDiscipline:
    def test_tdd_routes_to_tester(self):
        body = _read(".claude/agents/coordinator.md")
        assert "TDD Guide" not in body
        assert "tester" in body

    def test_tester_actually_loads_the_skill(self):
        """If it did not, the fold would have deleted the discipline rather than
        relocating it -- the whole premise of routing TDD to tester."""
        assert "test-driven-development" in _read(".claude/agents/tester.md")

    def test_the_ordering_constraint_survives_in_the_coordinator_too(self):
        body = _read(".claude/agents/coordinator.md")
        assert "MUST produce failing tests before implementer" in body
