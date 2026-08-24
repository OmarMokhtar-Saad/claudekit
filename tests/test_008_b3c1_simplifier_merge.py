"""Task 008 batch 3 cluster 1: `code-simplifier` merged into `refactor-cleaner`.

One cluster per plan, one plan per PR -- the owner's compensating control for batch 3
running WITHOUT its designed gate. The eval suite that was meant to prove routing
unchanged is blocked on cassettes, so it does NOT cover this merge and this file does not
pretend otherwise: it proves the CONTENT survived and the name still resolves. Routing is
unverified, and the PR says so.

Fragments are DERIVED from the deleted file (every backtick span, dotted identifier, bold
span and ALL-CAPS imperative absent from the survivor before the merge), plus headings --
never headings alone, which is how batch 1 shipped a fold that had lost three sections.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, ".claude", "agents")

UNION = [
    "Don't collapse necessary state",
    "Don't generalize working code",
    "Don't optimize for cleverness",
    "Don't over-simplify error handling",
    "Don't remove safety checks",
    'Preserve all functionality.',
    'Test:',
    'User.query.filter_by',
    'User.query.get',
    'event.items',
    'event.type',
    'item.price',
    'item.qty',
    'request.has_permission',
    'request.is_rate_limited',
    'user.is_active',
    'Simplification Targets',
    'Unnecessary Abstractions',
    'Premature Generalization',
    'Redundant Code',
    'Overly Complex Conditionals',
    'Temporary Variables That Obscure Flow',
    'Comments That Restate Code',
    'Review Workflow',
    'Measure Complexity',
    'What NOT to Simplify',
]


def _body(agent):
    with open(os.path.join(AGENTS, agent + ".md"), encoding="utf-8") as fh:
        return fh.read()


class TestTheMergeIsComplete:
    def test_the_merged_away_agent_is_gone(self):
        assert not os.path.isfile(os.path.join(AGENTS, "code-simplifier.md"))

    def test_the_survivor_exists(self):
        assert os.path.isfile(os.path.join(AGENTS, "refactor-cleaner.md"))

    @pytest.mark.parametrize("fragment", UNION)
    def test_the_union_survived(self, fragment):
        assert fragment in _body("refactor-cleaner"), fragment

    def test_the_core_rule_is_carried_verbatim(self):
        """`Preserve all functionality.` outranks every simplification target. A
        paraphrase would have satisfied a headings check and lost the rule."""
        assert "**Preserve all functionality.**" in _body("refactor-cleaner")


class TestTheNameStillResolves:
    def test_the_agent_alias_is_recorded(self):
        """FIRST use of the renamedAgents mechanism batch 3 phase 0 landed. Without it
        this deletion could not have shipped at all."""
        path = os.path.join(ROOT, ".claude", "skills", "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            registry = json.load(fh)
        assert registry["renamedAgents"]["code-simplifier"] == {
            "to": "refactor-cleaner", "kind": "agent"}

    def test_no_live_consumer_names_the_removed_agent(self):
        """The survivor's own seam may narrate what it absorbed; nothing else may
        route to a name that is gone."""
        allowed = os.path.abspath(os.path.join(AGENTS, "refactor-cleaner.md"))
        hits = []
        for rel in (".claude/agents", ".claude/commands", ".claude/skills", "docs",
                    "src/claudekit", "scripts"):
            base = os.path.join(ROOT, rel)
            if not os.path.isdir(base):
                continue
            for dirpath, _dirs, files in os.walk(base):
                for name in files:
                    if not name.endswith((".md", ".json", ".py")):
                        continue
                    if name == "skills-registry.json":
                        continue
                    path = os.path.join(dirpath, name)
                    if os.path.abspath(path) == allowed:
                        continue
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        if "code-simplifier" in fh.read():
                            hits.append(os.path.relpath(path, ROOT))
        assert hits == [], hits

    def test_the_model_policy_no_longer_names_it(self):
        path = os.path.join(ROOT, ".claude", "model-policy.json")
        with open(path, encoding="utf-8") as fh:
            policy = json.load(fh)
        assert "code-simplifier" not in policy["roles"]
