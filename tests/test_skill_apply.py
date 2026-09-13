"""`ck skill apply` -- enforce the profile's `disabled` via Claude Code `skillOverrides`.

Every test builds a real project under tmp_path, drives the real CLI, and asserts on the
JSON on disk and on what `ck doctor` / `ck diff` then say. Threat model: the profile is
repository content. It must not hide a protected skill, and apply must never destroy or
rewrite a settings key it does not own -- above all the `ECC_HOOK_PROFILE` env entry this
repo's own enforcement depends on.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"), ECC_HOOK_PROFILE="minimal",
           CLAUDEKIT_HOME=str(REPO_ROOT))

SKILLS = {
    "java-review-checklist": "Use when a diff contains .java files",
    "spring-notes": "Use when wiring Spring Boot beans",
    "golden-rule": "Use before proposing any code change",
    "house-mandatory": "Use when the registry says it is mandatory",
    "agent-core": "Use when the agent says it must load this",
    "preloaded": "Use when the agent preloads this",
    "block-preloaded": "Use when the agent preloads this as a block list",
}
USER_SETTINGS = {
    "env": {"ECC_HOOK_PROFILE": "minimal"},
    "permissions": {"allow": ["Bash(ls:*)"]},
    "skillOverrides": {"spring-notes": "name-only"},
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


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    skills_dir = root / ".claude" / "skills"
    for name, description in SKILLS.items():
        (skills_dir / name).mkdir(parents=True)
        (skills_dir / name / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n',
            encoding="utf-8")
    (skills_dir / "skills-registry.json").write_text(json.dumps({
        "version": "2.0", "agentMapping": {},
        "skills": [{"id": "house-mandatory", "mandatory": True}]}), encoding="utf-8")
    agents = root / ".claude" / "agents"
    agents.mkdir()
    (agents / "worker.md").write_text(
        "---\nname: worker\nskills: [preloaded]\n---\n\n## Skill Loading\n\n"
        "**Mandatory (load before any work, in order):**\n\n1. **agent-core** - always\n\n"
        "**On demand (load when the trigger fires):**\n\n- **java-review-checklist** - "
        "on .java\n\n## Next\n", encoding="utf-8")
    (agents / "helper.md").write_text(
        "---\nname: helper\nskills:\n  - block-preloaded\n---\n\nbody\n", encoding="utf-8")
    settings_local(root).write_text(json.dumps(USER_SETTINGS, indent=4), encoding="utf-8")
    return root


def settings_local(root):
    return root / ".claude" / "settings.local.json"


def read_settings(root):
    return json.loads(settings_local(root).read_text(encoding="utf-8"))


def profile(root, disabled, **extra):
    (root / ".claude" / "skills-profile.json").write_text(
        json.dumps(dict({"disabled": disabled}, **extra)), encoding="utf-8")


def apply_json(root, *extra):
    proc = ck(root, "skill", "apply", "--json", *extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def doctor_out(root):
    proc = ck(root, "doctor")
    return proc.returncode, proc.stdout + proc.stderr


class TestApply:
    def test_merges_off_and_preserves_every_other_key(self, project):
        profile(project, ["java-review-checklist"])
        skills_before = {k: v for k, v in tree_digest(project).items() if "/skills/" in k}
        result = apply_json(project)
        assert result["hidden"] == ["java-review-checklist"]
        assert result["tokens_saved"] == (len(SKILLS["java-review-checklist"]) + 3) // 4
        doc = read_settings(project)
        assert doc["env"] == {"ECC_HOOK_PROFILE": "minimal"}
        assert doc["permissions"] == USER_SETTINGS["permissions"]
        assert doc["skillOverrides"] == {"spring-notes": "name-only",
                                         "java-review-checklist": "off"}
        record = json.loads((project / ".claude" / "skills-applied.json").read_text())
        assert record["managed"] == {"java-review-checklist": "off"}
        assert {k: v for k, v in tree_digest(project).items()
                if "/skills/" in k} == skills_before

    def test_disabled_mode_user_invocable_only(self, project):
        profile(project, ["java-review-checklist"], disabled_mode="user-invocable-only")
        apply_json(project)
        assert read_settings(project)["skillOverrides"]["java-review-checklist"] == \
            "user-invocable-only"

    def test_an_unknown_disabled_mode_is_refused(self, project):
        profile(project, ["java-review-checklist"], disabled_mode="name-only")
        before = tree_digest(project)
        proc = ck(project, "skill", "apply")
        assert proc.returncode == 1
        assert "disabled_mode" in proc.stderr
        assert tree_digest(project) == before

    def test_restore_removes_exactly_what_apply_wrote(self, project):
        profile(project, ["java-review-checklist"])
        apply_json(project)
        result = apply_json(project, "--restore")
        assert result["removed"] == ["java-review-checklist"]
        assert read_settings(project) == USER_SETTINGS
        assert not (project / ".claude" / "skills-applied.json").exists()

    def test_a_user_set_override_is_never_taken_over_or_removed(self, project):
        profile(project, ["spring-notes"])
        result = apply_json(project)
        assert result["kept_user_set"] == ["spring-notes"]
        assert read_settings(project)["skillOverrides"]["spring-notes"] == "name-only"
        apply_json(project, "--restore")
        assert read_settings(project)["skillOverrides"]["spring-notes"] == "name-only"

    def test_a_value_the_user_changed_after_apply_survives_restore(self, project):
        profile(project, ["java-review-checklist"])
        apply_json(project)
        doc = read_settings(project)
        doc["skillOverrides"]["java-review-checklist"] = "on"
        settings_local(project).write_text(json.dumps(doc), encoding="utf-8")
        result = apply_json(project, "--restore")
        assert result["kept_user_set"] == ["java-review-checklist"]
        assert read_settings(project)["skillOverrides"]["java-review-checklist"] == "on"

    def test_dropping_a_name_converges_and_rerun_is_a_noop(self, project):
        profile(project, ["java-review-checklist"])
        apply_json(project)
        mtime = settings_local(project).stat().st_mtime_ns
        apply_json(project)
        assert settings_local(project).stat().st_mtime_ns == mtime
        profile(project, [])
        assert apply_json(project)["removed"] == ["java-review-checklist"]
        assert "java-review-checklist" not in read_settings(project)["skillOverrides"]

    def test_creates_settings_local_when_absent_and_drops_an_empty_block(self, project):
        settings_local(project).unlink()
        profile(project, ["java-review-checklist"])
        apply_json(project)
        assert read_settings(project) == {"skillOverrides": {"java-review-checklist": "off"}}
        apply_json(project, "--restore")
        assert read_settings(project) == {}

    def test_not_installed_names_are_reported_not_written(self, project):
        profile(project, ["never-installed"])
        result = apply_json(project)
        assert result["skipped"] == [{"name": "never-installed", "reason": "not installed"}]
        assert read_settings(project) == USER_SETTINGS

    @pytest.mark.parametrize("content", ["{not json", "[]", '{"skillOverrides": []}'])
    def test_an_unparseable_settings_file_is_never_overwritten(self, project, content):
        settings_local(project).write_text(content, encoding="utf-8")
        profile(project, ["java-review-checklist"])
        before = tree_digest(project)
        proc = ck(project, "skill", "apply")
        assert proc.returncode == 1
        assert "nothing was changed" in proc.stderr
        assert tree_digest(project) == before

    def test_a_symlinked_settings_file_is_not_written_through(self, project, tmp_path):
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        settings_local(project).unlink()
        settings_local(project).symlink_to(outside)
        profile(project, ["java-review-checklist"])
        proc = ck(project, "skill", "apply")
        assert proc.returncode == 1
        assert outside.read_text(encoding="utf-8") == "{}"

    def test_no_kit_file_changes_so_diff_is_unaffected(self, project):
        claude = project / ".claude"
        files = {str(p.relative_to(claude)): sha(p) for p in claude.rglob("*")
                 if p.is_file() and p.name != "settings.local.json"}
        (claude / ".claudekit-manifest.json").write_text(
            json.dumps({"version": "t", "mode": "full", "files": files}), encoding="utf-8")
        profile(project, ["java-review-checklist"])
        apply_json(project)
        diff = ck(project, "diff")
        assert "modified" not in diff.stdout + diff.stderr, diff.stdout


class TestHostileProfile:
    @pytest.mark.parametrize("name,why", [
        ("golden-rule", "kit safety rail"),
        ("house-mandatory", "registry mandatory"),
        ("agent-core", "mandatory load for agent worker"),
        ("preloaded", "preloaded by agent worker"),
        ("block-preloaded", "preloaded by agent helper"),
    ])
    def test_a_protected_skill_refuses_the_whole_profile(self, project, name, why):
        profile(project, ["java-review-checklist", name])
        before = tree_digest(project)
        proc = ck(project, "skill", "apply")
        assert proc.returncode == 1
        assert name in proc.stderr and why in proc.stderr
        assert "nothing was changed" in proc.stderr
        assert tree_digest(project) == before
        code, out = doctor_out(project)
        assert code == 1
        assert f"protected skill '{name}'" in out

    def test_an_on_demand_agent_skill_is_not_protected(self, project):
        profile(project, ["java-review-checklist"])
        assert apply_json(project)["hidden"] == ["java-review-checklist"]

    def test_a_path_shaped_name_is_refused_before_any_write(self, project):
        profile(project, ["java-review-checklist", "../../etc"])
        before = tree_digest(project)
        assert ck(project, "skill", "apply").returncode == 1
        assert tree_digest(project) == before

    @pytest.mark.parametrize("settings_name", ["settings.json", "settings.local.json"])
    def test_doctor_fails_when_settings_already_hide_a_protected_skill(self, project,
                                                                      settings_name):
        path = project / ".claude" / settings_name
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        doc["skillOverrides"] = {"golden-rule": "off"}
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, out = doctor_out(project)
        assert code == 1
        assert "skillOverrides hides protected skill(s): golden-rule" in out

    def test_a_forged_record_cannot_remove_a_user_value_it_does_not_match(self, project):
        (project / ".claude" / "skills-applied.json").write_text(json.dumps(
            {"schema": 1, "managed": {"spring-notes": "off"}}), encoding="utf-8")
        apply_json(project, "--restore")
        assert read_settings(project)["skillOverrides"]["spring-notes"] == "name-only"


class TestDoctor:
    def test_reports_divergence_then_tokens_saved(self, project):
        profile(project, ["java-review-checklist"])
        _, out = doctor_out(project)
        assert "java-review-checklist is disabled but not set to off" in out
        apply_json(project)
        _, out = doctor_out(project)
        saved = (len(SKILLS["java-review-checklist"]) + 3) // 4
        assert (f"Skill visibility: 1 skill(s) hidden via skillOverrides, ~{saved} "
                f"always-on tokens saved") in out

    def test_hidden_but_no_longer_disabled_warns(self, project):
        profile(project, ["java-review-checklist"])
        apply_json(project)
        profile(project, [])
        _, out = doctor_out(project)
        assert "java-review-checklist is still hidden but no longer disabled" in out

    def test_no_profile_and_no_overrides_adds_no_check(self, project):
        settings_local(project).write_text('{"env": {}}', encoding="utf-8")
        _, out = doctor_out(project)
        assert "Skill visibility" not in out


def _install(dest):
    subprocess.run(["git", "init", "-q", "."], cwd=str(dest), check=True)
    proc = subprocess.run(["bash", str(REPO_ROOT / "install.sh"), "--full", "--yes", "."],
                          cwd=str(dest), capture_output=True, text=True, timeout=300,
                          env=ENV)
    assert proc.returncode == 0, proc.stdout + proc.stderr


class TestRealInstall:
    def test_update_keeps_the_overrides_the_record_and_the_hook_profile(self, tmp_path):
        _install(tmp_path)
        settings_local(tmp_path).write_text(
            json.dumps({"env": {"ECC_HOOK_PROFILE": "minimal"}}), encoding="utf-8")
        profile(tmp_path, ["java-review-checklist"])
        assert apply_json(tmp_path)["hidden"] == ["java-review-checklist"]
        diff = ck(tmp_path, "diff")
        assert "modified" not in diff.stdout + diff.stderr, diff.stdout

        update = ck(tmp_path, "update", "--yes")
        assert update.returncode == 0, update.stdout + update.stderr
        assert "Skills profile re-applied: 1 skill(s) hidden" in update.stdout
        assert read_settings(tmp_path) == {
            "env": {"ECC_HOOK_PROFILE": "minimal"},
            "skillOverrides": {"java-review-checklist": "off"}}
        assert (tmp_path / ".claude" / "skills-applied.json").is_file()
        result = apply_json(tmp_path, "--restore")
        assert result["removed"] == ["java-review-checklist"]
        assert read_settings(tmp_path) == {"env": {"ECC_HOOK_PROFILE": "minimal"}}
