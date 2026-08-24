"""Tests for all new skills added in v2.0.0.

They were duplicated in `templates/skills/` until task 008 batch 1 deleted that
copy. `i18n-workflow` is absent from the list on purpose: it existed only in
`templates/`, and its five uncovered sections were folded into `i18n-patterns`.
"""
import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
SKILLS_DIR = os.path.join(ROOT, ".claude", "skills")

NEW_SKILLS = [
    "command-flags",
    "mcp-integration",
    "spec-driven-development",
    "token-optimization",
    "codebase-mapping",
    "context-keeper",
    "autonomous-loop",
    "hook-profiling",
    "safe-command-approval",
    "usage-monitoring",
    "prompt-injection-defense",
    "incident-response",
]


class TestNewSkillsExist:
    """Verify all new skills exist."""

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_directory_exists(self, skill):
        path = os.path.join(SKILLS_DIR, skill)
        assert os.path.isdir(path), f"Skill directory missing: {skill}"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_file_exists(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        assert os.path.isfile(path), f"SKILL.md missing for: {skill}"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_frontmatter(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert content.strip().startswith("---"), f"{skill} missing frontmatter"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_name(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "name:" in content, f"{skill} missing name field"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_has_description(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content, f"{skill} missing description"

    @pytest.mark.parametrize("skill", NEW_SKILLS)
    def test_skill_not_empty(self, skill):
        path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        assert os.path.getsize(path) > 200, f"{skill} too small"


class TestOneCanonicalTree:
    """`.claude/skills/` is the only skill source install.sh reads."""

    def test_there_is_no_second_skill_tree(self):
        """Asserted on component FILES, not the directory. `file_delete` removes files and leaves the
        directory, and git does not track an empty directory -- so a directory-existence
        assertion FAILS in the tree that just ran the batch and PASSES in a fresh clone.
        A check whose answer depends on which of those you are in proves nothing."""
        project_dir = os.path.dirname(os.path.dirname(__file__))
        stale = glob.glob(os.path.join(project_dir, "templates", "skills", "*", "SKILL.md"))
        assert stale == [], f"a second skill tree is back: {stale}"

    def test_i18n_patterns_absorbed_what_i18n_workflow_covered(self):
        """The five sections i18n-patterns did not have before the fold. Named
        one by one so a silent regression on any of them goes red."""
        path = os.path.join(SKILLS_DIR, "i18n-patterns", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        for heading in ("Gender / Select", "Nested (select wrapping plural)",
                        "Relative Time", "Translation File Formats by Ecosystem",
                        "Translation Quality Checks", "Anti-Patterns"):
            assert heading in body, f"i18n fold lost: {heading}"

    def test_total_skill_count(self):
        skills = [
            d for d in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, d))
            and os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
        ]
        assert len(skills) >= 71, f"Expected >= 71 skills, found {len(skills)}"
