"""The kit's settings.json template ships the context-saving keys measured on qa-agents
(~27k tokens per session): a permissions.deny list for tools no agent uses, a 150-char
skill-listing description cap, and a skillOverrides block that hides optional skills.
They ride the same rule as every other project key: a fresh install gets them, a project
that changed them keeps its own values on reinstall.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
KIT_SETTINGS = ROOT / ".claude" / "settings.json"
sys.path.insert(0, str(ROOT / "src"))
from claudekit import skill_fit  # noqa: E402

EXPECTED_DENY = {"Artifact", "Glob", "TodoWrite", "NotebookEdit", "Workflow"}


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


def _settings(claude_dir):
    return json.loads((claude_dir / "settings.json").read_text())


def test_kit_template_declares_the_three_keys():
    kit = json.loads(KIT_SETTINGS.read_text())
    assert kit["skillListingMaxDescChars"] == 150
    assert EXPECTED_DENY <= set(kit["permissions"]["deny"])
    assert kit["skillOverrides"]["prompt-injection-defense"] == "on"
    assert sum(1 for v in kit["skillOverrides"].values() if v == "off") >= 50


def test_template_never_hides_a_skill_a_full_install_protects(tmp_path):
    claude = fresh_project(tmp_path)
    protected = set(skill_fit.protected_skills(tmp_path))
    hidden = {k for k, v in _settings(claude)["skillOverrides"].items() if v == "off"}
    assert not (hidden & protected), f"template hides protected skills: {sorted(hidden & protected)}"


def test_fresh_install_ships_the_three_keys(tmp_path):
    got = _settings(fresh_project(tmp_path))
    kit = json.loads(KIT_SETTINGS.read_text())
    assert got["skillListingMaxDescChars"] == 150
    assert got["permissions"]["deny"] == kit["permissions"]["deny"]
    assert got["skillOverrides"] == kit["skillOverrides"]


def test_project_values_for_the_three_keys_win_on_reinstall(tmp_path):
    claude = fresh_project(tmp_path)
    mine = _settings(claude)
    mine["skillListingMaxDescChars"] = 1536
    mine["permissions"]["deny"] = ["Glob"]
    mine["skillOverrides"] = {"anthropic-skills:docx": "off", "brainstorming": "on"}
    (claude / "settings.json").write_text(json.dumps(mine, indent=2))

    r = install(tmp_path, "--full", "--yes", "--force")
    assert r.returncode == 0, r.stderr + r.stdout
    got = _settings(claude)
    assert got["skillListingMaxDescChars"] == 1536
    assert got["permissions"]["deny"] == ["Glob"]
    # verbatim: the kit's entries are not merged back in behind the project's choice
    assert got["skillOverrides"] == {"anthropic-skills:docx": "off", "brainstorming": "on"}
    assert got["hooks"] == json.loads(KIT_SETTINGS.read_text())["hooks"]
