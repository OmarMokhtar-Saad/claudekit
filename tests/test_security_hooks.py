"""Tests for security hooks."""
import os

import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
HOOKS_DIR = os.path.join(TEMPLATE_DIR, "hooks")

SECURITY_HOOKS = ["file-guard.sh", "check-comment-replacement.sh", "prompt-injection-scanner.sh"]
ALL_HOOKS = SECURITY_HOOKS + ["auto-checkpoint.sh"]


class TestHookFiles:
    """Verify security hook files exist and are executable."""

    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_hook_exists(self, hook):
        path = os.path.join(HOOKS_DIR, hook)
        assert os.path.isfile(path), f"Hook missing: {hook}"

    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_hook_is_executable(self, hook):
        path = os.path.join(HOOKS_DIR, hook)
        assert os.access(path, os.X_OK), f"Hook not executable: {hook}"

    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_hook_has_shebang(self, hook):
        path = os.path.join(HOOKS_DIR, hook)
        with open(path) as f:
            first_line = f.readline()
        assert first_line.startswith("#!/"), f"Hook missing shebang: {hook}"

    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_hook_uses_strict_mode(self, hook):
        path = os.path.join(HOOKS_DIR, hook)
        with open(path) as f:
            content = f.read()
        assert "set -e" in content or "set -euo pipefail" in content, f"Hook missing strict mode: {hook}"


class TestFileGuard:
    """Verify file-guard covers key sensitive patterns."""

    @pytest.fixture
    def file_guard_content(self):
        path = os.path.join(HOOKS_DIR, "file-guard.sh")
        with open(path) as f:
            return f.read()

    def test_checks_env_files(self, file_guard_content):
        assert ".env" in file_guard_content

    def test_checks_ssh_keys(self, file_guard_content):
        assert "id_rsa" in file_guard_content

    def test_checks_credentials(self, file_guard_content):
        assert "credentials" in file_guard_content.lower()

    def test_checks_aws_config(self, file_guard_content):
        assert ".aws" in file_guard_content

    def test_checks_pem_files(self, file_guard_content):
        assert "pem" in file_guard_content

    def test_checks_terraform_state(self, file_guard_content):
        assert "tfstate" in file_guard_content


class TestAgentignore:
    """Verify .agentignore template exists."""

    def test_agentignore_exists(self):
        path = os.path.join(TEMPLATE_DIR, ".agentignore")
        assert os.path.isfile(path)

    def test_agentignore_has_patterns(self):
        path = os.path.join(TEMPLATE_DIR, ".agentignore")
        with open(path) as f:
            content = f.read()
        assert ".env" in content
        assert ".ssh" in content or "id_rsa" in content
