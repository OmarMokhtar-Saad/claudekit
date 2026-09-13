"""`.claude/skills-profile.json` is the PROJECT's file: install, update and fleet sync
must leave it byte-identical.

Behavioural: the real installer is run twice, and the real fleet-sync script is run
against a temp fleet, rather than asserting that source text mentions the filename.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
FLEET_SYNC = REPO / ".claude" / "operations" / "scripts" / "fleet-sync.py"
ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal")
PROFILE = '{\n  "disabled": ["java-review-checklist"],\n  "roles": {"planner": []}\n}\n'


def _install(dest):
    subprocess.run(["git", "init", "-q", "."], cwd=str(dest), check=True)
    proc = subprocess.run(["bash", str(INSTALL), "--full", "--yes", "."], cwd=str(dest),
                          capture_output=True, text=True, timeout=300, env=ENV)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(dest) / ".claude"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestInstallPreservesTheProfile:
    def test_the_kit_does_not_ship_a_profile(self, tmp_path):
        """If the kit tree ever carried one, an install would overwrite the project's."""
        claude = _install(tmp_path)
        assert not (claude / "skills-profile.json").exists()
        assert not (REPO / ".claude" / "skills-profile.json").exists()

    def test_a_reinstall_leaves_the_profile_byte_identical(self, tmp_path):
        claude = _install(tmp_path)
        profile = claude / "skills-profile.json"
        profile.write_text(PROFILE, encoding="utf-8")
        before = _sha(profile)
        _install(tmp_path)
        assert _sha(profile) == before

    def test_it_survives_even_when_the_manifest_claims_it(self, tmp_path):
        """Ownership by name, never by a manifest a previous build may have got wrong --
        the same transition class that once cost a project its agent memory."""
        claude = _install(tmp_path)
        profile = claude / "skills-profile.json"
        profile.write_text(PROFILE, encoding="utf-8")
        manifest = claude / ".claudekit-manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["files"]["skills-profile.json"] = _sha(profile)
        manifest.write_text(json.dumps(data), encoding="utf-8")
        _install(tmp_path)
        assert profile.read_text(encoding="utf-8") == PROFILE


class TestFleetSyncPreservesTheProfile:
    def test_a_sync_run_leaves_the_profile_byte_identical(self, tmp_path, monkeypatch):
        fleet = tmp_path / "fleet"
        project = fleet / "demo"
        (project / ".claude" / "skills").mkdir(parents=True)
        (project / ".claude" / "skills" / "skills-registry.json").write_text(
            json.dumps({"skills": []}), encoding="utf-8")
        profile = project / ".claude" / "skills-profile.json"
        profile.write_text(PROFILE, encoding="utf-8")
        before = _sha(profile)

        spec = importlib.util.spec_from_file_location("fleet_sync_under_test", FLEET_SYNC)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "ROOT", str(fleet))
        monkeypatch.setattr(module, "KIT_SKILLS", str(REPO / ".claude" / "skills"))
        monkeypatch.setattr(module, "STACKS", {"demo": ["python"]})
        monkeypatch.setattr(sys, "argv", ["fleet-sync.py", "--report",
                                          str(tmp_path / "report.md")])
        module.main()

        assert (project / ".claude" / "skills" / "python-review-checklist").is_dir(), \
            "fixture invalid: the sync did not run against the temp fleet"
        assert _sha(profile) == before
