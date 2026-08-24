"""Task 008 batch 3 cluster 7 (FINAL): `harness-optimizer` folds into `context-budget`.

The skill MEASURED where the context budget goes; the agent acted on the measurement by
reading the same files. `/context-budget` already loaded the skill, so the split bought a
second spawn to re-derive numbers the invoker already had.

This file also closes BATCH 3 as a whole: the alias map is checked for every one of the
nine removed agent names, in both kinds.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = ".claude/skills/context-budget/SKILL.md"

UNION = [
    '- ALWAYS maintain cross-platform compatibility (macOS/Linux/WSL)',
    '- ALWAYS test hook changes with a dry-run before activating',
    '- NEVER modify product source code (only `.claude/` directory)',
    '- NEVER reduce security hooks (pre-commit, pre-push, block-no-verify)',
    '- NEVER remove a hook without creating a backup',
    'SKILL.md',
    '`.claude/`',
    '`allowedTools`',
    '`using-superpowers`',
    'cfg.get',
    'coordinator.md',
    'json.load',
    'mcp.items',
    'post-tool-use.sh',
    'raise agent completion quality by improving configuration, not rewriting product code.',
    'reversible',
    'settings.json',
    'settings.json.bak',
    'sys.stdin',
    'Core Mission',
    'Operational Workflow',
    'Common Optimizations',
    'Constraints',
]

#: Every agent batch 3 removed, and what it became. Nine names, seven clusters.
REMOVED_BY_BATCH_3 = {
    "code-simplifier": ("refactor-cleaner", "agent"),
    "silent-failure-hunter": ("code-reviewer", "agent"),
    "python-reviewer": ("python-review-checklist", "skill"),
    "typescript-reviewer": ("typescript-review-checklist", "skill"),
    "documenter": ("docs", "agent"),
    "doc-updater": ("docs", "agent"),
    "tdd-guide": ("test-driven-development", "skill"),
    "model-router": ("coordinator", "agent"),
    "harness-optimizer": ("context-budget", "skill"),
}


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestTheFinalFold:
    def test_the_agent_is_gone(self):
        assert not os.path.isfile(
            os.path.join(ROOT, ".claude", "agents", "harness-optimizer.md"))

    @pytest.mark.parametrize("fragment", UNION)
    def test_the_union_survived(self, fragment):
        assert fragment in _read(SKILL), fragment

    def test_the_command_still_reaches_the_workflow(self):
        """/context-budget loads this skill; if it did not, the audit workflow would
        have been deleted rather than relocated."""
        assert "context-budget" in _read(".claude/commands/context-budget.md")


class TestBatchThreeIsClosed:
    """Nine agents removed across seven clusters. Every name must still resolve --
    that was the condition the sign-off attached to approving batch 3 at all, in place
    of the eval-suite gate that does not exist."""

    @pytest.mark.parametrize("old", sorted(REMOVED_BY_BATCH_3))
    def test_every_removed_agent_is_actually_gone(self, old):
        assert not os.path.isfile(os.path.join(ROOT, ".claude", "agents", old + ".md"))

    @pytest.mark.parametrize("old", sorted(REMOVED_BY_BATCH_3))
    def test_every_removed_name_still_resolves(self, old):
        target, kind = REMOVED_BY_BATCH_3[old]
        registry = json.loads(_read(".claude/skills/skills-registry.json"))
        assert registry["renamedAgents"][old] == {"to": target, "kind": kind}

    @pytest.mark.parametrize("old", sorted(REMOVED_BY_BATCH_3))
    def test_every_alias_target_exists_on_disk(self, old):
        """An alias pointing at nothing is worse than no alias: it tells a consumer
        the rename succeeded."""
        target, kind = REMOVED_BY_BATCH_3[old]
        if kind == "agent":
            path = os.path.join(ROOT, ".claude", "agents", target + ".md")
        else:
            path = os.path.join(ROOT, ".claude", "skills", target, "SKILL.md")
        assert os.path.isfile(path), (old, target, kind)

    def test_both_alias_kinds_are_represented(self):
        registry = json.loads(_read(".claude/skills/skills-registry.json"))
        kinds = {s["kind"] for s in registry["renamedAgents"].values()}
        assert kinds == {"agent", "skill"}

    def test_the_uncovered_risk_is_recorded_somewhere_a_reader_will_hit_it(self):
        """Batch 3 shipped WITHOUT its designed gate. Every cluster plan says so; this
        asserts the statement did not quietly disappear from the last one."""
        plans = os.path.join(ROOT, ".claude", "plans")
        found = []
        for name in os.listdir(plans):
            if name.startswith("plan-008-b3c") and name.endswith(".md"):
                with open(os.path.join(plans, name), encoding="utf-8") as fh:
                    if "not demonstrated unchanged" in fh.read():
                        found.append(name)
        assert len(found) >= 7, found