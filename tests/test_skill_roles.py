"""`ck skill roles` -- bind generic agents' skill roles to a project's installed skills.

Every behavioral test builds a real project under tmp_path from the kit's OWN role agent
files, drives the real CLI, and asserts on the bytes on disk and on what `ck diff` /
`ck doctor` then say. Threat model: the profile is repository content. A binding may only
ADD a preload of an installed, model-visible skill under .claude/skills/; it must never
remove a mandatory Skill Loading line, reach outside .claude/skills/, or hide a
protected skill -- and every refusal must leave the tree untouched.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from claudekit import skill_fit, skill_roles  # noqa: E402

ENV = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"), ECC_HOOK_PROFILE="minimal",
           CLAUDEKIT_HOME=str(REPO_ROOT))
ROLE_AGENTS = sorted(skill_roles.ROLE_CATALOG)
KIT_AGENTS = REPO_ROOT / ".claude" / "agents"
SKILLS = {
    "pytest-debugging": "Use when a pytest run fails",
    "python-gotchas": "Use when touching this project's Python code",
    "junit-debugging": "Use when a JUnit run fails",
    "extra-one": "Use for extra one",
    "golden-rule": "Use before proposing any code change",
}


def ck(root, *args):
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", *args],
                          capture_output=True, text=True, cwd=str(root), env=ENV,
                          timeout=300)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_digest(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(Path(root).rglob("*"))
            if p.is_file() and not p.is_symlink()}


def kit_bytes(agent):
    return (KIT_AGENTS / f"{agent}.md").read_bytes()


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    claude = root / ".claude"
    for name, description in SKILLS.items():
        (claude / "skills" / name).mkdir(parents=True)
        (claude / "skills" / name / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n',
            encoding="utf-8")
    (claude / "skills" / "hidden-one").mkdir()
    (claude / "skills" / "hidden-one" / "SKILL.md").write_text(
        "---\nname: hidden-one\ndescription: x\ndisable-model-invocation: true\n---\n",
        encoding="utf-8")
    (claude / "skills" / "skills-registry.json").write_text(
        json.dumps({"version": "2.0", "agentMapping": {}, "skills": []}), encoding="utf-8")
    (claude / "agents").mkdir()
    for agent in ROLE_AGENTS:
        (claude / "agents" / f"{agent}.md").write_bytes(kit_bytes(agent))
    files = {str(p.relative_to(claude)): sha(p) for p in claude.rglob("*") if p.is_file()}
    (claude / ".claudekit-manifest.json").write_text(
        json.dumps({"version": "t", "mode": "full", "files": files}, indent=2),
        encoding="utf-8")
    return root


def profile(root, roles, disabled=()):
    (root / ".claude" / "skills-profile.json").write_text(json.dumps(
        {"schema": 1, "packs": [], "disabled": list(disabled), "overlays": {},
         "roles": roles}, indent=2), encoding="utf-8")


def apply_json(root):
    proc = ck(root, "skill", "roles", "apply", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def agent_path(root, agent):
    return root / ".claude" / "agents" / f"{agent}.md"


def preloads(root, agent):
    return skill_fit.agent_preloaded_skills(agent_path(root, agent).read_text("utf-8"))


def body(data):
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    return text[text.index("\n---\n", 3):]


class TestKitContract:
    def test_role_agents_exist_and_ship_no_skills_key(self):
        for agent in ROLE_AGENTS:
            text = kit_bytes(agent).decode("utf-8")
            assert skill_fit.agent_preloaded_skills(text) == [], agent
            assert skill_roles.with_skills(text, []) == text, agent

    def test_a_block_sequence_skills_key_is_replaced_whole(self):
        text = "---\nname: x\nskills:\n  - a\n  - b\ntools: [Read]\n---\n\n  - body item\n"
        assert skill_roles.with_skills(text, ["c"]) == (
            "---\nname: x\ntools: [Read]\nskills: [c]\n---\n\n  - body item\n")
        assert skill_roles.with_skills(text, []) == (
            "---\nname: x\ntools: [Read]\n---\n\n  - body item\n")

    def test_every_declared_role_is_described(self):
        declared = {r for roles in skill_roles.ROLE_CATALOG.values() for r in roles}
        assert declared == set(skill_roles.ROLE_DESCRIPTIONS)


class TestApply:
    def test_binds_by_id_and_by_skill_path_and_restamps_the_receipt(self, project):
        profile(project, {"stack-debugging": "pytest-debugging",
                          "project-gotchas": ".claude/skills/python-gotchas/SKILL.md"})
        result = apply_json(project)
        assert result["written"] == ROLE_AGENTS
        assert preloads(project, "debugger") == ["pytest-debugging", "python-gotchas"]
        assert preloads(project, "tester") == ["python-gotchas"]
        assert preloads(project, "code-reviewer") == ["python-gotchas"]
        for agent in ROLE_AGENTS:
            assert body(agent_path(project, agent).read_bytes()) == body(kit_bytes(agent))
        manifest = json.loads((project / ".claude" / ".claudekit-manifest.json").read_text())
        for agent in ROLE_AGENTS:
            assert manifest["files"][f"agents/{agent}.md"] == sha(agent_path(project, agent))
        diff = ck(project, "diff")
        assert "modified" not in diff.stdout + diff.stderr, diff.stdout

    def test_frontmatter_stays_key_lines_and_protection_widens(self, project):
        before = skill_fit.protected_skills(project)
        profile(project, {"stack-debugging": "pytest-debugging"})
        apply_json(project)
        after = skill_fit.protected_skills(project)
        assert set(before) <= set(after)
        assert "pytest-debugging" in after
        fm = agent_path(project, "debugger").read_text("utf-8").split("\n---\n", 1)[0]
        for line in fm.split("\n")[1:]:
            assert line == "" or line.startswith((" ", "\t")) or ":" in line.split(" ")[0]

    def test_a_bound_skill_cannot_then_be_disabled(self, project):
        profile(project, {"stack-debugging": "pytest-debugging"})
        apply_json(project)
        profile(project, {"stack-debugging": "pytest-debugging"},
                disabled=["pytest-debugging"])
        proc = ck(project, "skill", "roles", "apply")
        assert proc.returncode == 1
        assert "disables" in proc.stderr

    def test_idempotent(self, project):
        profile(project, {"project-gotchas": "python-gotchas"})
        apply_json(project)
        digest = tree_digest(project)
        result = apply_json(project)
        assert result["written"] == [] and result["restamped"] == []
        assert tree_digest(project) == digest

    def test_unbinding_restores_kit_bytes_and_receipt(self, project):
        manifest_path = project / ".claude" / ".claudekit-manifest.json"
        original = json.loads(manifest_path.read_text())["files"]
        profile(project, {"stack-debugging": ["pytest-debugging", "junit-debugging"]})
        apply_json(project)
        profile(project, {})
        apply_json(project)
        for agent in ROLE_AGENTS:
            assert agent_path(project, agent).read_bytes() == kit_bytes(agent)
        assert json.loads(manifest_path.read_text())["files"] == original

    def test_a_local_edit_keeps_its_old_receipt(self, project):
        path = agent_path(project, "debugger")
        path.write_bytes(path.read_bytes() + b"\nlocal note\n")
        profile(project, {"stack-debugging": "pytest-debugging"})
        result = apply_json(project)
        assert result["not_restamped"] == ["debugger"]
        diff = ck(project, "diff")
        assert "debugger.md" in diff.stdout + diff.stderr

    def test_recovers_when_the_receipt_write_was_lost(self, project):
        path = agent_path(project, "tester")
        path.write_text(skill_roles.with_skills(path.read_text("utf-8"), ["python-gotchas"]),
                        encoding="utf-8")
        profile(project, {"project-gotchas": "python-gotchas"})
        result = apply_json(project)
        assert "tester" in result["restamped"]
        manifest = json.loads((project / ".claude" / ".claudekit-manifest.json").read_text())
        assert manifest["files"]["agents/tester.md"] == sha(path)

    def test_refuses_the_kit_source_tree(self, project):
        (project / "scripts").mkdir()
        (project / "scripts" / "gen-registry.py").write_text("", encoding="utf-8")
        (project / "src" / "claudekit").mkdir(parents=True)
        profile(project, {"stack-debugging": "pytest-debugging"})
        proc = ck(project, "skill", "roles", "apply")
        assert proc.returncode == 1 and "source tree" in proc.stderr


class TestHostileProfile:
    @pytest.mark.parametrize("roles, fragment", [
        ({"root-access": "pytest-debugging"}, "unknown role"),
        ({"stack-debugging": "/etc/passwd"}, "neither a skill id"),
        ({"stack-debugging": "../../etc/passwd"}, "neither a skill id"),
        ({"stack-debugging": ".claude/skills/../skills/pytest-debugging/SKILL.md"},
         "neither a skill id"),
        ({"stack-debugging": ".claude/agents/debugger.md"}, "neither a skill id"),
        ({"stack-debugging": ".claude/skills/pytest-debugging/notes.md"}, "neither a skill id"),
        ({"stack-debugging": "not-installed"}, "not installed"),
        ({"stack-debugging": "hidden-one"}, "disable-model-invocation"),
        ({"stack-debugging": ["pytest-debugging", "junit-debugging", "extra-one"]},
         "the limit is"),
        ({"stack-debugging": ["pytest-debugging", "junit-debugging"],
          "project-gotchas": ["python-gotchas", "extra-one"],
          "debugging-method": "golden-rule"}, "the limit is"),
        ({"stack-debugging": 123}, "must be a skill id"),
        ({"stack-debugging": []}, "must be a skill id"),
    ])
    def test_refused_whole_before_any_write(self, project, roles, fragment):
        profile(project, roles)
        digest = tree_digest(project)
        proc = ck(project, "skill", "roles", "apply")
        assert proc.returncode == 1, proc.stdout
        assert fragment in proc.stderr, proc.stderr
        assert tree_digest(project) == digest

    def test_symlinked_skill_outside_the_skills_dir_is_refused(self, project, tmp_path):
        outside = tmp_path / "outside" / "evil"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("---\nname: evil\ndescription: x\n---\n",
                                          encoding="utf-8")
        (project / ".claude" / "skills" / "evil").symlink_to(outside)
        profile(project, {"stack-debugging": "evil"})
        digest = tree_digest(project)
        proc = ck(project, "skill", "roles", "apply")
        assert proc.returncode == 1 and "outside" in proc.stderr
        assert tree_digest(project) == digest

    def test_disabled_skill_is_refused(self, project):
        profile(project, {"stack-debugging": "pytest-debugging"},
                disabled=["pytest-debugging"])
        digest = tree_digest(project)
        proc = ck(project, "skill", "roles", "apply")
        assert proc.returncode == 1 and "hidden skill cannot be preloaded" in proc.stderr
        assert tree_digest(project) == digest


class TestCheckAndDoctor:
    def test_check_reports_drift_then_clean(self, project):
        profile(project, {"stack-debugging": "pytest-debugging"})
        proc = ck(project, "skill", "roles", "check")
        assert proc.returncode == 0
        assert "run `ck skill roles apply`" in proc.stdout + proc.stderr
        apply_json(project)
        proc = ck(project, "skill", "roles", "check")
        assert proc.returncode == 0 and "apply`" not in proc.stdout + proc.stderr

    def test_doctor_passes_warns_and_fails(self, project):
        profile(project, {"stack-debugging": "pytest-debugging"})
        apply_json(project)
        out = ck(project, "doctor")
        assert "Skill roles: 1 bound skill preload(s) resolve" in out.stdout
        path = agent_path(project, "debugger")
        path.write_bytes(kit_bytes("debugger"))
        out = ck(project, "doctor")
        assert "Skill roles" in out.stdout and "ck skill roles apply" in out.stdout
        (project / ".claude" / "skills" / "pytest-debugging" / "SKILL.md").unlink()
        out = ck(project, "doctor")
        assert "not installed" in out.stdout + out.stderr

    def test_no_roles_adds_no_doctor_check(self, project):
        profile(project, {})
        out = ck(project, "doctor")
        assert "Skill roles" not in out.stdout + out.stderr

    def test_list_names_every_role_agent(self, project):
        proc = ck(project, "skill", "roles", "list", "--json")
        assert proc.returncode == 0
        assert sorted(json.loads(proc.stdout)["agents"]) == ROLE_AGENTS


def _install(dest):
    subprocess.run(["git", "init", "-q", "."], cwd=str(dest), check=True)
    proc = subprocess.run(["bash", str(REPO_ROOT / "install.sh"), "--full", "--yes", "."],
                          cwd=str(dest), capture_output=True, text=True, timeout=300,
                          env=ENV)
    assert proc.returncode == 0, proc.stdout + proc.stderr


class TestRealInstall:
    def test_update_reapplies_roles_and_diff_stays_clean(self, tmp_path):
        _install(tmp_path)
        skill = tmp_path / ".claude" / "skills" / "house-gotchas"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            '---\nname: house-gotchas\ndescription: "Use when touching this repo"\n---\n',
            encoding="utf-8")
        profile(tmp_path, {"project-gotchas": "house-gotchas"})
        result = apply_json(tmp_path)
        assert sorted(result["written"]) == ROLE_AGENTS
        diff = ck(tmp_path, "diff")
        assert "modified" not in diff.stdout + diff.stderr, diff.stdout

        update = ck(tmp_path, "update", "--yes")
        assert update.returncode == 0, update.stdout + update.stderr
        assert "Skill roles re-applied" in update.stdout
        for agent in ROLE_AGENTS:
            assert preloads(tmp_path, agent) == ["house-gotchas"]
        diff = ck(tmp_path, "diff")
        assert "modified" not in diff.stdout + diff.stderr, diff.stdout
