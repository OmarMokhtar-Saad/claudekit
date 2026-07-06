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
            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert result.returncode == 0, f"Install failed: {result.stderr}"
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
            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert result.returncode == 0, f"Install failed: {result.stderr}"
            cmds_dir = os.path.join(tmpdir, '.claude', 'commands')
            expected_cmds = [
                'plan.md', 'review.md', 'implement.md', 'verify.md',
                'debug.md', 'docs.md', 'git.md', 'coordinator.md'
            ]
            for cmd in expected_cmds:
                assert os.path.exists(os.path.join(cmds_dir, cmd)), f"Missing command: {cmd}"

    def test_operations_scripts_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert result.returncode == 0, f"Install failed: {result.stderr}"
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
            result = subprocess.run(
                ['bash', INSTALL_SCRIPT, tmpdir, '--minimal', '--force'],
                capture_output=True, text=True,
                timeout=60
            )
            assert result.returncode == 0, f"Install failed: {result.stderr}"
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


class TestInstallSafety:
    """Task 005 — data-loss protection, settings.json, manifest, non-interactive."""

    def _install(self, tmpdir, *args):
        return subprocess.run(
            ['bash', INSTALL_SCRIPT, tmpdir, *args],
            capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL,
        )

    def test_full_install_ships_settings_json(self):
        # Without settings.json the hooks are dead on arrival — this was omitted for years.
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, 'pyproject.toml'), 'w').close()
            r = self._install(tmpdir, '--full', '--yes')
            assert r.returncode == 0, r.stderr
            assert os.path.isfile(os.path.join(tmpdir, '.claude', 'settings.json'))

    def test_install_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, 'go.mod'), 'w').close()
            r = self._install(tmpdir, '--full', '--yes')
            assert r.returncode == 0, r.stderr
            manifest = os.path.join(tmpdir, '.claude', '.claudekit-manifest.json')
            assert os.path.isfile(manifest)
            import json
            data = json.load(open(manifest))
            assert data['version'] and isinstance(data['files'], dict) and data['files']

    def test_yes_flag_non_interactive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            r = self._install(tmpdir, '--minimal', '--yes')
            assert r.returncode == 0, r.stderr
            assert os.path.isdir(os.path.join(tmpdir, '.claude'))

    def test_reinstall_backs_up_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            r1 = self._install(tmpdir, '--minimal', '--yes')
            assert r1.returncode == 0, r1.stderr
            r2 = self._install(tmpdir, '--minimal', '--yes', '--force')
            assert r2.returncode == 0, r2.stderr
            backups = [d for d in os.listdir(tmpdir) if d.startswith('.claude.bak-')]
            assert backups, "reinstall did not create a backup"

    def test_mid_failure_preserves_existing_claude(self):
        # The core data-loss guarantee: a mid-install failure must NOT delete the
        # user's existing .claude (the old ERR trap did `rm -rf $DEST`).
        import shutil
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template = os.path.join(repo, '.claude', 'local', 'CONSTITUTION.template.md')
        with tempfile.TemporaryDirectory() as tmpdir:
            claude = os.path.join(tmpdir, '.claude', 'local')
            os.makedirs(claude)
            sentinel = os.path.join(claude, 'CONSTITUTION.md')
            with open(sentinel, 'w') as f:
                f.write('USER CUSTOM CONTENT')
            moved = template + '.hidden'
            shutil.move(template, moved)
            try:
                r = self._install(tmpdir, '--full', '--yes', '--force')
            finally:
                shutil.move(moved, template)
            assert r.returncode != 0, "expected install to fail with the template hidden"
            # The user's file must still be there, unchanged.
            assert os.path.isfile(sentinel)
            assert open(sentinel).read() == 'USER CUSTOM CONTENT'
            staging = [d for d in os.listdir(tmpdir) if d.startswith('.claude.staging.')]
            assert not staging, "staging dir leaked after failure"
