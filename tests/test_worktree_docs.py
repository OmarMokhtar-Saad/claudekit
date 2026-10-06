"""Docs contract for the worktree lifecycle (X04-X08): the command doc, the
skill (and its Codex mirror) and the CHANGELOG describe `reap`, the merged-proof
rules, locks, the deletion cap and stray Claude Code agent dirs, and no longer
document remove --delete-branch / --archive and do not hand `git branch -D`.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMD = ROOT / ".claude/commands/worktree.md"
SKILL = ROOT / ".claude/skills/using-git-worktrees/SKILL.md"
MIRROR = ROOT / ".agents/skills/using-git-worktrees/SKILL.md"
HYGIENE = ROOT / ".claude/operations/scripts/repo-hygiene.py"
CHANGELOG = ROOT / "CHANGELOG.md"


def text(p):
    return p.read_text(encoding="utf-8")


def unreleased():
    t = text(CHANGELOG)
    start = t.index("## [Unreleased]")
    m = re.search(r"^## \[", t[start + 5:], re.M)
    return t[start: start + 5 + m.start()] if m else t[start:]


def test_x04_command_documents_reap_and_keeps_clean_delegation():
    t = text(CMD)
    assert "reap" in t
    assert "--yes" in t and "--max-deletions" in t and "default 10" in t
    assert "repo-hygiene.py" in t and "/worktree clean" in t


def test_remove_flags_and_archive_documented():
    for p in (CMD, SKILL, MIRROR):
        t = text(p)
        assert "--delete-branch" in t, p
        assert "--archive" in t, p
        assert ".claude/state/worktree-archive/" in t, p
        assert "refs/archive/" in t, p
        assert "KEEPS the branch" in t, p
        assert "summary: reaped=" in t, p
        assert "1 operational error" in t and "2 validation refusal" in t, p
        assert "default 10" in t or "defaults to 10" in t, p
        assert "25" not in re.findall(r"max-deletions[^\n]*", t)[-1], p


def test_command_documents_semantics():
    t = text(CMD).lower()
    assert "dry-run" in t
    for word in ("lock", "squash", "origin/", "fetch", ".claude/worktrees/agent-"):
        assert word in t, word
    assert "deletes nothing" in t


def test_command_no_manual_branch_force_delete_instruction():
    sec = text(CMD).split("## Cleanup After a Failed Run")[1].split("\n## ")[0]
    assert 'git branch -D "agent/' not in sec
    assert "reap" in sec


def test_x05_skill_cleanup_section():
    for p in (SKILL, MIRROR):
        t = text(p)
        assert "reap" in t
        assert re.search(r"never[^\n]*rm -rf", t, re.I)
        assert re.search(r"worktree and (its )?branch", t, re.I)
        assert "refs/recovered" in t
        assert ".claude/worktrees/agent-" in t
        assert "squash" in t.lower()


def test_x06_mirror_identical_and_no_drift():
    assert text(SKILL) == text(MIRROR)
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen-agents-mirror.py"), "--check"],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stdout + r.stderr


def test_x08_changelog_mentions_reap():
    u = unreleased()
    assert "reap" in u and "worktree" in u.lower()
    assert "--delete-branch" in u and "--archive" in u and "refs/archive/" in u
    assert "default 10" in u


def test_hygiene_points_to_reap():
    assert "worktree-manager.py reap" in text(HYGIENE)
