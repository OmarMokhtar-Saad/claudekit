"""Tests for install.sh"""

import os
import subprocess
import tempfile
import pytest


INSTALL_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'install.sh')


class TestInstallScript:
    """Tests for the installer."""

    def test_script_exists(self):
        assert os.path.exists(INSTALL_SCRIPT)

    def test_script_executable(self):
        assert os.access(INSTALL_SCRIPT, os.X_OK)

    def test_help_flag(self):
        result = subprocess.run(
            ['bash', INSTALL_SCRIPT, '--help'],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert 'Usage' in result.stdout

    def test_install_to_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert result.returncode == 0
            assert os.path.isdir(os.path.join(tmpdir, '.claude'))
            assert os.path.isdir(os.path.join(tmpdir, '.claude', 'agents'))
            assert os.path.isdir(os.path.join(tmpdir, '.claude', 'commands'))
            assert os.path.isdir(os.path.join(tmpdir, '.claude', 'operations', 'scripts'))

    def test_agents_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            agents_dir = os.path.join(tmpdir, '.claude', 'agents')
            expected_agents = [
                'coordinator.md', 'planner.md', 'reviewer.md',
                'implementer.md', 'verifier.md', 'debugger.md',
                'documenter.md', 'gitOps.md', 'explore.md'
            ]
            for agent in expected_agents:
                assert os.path.exists(os.path.join(agents_dir, agent)), f"Missing agent: {agent}"

    def test_commands_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            cmds_dir = os.path.join(tmpdir, '.claude', 'commands')
            expected_cmds = [
                'plan.md', 'review.md', 'implement.md', 'verify.md',
                'debug.md', 'docs.md', 'git.md', 'coordinator.md'
            ]
            for cmd in expected_cmds:
                assert os.path.exists(os.path.join(cmds_dir, cmd)), f"Missing command: {cmd}"

    def test_operations_scripts_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            scripts_dir = os.path.join(tmpdir, '.claude', 'operations', 'scripts')
            expected_scripts = [
                'validate-config-json.py', 'execute-json-ops.py',
                'restore-backup.py', 'shared.py', 'operations-schema.json'
            ]
            for script in expected_scripts:
                assert os.path.exists(os.path.join(scripts_dir, script)), f"Missing script: {script}"

    def test_language_detection_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a pyproject.toml to trigger Python detection
            with open(os.path.join(tmpdir, 'pyproject.toml'), 'w') as f:
                f.write('[project]\nname = "test"\n')

            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert 'python' in result.stdout.lower()

    def test_language_detection_typescript(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'package.json'), 'w') as f:
                f.write('{"name": "test"}\n')

            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert 'typescript' in result.stdout.lower()

    def test_gitignore_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            gitignore = os.path.join(tmpdir, '.gitignore')
            assert os.path.exists(gitignore)
            with open(gitignore) as f:
                content = f.read()
            assert 'ClaudeKit' in content
            assert 'backups/' in content

    def test_nonexistent_dir_fails(self):
        result = subprocess.run(
            ['bash', INSTALL_SCRIPT, '/nonexistent/path/xyz', '--force'],
            capture_output=True, text=True
        )
        assert result.returncode != 0
