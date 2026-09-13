"""Tests for behavioral modes system."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
MODES_DIR = os.path.join(ROOT, ".claude", "modes")
COMMANDS_DIR = os.path.join(ROOT, ".claude", "commands")

EXPECTED_MODES = [
    "default",
    "brainstorm",
    "token-efficient",
    "deep-research",
    "implementation",
    "review",
    "orchestration",
    "action-first",
]


class TestModesExist:
    """Verify all 8 behavioral mode files exist."""

    @pytest.mark.parametrize("mode", EXPECTED_MODES)
    def test_mode_file_exists(self, mode):
        path = os.path.join(MODES_DIR, f"{mode}.md")
        assert os.path.isfile(path), f"Mode file missing: {mode}.md"

    def test_modes_directory_exists(self):
        assert os.path.isdir(MODES_DIR), "modes/ directory missing"

    def test_mode_count(self):
        modes = [f for f in os.listdir(MODES_DIR) if f.endswith(".md")]
        assert len(modes) >= 8, f"Expected at least 8 modes, found {len(modes)}"


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
        path = os.path.join(COMMANDS_DIR, "mode.md")
        assert os.path.isfile(path), "/mode command file missing"

    def test_mode_command_has_frontmatter(self):
        path = os.path.join(COMMANDS_DIR, "mode.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content
        assert "argument-hint:" in content


class TestActionFirstRules:
    """Behavioral: each action-first rule is present, so deleting one fails a test."""

    PATH = os.path.join(MODES_DIR, "action-first.md")

    @pytest.mark.parametrize("phrase", [
        "name: action-first",
        "The first line is the answer, or the next action the user must take",
        "One action per step",
        "No tangents",
        "Done: ... / Now: ... / Next: ...",
        "Time estimates",
        "Name the wins",
        "Lists capped at 5",
        "N more",
        "No preamble, no recap, no closers",
        "Bold the one thing not to miss",
        "Never drop error output, security warnings, or destructive-action",
        "Do this / Not this",
        "### Question",
        "### Task done",
        "### Blocked",
        "### Multi-step instructions",
    ])
    def test_rule_present(self, phrase):
        with open(self.PATH) as f:
            content = f.read()
        assert phrase in content, f"action-first.md lost rule text: {phrase!r}"

    def test_mode_command_lists_action_first(self):
        with open(os.path.join(COMMANDS_DIR, "mode.md")) as f:
            content = f.read()
        assert "| `action-first` |" in content
        assert "/mode action-first" in content
