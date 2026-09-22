"""install.sh honours what a project parked, removed, or set in settings.json.

Measured 2026-09-22 on qa-agents: two committed changes (a deleted commands/coordinator.md,
twelve agents moved to agents-unused/) came back on every `ck update`, and the project's
committed settings.json (autoCompactWindow, env thresholds, permissions.deny, skillOverrides)
was replaced by the kit's file, keeping only settings.local.json.

Two layers: direct tests of operations/scripts/install_overrides.py, then end-to-end runs of
install.sh over a real previous install.

Mutants this file kills:
  - installer ignores the skip list      -> coordinator.md / the parked agent come back
  - manifest drops parked/removed        -> the second reinstall re-creates the file
  - settings copied instead of merged    -> the four project keys are gone
  - project wins on `hooks` too          -> stale hooks survive the update
  - unparseable settings.json overwritten -> install "succeeds" and the old tree is replaced
  - modified managed file overwritten     -> git status shows M after a reinstall
  - registry copied instead of merged     -> the project's skill entry is gone
  - runtime/ staged or receipted          -> events jsonl changes / manifest churns
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
MODULE = ROOT / ".claude" / "operations" / "scripts" / "install_overrides.py"

spec = importlib.util.spec_from_file_location("install_overrides", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PROJECT_SETTINGS = {
    "autoCompactWindow": 100000,
    "env": {"CK_CONTEXT_WARN": "150000", "CK_CONTEXT_BLOCK": "180000",
            "CK_SESSION_START_BRIEF": "1"},
    "permissions": {"deny": ["Artifact", "Glob", "TodoWrite"]},
    "skillOverrides": {"anthropic-skills:docx": "off"},
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "bash .claude/hooks/stale-hook-that-no-longer-ships.sh"}]}]},
}


def install(target, *args):
    return subprocess.run(
        ["bash", str(INSTALL), str(target), *args],
        capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
    )


def fresh_project(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    r = install(tmp_path, "--full", "--yes")
    assert r.returncode == 0, r.stderr + r.stdout
    return tmp_path / ".claude"


def manifest(claude_dir):
    return json.loads((claude_dir / ".claudekit-manifest.json").read_text())


# ---------------------------------------------------------------- module: skip_list

def test_skip_list_reads_manifest_lists_and_infers_deletions(tmp_path):
    d = tmp_path / ".claude"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "kept.md").write_text("x")
    (d / ".claudekit-manifest.json").write_text(json.dumps({
        "files": {"agents/kept.md": "a", "agents/gone.md": "b", "commands/coordinator.md": "c",
                  "hooks/missing-hook.sh": "d"},
        "parked": ["skills/old-skill"],
        "removed": ["commands/explicit.md"],
    }))
    parked, removed = mod.skip_list(str(d))
    assert parked == ["skills/old-skill"]
    assert removed == ["agents/gone.md", "commands/coordinator.md", "commands/explicit.md"]
    assert "hooks/missing-hook.sh" not in removed, "a missing wired hook must come back"


def test_skip_list_treats_dir_unused_as_parked(tmp_path):
    d = tmp_path / ".claude"
    (d / "agents-unused").mkdir(parents=True)
    (d / "agents-unused" / "planner.md").write_text("x")
    (d / "agents-unused" / ".DS_Store").write_text("")
    (d / "hooks-unused").mkdir()
    (d / "hooks-unused" / "web-park.py").write_text("x")
    parked, removed = mod.skip_list(str(d))
    assert parked == ["agents/planner.md", "hooks/web-park.py"]
    assert removed == []


def test_skip_list_on_fresh_target_is_empty(tmp_path):
    assert mod.skip_list(str(tmp_path / "nope")) == ([], [])


# ---------------------------------------------------------------- module: settings merge

def test_merge_keeps_project_keys_and_replaces_hooks():
    kit = {"hooks": {"PreToolUse": [{"matcher": "Bash"}]}, "autoCompactWindow": 200000,
           "env": {"CK_CONTEXT_WARN": "100000", "KIT_ONLY": "1"}}
    merged = mod.merge_settings(kit, PROJECT_SETTINGS)
    assert merged["hooks"] == kit["hooks"]
    assert merged["autoCompactWindow"] == 100000
    assert merged["env"]["CK_CONTEXT_WARN"] == "150000"
    assert merged["env"]["KIT_ONLY"] == "1", "kit-only keys are added"
    assert merged["permissions"]["deny"] == ["Artifact", "Glob", "TodoWrite"]
    assert merged["skillOverrides"] == {"anthropic-skills:docx": "off"}


def test_merge_drops_hooks_the_kit_no_longer_ships():
    assert "hooks" not in mod.merge_settings({"a": 1}, {"hooks": {"x": 1}})


def test_write_merged_settings_fails_closed_on_garbage(tmp_path):
    kit = tmp_path / "kit.json"
    kit.write_text('{"hooks": {}}')
    proj = tmp_path / "proj.json"
    proj.write_text("{not json")
    out = tmp_path / "out.json"
    assert mod.write_merged_settings(str(kit), str(proj), str(out)) == 1
    assert not out.exists()


def test_cli_usage_exit_code():
    assert mod.main([]) == 2


# ---------------------------------------------------------------- install.sh end to end

def test_deleted_coordinator_command_stays_deleted(tmp_path):
    """The user's acceptance test: delete commands/coordinator.md, reinstall, still gone."""
    claude = fresh_project(tmp_path)
    coordinator = claude / "commands" / "coordinator.md"
    assert coordinator.is_file(), "fixture: the kit ships commands/coordinator.md"
    coordinator.unlink()

    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    assert not coordinator.exists(), "install.sh re-created a command the project deleted"
    assert "commands/coordinator.md" in manifest(claude)["removed"]
    assert "commands/coordinator.md" not in manifest(claude)["files"]

    # Second reinstall: the inference signal (receipted-but-absent) is gone, so only the
    # carried-forward `removed` list keeps it out.
    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    assert not coordinator.exists(), "the manifest did not carry `removed` forward"
    assert (claude / "commands" / "plan.md").is_file(), "other commands still install"


def test_parked_agent_in_agents_unused_is_not_reinstalled(tmp_path):
    claude = fresh_project(tmp_path)
    src = claude / "agents" / "planner.md"
    unused = claude / "agents-unused"
    unused.mkdir()
    src.rename(unused / "planner.md")

    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    assert not src.exists(), "install.sh re-created an agent the project parked"
    assert (unused / "planner.md").is_file(), "the parked copy was lost"
    assert "agents/planner.md" in manifest(claude)["parked"]
    assert (claude / "agents" / "reviewer.md").is_file()


def test_manifest_removed_list_is_honoured_for_hooks(tmp_path):
    """Hooks are never inferred as removed (a missing wired hook blocks every tool call),
    but an explicit manifest entry is a decision and is honoured."""
    claude = fresh_project(tmp_path)
    m = manifest(claude)
    m["removed"] = ["hooks/notify.sh"]
    (claude / ".claudekit-manifest.json").write_text(json.dumps(m))
    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    assert not (claude / "hooks" / "notify.sh").exists()


def test_project_settings_keys_survive_reinstall_and_hooks_are_the_kits(tmp_path):
    """The addendum's acceptance test: autoCompactWindow, env thresholds, permissions.deny
    and skillOverrides survive; `hooks` is the kit's, not the stale project copy."""
    claude = fresh_project(tmp_path)
    kit_hooks = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]
    (claude / "settings.json").write_text(json.dumps(PROJECT_SETTINGS, indent=2))

    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    got = json.loads((claude / "settings.json").read_text())
    assert got["autoCompactWindow"] == 100000
    assert got["env"]["CK_CONTEXT_WARN"] == "150000"
    assert got["env"]["CK_CONTEXT_BLOCK"] == "180000"
    assert got["env"]["CK_SESSION_START_BRIEF"] == "1"
    assert got["permissions"]["deny"] == ["Artifact", "Glob", "TodoWrite"]
    assert got["skillOverrides"] == {"anthropic-skills:docx": "off"}
    assert got["hooks"] == kit_hooks
    assert "stale-hook-that-no-longer-ships" not in json.dumps(got)


def test_unparseable_project_settings_aborts_without_touching_the_tree(tmp_path):
    claude = fresh_project(tmp_path)
    (claude / "settings.json").write_text("{not json")
    before = sorted(p.name for p in claude.iterdir())
    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode != 0
    assert "settings.json" in r.stderr + r.stdout
    assert (claude / "settings.json").read_text() == "{not json"
    assert sorted(p.name for p in claude.iterdir()) == before
    assert not list(tmp_path.glob(".claude.staging.*")), "staging dir leaked"


def test_fresh_install_still_copies_settings(tmp_path):
    claude = fresh_project(tmp_path)
    kit = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert json.loads((claude / "settings.json").read_text()) == kit


@pytest.mark.parametrize("key", ["parked", "removed"])
def test_fresh_manifest_has_empty_override_lists(tmp_path, key):
    assert manifest(fresh_project(tmp_path))[key] == []


# ---------------------------------------------------------------- module: merge order / registry

def test_deep_merge_keeps_project_key_order_then_appends_kit_keys():
    merged = mod._deep_merge({"a": 1, "b": {"x": 1, "y": 2}, "z": 9}, {"b": {"y": 3}, "a": 2})
    assert list(merged) == ["b", "a", "z"]
    assert merged["b"] == {"y": 3, "x": 1}


KIT_REG = {"version": "2.0", "lastUpdated": "2026-09-01",
           "skills": [{"id": "tdd", "name": "tdd", "path": "skills/tdd/SKILL.md", "usedBy": ["tester"]},
                      {"id": "new-kit", "name": "new-kit", "path": "skills/new-kit/SKILL.md"}],
           "agentMapping": {"tester": ["tdd"]}, "agentsWithoutSkills": ["gitOps"]}
PROJ_REG = {"version": "1.0", "lastUpdated": "2026-09-10",
            "skills": [{"id": "flow-diagram", "name": "flow-diagram", "path": "skills/flow-diagram/SKILL.md"},
                       {"id": "tdd", "name": "tdd", "path": "skills/tdd/SKILL.md", "usedBy": []}],
            "agentMapping": {"tester": ["tdd"], "qa-lead": ["flow-diagram"]},
            "agentsWithoutSkills": ["gitOps", "local-only"]}


def test_merge_registry_keeps_project_entries_and_adds_kit_ones():
    got = mod.merge_registry(KIT_REG, PROJ_REG)
    ids = [s["id"] for s in got["skills"]]
    assert ids == ["flow-diagram", "tdd", "new-kit"]
    assert got["skills"][1]["usedBy"] == ["tester"], "shared entry takes the kit version"
    assert got["agentMapping"] == {"tester": ["tdd"], "qa-lead": ["flow-diagram"]}
    assert got["agentsWithoutSkills"] == ["gitOps", "local-only"]
    assert got["version"] == "2.0" and got["lastUpdated"] == "2026-09-10"


def test_merge_registry_is_idempotent():
    once = mod.merge_registry(KIT_REG, PROJ_REG)
    assert mod.merge_registry(KIT_REG, once) == once


def test_write_merged_registry_fails_closed_on_garbage(tmp_path):
    kit = tmp_path / "kit.json"
    kit.write_text(json.dumps(KIT_REG))
    proj = tmp_path / "proj.json"
    proj.write_text("[not an object]")
    out = tmp_path / "out.json"
    assert mod.write_merged_registry(str(kit), str(proj), str(out)) == 1
    assert not out.exists()


def test_modified_files_reports_only_changed_managed_files(tmp_path):
    final = tmp_path / "final"
    staging = tmp_path / "staging"
    for d in (final, staging):
        (d / "agents").mkdir(parents=True)
        (d / "runtime" / "events").mkdir(parents=True)
        (d / "agents" / "same.md").write_text("same")
        (d / "agents" / "edited.md").write_text("kit")
        (d / "settings.json").write_text("{}")
        (d / "agents" / "unreceipted.md").write_text("kit-shipped")
    (final / "agents" / "edited.md").write_text("project")
    (final / "agents" / "unreceipted.md").write_text("project-added")
    (final / "agents" / "gone-from-kit.md").write_text("project")
    (final / "runtime" / "events" / "local.jsonl").write_text("x")
    (final / "settings.json").write_text('{"a": 1}')
    h = lambda s: mod.hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
    (final / ".claudekit-manifest.json").write_text(json.dumps({"files": {
        "agents/same.md": h("same"), "agents/edited.md": h("kit"),
        "agents/gone-from-kit.md": h("kit"), "runtime/events/local.jsonl": h("kit"),
        "settings.json": h("{}"), "hooks.log": h("kit")}}))
    assert mod.modified_files(str(final), str(staging)) == {
        "agents/edited.md": h("kit"), "agents/unreceipted.md": h("kit-shipped")}


# ---------------------------------------------------------------- install.sh: modified tree

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          check=True).stdout


def test_reinstall_over_modified_committed_tree_changes_no_tracked_file(tmp_path):
    """The user's acceptance test (qa-agents, 2026-09-23): commit a project tree that edits
    an agent, a hook, a skill, settings.json, the registry and runtime events; reinstall;
    `git status --short` shows no modified tracked file. `--force` then overwrites."""
    claude = fresh_project(tmp_path)
    planner = claude / "agents" / "planner.md"
    planner.write_text("# project planner\n")
    hook = claude / "hooks" / "auto-checkpoint.sh"
    hook.write_text(hook.read_text() + "\n# project tweak\n")
    skill = next(claude.glob("skills/*/SKILL.md"))
    skill.write_text(skill.read_text() + "\nproject addendum\n")
    settings = json.loads((claude / "settings.json").read_text())
    settings["autoCompactWindow"] = 123456
    settings["env"] = dict(settings.get("env", {}), CK_PROJECT_ONLY="1")
    (claude / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    reg_path = claude / "skills" / "skills-registry.json"
    reg = json.loads(reg_path.read_text())
    reg["skills"].append({"id": "flow-diagram", "name": "flow-diagram",
                          "path": "skills/flow-diagram/SKILL.md", "mandatory": False,
                          "usedBy": ["qa-lead"], "description": "project skill"})
    reg_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    events = claude / "runtime" / "events" / "local.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"event": "project"}\n')
    # The receipt legitimately changes on the first run after settings/registry edits
    # (merged files are hashed after the merge); the committed baseline is that run.
    r0 = install(tmp_path, "--full", "--yes")
    assert r0.returncode == 0, r0.stderr + r0.stdout
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "project state")

    r = install(tmp_path, "--full", "--yes")
    assert r.returncode == 0, r.stderr + r.stdout
    status = [ln for ln in _git(tmp_path, "status", "--short").splitlines() if not ln.startswith("??")]
    assert status == [], "reinstall changed tracked files:\n" + "\n".join(status)
    untracked = [ln for ln in _git(tmp_path, "status", "--short").splitlines() if ln.startswith("??")]
    assert all(".claude.bak-" in ln for ln in untracked), untracked
    assert "Kept locally-modified agents/planner.md" in r.stdout + r.stderr
    assert manifest(claude)["files"]["agents/planner.md"] != mod._sha256(str(planner)), \
        "a kept file must be receipted with the kit hash so it stays kept"
    assert not any(k.startswith("runtime/") for k in manifest(claude)["files"])

    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    assert planner.read_text() != "# project planner\n", "--force must overwrite"
    assert events.read_text() == '{"event": "project"}\n', "runtime is never the installer's"
    assert json.loads((claude / "settings.json").read_text())["autoCompactWindow"] == 123456


def test_manifest_is_stable_across_reinstall_and_carries_foreign_keys(tmp_path):
    claude = fresh_project(tmp_path)
    path = claude / ".claudekit-manifest.json"
    m = manifest(claude)
    m["last_enhanced"] = "2026-01-01T00:00:00"
    path.write_text(json.dumps(m, indent=2))
    r = install(tmp_path, "--full", "--yes")
    assert r.returncode == 0, r.stderr + r.stdout
    got = manifest(claude)
    assert got["last_enhanced"] == "2026-01-01T00:00:00"
    assert got["installed_at"] == m["installed_at"], "unchanged install must keep its timestamp"
    first = path.read_bytes()
    r = install(tmp_path, "--full", "--yes")
    assert r.returncode == 0, r.stderr + r.stdout
    assert path.read_bytes() == first
