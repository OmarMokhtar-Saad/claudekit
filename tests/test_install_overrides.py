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
