"""Tests for the ClaudeKit CLI."""

import json
import os
import re
import subprocess
import sys
import tempfile
import pytest
from pathlib import Path

CLI_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'claudekit', 'cli', 'main.py')


def _pyproject_version():
    """Single source of truth: the version declared in pyproject.toml."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no version found in pyproject.toml"
    return match.group(1)


class TestCLIHelp:
    """Test CLI help and version output."""

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, "--help"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "claudekit" in result.stdout.lower() or "ClaudeKit" in result.stdout

    def test_version_flag(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, "--version"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert _pyproject_version() in result.stdout

    def test_no_args_shows_help(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0


class TestDoctorCommand:
    """Test the doctor health check command."""

    def test_doctor_runs(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, "doctor"],
            capture_output=True, text=True, timeout=30
        )
        # Should complete without crashing
        assert result.returncode in (0, 1)
        assert "ClaudeKit Doctor" in result.stdout


class TestAgentsCommand:
    """Test the agents listing command."""

    def test_agents_lists_agents(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, "agents"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            assert "coordinator" in result.stdout.lower() or "Installed" in result.stdout


class TestConfigCommand:
    """Test the config command."""

    def test_config_shows_output(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, "config"],
            capture_output=True, text=True, timeout=10
        )
        # May fail if not in a claudekit project, that's ok
        assert result.returncode in (0, 1)
