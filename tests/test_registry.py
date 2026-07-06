"""Integrity checks for .claude/skills/skills-registry.json.

The doctor and a CI job both validate the registry at runtime; this pins it in
the test suite so a dangling agent->skill reference fails fast (regression guard
for the `documenter -> i18n-workflow` dangling ref).
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / ".claude" / "skills" / "skills-registry.json"


def _registry():
    return json.loads(REGISTRY.read_text())


def test_registry_is_valid_json():
    assert isinstance(_registry(), dict)


def test_no_dangling_agent_skill_references():
    reg = _registry()
    skill_ids = {s["id"] for s in reg["skills"]}
    dangling = {
        (agent, sid)
        for agent, skills in reg["agentMapping"].items()
        for sid in skills
        if sid not in skill_ids
    }
    assert not dangling, f"agentMapping references unknown skills: {sorted(dangling)}"


def test_every_registry_skill_has_a_directory():
    reg = _registry()
    skills_dir = REPO / ".claude" / "skills"
    missing = [
        s["id"] for s in reg["skills"]
        if not (skills_dir / s["id"] / "SKILL.md").exists()
    ]
    assert not missing, f"registry skills without a SKILL.md dir: {missing}"
