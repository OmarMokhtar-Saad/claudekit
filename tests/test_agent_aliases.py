"""The agent half of the one-release rename window.

Task 008 batch 3's stated BLOCKER: `renamed` resolves its targets against
`.claude/skills/`, so aliasing an agent name was rejected outright --

    renamed: 'python-reviewer' -> 'code-reviewer', which does not exist

-- while the sign-off requires every removed AGENT name to resolve for one release.
This mechanism had to land before any agent could be deleted, the same way the `*.md`
protected-glob fix had to land before batch 1 could run at all.

`renamedAgents` is a separate map with an explicit target `kind` because batch 3 turns
three agents INTO skills (`python-reviewer`, `typescript-reviewer` become per-language
checklist skills; `tdd-guide` folds into `test-driven-development`), so the alias must
say which namespace to validate the target against. Every rule below is proven by
building a registry that violates it, not by reading the validator.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

from claudekit.skills import renamed_agents_map, resolve_agent_id

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(REPO, "scripts", "gen-registry.py")


class TestTheResolver:
    def test_an_unaliased_name_resolves_to_itself_as_an_agent(self):
        assert resolve_agent_id({}, "planner") == {"to": "planner", "kind": "agent"}

    def test_an_agent_can_resolve_to_an_agent(self):
        doc = {"renamedAgents": {"gone": {"to": "code-reviewer", "kind": "agent"}}}
        assert resolve_agent_id(doc, "gone") == {"to": "code-reviewer", "kind": "agent"}

    def test_an_agent_can_resolve_to_a_SKILL_across_namespaces(self):
        """The case `renamed` structurally could not express, and the reason this map
        exists at all."""
        doc = {"renamedAgents": {"tdd-guide": {"to": "test-driven-development",
                                              "kind": "skill"}}}
        assert resolve_agent_id(doc, "tdd-guide") == {
            "to": "test-driven-development", "kind": "skill"}

    @pytest.mark.parametrize("junk", [
        {"renamedAgents": []},
        {"renamedAgents": "nope"},
        {"renamedAgents": {"a": "bare-string"}},
        {"renamedAgents": {"a": {"to": "x"}}},
        {"renamedAgents": {"a": {"to": "x", "kind": "command"}}},
        {"renamedAgents": {"a": {"to": "", "kind": "agent"}}},
    ])
    def test_malformed_entries_degrade_rather_than_crash(self, junk):
        """A caller that only wanted to resolve a name must not inherit a crash from a
        junk registry -- same tolerance `renamed_map` has."""
        assert renamed_agents_map(junk) == {}
        assert resolve_agent_id(junk, "a") == {"to": "a", "kind": "agent"}

    def test_resolution_is_a_single_hop(self):
        """A chain means two releases of aliases outliving a one-release window."""
        doc = {"renamedAgents": {"a": {"to": "b", "kind": "agent"},
                                 "b": {"to": "c", "kind": "agent"}}}
        assert resolve_agent_id(doc, "a")["to"] == "b"


class TestTheGeneratorRefusesADishonestAlias:
    """Each case is a registry the validator must REJECT. Without these the map is
    stored data that changes no behaviour -- the finding review made about `renamed`
    the first time it landed."""

    def _project(self, tmp_path, aliases):
        root = tmp_path / "proj"
        (root / ".claude" / "agents").mkdir(parents=True)
        (root / ".claude" / "skills" / "real-skill").mkdir(parents=True)
        (root / ".claude" / "skills" / "real-skill" / "SKILL.md").write_text(
            "---\nname: real-skill\ndescription: d\n---\n\n# S\n", encoding="utf-8")
        (root / ".claude" / "agents" / "real-agent.md").write_text(
            "---\nname: real-agent\ndescription: d\n---\n\n# A\n", encoding="utf-8")
        registry = {
            "version": "1.0", "renamed": {}, "renamedAgents": aliases,
            "skills": [{"id": "real-skill", "name": "Real Skill",
                        "path": "skills/real-skill/SKILL.md", "mandatory": False,
                        "usedBy": [], "description": "d"}],
            "agentsWithoutSkills": ["real-agent"], "agentMapping": {},
        }
        (root / ".claude" / "skills" / "skills-registry.json").write_text(
            json.dumps(registry, indent=2), encoding="utf-8")
        shutil.copytree(os.path.join(REPO, "scripts"), str(root / "scripts"))
        return root

    def _check(self, root):
        return subprocess.run([sys.executable, str(root / "scripts" / "gen-registry.py"),
                               "--check"], cwd=str(root), capture_output=True, text=True)

    def test_a_target_that_does_not_exist_is_refused(self, tmp_path):
        proc = self._check(self._project(
            tmp_path, {"gone": {"to": "nonexistent", "kind": "agent"}}))
        assert proc.returncode == 1
        assert "does not exist" in proc.stderr

    def test_the_wrong_namespace_is_refused(self, tmp_path):
        """`kind: agent` pointing at a real SKILL must fail -- otherwise the `kind`
        field is decoration and the cross-namespace case is unvalidated."""
        proc = self._check(self._project(
            tmp_path, {"gone": {"to": "real-skill", "kind": "agent"}}))
        assert proc.returncode == 1
        assert "does not exist" in proc.stderr

    def test_a_correct_cross_namespace_alias_is_accepted(self, tmp_path):
        proc = self._check(self._project(
            tmp_path, {"gone": {"to": "real-skill", "kind": "skill"}}))
        assert proc.returncode == 0, proc.stderr

    def test_aliasing_a_live_agent_is_refused(self, tmp_path):
        """Shadowing: if the old name still exists, the alias tells a consumer to stop
        using an agent they still have."""
        proc = self._check(self._project(
            tmp_path, {"real-agent": {"to": "real-skill", "kind": "skill"}}))
        assert proc.returncode == 1
        assert "still exists on disk" in proc.stderr

    def test_an_empty_key_is_refused(self, tmp_path):
        proc = self._check(self._project(
            tmp_path, {"": {"to": "real-agent", "kind": "agent"}}))
        assert proc.returncode == 1

    @pytest.mark.parametrize("spec", ["bare-string", {"to": "real-agent"},
                                      {"to": "real-agent", "kind": "command"}])
    def test_a_malformed_spec_is_refused_by_the_generator(self, tmp_path, spec):
        """The resolver TOLERATES junk so a lookup cannot crash; the generator must
        REFUSE it so junk never ships. Both behaviours, deliberately different."""
        proc = self._check(self._project(tmp_path, {"gone": spec}))
        assert proc.returncode == 1, proc.stdout + proc.stderr


class TestThisRepoIsStillClean:
    def test_the_generator_accepts_the_shipped_registry(self):
        proc = subprocess.run([sys.executable, GEN, "--check"], cwd=REPO,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_no_agent_aliases_exist_yet(self):
        """The mechanism lands BEFORE the merges that need it, so this is empty today.
        Batch 3's first merge cluster is what fills it."""
        with open(os.path.join(REPO, ".claude", "skills", "skills-registry.json"),
                  encoding="utf-8") as fh:
            assert renamed_agents_map(json.load(fh)) == {}
