"""Tests for all new commands added in v2.0.0.

They shipped from `templates/commands/` until task 008 batch 1 promoted them into
`.claude/commands/`, the single tree the installer now reads.
"""
import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
COMMANDS_DIR = os.path.join(ROOT, ".claude", "commands")

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


class TestOneCanonicalTree:
    """`.claude/commands/` is the only command source install.sh reads."""

    def test_there_is_no_second_command_tree(self):
        """A second commands tree would be copied to the same destination as
        .claude/commands/, so which file installs would again depend on copy order.

        Asserted on component FILES, not the directory. `file_delete` removes files and leaves the
        directory, and git does not track an empty directory -- so a directory-existence
        assertion FAILS in the tree that just ran the batch and PASSES in a fresh clone.
        A check whose answer depends on which of those you are in proves nothing."""
        project_dir = os.path.dirname(os.path.dirname(__file__))
        stale = glob.glob(os.path.join(project_dir, "templates", "commands", "*.md"))
        assert stale == [], f"a second command tree is back: {stale}"

    def test_every_v2_command_survived_the_promotion(self):
        cmds = {f for f in os.listdir(COMMANDS_DIR) if f.endswith(".md")}
        missing = sorted(f"{c}.md" for c in NEW_COMMANDS if f"{c}.md" not in cmds)
        assert missing == [], f"lost in the promotion: {missing}"

    def test_total_command_count(self):
        cmds = [f for f in os.listdir(COMMANDS_DIR) if f.endswith(".md")]
        assert len(cmds) >= 55, f"Expected >= 55 commands, found {len(cmds)}"
