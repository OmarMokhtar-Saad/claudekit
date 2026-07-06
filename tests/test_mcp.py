"""Tests for MCP server configurations."""
import json
import os
import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
MCP_DIR = os.path.join(TEMPLATE_DIR, "mcp")

EXPECTED_SERVERS = ["context7", "sequential-thinking", "playwright", "memory", "filesystem"]


class TestMCPDirectory:
    """Verify MCP directory and files exist."""

    def test_mcp_directory_exists(self):
        assert os.path.isdir(MCP_DIR), "mcp/ directory missing"

    def test_mcp_readme_exists(self):
        assert os.path.isfile(os.path.join(MCP_DIR, "README.md"))

    def test_mcp_settings_exists(self):
        assert os.path.isfile(os.path.join(MCP_DIR, "mcp-settings.json"))


class TestMCPSettings:
    """Verify MCP settings JSON is valid."""

    @pytest.fixture
    def mcp_settings(self):
        path = os.path.join(MCP_DIR, "mcp-settings.json")
        with open(path) as f:
            return json.load(f)

    def test_valid_json(self, mcp_settings):
        assert isinstance(mcp_settings, dict)

    def test_has_mcpservers_key(self, mcp_settings):
        assert "mcpServers" in mcp_settings

    @pytest.mark.parametrize("server", EXPECTED_SERVERS)
    def test_server_configured(self, mcp_settings, server):
        assert server in mcp_settings["mcpServers"], f"Server '{server}' missing"

    @pytest.mark.parametrize("server", EXPECTED_SERVERS)
    def test_server_has_command(self, mcp_settings, server):
        assert "command" in mcp_settings["mcpServers"][server]

    @pytest.mark.parametrize("server", EXPECTED_SERVERS)
    def test_server_has_args(self, mcp_settings, server):
        assert "args" in mcp_settings["mcpServers"][server]
        assert isinstance(mcp_settings["mcpServers"][server]["args"], list)


class TestMCPCommand:
    """Verify /mcp command exists."""

    def test_mcp_command_exists(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "mcp.md")
        assert os.path.isfile(path)

    def test_mcp_command_has_frontmatter(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "mcp.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content


class TestMCPSkill:
    """Verify MCP integration skill exists."""

    def test_mcp_skill_exists(self):
        path = os.path.join(TEMPLATE_DIR, "skills", "mcp-integration", "SKILL.md")
        assert os.path.isfile(path)
