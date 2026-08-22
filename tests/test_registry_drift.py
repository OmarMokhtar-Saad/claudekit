"""Behavioural proof that `gen-registry.py --check` sees the FILESYSTEM.

Before 2026-08-21 this gate only compared agent files to `agentMapping`. A skill
directory created by hand, and an agent file with no `## Skill Loading` section,
both passed `--check` in silence -- verified by running the shipped script against
a tree containing exactly those two mutants and getting exit 0.

Every test here mutates a real copy of the corpus and executes the real script.
A gate asserted to bind, rather than watched binding, has shipped broken twice in
this repo.
"""
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "gen-registry.py")

HAND_SKILL = (
    "---\nname: hand-made-drift\n"
    'description: "A skill someone created by hand, bypassing every generator."\n'
    "---\n\n# Hand Made Drift\n\nBody.\n"
)
HAND_AGENT = (
    "---\nname: hand-made-agent\ndescription: \"An agent nobody registered.\"\n"
    "---\n\nBody with no Skill Loading section.\n"
)


@pytest.fixture()
def corpus(tmp_path):
    """A real copy of the shipped corpus plus the script under test."""
    root = tmp_path / "tree"
    (root / "scripts").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "gen-registry.py")
    for name in ("agents", "skills"):
        shutil.copytree(os.path.join(REPO_ROOT, ".claude", name),
                        root / ".claude" / name)
    return root


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "gen-registry.py"), *args],
        capture_output=True, text=True,
    )


def test_shipped_corpus_is_clean(corpus):
    result = run(corpus, "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_hand_created_skill_fails_check(corpus):
    (corpus / ".claude" / "skills" / "hand-made-drift").mkdir()
    (corpus / ".claude" / "skills" / "hand-made-drift" / "SKILL.md").write_text(HAND_SKILL)
    result = run(corpus, "--check")
    assert result.returncode == 1, result.stdout
    assert "UNREGISTERED skill 'hand-made-drift'" in result.stderr, result.stderr


def test_hand_created_agent_fails_check(corpus):
    (corpus / ".claude" / "agents" / "hand-made-agent.md").write_text(HAND_AGENT)
    result = run(corpus, "--check")
    assert result.returncode == 1, result.stdout
    assert "hand-made-agent" in result.stderr, result.stderr


def test_regenerating_fixes_both_mutants(corpus):
    (corpus / ".claude" / "skills" / "hand-made-drift").mkdir()
    (corpus / ".claude" / "skills" / "hand-made-drift" / "SKILL.md").write_text(HAND_SKILL)
    (corpus / ".claude" / "agents" / "hand-made-agent.md").write_text(HAND_AGENT)
    assert run(corpus, "--check").returncode == 1
    written = run(corpus)
    assert written.returncode == 0, written.stdout + written.stderr
    after = run(corpus, "--check")
    assert after.returncode == 0, after.stdout + after.stderr


def test_registry_row_without_a_directory_is_never_auto_removed(corpus):
    """Deleting an asset is owner-gated: the generator reports and refuses."""
    shutil.rmtree(corpus / ".claude" / "skills" / "writing-plans")
    for args in (("--check",), ()):
        result = run(corpus, *args)
        assert result.returncode == 1, result.stdout
        assert "writing-plans" in result.stderr
        assert "never auto-removed" in result.stderr


def test_the_check_would_have_passed_the_mutants_before(corpus):
    """Pins WHY this exists: the mutants are invisible to agentMapping alone."""
    (corpus / ".claude" / "skills" / "hand-made-drift").mkdir()
    (corpus / ".claude" / "skills" / "hand-made-drift" / "SKILL.md").write_text(HAND_SKILL)
    result = run(corpus, "--check")
    assert "DRIFT agentMapping" not in result.stderr
    assert result.returncode == 1
