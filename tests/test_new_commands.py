"""Tests for all new commands added in v2.0.0."""
import os

import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
COMMANDS_DIR = os.path.join(TEMPLATE_DIR, "commands")

NEW_COMMANDS = [
    "mode", "index", "mcp", "specify", "clarify", "analyze", "checklist",
    "flags", "load", "checkpoint", "spawn", "ship", "translate",
]


class TestNewCommandsExist:
    """Verify all new commands exist."""

    @pytest.mark.parametrize("cmd", NEW_COMMANDS)
    def test_command_file_exists(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        assert os.path.isfile(path), f"Command /{cmd} missing"

    @pytest.mark.parametrize("cmd", NEW_COMMANDS)
    def test_command_has_frontmatter(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        with open(path) as f:
            content = f.read()
        assert content.strip().startswith("---"), f"/{cmd} missing YAML frontmatter"

    @pytest.mark.parametrize("cmd", NEW_COMMANDS)
    def test_command_has_description(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content, f"/{cmd} missing description"

    @pytest.mark.parametrize("cmd", NEW_COMMANDS)
    def test_command_not_empty(self, cmd):
        path = os.path.join(COMMANDS_DIR, f"{cmd}.md")
        assert os.path.getsize(path) > 100, f"/{cmd} too small (likely empty)"


class TestTotalCommandCount:
    """Verify total command count meets target."""

    def test_minimum_new_command_count(self):
        """templates/commands/ has new v2.0 commands; existing ones are in .claude/commands/"""
        cmds = [f for f in os.listdir(COMMANDS_DIR) if f.endswith(".md")]
        assert len(cmds) >= 13, f"Expected >= 13 new commands, found {len(cmds)}"

    def test_total_command_count_with_existing(self):
        """Total commands across templates + .claude should be >= 27."""
        project_dir = os.path.dirname(os.path.dirname(__file__))
        existing_dir = os.path.join(project_dir, ".claude", "commands")
        new_cmds = set(f for f in os.listdir(COMMANDS_DIR) if f.endswith(".md"))
        existing_cmds = set()
        if os.path.isdir(existing_dir):
            existing_cmds = set(f for f in os.listdir(existing_dir) if f.endswith(".md"))
        total = len(new_cmds | existing_cmds)
        assert total >= 27, f"Expected >= 27 total commands, found {total}"
