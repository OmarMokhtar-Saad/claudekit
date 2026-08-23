"""Tests for international support."""
import os

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
I18N_DIR = os.path.join(PROJECT_DIR, "i18n")
TEMPLATE_DIR = os.path.join(PROJECT_DIR, "templates")
COMMANDS_DIR = os.path.join(PROJECT_DIR, ".claude", "commands")
SKILLS_DIR = os.path.join(PROJECT_DIR, ".claude", "skills")

EXPECTED_LANGUAGES = ["ar", "zh", "es", "fr", "ja", "ko"]


class TestI18nDirectory:
    """Verify i18n directory and files exist."""

    def test_i18n_directory_exists(self):
        assert os.path.isdir(I18N_DIR), "i18n/ directory missing"

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_readme_translation_exists(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        assert os.path.isfile(path), f"README.{lang}.md missing"

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_readme_not_empty(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        assert os.path.getsize(path) > 500, f"README.{lang}.md too small"

    def test_language_count(self):
        readmes = [f for f in os.listdir(I18N_DIR) if f.startswith("README.") and f.endswith(".md")]
        assert len(readmes) >= 6, f"Expected >= 6 translations, found {len(readmes)}"


class TestArabicRTL:
    """Verify Arabic README has RTL support."""

    def test_arabic_has_rtl_dir(self):
        path = os.path.join(I18N_DIR, "README.ar.md")
        with open(path) as f:
            content = f.read()
        assert 'dir="rtl"' in content or "dir='rtl'" in content, "Arabic README missing RTL direction"


class TestLanguageSelectors:
    """Verify all READMEs have language selectors."""

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_has_language_selector(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        with open(path) as f:
            content = f.read()
        assert "English" in content, f"README.{lang}.md missing English link"


class TestTranslateCommand:
    """Verify /translate command exists."""

    def test_translate_command_exists(self):
        path = os.path.join(COMMANDS_DIR, "translate.md")
        assert os.path.isfile(path)

    def test_translate_has_frontmatter(self):
        path = os.path.join(COMMANDS_DIR, "translate.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content


class TestI18nSkill:
    """Verify i18n workflow skill."""

    def test_i18n_skill_exists(self):
        path = os.path.join(SKILLS_DIR, "i18n-patterns", "SKILL.md")
        assert os.path.isfile(path)

    FOLDED_FROM_I18N_WORKFLOW = [
        # headings
        "Gender / Select", "Nested (select wrapping plural)", "Relative Time",
        "Translation File Formats by Ecosystem", "Translation Quality Checks",
        "Anti-Patterns", "Externalization APIs by Language", "The CI Round-Trip",
        "RTL Testing",
        # operative content -- headings alone passed while the bodies were missing
        "NSLocalizedString", "gettext", "getString", "intl.formatMessage",
        "Crowdin", "Lokalise", "Phrase", "bdi", "scrollbars",
    ]

    @pytest.mark.parametrize("fragment", FOLDED_FROM_I18N_WORKFLOW)
    def test_the_i18n_workflow_fold_survives(self, fragment):
        """`i18n-workflow` was deleted and its content folded into `i18n-patterns`.
        The only copy of this text is now here; if it goes, it is a `git show` away
        and nobody notices.

        Asserts on operative CONTENT, not only headings. The batch-1 acceptance
        criterion checked the five headings and passed while the externalization API
        table, the CI round-trip and the RTL checklist were all missing -- review
        found that by grepping for the APIs, which is what this now does."""
        path = os.path.join(SKILLS_DIR, "i18n-patterns", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        assert fragment in body, f"i18n fold lost: {fragment}"
    def test_i18n_skill_covers_rtl(self):
        path = os.path.join(SKILLS_DIR, "i18n-patterns", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "RTL" in content or "rtl" in content
