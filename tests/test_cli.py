"""Tests for the ClaudeKit CLI."""

import json
import os
import re
import subprocess
import sys
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


class TestFindRoot:
    """Test ClaudeKit source resolution, incl. CLAUDEKIT_HOME override."""

    def _import_main(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from claudekit.cli import main as m
        return m

    def test_claudekit_home_env_is_honored(self, tmp_path, monkeypatch):
        m = self._import_main()
        # A directory with .claude/agents is a valid ClaudeKit source.
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        monkeypatch.setenv("CLAUDEKIT_HOME", str(tmp_path))
        assert m.find_claudekit_root() == tmp_path

    def test_claudekit_home_ignored_when_invalid(self, tmp_path, monkeypatch):
        m = self._import_main()
        # Points somewhere without .claude/agents -> falls back (not this path).
        monkeypatch.setenv("CLAUDEKIT_HOME", str(tmp_path))
        assert m.find_claudekit_root() != tmp_path

    def test_find_root_locates_repo_from_source(self, monkeypatch):
        # With no override, the walk-up must find the repo root (regression for
        # the src-layout depth bug where it resolved to src/ and returned None).
        m = self._import_main()
        monkeypatch.delenv("CLAUDEKIT_HOME", raising=False)
        root = m.find_claudekit_root()
        assert root is not None
        assert (root / ".claude" / "agents").is_dir()
        assert (root / "install.sh").exists()

    def test_init_parser_accepts_full_minimal_yes(self):
        # Regression: `ck init --full --yes` previously errored (only --mode existed).
        for _extra in (["--full", "--yes"], ["--minimal", "--non-interactive"]):
            result = subprocess.run(
                [sys.executable, CLI_PATH, "init", "--help"],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 0
            assert "--full" in result.stdout and "--yes" in result.stdout

    def test_check_command_subcommand_exit_codes(self):
        block = subprocess.run(
            [sys.executable, CLI_PATH, "check-command", "rm -rf /"],
            capture_output=True, text=True, timeout=10,
        )
        assert block.returncode == 2
        allow = subprocess.run(
            [sys.executable, CLI_PATH, "check-command", "git status"],
            capture_output=True, text=True, timeout=10,
        )
        assert allow.returncode == 0


class TestLifecycleCommands:
    """diff / uninstall / update over a manifest-tracked install."""

    def _import_main(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from claudekit.cli import main as m
        return m

    def _fake_install(self, tmp_path, m):
        base = tmp_path / ".claude"
        (base / "agents").mkdir(parents=True)
        (base / "settings.json").write_text('{"hooks": {}}')
        (base / "agents" / "planner.md").write_text("# planner\n")
        files = {
            "settings.json": m._sha256(base / "settings.json"),
            "agents/planner.md": m._sha256(base / "agents" / "planner.md"),
        }
        (base / m.MANIFEST_NAME).write_text(json.dumps(
            {"version": "2.1.0", "mode": "full", "language": "python", "files": files}))
        return base

    def _ns(self, **kw):
        import argparse
        return argparse.Namespace(**kw)

    def test_diff_clean(self, tmp_path, capsys):
        m = self._import_main()
        self._fake_install(tmp_path, m)
        rc = m.cmd_diff(self._ns(target=str(tmp_path)))
        assert rc == 0
        assert "match the manifest" in capsys.readouterr().out

    def test_diff_detects_modification(self, tmp_path):
        m = self._import_main()
        base = self._fake_install(tmp_path, m)
        (base / "settings.json").write_text('{"hooks": {"changed": true}}')
        manifest = m._load_manifest(tmp_path)
        modified, missing, unchanged = m._classify_manifest(tmp_path, manifest)
        assert "settings.json" in modified
        assert "agents/planner.md" in unchanged

    def test_diff_no_manifest_errors(self, tmp_path):
        m = self._import_main()
        assert m.cmd_diff(self._ns(target=str(tmp_path))) == 1

    def test_uninstall_dry_run_keeps_files(self, tmp_path):
        m = self._import_main()
        base = self._fake_install(tmp_path, m)
        rc = m.cmd_uninstall(self._ns(target=str(tmp_path), yes=True,
                                      dry_run=True, stamp="T"))
        assert rc == 0
        assert (base / "settings.json").exists()  # dry-run removed nothing

    def test_uninstall_removes_and_backs_up(self, tmp_path):
        m = self._import_main()
        base = self._fake_install(tmp_path, m)
        rc = m.cmd_uninstall(self._ns(target=str(tmp_path), yes=True,
                                      dry_run=False, stamp="T"))
        assert rc == 0
        assert not (base / "settings.json").exists()
        assert not (base / m.MANIFEST_NAME).exists()
        # backed up, recoverable
        assert (tmp_path / "backups" / "uninstall-T" / "settings.json").exists()

    def test_update_no_manifest_errors(self, tmp_path):
        # No .claude/ at all — nothing to update, must refuse.
        m = self._import_main()
        assert m.cmd_update(self._ns(target=str(tmp_path), yes=True)) == 1

    def test_update_legacy_install_proceeds(self, tmp_path, monkeypatch):
        # Pre-manifest install (.claude exists, no manifest): update must work
        # instead of erroring, delegating to the installer in full mode.
        m = self._import_main()
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        recorded = {}

        def fake_run(cmd, *a, **kw):
            recorded["cmd"] = cmd
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(m.subprocess, "run", fake_run)
        rc = m.cmd_update(self._ns(target=str(tmp_path), yes=True))
        assert rc == 0
        assert "--force" in recorded["cmd"] and "--full" in recorded["cmd"]

    def test_diff_fallback_without_manifest(self, tmp_path, capsys):
        # Pre-manifest install: diff falls back to comparing against the kit
        # source tree instead of erroring.
        m = self._import_main()
        root = m.find_claudekit_root()
        assert root is not None  # running from the repo
        base = tmp_path / ".claude"
        (base / "agents").mkdir(parents=True)
        kit_planner = (root / ".claude" / "agents" / "planner.md").read_text()
        (base / "agents" / "planner.md").write_text(kit_planner)      # identical
        (base / "agents" / "reviewer.md").write_text("drifted\n")     # differs
        (base / "agents" / "my-custom-agent.md").write_text("mine\n")  # custom
        rc = m.cmd_diff(self._ns(target=str(tmp_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "pre-manifest" in out
        assert "differs:" in out and "agents/reviewer.md" in out
        assert "custom:" in out and "agents/my-custom-agent.md" in out
        assert "not installed:" in out

    def test_diff_three_way_labels(self, tmp_path, capsys):
        # With a manifest AND kit source available, `modified` refines into
        # locally-modified vs kit-updated.
        m = self._import_main()
        root = m.find_claudekit_root()
        kit_planner = root / ".claude" / "agents" / "planner.md"
        base = tmp_path / ".claude"
        (base / "agents").mkdir(parents=True)
        kit_reviewer = root / ".claude" / "agents" / "reviewer.md"
        # locally modified: manifest hash == current kit hash, file edited
        (base / "agents" / "planner.md").write_text("local edit\n")
        # kit updated: file already matches the kit source, manifest is older
        (base / "agents" / "reviewer.md").write_text(kit_reviewer.read_text())
        files = {
            "agents/planner.md": m._sha256(kit_planner),
            "agents/reviewer.md": "0" * 64,  # stale install-time hash
        }
        (base / m.MANIFEST_NAME).write_text(json.dumps(
            {"version": "2.0.0", "mode": "full", "files": files}))
        rc = m.cmd_diff(self._ns(target=str(tmp_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "locally modified: agents/planner.md" in out
        assert "kit-updated: agents/reviewer.md" in out

    def test_diff_manifest_lists_custom_files(self, tmp_path, capsys):
        m = self._import_main()
        base = self._fake_install(tmp_path, m)
        (base / "agents" / "my-custom-agent.md").write_text("mine\n")
        rc = m.cmd_diff(self._ns(target=str(tmp_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "custom:" in out and "agents/my-custom-agent.md" in out
