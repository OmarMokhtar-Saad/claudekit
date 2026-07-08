"""Tests for behavioral modes system."""
import os

import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
MODES_DIR = os.path.join(TEMPLATE_DIR, "modes")

EXPECTED_MODES = [
    "default",
    "brainstorm",
    "token-efficient",
    "deep-research",
    "implementation",
    "review",
    "orchestration",
]


class TestModesExist:
    """Verify all 7 behavioral mode files exist."""

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_file_exists(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        assert os.path.isfile(path), f"Mode file missing: {mode}.md"

    def test_modes_directory_exists(self):
        assert os.path.isdir(MODES_DIR), "modes/ directory missing"

    def test_mode_count(self):
        modes = [f for f in os.listdir(MODES_DIR) if f.endswith(".md")]
        assert len(modes) >= 7, f"Expected at least 7 modes, found {len(modes)}"


class TestModeContent:
    """Verify mode files have required content."""

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_has_frontmatter(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        with open(path) as f:
            content = f.read()
        assert content.startswith("---"), f"{mode}.md missing YAML frontmatter"
        assert content.count("---") >= 2, f"{mode}.md frontmatter not closed"

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_has_name(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        with open(path) as f:
            content = f.read()
        assert "name:" in content, f"{mode}.md missing 'name' field"

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_has_description(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content, f"{mode}.md missing 'description' field"

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_has_guidelines(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        with open(path) as f:
            content = f.read()
        assert "##" in content, f"{mode}.md missing section headers"


class TestModeCommand:
    """Verify /mode command exists."""

    def test_mode_command_exists(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "mode.md")
        assert os.path.isfile(path), "/mode command file missing"

    def test_mode_command_has_frontmatter(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "mode.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content
        assert "argument-hint:" in content
