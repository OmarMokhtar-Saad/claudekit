"""Tests for checkpoint system."""
import os

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


class TestCheckpointCommand:
    """Verify checkpoint command."""

    def test_checkpoint_command_exists(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "checkpoint.md")
        assert os.path.isfile(path)

    def test_checkpoint_has_create_action(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "checkpoint.md")
        with open(path) as f:
            content = f.read()
        assert "create" in content.lower()

    def test_checkpoint_has_restore_action(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "checkpoint.md")
        with open(path) as f:
            content = f.read()
        assert "restore" in content.lower()

    def test_checkpoint_has_list_action(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "checkpoint.md")
        with open(path) as f:
            content = f.read()
        assert "list" in content.lower()


class TestAutoCheckpointHook:
    """Verify auto-checkpoint hook."""

    def test_hook_exists(self):
        path = os.path.join(TEMPLATE_DIR, "hooks", "auto-checkpoint.sh")
        assert os.path.isfile(path)

    def test_hook_is_executable(self):
        path = os.path.join(TEMPLATE_DIR, "hooks", "auto-checkpoint.sh")
        assert os.access(path, os.X_OK)

    def test_hook_uses_git_stash(self):
        path = os.path.join(TEMPLATE_DIR, "hooks", "auto-checkpoint.sh")
        with open(path) as f:
            content = f.read()
        assert "git stash" in content
