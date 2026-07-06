"""Tests for spec-driven development workflow."""
import os
import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
COMMANDS_DIR = os.path.join(TEMPLATE_DIR, "commands")
SKILLS_DIR = os.path.join(TEMPLATE_DIR, "skills")

SPEC_COMMANDS = ["specify", "clarify", "analyze", "checklist"]


class TestSpecCommands:
    """Verify all spec-driven commands exist."""

    @pytest.mark.parametrize("cmd", SPEC_COMMANDS)
    def test_command_exists(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        assert os.path.isfile(path), f"/{cmd} command missing"

    @pytest.mark.parametrize("cmd", SPEC_COMMANDS)
    def test_command_has_frontmatter(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        with open(path) as f:
            content = f.read()
        assert content.startswith("---"), f"/{cmd} missing frontmatter"
        assert "description:" in content

    @pytest.mark.parametrize("cmd", SPEC_COMMANDS)
    def test_command_has_argument_hint(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        with open(path) as f:
            content = f.read()
        assert "argument-hint:" in content


class TestSpecSkill:
    """Verify spec-driven development skill."""

    def test_skill_exists(self):
        path = os.path.join(SKILLS_DIR, "spec-driven-development", "SKILL.md")
        assert os.path.isfile(path)

    def test_skill_has_workflow(self):
        path = os.path.join(SKILLS_DIR, "spec-driven-development", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "specify" in content.lower()
        assert "clarify" in content.lower()
        assert "plan" in content.lower()
