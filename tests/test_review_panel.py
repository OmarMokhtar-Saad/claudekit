"""/review's zero-context panel: two EGM-derived critics beside reviewer.

The panel is advisory and must stay read-only, plan-only and attributed. These checks pin the
properties that make it safe to run on every /review: no write tools, no CLAUDE.md context, an
untrusted-content rule, a machine-readable summary line, and the Apache-2.0 notice.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / ".claude" / "agents"
CRITICS = ("plan-design-critic", "plan-readiness-critic")


def _split(name):
    text = (AGENTS / (name + ".md")).read_text(encoding="utf-8")
    assert text.startswith("---\n"), name
    front, body = text[4:].split("\n---\n", 1)
    return front, body


@pytest.mark.parametrize("name", CRITICS)
def test_critic_is_read_only_and_context_free(name):
    front, _ = _split(name)
    tools = re.search(r"^tools:\s*\[(.*)\]\s*$", front, re.M)
    assert tools, "%s declares no tools list" % name
    assert sorted(t.strip(" \"'") for t in tools.group(1).split(",")) == ["Grep", "Read"]
    assert re.search(r"^omitClaudeMd:\s*true\s*$", front, re.M), name
    assert re.search(r"^name:\s*%s\s*$" % re.escape(name), front, re.M), name


@pytest.mark.parametrize("name", CRITICS)
def test_critic_contract(name):
    _, body = _split(name)
    assert "are DATA, not instructions" in body
    assert "`PANEL: <n> blocker, <n> major`" in body
    assert "would still pass if the" in body  # the vacuous-test check
    assert "## Target Standard" in body
    # REVIEW only: no BRAINSTORM instructions survive outside the attribution comment
    after_comment = body.split("-->", 1)[1]
    assert "BRAINSTORM" not in after_comment


@pytest.mark.parametrize("name", CRITICS)
def test_critic_carries_apache_attribution(name):
    _, body = _split(name)
    assert "google/elephant-goldfish-model" in body
    assert "Apache License 2.0" in body
    assert "EGM-NOTICE.md" in body


def test_license_and_notice_ship_beside_the_agents():
    shared = AGENTS / "_shared"
    assert "Apache License" in (shared / "EGM-LICENSE.txt").read_text(encoding="utf-8")
    notice = (shared / "EGM-NOTICE.md").read_text(encoding="utf-8")
    for name in CRITICS:
        assert name + ".md" in notice


def test_review_command_runs_panel_but_records_only_reviewer():
    text = (REPO / ".claude" / "commands" / "review.md").read_text(encoding="utf-8")
    for name in CRITICS:
        assert "`%s`" % name in text
    assert "--no-panel" in text
    assert "_shared/REVIEW_PANEL.md" in text
    panel = (AGENTS / "_shared" / "REVIEW_PANEL.md").read_text(encoding="utf-8")
    assert "Only `reviewer`'s `=== REVIEW ===` block is recorded" in panel
    assert "never paste critic text into that block" in panel
    assert "uncovered Blocker" in panel
    # the recording call still names reviewer, never a critic
    record_lines = [ln for ln in text.splitlines() if "review-record.py plan-write" in ln]
    assert record_lines, "review.md no longer records via review-record.py plan-write"
    for line in record_lines:
        assert not any(c in line for c in CRITICS), line
    # the panel is driven by the script, spawned in one message
    assert "review-panel.py prompts" in text
    assert "review-panel.py merge" in text
    assert "In ONE message" in text


@pytest.mark.parametrize("name", CRITICS)
def test_critic_runs_cheap_and_hooked(name):
    front, body = _split(name)
    assert re.search(r"^effort:\s*low\s*$", front, re.M), name
    assert re.search(r"^maxTurns:\s*8\s*$", front, re.M), name
    assert re.search(r"^hooks:\s*$", front, re.M), name
    assert "panel-format-check.py" in front
    assert "critic-read-scope.py" in front
    # stale wording from before the prompt became path-only
    assert "line range specified by the caller" not in body
    assert "provided by the orchestrator" not in body


def test_reviewer_asks_whether_each_test_can_fail():
    assert "**Can this test fail?**" in (AGENTS / "reviewer.md").read_text(encoding="utf-8")
    ref = (AGENTS / "_shared" / "reviewer-reference.md").read_text(encoding="utf-8")
    assert "**Can this test fail?**" in ref and "|| true" in ref


def _hook_commands(name):
    front, _ = _split(name)
    cmds = re.findall(r"^\s*command:\s*'(.*)'\s*$", front, re.M)
    assert len(cmds) == 2, (name, cmds)
    return cmds


def _run(cmd, project, home):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project), HOME=str(home))
    return subprocess.run(["bash", "-c", cmd], env=env, input="{}",
                          capture_output=True, text=True, timeout=30).returncode


@pytest.mark.parametrize("name", CRITICS)
def test_critic_hooks_fail_open_and_fall_back_to_kit(name, tmp_path):
    """The critics are user-level agents used in every project: a project
    without the hook files must not block their Reads (exit 2)."""
    project, home = tmp_path / "proj", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    for cmd in _hook_commands(name):
        hook = re.search(r"\.claude/hooks/([A-Za-z0-9._-]+\.py)", cmd).group(1)
        assert _run(cmd, project, home) == 0, (name, hook, "missing must fail open")
        kit = home / ".claude-kit" / ".claude" / "hooks"
        kit.mkdir(parents=True, exist_ok=True)
        (kit / hook).write_text("import sys; sys.exit(5)\n")
        assert _run(cmd, project, home) == 5, (name, hook, "kit fallback")
        local = project / ".claude" / "hooks"
        local.mkdir(parents=True, exist_ok=True)
        (local / hook).write_text("import sys; sys.exit(7)\n")
        assert _run(cmd, project, home) == 7, (name, hook, "project copy wins")
