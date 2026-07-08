"""Tests for all new skills added in v2.0.0."""
import os

import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
SKILLS_DIR = os.path.join(TEMPLATE_DIR, "skills")

NEW_SKILLS = [
    "command-flags",
    "mcp-integration",
    "spec-driven-development",
    "i18n-workflow",
    "token-optimization",
    "codebase-mapping",
    "session-continuity",
    "autonomous-loop",
    "context-priming",
    "hook-profiling",
    "safe-command-approval",
    "usage-monitoring",
    "prompt-injection-defense",
    "incident-response",
]


class TestNewSkillsExist:
    """Verify all new skills exist."""

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_directory_exists(self, skill):
        path = os.path.join(SKILLS_DIR, skill)
        assert os.path.isdir(path), f"Skill directory missing: {skill}"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_file_exists(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        assert os.path.isfile(path), f"SKILL.md missing for: {skill}"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_frontmatter(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert content.strip().startswith("---"), f"{skill} missing frontmatter"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_name(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "name:" in content, f"{skill} missing name field"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_description(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content, f"{skill} missing description"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_not_empty(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        assert os.path.getsize(path) > 200, f"{skill} too small"


class TestTotalSkillCount:
    """Verify total skill count meets target."""

    def test_minimum_new_skill_count(self):
        """templates/skills/ has new v2.0 skills; existing ones are in .claude/skills/"""
        skills = [
            d for d in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, d))
            and os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
        ]
        assert len(skills) >= 14, f"Expected >= 14 new skills, found {len(skills)}"

    def test_total_skill_count_with_existing(self):
        """Total skills across templates + .claude should be >= 55."""
        project_dir = os.path.dirname(os.path.dirname(__file__))
        existing_dir = os.path.join(project_dir, ".claude", "skills")
        new_skills = set(
            d for d in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, d))
            and os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
        )
        existing_skills = set()
        if os.path.isdir(existing_dir):
            existing_skills = set(
                d for d in os.listdir(existing_dir)
                if os.path.isdir(os.path.join(existing_dir, d))
                and os.path.isfile(os.path.join(existing_dir, d, "SKILL.md"))
            )
        total = len(new_skills | existing_skills)
        assert total >= 55, f"Expected >= 55 total skills, found {total}"
